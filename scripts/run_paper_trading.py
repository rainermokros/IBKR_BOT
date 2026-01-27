#!/usr/bin/env python3
"""
Run Paper Trading Bot

This script runs the paper trading orchestrator, which executes entry/monitoring/exit
workflows with paper trading configuration and safety limits.

Usage:
    # Run with default config (config/paper_trading.yaml)
    python scripts/run_paper_trading.py

    # Run with custom config
    python scripts/run_paper_trading.py --config /path/to/config.yaml

    # Run in foreground with verbose logging
    python scripts/run_paper_trading.py --verbose

    # Run with mock IB (for testing without IB Gateway)
    python scripts/run_paper_trading.py --mock-ib
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from loguru import logger

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.v6.config import PaperTradingConfig
from src.v6.orchestration import PaperTrader


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run V6 Paper Trading Bot",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--config",
        type=str,
        default="config/paper_trading.yaml",
        help="Path to paper trading config file",
    )

    parser.add_argument(
        "--env",
        action="store_true",
        help="Load config from environment variables instead of file",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.add_argument(
        "--mock-ib",
        action="store_true",
        help="Use mock IB connection (for testing without IB Gateway)",
    )

    parser.add_argument(
        "--entry-interval",
        type=int,
        default=3600,
        help="Seconds between entry cycles (default: 1 hour)",
    )

    parser.add_argument(
        "--monitoring-interval",
        type=int,
        default=30,
        help="Seconds between monitoring cycles (default: 30 seconds)",
    )

    parser.add_argument(
        "--exit-interval",
        type=int,
        default=60,
        help="Seconds between exit cycles (default: 1 minute)",
    )

    return parser.parse_args()


async def main():
    """Main entry point for paper trading bot."""
    args = parse_args()

    # Configure logging
    log_level = "DEBUG" if args.verbose else "INFO"
    logger.remove()  # Remove default handler
    logger.add(
        sys.stderr,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )
    logger.bind(paper_trading=True)

    # Log startup
    logger.info("=" * 80)
    logger.info("V6 Paper Trading Bot Starting")
    logger.info("=" * 80)

    # Load configuration
    try:
        if args.env:
            logger.info("Loading config from environment variables...")
            config = PaperTradingConfig.load_from_env()
        else:
            logger.info(f"Loading config from {args.config}...")
            config = PaperTradingConfig.load_from_file(args.config)

        logger.info(f"Config loaded: dry_run={config.dry_run}, max_positions={config.max_positions}")
        logger.info(f"Allowed symbols: {config.allowed_symbols}")

    except FileNotFoundError as e:
        logger.error(f"Config file not found: {e}")
        logger.info("Create a config file:")
        logger.info("  cp config/paper_trading.yaml.example config/paper_trading.yaml")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        sys.exit(1)

    # Create paper trader
    logger.info("Initializing PaperTrader...")
    try:
        paper_trader = PaperTrader(config=config)
    except Exception as e:
        logger.error(f"Failed to initialize PaperTrader: {e}")
        sys.exit(1)

    # Start paper trader
    try:
        await paper_trader.start()
        logger.info("PaperTrader started successfully")
    except Exception as e:
        logger.error(f"Failed to start PaperTrader: {e}")
        sys.exit(1)

    # Run main loop
    try:
        logger.info("Starting main loop...")
        logger.info(f"Entry interval: {args.entry_interval}s")
        logger.info(f"Monitoring interval: {args.monitoring_interval}s")
        logger.info(f"Exit interval: {args.exit_interval}s")

        await paper_trader.run_main_loop(
            entry_interval=args.entry_interval,
            monitoring_interval=args.monitoring_interval,
            exit_interval=args.exit_interval,
        )

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Error in main loop: {e}", exc_info=True)
    finally:
        # Stop paper trader
        logger.info("Stopping PaperTrader...")
        await paper_trader.stop()

    # Print metrics
    logger.info("Paper Trading Metrics:")
    metrics = paper_trader.get_paper_metrics()
    for key, value in metrics.items():
        logger.info(f"  {key}: {value}")

    logger.info("Paper Trading Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
