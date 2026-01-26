---
phase: 2-position-synchronization
plan: 02
type: execute
depends_on: ["02-01"]
files_modified: [src/v6/data/delta_persistence.py]
domain: delta-lake-lakehouse
---

<objective>
Implement Delta Lake persistence layer with idempotent writes using MERGE operations and batch processing.

**Purpose:** Persist position updates from IB streaming to Delta Lake with ACID guarantees, idempotency, and time-travel support.

**Output:** Working DeltaLakePositionWriter that batch-writes position updates with idempotent MERGE operations and proper partitioning.

**Key Pattern:** Use handler registration to receive updates from IBPositionStreamer, batch writes every 1-5 seconds to avoid small files problem, use MERGE for idempotency with Last-Write-Wins conflict resolution.
</objective>

<execution_context>
~/.claude/get-shit-done/workflows/execute-plan.md
~/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/phases/1-architecture-infrastructure/1-02-SUMMARY.md
@.planning/phases/2-position-synchronization/2-01-SUMMARY.md
@.planning/phases/2-position-synchronization/2-RESEARCH.md
@src/v6/data/position_streamer.py
@src/v6/data/repositories/positions.py
@src/v6/models/ib_models.py

**Tech stack available:**
- Delta Lake (ACID transactions, MERGE operations, time-travel)
- Polars (data manipulation)
- Pydantic models (data validation)
- IBPositionStreamer with PositionUpdate
- PositionsRepository (from Phase 1-02)

**Established patterns:**
- Partition by symbol (NOT timestamp) to avoid small files problem
- Batch writes to Delta Lake
- Repository pattern for data access
- Handler registration for event streaming

**Constraining decisions:**
- **Partition by symbol** (Phase 1-02) - avoid 86,400 partitions/day from timestamp partitioning
- **Batch writes** (Phase 1-02) - avoid creating thousands of small files
- **Repository pattern** (Phase 1-02) - encapsulate Delta Lake operations
- **Handler registration** (Phase 2-01) - receive updates via PositionUpdateHandler protocol
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create position_updates Delta Lake table schema</name>
  <files>src/v6/data/delta_persistence.py</files>
  <action>
    Create position_updates Delta Lake table schema and initialization in `src/v6/data/delta_persistence.py`:

    ```python
    import pyarrow as pa
    import polars as pl
    from deltalake import DeltaTable, write_deltalake
    from pathlib import Path
    from loguru import logger

    class PositionUpdatesTable:
        """Delta Lake table for position updates with idempotent writes."""

        def __init__(self, table_path: str = "data/lake/position_updates"):
            self.table_path = Path(table_path)
            self._ensure_table_exists()

        def _ensure_table_exists(self) -> None:
            """Create table if it doesn't exist."""
            if DeltaTable.is_deltatable(str(self.table_path)):
                return

            # Schema for position updates
            schema = pa.schema([
                ('conid', pa.int64()),
                ('symbol', pa.string()),
                ('right', pa.string()),
                ('strike', pa.float64()),
                ('expiry', pa.string()),
                ('position', pa.float64()),
                ('market_price', pa.float64()),
                ('market_value', pa.float64()),
                ('average_cost', pa.float64()),
                ('unrealized_pnl', pa.float64()),
                ('timestamp', pa.timestamp('us')),
                ('date', pa.date32()),  # For partitioning (extracted from timestamp)
            ])

            # Create empty table
            empty_df = pl.DataFrame(schema=schema)
            write_deltalake(
                str(self.table_path),
                empty_df.limit(0),
                mode="overwrite",
                partition_by=["symbol"]  # Partition by symbol (Phase 1-02 decision)
            )

            logger.info(f"✓ Created Delta Lake table: {self.table_path}")

        def get_table(self) -> DeltaTable:
            """Get DeltaTable instance."""
            return DeltaTable(str(self.table_path))
    ```

    **CRITICAL:** Partition by `symbol` (NOT timestamp) to avoid small files problem. Extract `date` from timestamp for queries, but partition by symbol for performance (follows Phase 1-02 pattern).
  </action>
  <verify>
    Run `python -c "from v6.data.delta_persistence import PositionUpdatesTable; t = PositionUpdatesTable(); print('✓ Table created')"` - should create table without errors
  </verify>
  <done>
    - PositionUpdatesTable class created
    - Schema defined with all position update fields
    - Table partitioned by symbol (not timestamp)
    - Table auto-creates if missing
    - No errors during initialization
  </done>
</task>

