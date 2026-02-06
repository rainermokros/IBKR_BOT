#!/usr/bin/env python
"""
GET DATA NOW - Simple direct market data requests

Skips complex qualification - just requests market data directly.
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ib_async import IB, Stock
from loguru import logger


async def get_data_now():
    """Get option data NOW using direct market data requests."""

    logger.remove()
    logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>")

    logger.info("=" * 70)
    logger.info("GETTING DATA NOW - Simple Direct Requests")
    logger.info("=" * 70)

    ib = IB()
    await ib.connectAsync(host="127.0.0.1", port=4002, timeout=10)

    try:
        # Get stock price first
        spy_stock = Stock('SPY', 'SMART', 'USD')
        await ib.qualifyContractsAsync(spy_stock)
        spy_ticker = ib.reqMktData(spy_stock, "", False, False)
        await asyncio.sleep(2)

        spy_price = spy_ticker.marketPrice() if hasattr(spy_ticker, 'marketPrice') else 0
        logger.info(f"SPY Price: {spy_price}")

        # Define a few option contracts around ATM for 20260320 (what worked before)
        # Strikes around 700
        strikes = [680, 690, 700, 710, 720]

        all_snapshots = []

        for strike in strikes:
            for right in ['P', 'C']:
                try:
                    # Create option directly
                    option = ib.queryOption(
                        symbol="SPY",
                        expiry="20260320",
                        strike=strike,
                        right=right,
                        exchange="SMART",
                        currency="USD"
                    )[0]

                    # Request market data
                    ticker = ib.reqMktData(option, "", False, False)
                    await asyncio.sleep(0.1)

                    # Check if we got any data
                    if ticker and (ticker.bid or ticker.ask or ticker.last):
                        snapshot = {
                            "timestamp": datetime.now(),
                            "symbol": "SPY",
                            "strike": float(strike),
                            "expiry": "20260320",
                            "right": "CALL" if right == "C" else "PUT",
                            "bid": float(ticker.bid) if ticker.bid else 0.0,
                            "ask": float(ticker.ask) if ticker.ask else 0.0,
                            "last": float(ticker.last) if ticker.last else 0.0,
                            "volume": int(ticker.volume) if hasattr(ticker, 'volume') else 0,
                            "open_interest": int(ticker.openInterest) if hasattr(ticker, 'openInterest') else 0,
                            "iv": 0.0, "delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0
                        }

                        all_snapshots.append(snapshot)
                        logger.success(f"✓ SPY 20260320 {strike} {right}: bid={ticker.bid} ask={ticker.ask}")

                except Exception as e:
                    logger.debug(f"Error for {strike} {right}: {e}")
                    continue

        logger.info(f"\nCollected {len(all_snapshots)} option quotes")

        # Save to Delta Lake
        if all_snapshots:
            logger.info("Saving to Delta Lake...")

            import polars as pl
            from v6.system_monitor.data.option_snapshots import OptionSnapshotsTable

            df = pl.DataFrame(all_snapshots)
            table = OptionSnapshotsTable()

            # Write directly
            table.append_snapshot(df)

            logger.success(f"✓✓✓ SAVED {len(all_snapshots)} records to option_snapshots ✓✓✓")
            return len(all_snapshots)
        else:
            logger.warning("No data collected")
            return 0

    finally:
        await ib.disconnect()


if __name__ == "__main__":
    result = asyncio.run(get_data_now())
    logger.info(f"Final result: {result} contracts collected")
    sys.exit(0 if result > 0 else 1)
