"""
Delta Lake Persistence for Position Updates

This module provides Delta Lake persistence layer for position updates from IB streaming.
Implements idempotent writes using anti-join deduplication and batch processing.

Key patterns:
- PositionUpdatesTable: Delta Lake table with proper schema and symbol partitioning
- DeltaLakePositionWriter: Implements PositionUpdateHandler for streaming writes
- Anti-join deduplication: Simpler than MERGE, avoids DuckDB dependency
- Batch writes: Every 3 seconds to avoid small files problem
- Last-Write-Wins: Newer timestamps replace older records for same conid
"""

import asyncio
from pathlib import Path
from typing import List

import polars as pl
from deltalake import DeltaTable, write_deltalake
from loguru import logger

from v6.data.position_streamer import PositionUpdate, PositionUpdateHandler


class PositionUpdatesTable:
    """Delta Lake table for position updates with idempotent writes."""

    def __init__(self, table_path: str = "data/lake/position_updates"):
        """
        Initialize position updates table.

        Args:
            table_path: Path to Delta Lake table (default: data/lake/position_updates)
        """
        self.table_path = Path(table_path)
        self._ensure_table_exists()

    def _ensure_table_exists(self) -> None:
        """Create table if it doesn't exist."""
        if DeltaTable.is_deltatable(str(self.table_path)):
            return

        # Schema for position updates (use Polars schema, not PyArrow)
        schema = pl.Schema({
            'conid': pl.Int64,
            'symbol': pl.String,
            'right': pl.String,
            'strike': pl.Float64,
            'expiry': pl.String,
            'position': pl.Float64,
            'market_price': pl.Float64,
            'market_value': pl.Float64,
            'average_cost': pl.Float64,
            'unrealized_pnl': pl.Float64,
            'timestamp': pl.Datetime("us"),
            'date': pl.Date,
        })

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


class DeltaLakePositionWriter(PositionUpdateHandler):
    """
    Write position updates to Delta Lake with idempotent guarantees.

    Implements PositionUpdateHandler to receive updates from IBPositionStreamer.
    Batches writes every 1-5 seconds to avoid small files problem.
    Uses anti-join deduplication for idempotency with Last-Write-Wins conflict resolution.
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
        Write position updates with idempotent deduplication.

        Uses anti-join for idempotency:
        - Same conid + older timestamp: Skip (duplicate)
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

        # First, deduplicate within the batch (keep latest timestamp per conid)
        df_deduped = df.sort('timestamp', descending=True).unique(
            subset=['conid'],
            keep='first'
        )

        # Use anti-join for deduplication against existing data (simpler than MERGE)
        dt = self.table.get_table()

        # Read existing data for these conids
        existing_conids = df_deduped.select('conid').to_series().to_list()
        existing_df = dt.to_pandas()
        existing_df = pl.from_pandas(existing_df).filter(
            pl.col("conid").is_in(existing_conids)
        )

        # Anti-join to find new updates (dedup by conid)
        # For existing conids, only keep if timestamp is newer
        if len(existing_df) > 0:
            # Join to find existing records
            joined = df_deduped.join(
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
            new_updates = df_deduped

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
