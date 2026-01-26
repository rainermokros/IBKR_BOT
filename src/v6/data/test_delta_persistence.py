"""
Integration test for Delta Lake persistence

This script tests the Delta Lake persistence layer by:
- Creating PositionUpdatesTable with proper schema
- Writing position updates via DeltaLakePositionWriter
- Verifying idempotency (Last-Write-Wins conflict resolution)
- Confirming data persisted to Delta Lake

Run this script to verify the persistence layer works correctly.
"""

import asyncio
from datetime import datetime

from loguru import logger

from src.v6.data.delta_persistence import DeltaLakePositionWriter, PositionUpdatesTable
from src.v6.data.position_streamer import PositionUpdate


async def main():
    """Test Delta Lake persistence."""
    logger.info("Starting Delta Lake persistence test...")

    # Create table
    table = PositionUpdatesTable()
    logger.info("✓ Position updates table ready")

    # Create writer
    writer = DeltaLakePositionWriter(table, batch_interval=2)

    # Create test updates
    test_updates = [
        PositionUpdate(
            conid=123456,
            symbol="SPY",
            right="CALL",
            strike=450.0,
            expiry="20260220",
            position=1.0,
            market_price=5.25,
            market_value=525.0,
            average_cost=5.00,
            unrealized_pnl=25.0,
            timestamp=datetime.now()
        ),
        PositionUpdate(
            conid=123456,  # Same conid, newer timestamp (should update)
            symbol="SPY",
            right="CALL",
            strike=450.0,
            expiry="20260220",
            position=1.0,
            market_price=5.50,
            market_value=550.0,
            average_cost=5.00,
            unrealized_pnl=50.0,
            timestamp=datetime.now()
        ),
    ]

    # Test handler interface
    for update in test_updates:
        await writer.on_position_update(update)

    # Start batch writing
    await writer.start_batch_writing()

    # Wait for batch write
    await asyncio.sleep(3)

    # Stop and flush
    await writer.stop_batch_writing()

    # Verify data in Delta Lake
    dt = table.get_table()
    df = dt.to_pandas()
    import polars as pl
    df = pl.from_pandas(df)

    logger.info(f"✓ Delta Lake has {len(df)} records")

    # Check idempotency (should only have 1 record for conid 123456)
    conid_123456_count = df.filter(pl.col("conid") == 123456).shape[0]
    logger.info(f"✓ Records for conid 123456: {conid_123456_count} (should be 1)")

    if conid_123456_count == 1:
        logger.info("✓ Idempotency verified - Last-Write-Wins working")

        # Check that the newer data (market_price=5.50) was kept
        record = df.filter(pl.col("conid") == 123456).row(0)
        # Columns: conid, symbol, right, strike, expiry, position, market_price, market_value, average_cost, unrealized_pnl, timestamp, date
        market_price = record[6]  # market_price is at index 6
        if abs(market_price - 5.50) < 0.01:
            logger.info(f"✓ Last-Write-Wins verified - market_price={market_price} (expected 5.50)")
        else:
            logger.error(f"✗ Last-Write-Wins failed - market_price={market_price} (expected 5.50)")
    else:
        logger.error(f"✗ Idempotency failed - expected 1 record, got {conid_123456_count}")

    logger.info("✓ Test complete")


if __name__ == "__main__":
    asyncio.run(main())
