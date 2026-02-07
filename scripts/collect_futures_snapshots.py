#!/usr/bin/env python
"""
Collect Futures Snapshots

Cron-friendly script to collect futures data for ES, NQ, RTY.
Designed to run every 5 minutes during market hours (9:30 AM - 4:00 PM ET).
Uses unified IBConnectionManager for shared connection.

Usage:
    python scripts/collect_futures_snapshots.py [--symbols ES,NQ,RTY] [--dry-run]

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

from v6.core.futures_fetcher import FuturesFetcher
from v6.data.futures_persistence import FuturesSnapshotsTable
from v6.utils.ib_connection import IBConnectionManager


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
    parser.add_argument(
        "--client-id",
        type=int,
        default=9981,
        help="IB client ID (default: 9981)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write to Delta Lake (just fetch and display)"
    )

    return parser.parse_args()


async def collect_futures(
    symbols: list,
    ib_host: str,
    ib_port: int,
    client_id: int,
    timeout: int,
    dry_run: bool
) -> int:
    """
    Collect futures data for all symbols.

    Args:
        symbols: List of symbols to collect
        ib_host: IB Gateway host
        ib_port: IB Gateway port
        client_id: IB client ID
        timeout: Collection timeout in seconds
        dry_run: If True, don't write to Delta Lake

    Returns:
        Number of futures snapshots collected

    Raises:
        Exception: If collection fails
    """
    logger.info(f"Connecting to IB Gateway at {ib_host}:{ib_port}")

    # Use unified IBConnectionManager
    ib_conn = IBConnectionManager(
        host=ib_host,
        port=ib_port,
        client_id=client_id,
        max_retries=3,
        retry_delay=2.0,
    )

    try:
        await ib_conn.connect()
        await ib_conn.start_heartbeat()

        # Create futures table
        futures_table = FuturesSnapshotsTable()

        # Create fetcher
        fetcher = FuturesFetcher(ib_conn=ib_conn, symbols=symbols)

        collection_time = datetime.now()
        snapshots_data = []

        logger.info(f"Collecting futures for {', '.join(symbols)}...")

        # Subscribe to futures and get snapshots
        snapshots = await fetcher.subscribe_to_futures()

        if not snapshots:
            logger.warning("No snapshots collected (may be in maintenance window)")
            return 0

        # Convert snapshots to dict format
        for symbol, snapshot in snapshots.items():
            snapshot_dict = snapshot.to_dict()
            snapshots_data.append(snapshot_dict)

            logger.info(
                f"  ✓ {symbol}: {snapshot.last:.2f} "
                f"(1h: {snapshot.change_1h:+.2f}%, 4h: {snapshot.change_4h:+.2f}%)"
            )

        # Write to Delta Lake (unless dry-run)
        if not dry_run and snapshots_data:
            futures_table.write_snapshots(snapshots_data)
            logger.info(f"✓ Wrote {len(snapshots_data)} futures snapshots to Delta Lake")
        elif dry_run:
            logger.info("[DRY RUN] Would write {len(snapshots_data)} futures snapshots")

        return len(snapshots_data)

    finally:
        await ib_conn.stop_heartbeat()
        await ib_conn.disconnect()


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
    logger.info(f"Timeout: {args.timeout}s")
    logger.info(f"Dry Run: {args.dry_run}")
    logger.info("-" * 70)

    try:
        # Parse symbols
        symbols = [s.strip().upper() for s in args.symbols.split(",")]

        # Validate symbols
        valid_symbols = {"ES", "NQ", "RTY"}
        for symbol in symbols:
            if symbol not in valid_symbols:
                logger.error(f"Invalid symbol: {symbol}. Must be one of {valid_symbols}")
                return 2

        # Collect with timeout
        collected = await asyncio.wait_for(
            collect_futures(
                symbols=symbols,
                ib_host=args.ib_host,
                ib_port=args.ib_port,
                client_id=args.client_id,
                timeout=args.timeout,
                dry_run=args.dry_run
            ),
            timeout=args.timeout
        )

        logger.info("-" * 70)
        logger.info(f"✓ Collection complete: {collected} futures snapshots")
        logger.info("=" * 70)

        return 0

    except asyncio.TimeoutError:
        logger.error(f"✗ Collection timed out after {args.timeout}s")
        return 1  # Recoverable error

    except ConnectionError as e:
        logger.error(f"✗ Connection error: {e}")
        return 1  # Recoverable error

    except Exception as e:
        logger.error(f"✗ Collection failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 2  # Fatal error


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
