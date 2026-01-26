"""
Repository for options positions with Delta Lake backend.

This repository encapsulates Delta Lake operations for positions data,
providing a clean API for CRUD operations and time-travel queries.

Pattern from research: Use write_deltalake() for writes, DeltaTable() for reads.
"""

from pathlib import Path

import polars as pl
from deltalake import DeltaTable, write_deltalake
from loguru import logger


class PositionsRepository:
    """Repository for options positions with Delta Lake backend."""

    def __init__(self, table_path: str = "src/v6/data/lake/positions"):
        """
        Initialize the positions repository.

        Args:
            table_path: Path to Delta Lake table (default: src/v6/data/lake/positions)
        """
        self.table_path = table_path
        self._ensure_table_exists()

    def _ensure_table_exists(self) -> None:
        """Initialize table if it doesn't exist."""
        if not Path(self.table_path).exists():
            logger.info(f"Initializing positions table at {self.table_path}")
            # Create with schema (from research)
            # Note: Datetime requires time unit specification ("us" for microseconds)
            schema = pl.Schema({
                "strategy_id": pl.String,
                "strategy_type": pl.String,  # "iron_condor", "vertical_spread", etc.
                "symbol": pl.String,
                "status": pl.String,  # "open", "closed", "rolling"
                "entry_date": pl.Datetime("us"),
                "exit_date": pl.Datetime("us"),
                "entry_price": pl.Float64,
                "exit_price": pl.Float64,
                "quantity": pl.Int32,
                "delta": pl.Float64,
                "gamma": pl.Float64,
                "theta": pl.Float64,
                "vega": pl.Float64,
                "unrealized_pnl": pl.Float64,
                "realized_pnl": pl.Float64,
                "timestamp": pl.Datetime("us"),
            })
            df = pl.DataFrame(schema=schema)
            write_deltalake(
                self.table_path,
                df,
                mode="overwrite",
                partition_by=["symbol"]  # CRITICAL: partition by symbol, NOT timestamp
            )

    def get_latest(self) -> pl.DataFrame:
        """
        Get latest positions.

        Returns:
            Polars DataFrame with all positions
        """
        dt = DeltaTable(self.table_path)
        df_pandas = dt.to_pandas()
        return pl.from_pandas(df_pandas)

    def get_at_version(self, version: int) -> pl.DataFrame:
        """
        Time travel to specific version.

        Args:
            version: Delta Lake version number

        Returns:
            Polars DataFrame with positions at that version
        """
        dt = DeltaTable(self.table_path, version=version)
        df_pandas = dt.to_pandas()
        return pl.from_pandas(df_pandas)

    def get_at_time(self, timestamp: str) -> pl.DataFrame:
        """
        Time travel to specific timestamp.

        Args:
            timestamp: ISO format timestamp (e.g., "2026-01-26 09:30:00")

        Returns:
            Polars DataFrame with positions at that timestamp
        """
        dt = DeltaTable(self.table_path)
        # Note: as_at_datetime may not be available in all deltalake versions
        # This is a placeholder - implementation depends on deltalake version
        logger.warning(f"get_at_time() may not be fully supported: {timestamp}")
        df_pandas = dt.to_pandas()
        df = pl.from_pandas(df_pandas)
        # Filter by timestamp as fallback
        return df.filter(pl.col("timestamp") <= timestamp)

    def append(self, df: pl.DataFrame) -> None:
        """
        Append new positions (batch write to avoid small files problem).

        Args:
            df: Polars DataFrame with positions to append

        Note:
            This writes data in batch mode to avoid creating thousands of small files.
            See research Pitfall 1: Delta Lake Small Files Problem.
        """
        write_deltalake(
            self.table_path,
            df,
            mode="append",
            partition_by=["symbol"]  # CRITICAL: partition by symbol, NOT timestamp
        )
        logger.info(f"Appended {df.shape[0]} positions to {self.table_path}")

    def update_position(self, strategy_id: str, updates: dict) -> None:
        """
        Update specific position fields.

        Args:
            strategy_id: Strategy ID to update
            updates: Dictionary of field names and new values

        Note:
            This is a placeholder - full implementation would use Delta Lake merge
            operation which may not be available in all deltalake versions.
            Alternative: Read, modify, rewrite (not ideal but works).
        """
        logger.warning(f"update_position() is placeholder: {strategy_id}, {updates}")
        # TODO: Implement merge operation when available or use read-modify-rewrite
        pass

    def get_by_symbol(self, symbol: str) -> pl.DataFrame:
        """
        Get positions for specific symbol.

        Args:
            symbol: Underlying symbol (e.g., "SPY")

        Returns:
            Polars DataFrame filtered by symbol
        """
        dt = DeltaTable(self.table_path)
        df_pandas = dt.to_pandas()
        df = pl.from_pandas(df_pandas)
        return df.filter(pl.col("symbol") == symbol)

    def get_open_positions(self) -> pl.DataFrame:
        """
        Get all open positions.

        Returns:
            Polars DataFrame filtered by status="open"
        """
        dt = DeltaTable(self.table_path)
        df_pandas = dt.to_pandas()
        df = pl.from_pandas(df_pandas)
        return df.filter(pl.col("status") == "open")

    def get_by_strategy_id(self, strategy_id: str) -> pl.DataFrame:
        """
        Get position by strategy ID.

        Args:
            strategy_id: Unique strategy identifier

        Returns:
            Polars DataFrame filtered by strategy_id
        """
        dt = DeltaTable(self.table_path)
        df_pandas = dt.to_pandas()
        df = pl.from_pandas(df_pandas)
        return df.filter(pl.col("strategy_id") == strategy_id)

    def get_version(self) -> int:
        """
        Get current Delta Lake version.

        Returns:
            Current version number
        """
        dt = DeltaTable(self.table_path)
        return dt.version()
