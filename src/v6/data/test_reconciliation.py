"""
Integration test for position reconciliation.

Tests PositionReconciler and ReconciliationService with real IB connection.
"""

import asyncio

from loguru import logger

from src.v6.data.position_streamer import IBPositionStreamer
from src.v6.data.reconciliation import PositionReconciler, ReconciliationService


async def main():
    """Test reconciliation."""
    logger.info("Starting reconciliation test...")

    # Get singleton streamer
    streamer = IBPositionStreamer()

    # Create reconciler
    reconciler = PositionReconciler(streamer)

    # Start IB connection (required for reconciliation)
    try:
        await streamer.start()
        logger.info("✓ IB connection established")

        # Run reconciliation
        result = await reconciler.reconcile()

        # Log results
        logger.info("Reconciliation complete:")
        logger.info(f"  IB positions: {result.ib_count}")
        logger.info(f"  Delta positions: {result.delta_count}")
        logger.info(f"  Discrepancies: {result.discrepancy_count}")
        logger.info(f"  Critical issues: {1 if result.has_critical_issues else 0}")
        logger.info(f"  Duration: {result.duration_seconds:.2f}s")

        # Log individual discrepancies
        for d in result.discrepancies:
            logger.warning(f"  [{d.type.value}] {d.symbol} ({d.conid}): {d.details}")

        # Test periodic service
        service = ReconciliationService(reconciler, interval=10)
        await service.start()
        logger.info("✓ Started periodic reconciliation (10s interval)")

        # Wait for one cycle
        await asyncio.sleep(12)

        # Stop service
        await service.stop()
        logger.info("✓ Stopped periodic reconciliation")

        # Stop streamer
        await streamer.stop()

        logger.info("✓ Test complete")

    except Exception as e:
        logger.error(f"Test failed: {e}")
        logger.info("Note: This test requires IB Gateway/TWS to be running")


if __name__ == "__main__":
    asyncio.run(main())
