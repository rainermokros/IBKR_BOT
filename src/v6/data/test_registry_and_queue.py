"""
Integration test for StrategyRegistry and PositionQueue.

Tests the foundation of hybrid position synchronization.
"""

import asyncio
from loguru import logger

from src.v6.data.strategy_registry import StrategyRegistry
from src.v6.data.position_queue import PositionQueue, QueueStatus


async def main():
    """Test StrategyRegistry and PositionQueue."""
    logger.info("Testing StrategyRegistry and PositionQueue...")

    # Test StrategyRegistry
    logger.info("\n=== Testing StrategyRegistry ===")
    registry = StrategyRegistry(delta_lake_path="data/lake/test_active_strategies")

    # Initialize (create table)
    await registry.initialize()
    logger.info("✓ Registry initialized")

    # Add active contracts
    await registry.add_active(
        conid=123456,
        symbol="SPY",
        right="CALL",
        strike=450.0,
        expiry="20260220",
        strategy_id=1
    )
    logger.info("✓ Added active contract 123456")

    await registry.add_active(
        conid=123457,
        symbol="SPY",
        right="PUT",
        strike=440.0,
        expiry="20260220",
        strategy_id=1
    )
    logger.info("✓ Added active contract 123457")

    # Check is_active
    assert registry.is_active(123456), "Contract 123456 should be active"
    assert registry.is_active(123457), "Contract 123457 should be active"
    assert not registry.is_active(999999), "Contract 999999 should not be active"
    logger.info("✓ is_active() working correctly")

    # Get all active
    active = await registry.get_all_active()
    assert len(active) == 2, f"Should have 2 active contracts, got {len(active)}"
    logger.info(f"✓ get_all_active() returned {len(active)} contracts")

    # Remove active
    await registry.remove_active(123456)
    assert not registry.is_active(123456), "Contract 123456 should no longer be active"
    logger.info("✓ remove_active() working correctly")

    # Test PositionQueue
    logger.info("\n=== Testing PositionQueue ===")
    queue = PositionQueue(delta_lake_path="data/lake/test_position_queue")

    # Initialize
    await queue.initialize()
    logger.info("✓ Queue initialized")

    # Insert items
    request_id_1 = await queue.insert(conid=234567, symbol="SPY", priority=2)
    logger.info(f"✓ Inserted item {request_id_1}")

    request_id_2 = await queue.insert(conid=234568, symbol="SPY", priority=2)
    logger.info(f"✓ Inserted item {request_id_2}")

    # Get batch
    batch = await queue.get_batch(priority=2, limit=10)
    assert len(batch) == 2, f"Should retrieve 2 items, got {len(batch)}"
    logger.info(f"✓ Retrieved batch of {len(batch)} items")

    # Mark as success
    await queue.mark_success([item.request_id for item in batch])
    logger.info("✓ Marked items as SUCCESS")

    # Verify no more PENDING items
    batch = await queue.get_batch(priority=2, limit=10)
    assert len(batch) == 0, f"Should have 0 pending items, got {len(batch)}"
    logger.info("✓ No more PENDING items (all processed)")

    logger.info("\n✓ All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