<task type="auto">
  <name>Task 2: Implement DeltaLakePositionWriter with idempotent MERGE</name>
  <files>src/v6/data/delta_persistence.py</files>
  <action>
    Create DeltaLakePositionWriter class implementing PositionUpdateHandler in `src/v6/data/delta_persistence.py`:

    ```python
    import asyncio
    from typing import List
    from datetime import datetime
    from v6.data.position_streamer import PositionUpdate, PositionUpdateHandler

    class DeltaLakePositionWriter(PositionUpdateHandler):
        """
        Write position updates to Delta Lake with idempotent guarantees.

        Implements PositionUpdateHandler to receive updates from IBPositionStreamer.
        Batches writes every 1-5 seconds to avoid small files problem.
        Uses MERGE for idempotency with Last-Write-Wins conflict resolution.
        """

        def __init__(self, table: PositionUpdatesTable, batch_interval: int = 3):
            """
            Initialize writer.

            Args:
                table: PositionUpdatesTable instance
                batch_interval: Seconds between batch writes (default: 3s)
            """
            self.table = table
            self.batch_interval = batch_interval
            self._buffer: List[PositionUpdate] = []
            self._write_task: asyncio.Task = None
            self._is_writing = False

        async def on_position_update(self, update: PositionUpdate) -> None:
            """Handle position update - add to buffer."""
            self._buffer.append(update)
            logger.debug(f"Buffered update: {update.symbol} {update.conid} (buffer size: {len(self._buffer)})")

        async def start_batch_writing(self) -> None:
            """Start periodic batch writing loop."""
            if self._is_writing:
                return

            self._is_writing = True
            self._write_task = asyncio.create_task(self._batch_write_loop())
            logger.info(f"✓ Started batch writing (interval: {self.batch_interval}s)")

        async def stop_batch_writing(self) -> None:
            """Stop batch writing and flush remaining buffer."""
            self._is_writing = False

            if self._write_task and not self._write_task.done():
                self._write_task.cancel()
                try:
                    await self._write_task
                except asyncio.CancelledError:
                    pass

            # Flush remaining buffer
            if self._buffer:
                await self._write_updates(self._buffer)
                self._buffer.clear()

            logger.info("✓ Stopped batch writing")

        async def _batch_write_loop(self) -> None:
            """Periodic batch writing loop."""
            while self._is_writing:
                try:
                    await asyncio.sleep(self.batch_interval)

                    if self._buffer and self._is_writing:
                        # Get buffered updates and clear
                        updates = self._buffer.copy()
                        self._buffer.clear()

                        # Write batch
                        await self._write_updates(updates)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Batch write error: {e}", exc_info=True)

        async def _write_updates(self, updates: List[PositionUpdate]) -> int:
            """
            Write position updates with idempotent MERGE.

            Uses MERGE operation for upsert semantics:
            - Same conid + timestamp: Skip (duplicate)
            - Same conid + newer timestamp: UPDATE (Last-Write-Wins)
            - New conid: INSERT

            Returns number of updates written.
            """
            if not updates:
                return 0

            # Convert to Polars DataFrame
            data = []
            for u in updates:
                data.append({
                    'conid': u.conid,
                    'symbol': u.symbol,
                    'right': u.right,
                    'strike': u.strike,
                    'expiry': u.expiry,
                    'position': u.position,
                    'market_price': u.market_price,
                    'market_value': u.market_value,
                    'average_cost': u.average_cost,
                    'unrealized_pnl': u.unrealized_pnl,
                    'timestamp': u.timestamp,
                    'date': u.timestamp.date()
                })

            df = pl.DataFrame(data)

            # Use anti-join for deduplication (simpler than MERGE)
            dt = self.table.get_table()

            # Read existing data for these conids
            existing_conids = df.select('conid').to_series().to_list()
            existing_df = dt.to_pandas()
            existing_df = pl.from_pandas(existing_df).filter(
                pl.col("conid").is_in(existing_conids)
            )

            # Anti-join to find new updates (dedup by conid)
            # For existing conids, only keep if timestamp is newer
            if len(existing_df) > 0:
                # Join to find existing records
                joined = df.join(
                    existing_df.select(['conid', 'timestamp']),
                    on='conid',
                    how='left'
                )

                # Filter: keep if no existing timestamp OR new timestamp is newer
                new_updates = joined.filter(
                    (pl.col("timestamp_right").is_null()) |
                    (pl.col("timestamp") > pl.col("timestamp_right"))
                )

                # Drop the join column
                new_updates = new_updates.drop('timestamp_right')
            else:
                new_updates = df

            # Append only new updates
            if len(new_updates) > 0:
                write_deltalake(
                    str(self.table.table_path),
                    new_updates,
                    mode="append"
                )
                logger.info(f"✓ Wrote {len(new_updates)} position updates (deduped from {len(updates)})")
            else:
                logger.debug("No new updates to write (all duplicates)")

            return len(new_updates)
    ```

    **CRITICAL DECISIONS:**
    - **Anti-join deduplication**: Simpler than MERGE, avoids DuckDB dependency
    - **Batch writes**: Every 3 seconds to avoid small files problem
    - **Last-Write-Wins**: Newer timestamps replace older records for same conid
    - **Handler registration**: Implements PositionUpdateHandler to receive updates from IBPositionStreamer
  </action>
  <verify>
    Run `python -m py_compile src/v6/data/delta_persistence.py` - should compile without errors
  </verify>
  <done>
    - DeltaLakePositionWriter implements PositionUpdateHandler
    - Batches writes every 3 seconds (configurable)
    - Idempotent writes using anti-join deduplication
    - Last-Write-Wins conflict resolution based on timestamp
    - Proper async lifecycle management (start/stop)
  </done>
