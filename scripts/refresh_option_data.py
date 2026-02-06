#!/usr/bin/env python
"""
Refresh Option Data - Focused Collection

Only fetches market data for existing contracts in option_snapshots table.
This avoids hitting IB's ticker limit (Error 101).

User Requirements:
- Collect option data every 5 minutes during market hours
- Use existing strikes from option_snapshots table
- Error 200 = normal (contract doesn't exist), ignore and skip
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Set

import polars as pl
from deltalake import DeltaTable
from ib_async import IB, Contract, Option
from loguru import logger

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def get_existing_contracts() -> dict:
    """
    Get unique contract identifiers from option_snapshots table.

    Returns:
        dict: {symbol: [(strike, expiry, right), ...]}
    """
    dt = DeltaTable('data/lake/option_snapshots')
    df = pl.from_pandas(dt.to_pandas())

    # Get unique contracts
    contracts_df = df.select(
        'symbol', 'strike', 'expiry', 'right'
    ).unique()

    # Group by symbol
    result = {}
    for symbol in ['SPY', 'QQQ', 'IWM']:
        symbol_df = contracts_df.filter(pl.col('symbol') == symbol)
        contracts = [
            (row['strike'], row['expiry'], row['right'])
            for row in symbol_df.iter_rows(named=True)
        ]
        result[symbol] = contracts

        logger.info(f"Found {len(contracts)} unique contracts for {symbol}")

    return result


async def refresh_option_data(ib: IB, contracts: dict) -> List[dict]:
    """
    Refresh market data for existing contracts.

    Strategy:
    - Request market data in small batches to avoid Error 101
    - Wait for data to arrive before requesting more
    - Skip contracts that return Error 200 (don't exist)

    Args:
        ib: Connected IB instance
        contracts: {symbol: [(strike, expiry, right), ...]}

    Returns:
        List[dict]: Fresh market data snapshots
    """
    snapshots = []
    ticker_slots = 50  # Conservative limit to avoid Error 101

    for symbol, contract_list in contracts.items():
        logger.info(f"Refreshing {len(contract_list)} contracts for {symbol}")

        # Process in batches
        for i in range(0, len(contract_list), ticker_slots):
            batch = contract_list[i:i+ticker_slots]
            logger.info(f"Processing batch {i//ticker_slots + 1}/{(len(contract_list)-1)//ticker_slots + 1} ({len(batch)} contracts)")

            # Create option contracts for this batch
            option_contracts = []
            for strike, expiry, right in batch:
                try:
                    opt = Option(
                        symbol=symbol,
                        lastTradeDateOrContractMonth=expiry,
                        strike=strike,
                        right=right,
                        exchange='CBOE',  # NOT SMART - use CBOE for options
                        currency='USD'
                    )
                    option_contracts.append(opt)
                except Exception as e:
                    logger.debug(f"Error creating contract: {e}")
                    continue

            # Qualify contracts
            qualified = []
            for opt in option_contracts:
                try:
                    qualified_opts = await ib.qualifyContractsAsync(opt)
                    if qualified_opts:
                        qualified.append(qualified_opts[0])
                except Exception as e:
                    logger.debug(f"Qualify error (skip): {e}")
                    continue

            logger.info(f"Qualified {len(qualified)}/{len(option_contracts)} contracts")

            # Request market data for qualified contracts
            tickers = []
            for opt in qualified:
                try:
                    ticker = ib.reqMktData(
                        opt,
                        "100,101,104,105,106",  # Greeks and IV
                        False,
                        False
                    )
                    tickers.append((opt, ticker))
                except Exception as e:
                    logger.debug(f"Request error (skip): {e}")
                    continue

            # Wait for data to arrive
            await asyncio.sleep(2)

            # Extract data
            for opt, ticker in tickers:
                try:
                    # Parse expiry to get right/strike/confirm it matches
                    strike = opt.strike
                    expiry = opt.lastTradeDateOrContractMonth
                    right = opt.right

                    # Parse yearmonth for partitioning
                    try:
                        yearmonth = int(expiry[:6])  # YYYYMM as integer
                    except Exception:
                        yearmonth = 202602  # Fallback

                    # Create strike_partition (bucket by 10)
                    strike_partition = int(strike // 10 * 10)

                    # Get date
                    date = datetime.now().date()

                    # Check if we got data
                    if ticker.bid or ticker.ask or ticker.last:
                        # Get openInterest safely (uses openInt attribute)
                        oi = 0
                        try:
                            if hasattr(ticker, 'openInt') and ticker.openInt is not None:
                                oi = int(ticker.openInt)
                        except Exception:
                            oi = 0

                        snapshot = {
                            'symbol': symbol,
                            'timestamp': datetime.now(),
                            'strike': strike,
                            'expiry': expiry,
                            'right': right,
                            'bid': ticker.bid if ticker.bid and ticker.bid > 0 else 0,
                            'ask': ticker.ask if ticker.ask and ticker.ask > 0 else 0,
                            'last': ticker.last if ticker.last and ticker.last > 0 else 0,
                            'volume': int(ticker.volume) if ticker.volume and ticker.volume > 0 else 0,
                            'open_interest': oi,
                            'iv': _get_greek(ticker, 'iv'),
                            'delta': _get_greek(ticker, 'delta'),
                            'gamma': _get_greek(ticker, 'gamma'),
                            'theta': _get_greek(ticker, 'theta'),
                            'vega': _get_greek(ticker, 'vega'),
                            'date': date,
                            'yearmonth': yearmonth,
                            'strike_partition': strike_partition,
                        }
                        snapshots.append(snapshot)
                except Exception as e:
                    logger.debug(f"Extract error (skip): {e}")
                    continue

            # Cancel market data to free up slots
            for opt, _ in tickers:
                try:
                    ib.cancelMktData(opt)
                except Exception:
                    pass

            # Small delay before next batch
            await asyncio.sleep(0.5)

    logger.info(f"Collected {len(snapshots)} fresh snapshots")
    return snapshots


def _get_greek(ticker, greek_name: str) -> float:
    """Extract Greek value from ticker. Always returns 0.0 if unavailable."""
    try:
        # Special case for IV
        if greek_name == 'iv':
            if hasattr(ticker, 'impliedVolatility') and ticker.impliedVolatility is not None:
                val = float(ticker.impliedVolatility)
                return val if not (val != val) else 0.0  # NaN check
            return 0.0

        # Standard greeks from modelGreeks
        if hasattr(ticker, 'modelGreeks'):
            greeks = ticker.modelGreeks
            if greeks and hasattr(greeks, greek_name):
                value = getattr(greeks, greek_name)
                if value is not None:
                    val = float(value)
                    return val if not (val != val) else 0.0  # NaN check
        return 0.0
    except Exception:
        return 0.0


def save_snapshots(snapshots: List[dict]) -> int:
    """Save snapshots to Delta Lake."""
    if not snapshots:
        return 0

    df = pl.DataFrame(snapshots)

    # Ensure all numeric columns have proper types and no NaN
    df = df.with_columns([
        pl.col('bid').cast(pl.Float64).fill_null(0.0).fill_nan(0.0),
        pl.col('ask').cast(pl.Float64).fill_null(0.0).fill_nan(0.0),
        pl.col('last').cast(pl.Float64).fill_null(0.0).fill_nan(0.0),
        pl.col('volume').cast(pl.Int64).fill_null(0),
        pl.col('open_interest').cast(pl.Int64).fill_null(0),
        pl.col('iv').cast(pl.Float64).fill_null(0.0).fill_nan(0.0),
        pl.col('delta').cast(pl.Float64).fill_null(0.0).fill_nan(0.0),
        pl.col('gamma').cast(pl.Float64).fill_null(0.0).fill_nan(0.0),
        pl.col('theta').cast(pl.Float64).fill_null(0.0).fill_nan(0.0),
        pl.col('vega').cast(pl.Float64).fill_null(0.0).fill_nan(0.0),
        pl.col('strike_partition').cast(pl.Float64),
        pl.col('yearmonth').cast(pl.Int64),
    ])

    # Write to Delta Lake with correct partitioning
    from deltalake import write_deltalake

    write_deltalake(
        'data/lake/option_snapshots',
        df,
        mode='append',
        partition_by=['strike_partition', 'symbol']
    )

    logger.success(f"✓ Saved {len(df)} snapshots to option_snapshots")
    return len(df)


async def main():
    """Refresh option data for existing contracts."""

    logger.info("=" * 70)
    logger.info("REFRESH OPTION DATA - FOCUSED COLLECTION")
    logger.info("=" * 70)
    logger.info(f"Time: {datetime.now()}")

    # Connect to IB (Gateway port 4002, NOT TWS port 7497)
    ib = IB()
    try:
        await ib.connectAsync(host='127.0.0.1', port=4002, clientId=9999, timeout=10)
        logger.success("✓ Connected to IB Gateway on port 4002")
    except Exception as e:
        logger.error(f"Failed to connect to IB: {e}")
        return 1

    try:
        # Get existing contracts
        contracts = get_existing_contracts()

        # Refresh market data
        snapshots = await refresh_option_data(ib, contracts)

        # Save to Delta Lake
        saved = save_snapshots(snapshots)

        logger.success(f"✓ Total refreshed: {saved} option snapshots")
        logger.info("=" * 70)

        return 0 if saved > 0 else 1

    finally:
        try:
            await ib.disconnect()
            logger.info("Disconnected from IB")
        except Exception as e:
            logger.debug(f"Disconnect error: {e}")


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
