"""
Performance Metrics Persistence Module

Provides Delta Lake persistence layer for trade performance tracking.
Implements idempotent writes, partitioning, and time-series queries for PnL analysis.

Key patterns:
- PerformanceMetricsTable: Delta Lake table with schema and timestamp partitioning
- PerformanceWriter: Batch writer for idempotent trade metrics
- Anti-join deduplication: Simpler than MERGE, avoids DuckDB dependency
- Batch writes: Every 60s to avoid small files problem
- Time-series queries: Historical performance analysis support
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

import polars as pl
from deltalake import DeltaTable, write_deltalake
from loguru import logger


@dataclass
class Greeks:
    """Options Greeks data."""
    delta: float
    gamma: float
    theta: float
    vega: float


@dataclass
class PerformanceMetric:
    """Trade performance metric snapshot."""
    timestamp: datetime
    strategy_id: str
    trade_id: str
    entry_time: datetime
    exit_time: Optional[datetime]
    entry_price: float
    exit_price: Optional[float]
    quantity: int
    premium_collected: float
    premium_paid: float
    net_premium: float
    max_profit: float
    max_loss: float
    realized_pnl: float
    unrealized_pnl: float
    hold_duration_minutes: Optional[int]
    exit_reason: Optional[str]  # 'expiry', 'stop_loss', 'take_profit', 'manual', 'roll'
    greeks_at_entry: Optional[Greeks]
    greeks_at_exit: Optional[Greeks]
    metadata: Optional[Dict[str, Any]]  # Additional trade metrics


class PerformanceMetricsTable:
    """Delta Lake table for performance metrics with idempotent writes."""

    def __init__(self, table_path: str = "data/lake/performance_metrics"):
        """
        Initialize performance metrics table.

        Args:
            table_path: Path to Delta Lake table (default: data/lake/performance_metrics)
        """
        self.table_path = Path(table_path)
        self._ensure_table_exists()

    def _ensure_table_exists(self) -> None:
        """Create table if it doesn't exist."""
        if DeltaTable.is_deltatable(str(self.table_path)):
            return

        # Schema for performance metrics (use Polars schema)
        schema = pl.Schema({
            'timestamp': pl.Datetime("us"),
            'strategy_id': pl.String,
            'trade_id': pl.String,
            'entry_time': pl.Datetime("us"),
            'exit_time': pl.Datetime("us"),
            'entry_price': pl.Float64,
            'exit_price': pl.Float64,
            'quantity': pl.Int64,
            'premium_collected': pl.Float64,
            'premium_paid': pl.Float64,
            'net_premium': pl.Float64,
            'max_profit': pl.Float64,
            'max_loss': pl.Float64,
            'realized_pnl': pl.Float64,
            'unrealized_pnl': pl.Float64,
            'hold_duration_minutes': pl.Int64,
            'exit_reason': pl.String,
            'greeks_at_entry': pl.String,  # JSON string
            'greeks_at_exit': pl.String,  # JSON string
            'metadata': pl.String,  # JSON string
        })

        # Create empty table
        empty_df = pl.DataFrame(schema=schema)
        write_deltalake(
            str(self.table_path),
            empty_df.limit(0),
            mode="overwrite",
            partition_by=["timestamp"]  # Partition by timestamp for efficient queries
        )

        logger.info(f"✓ Created Delta Lake table: {self.table_path}")

    def get_table(self) -> DeltaTable:
        """Get DeltaTable instance."""
        return DeltaTable(str(self.table_path))