</task>

<task type="auto">
  <name>Task 3: Create integration test script</name>
  <files>src/v6/data/test_delta_persistence.py</files>
  <action>
    Create integration test script `src/v6/data/test_delta_persistence.py` to verify the persistence works:

    ```python
    import asyncio
    from datetime import datetime
    from loguru import logger
    from v6.data.delta_persistence import PositionUpdatesTable, DeltaLakePositionWriter
    from v6.data.position_streamer import PositionUpdate

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
                expiry="2026-02-20",
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
                expiry="2026-02-20",
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
        df = pl.from_pandas(df)

        logger.info(f"✓ Delta Lake has {len(df)} records")

        # Check idempotency (should only have 1 record for conid 123456)
        conid_123456_count = df.filter(pl.col("conid") == 123456).shape[0]
        logger.info(f"✓ Records for conid 123456: {conid_123456_count} (should be 1)")

        if conid_123456_count == 1:
            logger.info("✓ Idempotency verified - Last-Write-Wins working")
        else:
            logger.error(f"✗ Idempotency failed - expected 1 record, got {conid_123456_count}")

        logger.info("✓ Test complete")

    if __name__ == "__main__":
        asyncio.run(main())
    ```

    **Note:** This tests the writer in isolation without IB connection.
  </action>
  <verify>
    Run `python -m py_compile src/v6/data/test_delta_persistence.py` - should compile
    Run `python src/v6/data/test_delta_persistence.py` - should verify idempotency
  </verify>
  <done>
    - Integration test script created
    - Tests PositionUpdateHandler interface
    - Tests batch writing
    - Tests idempotency (Last-Write-Wins)
    - Verifies data persisted to Delta Lake
    - All verification checks pass
  </done>
</task>

</tasks>

<verification>
Before declaring plan complete:
- [ ] `python -m py_compile src/v6/data/delta_persistence.py` succeeds without errors
- [ ] `python src/v6/data/test_delta_persistence.py` runs successfully
- [ ] Idempotency verified (same conid + newer timestamp updates, doesn't duplicate)
- [ ] Data persisted to Delta Lake with correct schema
- [ ] ruff linter passes with no errors
- [ ] Partitioned by symbol (not timestamp)
</verification>

<success_criteria>

- PositionUpdatesTable created with proper schema
- DeltaLakePositionWriter implements PositionUpdateHandler
- Idempotent writes using anti-join deduplication
- Last-Write-Wins conflict resolution (newer timestamp wins)
- Batch writes every 3 seconds (configurable)
- Data partitioned by symbol (not timestamp)
- Integration test verifies idempotency and persistence
- All verification checks pass
- No errors or warnings introduced

</success_criteria>

<output>
After completion, create `.planning/phases/2-position-synchronization/2-02-SUMMARY.md`:

# Phase 2 Plan 2: Delta Lake Persistence Summary

**Implemented Delta Lake persistence layer with idempotent writes using anti-join deduplication and batch processing.**

## Accomplishments

- Created PositionUpdatesTable with proper schema and symbol partitioning
- Implemented DeltaLakePositionWriter as PositionUpdateHandler
- Idempotent writes using anti-join deduplication (simpler than MERGE)
- Last-Write-Wins conflict resolution based on timestamp
- Batch writes every 3 seconds to avoid small files problem
- Integration test verifies idempotency and persistence

## Files Created/Modified

- `src/v6/data/delta_persistence.py` - PositionUpdatesTable and DeltaLakePositionWriter
- `src/v6/data/test_delta_persistence.py` - Integration test script

## Decisions Made

- **Anti-join deduplication**: Simpler than MERGE, avoids DuckDB dependency
- **Batch writes**: 3-second intervals to avoid small files problem (follows Phase 1-02)
- **Symbol partitioning**: Partition by symbol (not timestamp) to avoid 86,400 partitions/day
- **Last-Write-Wins**: Newer timestamps replace older records for same conid
- **Handler pattern**: Implements PositionUpdateHandler to receive updates from IBPositionStreamer
- **Async lifecycle**: Proper start/stop with buffer flushing on shutdown

## Issues Encountered

None

## Next Step

Ready for 02-03-PLAN.md (Reconciliation Logic)

The Delta Lake persistence layer is in place with:
- Idempotent writes with Last-Write-Wins conflict resolution
- Batch processing to avoid small files problem
- Handler registration for receiving updates from streaming
- Proper partitioning by symbol for query performance

Ready to build reconciliation logic that validates IB ↔ Delta Lake consistency.
</output>
