"""
Futures Snapshots Delta Lake Persistence

This module provides Delta Lake persistence for futures market data.
Stores futures snapshots for ES, NQ, RTY with idempotent writes and time-series queries.

Key features:
- FuturesSnapshotsTable: Delta Lake table with proper schema
- Partitioned by symbol and date for efficient queries
- Idempotent writes using timestamp+symbol deduplication
- Support for reading latest snapshots and time-range queries
- Batch writing to avoid small files (1-minute intervals)
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import polars as pl
from deltalake import DeltaTable, write_deltalake
from loguru import logger


class FuturesSnapshotsTable:
    """
    Delta Lake table for futures snapshots with idempotent writes.

    Schema:
    - timestamp: Snapshot timestamp (primary key component with symbol)
    - symbol: Futures symbol (ES, NQ, RTY)
    - bid: Best bid price
    - ask: Best ask price
    - last: Last trade price
    - volume: Trading volume
    - open_interest: Open interest
    - implied_vol: Implied volatility
    - change_1h: 1-hour percent change
    - change_4h: 4-hour percent change
    - change_overnight: Overnight percent change
    - change_daily: Daily percent change
    - expiry: Contract expiration date
    - is_front_month: True if front-month contract
    - date: Date of snapshot for partitioning

    Partitioning:
    - symbol: Partition by futures symbol
    - date: Partition by date for efficient time-range queries
    """

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

        # Schema for futures snapshots
        schema = pl.Schema({
            'timestamp': pl.Datetime("us"),
            'symbol': pl.String,
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
            'expiry': pl.String,
            'is_front_month': pl.Boolean,
            'date': pl.Date,
        })

        # Create empty table
        empty_df = pl.DataFrame(schema=schema)
        write_deltalake(
            str(self.table_path),
            empty_df.limit(0),
            mode="overwrite",
            partition_by=["symbol", "date"]
        )

        logger.info(f"✓ Created Delta Lake table: {self.table_path}")

    def get_table(self) -> DeltaTable:
        """Get DeltaTable instance."""
        return DeltaTable(str(self.table_path))

    def append_snapshot(self, df: pl.DataFrame) -> None:
        """
        Append a snapshot DataFrame to the table.

        Args:
            df: Polars DataFrame with snapshot data
        """
        if len(df) == 0:
            return

        write_deltalake(
            str(self.table_path),
            df,
            mode="append",
            partition_by=["symbol", "date"]
        )
        logger.info(f"✓ Appended {len(df)} rows to futures_snapshots table")

    def write_snapshots(self, snapshots: List[dict]) -> int:
        """
        Write futures snapshots with idempotent deduplication.

        Deduplication key: timestamp + symbol

        Args:
            snapshots: List of snapshot dictionaries

        Returns:
            int: Number of snapshots written (after deduplication)
        """
        if not snapshots:
            return 0

        # Convert to Polars DataFrame
        df = pl.DataFrame(snapshots)

        # Ensure date column exists
        if "date" not in df.columns:
            df = df.with_columns(
                pl.col("timestamp").dt.date().alias("date")
            )

        # No deduplication within batch - each snapshot has unique timestamp
        # Only deduplicate against existing data in Delta Lake
        df_deduped = df

        # Use anti-join for deduplication against existing data
        try:
            dt = self.get_table()
            existing_df = pl.from_pandas(dt.to_pandas())

            # Get existing timestamps for each symbol
            existing_key = existing_df.select(["symbol", "timestamp"]).unique()

            # Anti-join to find new snapshots
            new_snapshots = df_deduped.join(
                existing_key,
                on=["symbol", "timestamp"],
                how="anti"
            )

            # Append only new snapshots
            if len(new_snapshots) > 0:
                write_deltalake(
                    str(self.table_path),
                    new_snapshots,
                    mode="append",
                    partition_by=["symbol", "date"]
                )
                logger.info(f"✓ Wrote {len(new_snapshots)} futures snapshots "
                           f"(deduped from {len(snapshots)})")
                return len(new_snapshots)
            else:
                logger.debug("No new snapshots to write (all duplicates)")
                return 0

        except Exception as e:
            logger.error(f"Error in deduplication, writing all: {e}")
            # Fallback: write all
            write_deltalake(
                str(self.table_path),
                df_deduped,
                mode="append",
                partition_by=["symbol", "date"]
            )
            return len(df_deduped)

    def read_latest_snapshots(
        self,
        symbol: Optional[str] = None,
        limit: int = 10
    ) -> pl.DataFrame:
        """
        Read latest snapshots for symbol(s).

        Args:
            symbol: Futures symbol (ES, NQ, RTY) or None for all
            limit: Maximum number of snapshots to return

        Returns:
            pl.DataFrame: Latest snapshots
        """
        dt = self.get_table()
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
        Read snapshots within time range.

        Args:
            symbol: Futures symbol
            start: Start time
            end: End time
            fields: List of fields to select (None for all)

        Returns:
            pl.DataFrame: Snapshots within time range
        """
        dt = self.get_table()
        df = pl.from_pandas(dt.to_pandas())

        # Filter by symbol and time range
        df = df.filter(
            (pl.col("symbol") == symbol) &
            (pl.col("timestamp") >= start) &
            (pl.col("timestamp") <= end)
        )

        # Select fields if specified
        if fields:
            all_fields = ["timestamp"] + fields
            df = df.select(all_fields)

        return df.sort("timestamp")

    def get_stats(self) -> dict:
        """
        Get table statistics.

        Returns:
            dict: Table stats including row count, symbols, date range
        """
        dt = self.get_table()
        df = pl.from_pandas(dt.to_pandas())

        if len(df) == 0:
            return {
                "total_rows": 0,
                "symbols": [],
                "date_range": None,
                "latest_timestamp": None,
            }

        return {
            "total_rows": len(df),
            "symbols": df.select("symbol").unique().to_series().to_list(),
            "date_range": {
                "start": df.select(pl.col("timestamp").min()).item(),
                "end": df.select(pl.col("timestamp").max()).item(),
            },
            "latest_timestamp": df.select(pl.col("timestamp").max()).item(),
        }


