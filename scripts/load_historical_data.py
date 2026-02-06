#!/usr/bin/env python3
"""
Load Historical Market Data

Loads historical market data for SPY, QQQ, IWM from IB Gateway.
Populates Delta Lake tables for backtesting and analysis.

Usage:
    python scripts/load_historical_data.py
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
from deltalake import DeltaTable, write_deltalake
from ib_async import IB
from loguru import logger

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


async def fetch_historical_data(ib: IB, symbol: str, days: int = 30) -> pl.DataFrame:
    """
    Fetch historical bar data for a symbol.

    Args:
        ib: IB connection
        symbol: Symbol to fetch (e.g., "SPY")
        days: Number of days of history

    Returns:
        DataFrame with historical data
    """
    logger.info(f"Fetching {days} days of historical data for {symbol}...")

    # Create contract
    from ib_async import Stock
    contract = Stock(symbol, "SMART", "USD")

    # Qualify contract
    qualified = await ib.qualifyContractsAsync(contract)
    if not qualified:
        logger.error(f"Could not qualify contract for {symbol}")
        return pl.DataFrame()

    contract = qualified[0]

    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    logger.info(f"  Date range: {start_date.date()} to {end_date.date()}")

    # Request historical data
    bars = await ib.reqHistoricalDataAsync(
        contract,
        endDateTime=end_date,
        durationStr=f"{days} D",
        barSizeSetting='1 day',
        whatToShow='TRADES',
        useRTH=True
    )

    if not bars:
        logger.warning(f"No historical data returned for {symbol}")
        return pl.DataFrame()

    # Convert to DataFrame
    data = []
    for bar in bars:
        data.append({
            'symbol': symbol,
            'date': bar.date,
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
            'volume': bar.volume,
            'bar_count': bar.barCount,
        })

    df = pl.DataFrame(data)
    logger.success(f"✓ Fetched {len(df)} days of data for {symbol}")

    return df


async def main():
    """Main entry point."""

    logger.info("=" * 80)
    logger.info("LOAD HISTORICAL DATA")
    logger.info("=" * 80)
    logger.info(f"Time: {datetime.now()}")
    logger.info("")

    ib = IB()
    try:
        logger.info("Connecting to IB Gateway...")
        await ib.connectAsync(
            host='127.0.0.1',
            port=4002,
            clientId=9982,  # Data collection - historical data (9980-9994 range)
            timeout=10
        )
        logger.success("✓ Connected to IB Gateway")

        symbols = ["SPY", "QQQ", "IWM"]
        all_data = []

        for symbol in symbols:
            df = await fetch_historical_data(ib, symbol, days=30)
            if not df.is_empty():
                all_data.append(df)

        if not all_data:
            logger.error("No data fetched for any symbol")
            return 1

        # Combine all data
        combined_df = pl.concat(all_data)

        # Write to Delta Lake
        table_path = "data/lake/historical_data"

        try:
            write_deltalake(
                table_path,
                combined_df,
                mode="overwrite",
            )
            logger.success(f"✓ Wrote {len(combined_df)} rows to {table_path}")
        except Exception as e:
            logger.error(f"Failed to write to Delta Lake: {e}")
            return 1

        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("SUMMARY")
        logger.info("=" * 80)

        for symbol in symbols:
            symbol_count = len(combined_df.filter(pl.col("symbol") == symbol))
            logger.info(f"{symbol}: {symbol_count} days")

        logger.success("\n✓ Historical data loaded successfully")
        ib.disconnect()
        return 0

    except Exception as e:
        logger.error(f"Failed to load historical data: {e}")
        import traceback
        traceback.print_exc()

        try:
            ib.disconnect()
        except:
            pass

        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