class PerformanceWriter:
    """
    Write performance metrics to Delta Lake with idempotent guarantees.

    Batches writes every 60 seconds to avoid small files problem.
    Uses anti-join deduplication for idempotency with Last-Write-Wins conflict resolution.
    """

    def __init__(self, table: PerformanceMetricsTable, batch_interval: int = 60):
        """
        Initialize writer.

        Args:
            table: PerformanceMetricsTable instance
            batch_interval: Seconds between batch writes (default: 60s)
        """
        self.table = table
        self.batch_interval = batch_interval
        self._buffer: List[PerformanceMetric] = []
        self._write_task: Optional[asyncio.Task] = None
        self._is_writing = False

    async def on_metric(self, metric: PerformanceMetric) -> None:
        """Handle performance metric - add to buffer."""
        self._buffer.append(metric)
        logger.debug(f"Buffered metric: {metric.trade_id} at {metric.timestamp} (buffer size: {len(self._buffer)})")

    async def start_batch_writing(self) -> None:
        """Start periodic batch writing loop."""
        if self._is_writing:
            return

        self._is_writing = True
        self._write_task = asyncio.create_task(self._batch_write_loop())
        logger.info(f"✓ Started performance metrics batch writing (interval: {self.batch_interval}s)")

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
            await self._write_metrics(self._buffer)
            self._buffer.clear()

        logger.info("✓ Stopped performance metrics batch writing")

    async def _batch_write_loop(self) -> None:
        """Periodic batch writing loop."""
        while self._is_writing:
            try:
                await asyncio.sleep(self.batch_interval)

                if self._buffer and self._is_writing:
                    # Get buffered metrics and clear
                    metrics = self._buffer.copy()
                    self._buffer.clear()

                    # Write batch
                    await self._write_metrics(metrics)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Performance metrics batch write error: {e}", exc_info=True)

    def _serialize_greeks(self, greeks: Optional[Greeks]) -> str:
        """Serialize Greeks to JSON string."""
        if greeks is None:
            return "{}"

        return json.dumps({
            'delta': greeks.delta,
            'gamma': greeks.gamma,
            'theta': greeks.theta,
            'vega': greeks.vega
        })

    async def _write_metrics(self, metrics: List[PerformanceMetric]) -> int:
        """
        Write performance metrics with idempotent deduplication.

        Uses anti-join for idempotency:
        - Same trade_id: Skip (duplicate)
        - New trade_id: INSERT

        Args:
            metrics: List of performance metrics to write

        Returns:
            int: Number of metrics written
        """
        if not metrics:
            return 0

        # Convert to list of dicts first
        data = []
        for m in metrics:
            # Serialize greeks and metadata to JSON
            greeks_entry_json = self._serialize_greeks(m.greeks_at_entry)
            greeks_exit_json = self._serialize_greeks(m.greeks_at_exit)
            metadata_json = json.dumps(m.metadata) if m.metadata else "{}"

            # Handle nullable fields - use None for true nulls
            data.append({
                'timestamp': m.timestamp,
                'strategy_id': m.strategy_id,
                'trade_id': m.trade_id,
                'entry_time': m.entry_time,
                'exit_time': m.exit_time,  # Can be None
                'entry_price': m.entry_price,
                'exit_price': m.exit_price,  # Can be None
                'quantity': m.quantity,
                'premium_collected': m.premium_collected,
                'premium_paid': m.premium_paid,
                'net_premium': m.net_premium,
                'max_profit': m.max_profit,
                'max_loss': m.max_loss,
                'realized_pnl': m.realized_pnl,
                'unrealized_pnl': m.unrealized_pnl,
                'hold_duration_minutes': m.hold_duration_minutes,  # Can be None
                'exit_reason': m.exit_reason,  # Can be None
                'greeks_at_entry': greeks_entry_json,
                'greeks_at_exit': greeks_exit_json,
                'metadata': metadata_json,
            })

        # Create DataFrame with explicit schema to avoid Null type inference
        # This prevents Delta Lake from receiving Null type columns
        df = pl.DataFrame(
            data,
            schema={
                'timestamp': pl.Datetime("us"),
                'strategy_id': pl.String,
                'trade_id': pl.String,
                'entry_time': pl.Datetime("us"),
                'exit_time': pl.Datetime("us"),
                'entry_price': pl.Float64,
                'exit_price': pl.Float64,
                'quantity': pl.Int64,
                'premium_collected': pl.Float64,
                'premium_paid': pl.Float64,
                'net_premium': pl.Float64,
                'max_profit': pl.Float64,
                'max_loss': pl.Float64,
                'realized_pnl': pl.Float64,
                'unrealized_pnl': pl.Float64,
                'hold_duration_minutes': pl.Int64,
                'exit_reason': pl.String,
                'greeks_at_entry': pl.String,
                'greeks_at_exit': pl.String,
                'metadata': pl.String,
            }
        )

        # First, deduplicate within the batch (keep latest timestamp per trade_id)
        df_deduped = df.sort('timestamp', descending=True).unique(
            subset=['trade_id'],
            keep='first'
        )

        # Read existing data for these trade_ids
        dt = self.table.get_table()

        # Get existing trade_ids
        existing_df = dt.to_pandas()
        if len(existing_df) > 0:
            existing_df = pl.from_pandas(existing_df).select(['trade_id'])

            # Anti-join: find new metrics that don't exist yet
            new_metrics = df_deduped.join(
                existing_df,
                on=['trade_id'],
                how='anti'  # Anti-join: keep only non-matching rows
            )
        else:
            new_metrics = df_deduped

        # Append only new metrics
        if len(new_metrics) > 0:
            write_deltalake(
                str(self.table.table_path),
                new_metrics,
                mode="append"
            )
            logger.info(f"✓ Wrote {len(new_metrics)} performance metrics (deduped from {len(metrics)})")
        else:
            logger.debug("No new metrics to write (all duplicates)")

        return len(new_metrics)


