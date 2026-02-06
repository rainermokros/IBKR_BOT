#!/usr/bin/env python
"""
Collect Option Data using Working Code from Yesterday (Jan 27)

Uses the proven OptionDataFetcher that successfully collected 84,874 rows.
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from loguru import logger
from v6.core.market_data_fetcher import OptionDataFetcher


async def main():
    """Collect fresh option data for SPY, QQQ, IWM."""

    logger.info("=" * 70)
    logger.info("OPTION DATA COLLECTION - WORKING VERSION")
    logger.info("=" * 70)
    logger.info(f"Time: {datetime.now()}")

    # Initialize IB connection manager and table (IB Gateway uses port 4002, NOT TWS port 7497)
    from v6.utils.ib_connection import IBConnectionManager
    from v6.data.option_snapshots import OptionSnapshotsTable

    ib_conn = IBConnectionManager(port=4002)
    snapshots_table = OptionSnapshotsTable()

    # Initialize fetcher
    fetcher = OptionDataFetcher(ib_conn, snapshots_table)

    try:
        total_collected = 0

        for symbol in ["SPY", "QQQ", "IWM"]:
            logger.info(f"Fetching {symbol} options...")

            # Find best expiration (45+ DTE preferred)
            best_expiry = await fetcher.find_best_expiration(
                symbol,
                min_dte=20,
                target_dte=45,
                max_dte=60
            )

            if not best_expiry:
                logger.warning(f"No suitable expiration found for {symbol}")
                continue

            logger.info(f"Using expiry: {best_expiry}")

            # Fetch option chain (method filters expirations internally)
            option_chain = await fetcher.fetch_option_chain(symbol)

            if option_chain:
                logger.info(f"✓ Got {len(option_chain)} option contracts")

                # Save to database (write directly to Delta Lake)
                contracts = option_chain  # Already OptionContract objects
                written = snapshots_table.write_snapshots(contracts)
                total_collected += written
                logger.success(f"✓ Saved {written} option contracts for {symbol}")
            else:
                logger.warning(f"No option chain data for {symbol}")

        logger.success(f"✓ Total collected: {total_collected} option contracts")
        logger.info("=" * 70)

        return 0 if total_collected > 0 else 1

    finally:
        # Disconnect IB
        try:
            await ib_conn.disconnect()
        except Exception as e:
            logger.warning(f"Disconnect error (can be ignored): {e}")


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
