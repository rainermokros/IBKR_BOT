#!/usr/bin/env python
"""
Collect Futures Snapshots

Cron-friendly script to collect futures data for ES, NQ, RTY.
Designed to run every 5 minutes during market hours (9:30 AM - 4:00 PM ET).

Usage:
    python scripts/collect_futures_snapshots.py [--symbols ES,NQ,RTY]

Exit codes:
    0: Success
    1: Recoverable error (will retry)
    2: Fatal error (do not retry)
"""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from v6.system_monitor.data.futures_snapshots import FuturesSnapshotsTable
from v6.pybike.ib_wrapper import IBWrapper


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Collect futures snapshots"
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default="ES,NQ,RTY",
        help="Comma-separated list of futures symbols (default: ES,NQ,RTY)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Collection timeout in seconds (default: 60)"
    )
    parser.add_argument(
        "--ib-host",
        type=str,
        default="127.0.0.1",
        help="IB Gateway host (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--ib-port",
        type=int,
        default=4002,
        help="IB Gateway port (default: 4002)"
    )

    return parser.parse_args()


async def collect_futures(symbols: list, ib_host: str, ib_port: int, timeout: int) -> int:
    """
    Collect futures data for all symbols.

    Args:
        symbols: List of symbols to collect
        ib_host: IB Gateway host
        ib_port: IB Gateway port
        timeout: Collection timeout in seconds

    Returns:
        Number of futures snapshots collected

    Raises:
        Exception: If collection fails
    """
    logger.info(f"Connecting to IB Gateway at {ib_host}:{ib_port}")

    ib = IBWrapper()
    await ib.connect(host=ib_host, port=ib_port, timeout=10)

    try:
        futures_table = FuturesSnapshotsTable()
        total_collected = 0
        collection_time = datetime.now()

        for symbol in symbols:
            logger.info(f"Collecting futures for {symbol}...")

            try:
                # Get futures data
                snapshot = await ib.get_futures_snapshot(symbol)

                if not snapshot:
                    logger.warning(f"No data found for {symbol}")
                    continue

                # Add metadata
                snapshot["timestamp"] = collection_time
                snapshot["symbol"] = symbol

                # Save to Delta Lake
                import polars as pl

                df = pl.DataFrame([snapshot])
                futures_table.append_snapshot(df)

                logger.info(f"  ✓ Saved {symbol} snapshot (price: {snapshot.get('last_price', 'N/A')})")
                total_collected += 1

            except Exception as e:
                logger.error(f"  ✗ Error collecting {symbol}: {e}")
                # Continue with next symbol
                continue

        return total_collected

    finally:
        await ib.disconnect()


async def main():
    """Main entry point."""
    args = parse_args()

    # Setup logging
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>"
    )

    logger.info("=" * 70)
    logger.info("FUTURES SNAPSHOT COLLECTION")
    logger.info("=" * 70)
    logger.info(f"Time: {datetime.now()}")
    logger.info(f"Symbols: {args.symbols}")
    logger.info(f"Timeout: {args}s")
    logger.info("-" * 70)

    try:
        # Parse symbols
        symbols = [s.strip().upper() for s in args.symbols.split(",")]

        # Collect with timeout
        collected = await asyncio.wait_for(
            collect_futures(symbols, args.ib_host, args.ib_port, args.timeout),
            timeout=args.timeout
        )

        logger.info("-" * 70)
        logger.info(f"✓ Collection complete: {collected} futures snapshots")
        logger.info("=" * 70)

        return 0

    except asyncio.TimeoutError:
        logger.error(f"✗ Collection timed out after {args.timeout}s")
        return 1  # Recoverable error

    except Exception as e:
        logger.error(f"✗ Collection failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 2  # Fatal error


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
