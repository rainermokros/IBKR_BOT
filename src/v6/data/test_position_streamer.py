"""
Integration test for hybrid position synchronization.

Tests IBPositionStreamer with hybrid approach:
- Active contracts: streamed (real-time)
- Non-essential contracts: queued (batch processing)
"""

import asyncio

from loguru import logger

from v6.data.position_queue import PositionQueue
from v6.data.position_streamer import IBPositionStreamer, PositionUpdate, PositionUpdateHandler
from v6.data.strategy_registry import StrategyRegistry


class TestHandler(PositionUpdateHandler):
    """Test handler that logs position updates (streamed only)."""

    def __init__(self):
        self.updates_received = []

    async def on_position_update(self, update: PositionUpdate) -> None:
        logger.info(f"📡 STREAMED UPDATE: {update.symbol} {update.right} (conid: {update.conid}, pos: {update.position})")
        self.updates_received.append(update)


async def main():
    """Test hybrid position synchronization."""
    logger.info("Testing hybrid position synchronization...")

    # Create registry and queue
    registry = StrategyRegistry(delta_lake_path="data/lake/test_active_strategies")
    queue = PositionQueue(delta_lake_path="data/lake/test_position_queue")

    # Initialize
    await registry.initialize()
    await queue.initialize()

    # Add one active contract (should be streamed)
    await registry.add_active(
        conid=999999,
        symbol="TEST",
        right="CALL",
        strike=450.0,
        expiry="20260220",
        strategy_id=1
    )
    logger.info("✓ Added active contract 999999 (should be streamed)")

    # Create streamer with registry and queue
    streamer = IBPositionStreamer(registry=registry, queue=queue)

    # Create handler to catch streamed updates
    handler = TestHandler()
    streamer.register_handler(handler)

    try:
        # Start hybrid sync
        await streamer.start()
        logger.info("✓ Hybrid position sync started")

        # Wait for updates
        await asyncio.sleep(5)

        # Stop
        await streamer.stop()
        logger.info("✓ Hybrid position sync stopped")

        # Verify results
        logger.info("\n=== Results ===")
        logger.info(f"Streamed updates received: {len(handler.updates_received)}")

        # Check queue
        queued_items = await queue.get_batch(priority=2, limit=100)
        logger.info(f"Queued items (non-essential): {len(queued_items)}")

        logger.info("\n✓ Test complete")

    except Exception as e:
        logger.error(f"Test failed: {e}")
        logger.info("Note: This test requires IB Gateway/TWS to be running")


if __name__ == "__main__":
    # Configure loguru
    logger.remove()
    logger.add(
        lambda msg: print(msg, end=''),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | {message}\n",
        level="INFO"
    )

    # Run test
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nTest interrupted by user")
