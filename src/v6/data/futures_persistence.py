"""
Futures Persistence Module

Provides Delta Lake persistence layer for futures data snapshots.
Implements idempotent writes, partitioning, and time-travel queries for analytics.

Key patterns:
- FuturesSnapshotsTable: Delta Lake table with schema and symbol partitioning
- DeltaLakeFuturesWriter: Batch writer for idempotent snapshots
- Anti-join deduplication: Simpler than MERGE, avoids DuckDB dependency
- Batch writes: Every 1 minute to avoid small files problem
- Time-travel queries: Historical analysis support
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import polars as pl
from deltalake import DeltaTable, write_deltalake
from loguru import logger

from src.v6.core.futures_fetcher import FuturesSnapshot


class FuturesSnapshotsTable:
    """Delta Lake table for futures snapshots with idempotent writes."""

    def __init__(self, table_path: str = "data/lake/futures_snapshots"):
        """
        Initialize futures snapshots table.

        Args:
            table_path: Path to Delta Lake table (default: data/lake/futures_snapshots)
        """
        self.table_path = Path(table_path)
        self._ensure_table_exists()

    def _ensure_table_exists(self) -> None:
        """Create table if it doesn't exist."""
        if DeltaTable.is_deltatable(str(self.table_path)):
            return

        # Schema for futures snapshots (use Polars schema, not PyArrow)
        schema = pl.Schema({
            'symbol': pl.String,
            'timestamp': pl.Datetime("us"),
            'bid': pl.Float64,
            'ask': pl.Float64,
            'last': pl.Float64,
            'volume': pl.Int64,
            'open_interest': pl.Int64,
            'implied_vol': pl.Float64,
            'change_1h': pl.Float64,
            'change_4h': pl.Float64,
            'change_overnight': pl.Float64,
            'change_daily': pl.Float64,
            'date': pl.Date,
        })

        # Create empty table
        empty_df = pl.DataFrame(schema=schema)
        write_deltalake(
            str(self.table_path),
            empty_df.limit(0),
            mode="overwrite",
            partition_by=["symbol"]  # Partition by symbol for efficient queries
        )

        logger.info(f"✓ Created Delta Lake table: {self.table_path}")

    def get_table(self) -> DeltaTable:
        """Get DeltaTable instance."""
        return DeltaTable(str(self.table_path))


class DeltaLakeFuturesWriter:
    """
    Write futures snapshots to Delta Lake with idempotent guarantees.

    Batches writes every 1 minute to avoid small files problem.
    Uses anti-join deduplication for idempotency with Last-Write-Wins conflict resolution.
    """

    def __init__(self, table: FuturesSnapshotsTable, batch_interval: int = 60):
        """
        Initialize writer.

        Args:
            table: FuturesSnapshotsTable instance
            batch_interval: Seconds between batch writes (default: 60s)
        """
        self.table = table
        self.batch_interval = batch_interval
        self._buffer: List[FuturesSnapshot] = []
        self._write_task: Optional[asyncio.Task] = None
        self._is_writing = False

    async def on_snapshot(self, snapshot: FuturesSnapshot) -> None:
        """Handle futures snapshot - add to buffer."""
        self._buffer.append(snapshot)
        logger.debug(f"Buffered snapshot: {snapshot.symbol} at {snapshot.timestamp} (buffer size: {len(self._buffer)})")

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
            await self._write_snapshots(self._buffer)
            self._buffer.clear()

        logger.info("✓ Stopped batch writing")

    async def _batch_write_loop(self) -> None:
        """Periodic batch writing loop."""
        while self._is_writing:
            try:
                await asyncio.sleep(self.batch_interval)

                if self._buffer and self._is_writing:
                    # Get buffered snapshots and clear
                    snapshots = self._buffer.copy()
                    self._buffer.clear()

                    # Write batch
                    await self._write_snapshots(snapshots)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Batch write error: {e}", exc_info=True)

    async def _write_snapshots(self, snapshots: List[FuturesSnapshot]) -> int:
        """
        Write futures snapshots with idempotent deduplication.

        Uses anti-join for idempotency:
        - Same symbol + older timestamp: Skip (duplicate)
        - Same symbol + newer timestamp: UPDATE (Last-Write-Wins)
        - New symbol data: INSERT

        Args:
            snapshots: List of futures snapshots to write

        Returns:
            int: Number of snapshots written
        """
        if not snapshots:
            return 0

        # Convert to Polars DataFrame
        data = []
        for s in snapshots:
            data.append({
                'symbol': s.symbol,
                'timestamp': s.timestamp,
                'bid': s.bid,
                'ask': s.ask,
                'last': s.last,
                'volume': s.volume,
                'open_interest': s.open_interest if s.open_interest else None,
                'implied_vol': s.implied_vol if s.implied_vol else None,
                'change_1h': s.change_1h if s.change_1h else None,
                'change_4h': s.change_4h if s.change_4h else None,
                'change_overnight': s.change_overnight if s.change_overnight else None,
                'change_daily': s.change_daily if s.change_daily else None,
                'date': s.timestamp.date()
            })

        df = pl.DataFrame(data)

        # First, deduplicate within the batch (keep latest timestamp per symbol)
        df_deduped = df.sort('timestamp', descending=True).unique(
            subset=['symbol', 'timestamp'],
            keep='first'
        )

        # Simple approach: Read all existing data for these symbols and timestamps
        dt = self.table.get_table()

        # Get existing (symbol, timestamp) pairs
        existing_df = dt.to_pandas()
        if len(existing_df) > 0:
            existing_df = pl.from_pandas(existing_df).select(['symbol', 'timestamp'])

            # Anti-join: find new snapshots that don't exist yet
            # Join on symbol and timestamp to find exact matches
            new_snapshots = df_deduped.join(
                existing_df,
                on=['symbol', 'timestamp'],
                how='anti'  # Anti-join: keep only non-matching rows
            )
        else:
            new_snapshots = df_deduped

        # Append only new snapshots
        if len(new_snapshots) > 0:
            write_deltalake(
                str(self.table.table_path),
                new_snapshots,
                mode="append"
            )
            logger.info(f"✓ Wrote {len(new_snapshots)} futures snapshots (deduped from {len(snapshots)})")
        else:
            logger.debug("No new snapshots to write (all duplicates)")

        return len(new_snapshots)


