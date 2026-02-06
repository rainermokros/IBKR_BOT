#!/usr/bin/env python
"""
Validate IB Gateway Connection

Cron-friendly script to verify IB Gateway is ready for trading.
Designed to run at 8:45 AM ET before market open.

Usage:
    python scripts/validate_ib_connection.py [--ib-host 127.0.0.1] [--ib-port 4002]

Exit codes:
    0: Connection OK
    1: Connection failed
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

from v6.pybike.ib_wrapper import IBWrapper


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Validate IB Gateway connection"
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
        "--timeout",
        type=int,
        default=5,
        help="Connection timeout in seconds (default: 5)"
    )

    return parser.parse_args()


async def validate_connection(ib_host: str, ib_port: int, timeout: int) -> bool:
    """
    Validate IB Gateway connection.

    Args:
        ib_host: IB Gateway host
        ib_port: IB Gateway port
        timeout: Connection timeout

    Returns:
        True if connection successful, False otherwise
    """
    logger.info(f"Attempting to connect to IB Gateway at {ib_host}:{ib_port}...")

    ib = IBWrapper()

    try:
        await ib.connect(host=ib_host, port=ib_port, timeout=timeout)
        logger.info("✓ Connection successful")

        # Get account info to verify fully connected
        account = await ib.get_account_info()
        if account:
            logger.info(f"✓ Account info retrieved: {account.get('account_id', 'N/A')}")

        await ib.disconnect()
        return True

    except Exception as e:
        logger.error(f"✗ Connection failed: {e}")
        return False


def main():
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
    logger.info("VALIDATE IB GATEWAY CONNECTION")
    logger.info("=" * 70)
    logger.info(f"Time: {datetime.now()}")
    logger.info(f"Host: {args.ib_host}:{args.ib_port}")
    logger.info("-" * 70)

    try:
        # Validate connection
        connected = asyncio.run(validate_connection(args.ib_host, args.ib_port, args.timeout))

        logger.info("-" * 70)

        if connected:
            logger.info("✓ IB Gateway is ready")
            logger.info("=" * 70)
            return 0
        else:
            logger.error("✗ IB Gateway connection failed")
            logger.info("=" * 70)
            return 1

    except Exception as e:
        logger.error("-" * 70)
        logger.error(f"✗ Validation error: {e}")
        logger.info("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
