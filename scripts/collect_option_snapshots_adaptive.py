#!/usr/bin/env python
"""
Adaptive Option Collection - Tries multiple approaches to get data

Strategy: Keep adjusting parameters until we successfully collect option data.
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from loguru import logger
from v6.system_monitor.data.option_snapshots import OptionSnapshotsTable
from ib_async import IB, Stock, Option


async def collect_with_retry(symbol: str, ib: IB) -> int:
    """
    Try multiple strategies to collect option data.

    Returns: Number of contracts collected
    """

    strategies = [
        # Strategy 1: Standard SMART exchange, 20-60 DTE, rounded strikes
        {
            "name": "SMART, 20-60 DTE, rounded strikes",
            "exchange": "SMART",
            "min_dte": 20,
            "max_dte": 60,
            "strike_rounding": 1
        },
        # Strategy 2: CBOE exchange (some ETFs use this)
        {
            "name": "CBOE, 20-60 DTE, rounded strikes",
            "exchange": "CBOE",
            "min_dte": 20,
            "max_dte": 60,
            "strike_rounding": 1
        },
        # Strategy 3: Near-term weeklies (5-10 DTE)
        {
            "name": "SMART, 5-15 DTE weeklies",
            "exchange": "SMART",
            "min_dte": 5,
            "max_dte": 15,
            "strike_rounding": 1
        },
        # Strategy 4: Longer term 60-90 DTE
        {
            "name": "SMART, 60-90 DTE LEAPS",
            "exchange": "SMART",
            "min_dte": 60,
            "max_dte": 90,
            "strike_rounding": 1
        },
    ]

    for strategy in strategies:
        logger.info(f"\n{'='*70}")
        logger.info(f"Trying strategy: {strategy['name']}")
        logger.info(f"{'='*70}")

        try:
            result = await collect_with_params(
                ib, symbol,
                exchange=strategy['exchange'],
                min_dte=strategy['min_dte'],
                max_dte=strategy['max_dte'],
                strike_rounding=strategy['strike_rounding']
            )

            if result > 0:
                logger.success(f"✓ SUCCESS with strategy '{strategy['name']}': Collected {result} contracts")
                return result
            else:
                logger.warning(f"✗ Strategy '{strategy['name']}' returned 0 contracts")

        except Exception as e:
            logger.error(f"✗ Strategy '{strategy['name']}' failed: {e}")
            continue

    return 0


async def collect_with_params(ib: IB, symbol: str, exchange: str,
                             min_dte: int, max_dte: int, strike_rounding: float) -> int:
    """Collect options with specific parameters."""

    # Get stock
    stock = Stock(symbol, 'SMART', 'USD')
    await ib.qualifyContractsAsync(stock)

    # Get current price
    ticker = ib.reqMktData(stock, "", False, False)
    await asyncio.sleep(2)

    current_price = ticker.marketPrice() if hasattr(ticker, 'marketPrice') and ticker.marketPrice() else 0
    if not current_price:
        current_price = ticker.last if hasattr(ticker, 'last') and ticker.last else 0

    logger.info(f"Current price for {symbol}: {current_price}")

    if not current_price:
        logger.error(f"Cannot get current price for {symbol}")
        return 0

    # Get option chains
    chains = await ib.reqSecDefOptParamsAsync(symbol, '', 'STK', stock.conId)
    if not chains:
        logger.warning(f"No option chains for {symbol}")
        return 0

    # Find best chain
    chain = max(chains, key=lambda c: len(c.expirations))
    logger.info(f"Using {chain.exchange} with {len(chain.expirations)} expirations")

    # Calculate date range
    now = datetime.now()
    min_date = (now + timedelta(days=min_dte)).strftime("%Y%m%d")
    max_date = (now + timedelta(days=max_dte)).strftime("%Y%m%d")

    logger.info(f"Looking for expirations between {min_date} and {max_date}")

    # Filter expirations
    expirations = sorted([e for e in chain.expirations
                         if len(e) == 8 and min_date <= e <= max_date])[:3]

    if not expirations:
        logger.warning(f"No expirations found in range")
        return 0

    logger.info(f"Using expirations: {expirations}")

    # Calculate strike range
    min_strike = current_price * 0.97
    max_strike = current_price * 1.03

    # Round strikes to nearest interval
    raw_strikes = [s for s in chain.strikes if min_strike <= s <= max_strike]
    rounded_strikes = sorted(set([round(s / strike_rounding) * strike_rounding for s in raw_strikes]))[:12]

    logger.info(f"Selected {len(rounded_strikes)} strikes: {rounded_strikes[:5]}...")

    snapshots = []
    for expiry in expirations:
        for strike in rounded_strikes:
            for right in ['P', 'C']:
                try:
                    # Create option
                    option = Option(symbol, expiry, strike, right, exchange)

                    # Qualify it
                    qualified = await ib.qualifyContractsAsync(option)

                    if not qualified:
                        logger.debug(f"Not qualified: {symbol} {expiry} {strike} {right}")
                        continue

                    option = qualified[0]

                    # Request market data
                    mt = ib.reqMktData(option, "", False, False)
                    await asyncio.sleep(0.05)

                    # Check if we got data
                    if mt and (mt.bid or mt.ask or mt.last):
                        snapshot = {
                            "timestamp": datetime.now(),
                            "symbol": symbol,
                            "strike": float(strike),
                            "expiry": str(expiry),
                            "right": "CALL" if right == "C" else "PUT",
                            "bid": float(mt.bid) if mt.bid else 0.0,
                            "ask": float(mt.ask) if mt.ask else 0.0,
                            "last": float(mt.last) if mt.last else 0.0,
                            "volume": int(mt.volume) if hasattr(mt, "volume") else 0,
                            "open_interest": int(mt.openInterest) if hasattr(mt, "openInterest") else 0,
                        }

                        # Add Greeks if available
                        if hasattr(mt, "modelGreeks") and mt.modelGreeks:
                            snapshot["iv"] = float(mt.modelGreeks.impliedVol) if mt.modelGreeks.impliedVol else 0.0
                            snapshot["delta"] = float(mt.modelGreeks.delta) if mt.modelGreeks.delta else 0.0
                            snapshot["gamma"] = float(mt.modelGreeks.gamma) if mt.modelGreeks.gamma else 0.0
                            snapshot["theta"] = float(mt.modelGreeks.theta) if mt.modelGreeks.theta else 0.0
                            snapshot["vega"] = float(mt.modelGreeks.vega) if mt.modelGreeks.vega else 0.0
                        else:
                            snapshot.update({"iv": 0.0, "delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0})

                        snapshots.append(snapshot)
                        logger.success(f"✓ Got data: {symbol} {expiry} {strike} {right} bid={mt.bid} ask={mt.ask}")

                except Exception as e:
                    if "Error 200" not in str(e):
                        logger.debug(f"Error: {e}")
                    continue

    logger.info(f"Collected {len(snapshots)} snapshots for {symbol}")
    return len(snapshots)


async def main():
    """Main entry point."""

    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>"
    )

    logger.info("=" * 70)
    logger.info("ADAPTIVE OPTION COLLECTION")
    logger.info("=" * 70)
    logger.info(f"Time: {datetime.now()}")

    ib = IB()
    await ib.connectAsync(host="127.0.0.1", port=4002, timeout=10)

    try:
        snapshots_table = OptionSnapshotsTable()
        total_collected = 0

        for symbol in ["SPY", "QQQ", "IWM"]:
            logger.info(f"\n{'='*70}")
            logger.info(f"PROCESSING {symbol}")
            logger.info(f"{'='*70}")

            count = await collect_with_retry(symbol, ib)
            total_collected += count

        logger.info(f"\n{'='*70}")
        logger.info(f"TOTAL COLLECTED: {total_collected} option contracts")
        logger.info(f"{'='*70}")

        return 0 if total_collected > 0 else 1

    finally:
        ib.disconnect()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