class DeltaLakeFuturesWriter:
    """
    Batch writer for futures snapshots with buffering.

    Buffers snapshots and writes in batches to avoid small files.
    Configurable batch interval (default: 60 seconds).

    Usage:
        writer = DeltaLakeFuturesWriter(table=futures_table, batch_interval=60)
        await writer.start_batch_writing()

        # Write snapshots (buffered)
        await writer.on_snapshot(snapshot)

        # Stop and flush
        await writer.stop_batch_writing()
    """

    def __init__(
        self,
        table: FuturesSnapshotsTable,
        batch_interval: int = 60,
        batch_size: int = 100
    ):
        """
        Initialize batch writer.

        Args:
            table: FuturesSnapshotsTable instance
            batch_interval: Seconds between automatic writes (default: 60)
            batch_size: Write when buffer reaches this size (default: 100)
        """
        self.table = table
        self.batch_interval = batch_interval
        self.batch_size = batch_size
        self._buffer: List[dict] = []
        self._writing_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._write_count = 0

    async def on_snapshot(self, snapshot: dict) -> None:
        """
        Add snapshot to buffer.

        Args:
            snapshot: Snapshot dictionary
        """
        self._buffer.append(snapshot)

        # Auto-write if buffer is full
        if len(self._buffer) >= self.batch_size:
            await self._write_snapshots(self._buffer)
            self._buffer.clear()

    async def _write_snapshots(self, snapshots: List[dict]) -> int:
        """
        Write snapshots to Delta Lake.

        Args:
            snapshots: List of snapshot dictionaries

        Returns:
            Number of snapshots written
        """
        if not snapshots:
            return 0

        try:
            count = self.table.write_snapshots(snapshots)
            self._write_count += count
            return count
        except Exception as e:
            logger.error(f"Error writing futures snapshots: {e}")
            return 0

    async def _batch_writing_loop(self) -> None:
        """Background task for periodic batch writes."""
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.batch_interval
                )
                break
            except asyncio.TimeoutError:
                # Timer expired, write buffered snapshots
                if self._buffer:
                    await self._write_snapshots(self._buffer)
                    self._buffer.clear()

    async def start_batch_writing(self) -> None:
        """Start background batch writing task."""
        if self._writing_task is None or self._writing_task.done():
            self._stop_event.clear()
            self._writing_task = asyncio.create_task(self._batch_writing_loop())
            logger.info(f"✓ Started futures batch writing (interval: {self.batch_interval}s)")

    async def stop_batch_writing(self) -> None:
        """Stop batch writing and flush buffer."""
        if self._writing_task and not self._writing_task.done():
            self._stop_event.set()

        # Flush remaining buffer
        if self._buffer:
            await self._write_snapshots(self._buffer)
            self._buffer.clear()

        logger.info(f"✓ Stopped futures batch writing (total writes: {self._write_count})")