class FuturesDataReader:
    """
    Read futures data from Delta Lake for analysis.

    Provides time-travel queries, correlation analysis, and historical data access.
    """

    def __init__(self, table: FuturesSnapshotsTable):
        """
        Initialize reader.

        Args:
            table: FuturesSnapshotsTable instance
        """
        self.table = table

    def read_latest_snapshots(
        self,
        symbol: Optional[str] = None,
        limit: int = 100
    ) -> pl.DataFrame:
        """
        Read latest snapshots for symbol(s).

        Args:
            symbol: Futures symbol (ES, NQ, RTY) or None for all
            limit: Maximum number of snapshots to return

        Returns:
            pl.DataFrame: Latest snapshots
        """
        dt = self.table.get_table()

        # Read data
        df = pl.from_pandas(dt.to_pandas())

        # Filter by symbol if specified
        if symbol:
            df = df.filter(pl.col("symbol") == symbol)

        # Sort by timestamp descending and limit
        df = df.sort("timestamp", descending=True).head(limit)

        return df

    def read_time_range(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        fields: Optional[List[str]] = None
    ) -> pl.DataFrame:
        """
        Read snapshots for a symbol within a time range.

        Args:
            symbol: Futures symbol
            start: Start datetime
            end: End datetime
            fields: List of fields to select (None for all)

        Returns:
            pl.DataFrame: Snapshots within time range
        """
        dt = self.table.get_table()

        # Read data
        df = pl.from_pandas(dt.to_pandas())

        # Filter by symbol and time range
        df = df.filter(
            (pl.col("symbol") == symbol) &
            (pl.col("timestamp") >= start) &
            (pl.col("timestamp") <= end)
        )

        # Select fields if specified
        if fields:
            all_fields = ["symbol", "timestamp"] + fields
            df = df.select(all_fields)

        # Sort by timestamp
        df = df.sort("timestamp")

        return df

    def calculate_correlation(
        self,
        symbol1: str,
        symbol2: str,
        days: int = 1,
        field: str = "last"
    ) -> float:
        """
        Calculate correlation between two futures symbols.

        Args:
            symbol1: First symbol (e.g., "ES")
            symbol2: Second symbol (e.g., "NQ")
            days: Number of days to analyze
            field: Field to correlate (default: "last" price)

        Returns:
            float: Correlation coefficient (-1 to 1)
        """
        end = datetime.now()
        start = end - timedelta(days=days)

        # Read data for both symbols (include timestamp for join)
        df1 = self.read_time_range(symbol1, start, end, [field])
        df2 = self.read_time_range(symbol2, start, end, [field])

        # Check we have data
        if len(df1) < 2 or len(df2) < 2:
            logger.warning(
                f"Not enough data points for correlation between {symbol1} (n={len(df1)}) "
                f"and {symbol2} (n={len(df2)})"
            )
            return 0.0

        # Merge on timestamp (inner join) - ensure timestamp is in both
        if "timestamp" not in df1.columns or "timestamp" not in df2.columns:
            logger.error(f"Timestamp column missing from data")
            return 0.0

        merged = df1.join(
            df2.select(["timestamp", field]),
            on="timestamp",
            suffix=f"_{symbol2}"
        )

        if len(merged) < 2:
            logger.warning(
                f"Not enough overlapping data points for correlation between {symbol1} and {symbol2} "
                f"(after join: n={len(merged)})"
            )
            return 0.0

        # Calculate correlation using Polars
        field1 = field
        field2 = f"{field}_{symbol2}"

        # Check for null values
        if merged.select(pl.col(field1).null_count()).item() > 0 or \
           merged.select(pl.col(field2).null_count()).item() > 0:
            logger.warning(f"Null values found in correlation data, dropping nulls")
            merged = merged.drop_nulls([field1, field2])

        if len(merged) < 2:
            logger.warning(f"Not enough valid data points after dropping nulls")
            return 0.0

        corr = merged.select(
            pl.corr(pl.col(field1), pl.col(field2))
        ).item()

        return corr if corr is not None else 0.0

    def read_time_travel(
        self,
        symbol: str,
        version: Optional[int] = None,
        datetime_version: Optional[datetime] = None
    ) -> pl.DataFrame:
        """
        Read historical data using Delta Lake time travel.

        Args:
            symbol: Futures symbol
            version: Delta Lake version (if specified)
            datetime_version: Point in time to read (if specified)

        Returns:
            pl.DataFrame: Historical data at specified version
        """
        dt = self.table.get_table()

        # Load historical version
        if version is not None:
            df = pl.from_pandas(dt.as_version(version).to_pandas())
        elif datetime_version is not None:
            df = pl.from_pandas(dt.as_version(datetime_version).to_pandas())
        else:
            raise ValueError("Must specify either version or datetime_version")

        # Filter by symbol
        df = df.filter(pl.col("symbol") == symbol)

        return df
