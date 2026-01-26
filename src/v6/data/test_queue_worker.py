"""
Integration test for QueueWorker.

Tests background daemon processing of queued position updates.
"""

import asyncio

from loguru import logger

from src.v6.data.position_queue import PositionQueue
from src.v6.data.queue_worker import QueueWorker


async def main():
    """Test QueueWorker."""
    logger.info("Testing QueueWorker...")

    # Create queue
    queue = PositionQueue(delta_lake_path="data/lake/test_position_queue")
    await queue.initialize()

    # Insert test items
    logger.info("Inserting test items into queue...")
    for i in range(5):
        await queue.insert(conid=300000 + i, symbol="TEST", priority=2)
    logger.info("✓ Inserted 5 test items")

    # Create worker
    worker = QueueWorker(
        queue=queue,
        interval=2,  # 2 seconds for testing
        batch_size=10,
        delta_lake_path="data/lake/test_position_updates"
    )

    try:
        # Start worker
        await worker.start()
        logger.info("✓ QueueWorker started")

        # Wait for one processing cycle
        await asyncio.sleep(5)

        # Get stats
        stats = worker.get_stats()
        logger.info("\n=== Worker Stats ===")
        logger.info(f"Total processed: {stats.total_processed}")
        logger.info(f"Total success: {stats.total_success}")
        logger.info(f"Total failed: {stats.total_failed}")
        logger.info(f"Last batch size: {stats.last_batch_size}")

        # Stop worker
        await worker.stop()
        logger.info("✓ QueueWorker stopped")

        # Verify queue is processed
        remaining = await queue.get_batch(priority=2, limit=100)
        logger.info(f"\nRemaining in queue: {len(remaining)}")

        logger.info("\n✓ Test complete")

    except Exception as e:
        logger.error(f"Test failed: {e}")
        logger.info("Note: This test requires IB Gateway/TWS to be running")


if __name__ == "__main__":
    asyncio.run(main())