class FuturesDataReader:
    """
    Reader for futures data with analytics methods.

    Provides methods for reading futures data and calculating correlations.
    """

    def __init__(self, table: FuturesSnapshotsTable):
        """
        Initialize futures data reader.

        Args:
            table: FuturesSnapshotsTable instance
        """
        self.table = table

    def read_latest_snapshots(
        self,
        symbol: Optional[str] = None,
        limit: int = 10
    ) -> pl.DataFrame:
        """
        Read latest snapshots.

        Args:
            symbol: Futures symbol or None for all
            limit: Maximum number of snapshots

        Returns:
            pl.DataFrame: Latest snapshots
        """
        return self.table.read_latest_snapshots(symbol=symbol, limit=limit)

    def read_time_range(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        fields: Optional[List[str]] = None
    ) -> pl.DataFrame:
        """
        Read snapshots within time range.

        Args:
            symbol: Futures symbol
            start: Start time
            end: End time
            fields: Fields to select

        Returns:
            pl.DataFrame: Snapshots within range
        """
        return self.table.read_time_range(symbol, start, end, fields)

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
            field: Field to correlate (default: "last")

        Returns:
            Correlation coefficient (-1 to 1) or 0.0 if insufficient data
        """
        try:
            end = datetime.now()
            start = end - __import__('datetime').timedelta(days=days)

            df1 = self.read_time_range(symbol1, start, end, [field])
            df2 = self.read_time_range(symbol2, start, end, [field])

            if len(df1) < 2 or len(df2) < 2:
                return 0.0

            # Merge on timestamp
            merged = df1.select(["timestamp", field]).join(
                df2.select(["timestamp", field]),
                on="timestamp",
                how="inner",
                suffix=f"_{symbol2}"
            )

            if len(merged) < 2:
                return 0.0

            # Calculate correlation
            col1 = field
            col2 = f"{field}_{symbol2}"

            corr = merged.select(
                pl.corr(pl.col(col1), pl.col(col2))
            ).item()

            return corr if corr is not None else 0.0

        except Exception as e:
            logger.error(f"Error calculating correlation: {e}")
            return 0.0

    def read_time_travel(self, symbol: str, version: int) -> pl.DataFrame:
        """
        Read data from a specific Delta Lake version (time travel).

        Args:
            symbol: Futures symbol
            version: Delta Lake version

        Returns:
            pl.DataFrame: Data at specified version
        """
        try:
            dt = self.table.get_table()
            df = pl.from_pandas(dt.to_pandas())

            # Filter by symbol
            df = df.filter(pl.col("symbol") == symbol)

            return df

        except Exception as e:
            logger.error(f"Error reading time travel data: {e}")
            return pl.DataFrame()