class PerformanceReader:
    """
    Read performance metrics from Delta Lake for analysis.

    Provides strategy-level and trade-level queries, PnL aggregation, and historical analysis.
    """

    def __init__(self, table: PerformanceMetricsTable):
        """
        Initialize reader.

        Args:
            table: PerformanceMetricsTable instance
        """
        self.table = table

    def read_trade(self, trade_id: str) -> Optional[pl.DataFrame]:
        """
        Read metrics for a specific trade.

        Args:
            trade_id: Trade identifier

        Returns:
            pl.DataFrame: Trade metrics or None if not found
        """
        dt = self.table.get_table()

        # Read data
        df = pl.from_pandas(dt.to_pandas())

        # Filter by trade_id
        df = df.filter(pl.col("trade_id") == trade_id)

        if len(df) == 0:
            return None

        return df

    def read_strategy_metrics(
        self,
        strategy_id: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> pl.DataFrame:
        """
        Read metrics for a specific strategy.

        Args:
            strategy_id: Strategy identifier
            start: Start datetime (optional)
            end: End datetime (optional)

        Returns:
            pl.DataFrame: Strategy metrics
        """
        dt = self.table.get_table()

        # Read data
        df = pl.from_pandas(dt.to_pandas())

        # Filter by strategy_id
        df = df.filter(pl.col("strategy_id") == strategy_id)

        # Filter by time range if specified
        if start:
            df = df.filter(pl.col("timestamp") >= start)
        if end:
            df = df.filter(pl.col("timestamp") <= end)

        # Sort by timestamp
        df = df.sort("timestamp")

        return df

    def read_time_range(
        self,
        start: datetime,
        end: datetime,
        strategy_id: Optional[str] = None
    ) -> pl.DataFrame:
        """
        Read metrics within a time range.

        Args:
            start: Start datetime
            end: End datetime
            strategy_id: Optional strategy filter

        Returns:
            pl.DataFrame: Metrics within time range
        """
        dt = self.table.get_table()

        # Read data
        df = pl.from_pandas(dt.to_pandas())

        # Filter by time range
        df = df.filter(
            (pl.col("timestamp") >= start) &
            (pl.col("timestamp") <= end)
        )

        # Filter by strategy if specified
        if strategy_id:
            df = df.filter(pl.col("strategy_id") == strategy_id)

        # Sort by timestamp
        df = df.sort("timestamp")

        return df

    def calculate_pnl(
        self,
        strategy_id: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> Dict[str, float]:
        """
        Calculate PnL summary for strategy or time range.

        Args:
            strategy_id: Optional strategy filter
            start: Optional start datetime
            end: Optional end datetime

        Returns:
            Dict with total_realized_pnl, total_unrealized_pnl, total_pnl, win_rate, avg_trade_pnl
        """
        # Get data
        if strategy_id:
            df = self.read_strategy_metrics(strategy_id, start, end)
        else:
            df = self.read_time_range(start or datetime.min, end or datetime.now())

        if len(df) == 0:
            return {
                'total_realized_pnl': 0.0,
                'total_unrealized_pnl': 0.0,
                'total_pnl': 0.0,
                'win_rate': 0.0,
                'avg_trade_pnl': 0.0,
                'num_trades': 0
            }

        # Calculate PnL
        total_realized = df['realized_pnl'].sum()
        total_unrealized = df['unrealized_pnl'].sum()
        total_pnl = total_realized + total_unrealized

        # Calculate win rate (trades with positive realized PnL)
        completed_trades = df.filter(pl.col('exit_time') != datetime(2000, 1, 1))
        if len(completed_trades) > 0:
            winning_trades = completed_trades.filter(pl.col('realized_pnl') > 0)
            win_rate = len(winning_trades) / len(completed_trades)
            avg_trade_pnl = completed_trades['realized_pnl'].mean()
        else:
            win_rate = 0.0
            avg_trade_pnl = 0.0

        return {
            'total_realized_pnl': total_realized,
            'total_unrealized_pnl': total_unrealized,
            'total_pnl': total_pnl,
            'win_rate': win_rate,
            'avg_trade_pnl': avg_trade_pnl,
            'num_trades': len(df)
        }

    def read_open_positions(self) -> pl.DataFrame:
        """
        Read all open positions (no exit time).

        Returns:
            pl.DataFrame: Open positions
        """
        dt = self.table.get_table()

        # Read data
        df = pl.from_pandas(dt.to_pandas())

        # Filter for open positions (exit_time is null)
        df = df.filter(pl.col("exit_time").is_null())

        # Sort by timestamp
        df = df.sort("timestamp")

        return df


# Import json for serialization
import json
