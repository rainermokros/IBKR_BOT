#!/usr/bin/env python
"""
Production Entry Point

Main script for running the V6 trading system in production.
Starts the production orchestrator with all workflows.
"""

import asyncio
import signal
import sys

from loguru import logger

from src.v6.config.loader import load_and_validate_config
from src.v6.orchestration.production import ProductionOrchestrator


def setup_signal_handlers(orchestrator: ProductionOrchestrator) -> None:
    """
    Set up signal handlers for graceful shutdown.

    Args:
        orchestrator: ProductionOrchestrator instance
    """
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, initiating graceful shutdown...")
        asyncio.create_task(orchestrator.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGHUP, signal_handler)  # Reload config


async def main() -> int:
    """
    Main production entry point.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    logger.info("=" * 60)
    logger.info("V6 Trading Bot - Production Mode")
    logger.info("=" * 60)

    try:
        # Load and validate configuration
        logger.info("Loading production configuration...")
        config = load_and_validate_config("production")

        # Configure production logging
        log_config = config.get_log_config()
        logger.add(
            config.log_file,
            rotation=log_config["rotation"],
            retention=log_config["retention"],
            compression=log_config["compression"],
            level=log_config["level"],
            format=log_config["format"],
        )
        logger.info(f"Logging to: {config.log_file}")

        # Warn if dry_run is enabled
        if config.dry_run:
            logger.warning("🚨 DRY_RUN MODE: No live orders will be executed")
            logger.warning("🚨 Set dry_run=False in config for production trading")

        # Create orchestrator
        orchestrator = ProductionOrchestrator(config)

        # Set up signal handlers
        setup_signal_handlers(orchestrator)

        # Start orchestrator
        await orchestrator.start()

        # Run main loop
        await orchestrator.run()

        # Graceful shutdown
        await orchestrator.stop()

        logger.info("✓ Production orchestrator stopped cleanly")
        return 0

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
        return 0

    except Exception as e:
        logger.error(f"Production orchestrator failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
