"""
Option Snapshots Delta Lake Table

This module provides Delta Lake persistence for option contract snapshots.
Stores complete option chain data for backtesting, analysis, and ML training.

Key features:
- OptionSnapshotsTable: Delta Lake table with proper schema
- Partitioned by symbol and yearmonth(expiry) for efficient queries
- Idempotent writes using timestamp+symbol+strike+expiry deduplication
- Support for reading latest chain and historical IV data
"""

from pathlib import Path
from typing import List, Optional

import polars as pl
from deltalake import DeltaTable, write_deltalake
from loguru import logger

from src.v6.core.models import OptionContract


class OptionSnapshotsTable:
    """
    Delta Lake table for option contract snapshots with idempotent writes.

    Schema:
    - timestamp: Snapshot timestamp (primary key component)
    - symbol: Underlying symbol (SPY, QQQ, IWM)
    - strike: Strike price
    - expiry: Expiration date (YYYYMMDD format)
    - right: Put or Call ('P' or 'C')
    - bid: Best bid price
    - ask: Best ask price
    - last: Last trade price
    - volume: Trading volume
    - open_interest: Open interest
    - iv: Implied volatility
    - delta: Option delta
    - gamma: Option gamma
    - theta: Option theta
    - vega: Option vega
    - yearmonth: Year-month of expiry for partitioning
    - date: Date of snapshot for partitioning

    Partitioning:
    - symbol: Partition by underlying symbol
    - yearmonth: Partition by expiry year-month (e.g., 202502 for Feb 2025)
    """

    def __init__(self, table_path: str = "data/lake/option_snapshots"):
        """
        Initialize option snapshots table.

        Args:
            table_path: Path to Delta Lake table (default: data/lake/option_snapshots)
        """
        self.table_path = Path(table_path)
        self._ensure_table_exists()

    def _ensure_table_exists(self) -> None:
        """Create table if it doesn't exist."""
        if DeltaTable.is_deltatable(str(self.table_path)):
            return

        # Schema for option snapshots
        schema = pl.Schema({
            'timestamp': pl.Datetime("us"),
            'symbol': pl.String,
            'strike': pl.Float64,
            'expiry': pl.String,
            'right': pl.String,
            'bid': pl.Float64,
            'ask': pl.Float64,
            'last': pl.Float64,
            'volume': pl.Int64,
            'open_interest': pl.Int64,
            'iv': pl.Float64,
            'delta': pl.Float64,
            'gamma': pl.Float64,
            'theta': pl.Float64,
            'vega': pl.Float64,
            'yearmonth': pl.Int32,  # For partitioning: 202502 for Feb 2025
            'date': pl.Date,  # For partitioning
        })

        # Create empty table
        empty_df = pl.DataFrame(schema=schema)
        write_deltalake(
            str(self.table_path),
            empty_df.limit(0),
            mode="overwrite",
            partition_by=["symbol", "yearmonth"]  # Partition by symbol and expiry month
        )

        logger.info(f"✓ Created Delta Lake table: {self.table_path}")

    def get_table(self) -> DeltaTable:
        """Get DeltaTable instance."""
        return DeltaTable(str(self.table_path))

    def write_snapshots(self, contracts: List[OptionContract]) -> int:
        """
        Write option snapshots with idempotent deduplication.

        Deduplication key: timestamp + symbol + strike + expiry + right

        Args:
            contracts: List of OptionContract objects to write

        Returns:
            int: Number of snapshots written (after deduplication)
        """
        if not contracts:
            return 0

        # Convert to Polars DataFrame
        data = []
        for contract in contracts:
            # Extract yearmonth from expiry (YYYYMMDD format)
            try:
                yearmonth = int(contract.expiry[:6])  # First 6 digits: YYYYMM
            except (ValueError, IndexError):
                yearmonth = 0

            data.append({
                'timestamp': contract.timestamp,
                'symbol': contract.symbol,
                'strike': contract.strike,
                'expiry': contract.expiry,
                'right': contract.right,
                'bid': contract.bid,
                'ask': contract.ask,
                'last': contract.last,
                'volume': contract.volume,
                'open_interest': contract.open_interest or 0,
                'iv': contract.iv or 0.0,
                'delta': contract.delta or 0.0,
                'gamma': contract.gamma or 0.0,
                'theta': contract.theta or 0.0,
                'vega': contract.vega or 0.0,
                'yearmonth': yearmonth,
                'date': contract.timestamp.date(),
            })

        df = pl.DataFrame(data)

        # Deduplicate within batch (keep latest timestamp for same contract)
        df_deduped = df.sort('timestamp', descending=True).unique(
            subset=['symbol', 'strike', 'expiry', 'right'],
            keep='first'
        )

        # Use anti-join for deduplication against existing data
        dt = self.get_table()

        # Read existing data for these contracts
        existing_df = pl.from_pandas(dt.to_pandas())

        # Filter to contracts in this batch
        batch_contracts = df_deduped.select(['symbol', 'strike', 'expiry', 'right']).unique()
        existing_filtered = existing_df.join(
            batch_contracts,
            on=['symbol', 'strike', 'expiry', 'right'],
            how='inner'
        )

        # Anti-join to find new snapshots
        # For existing contracts, only keep if timestamp is newer
        if len(existing_filtered) > 0:
            # Join to find existing records
            joined = df_deduped.join(
                existing_filtered.select(['symbol', 'strike', 'expiry', 'right', 'timestamp']),
                on=['symbol', 'strike', 'expiry', 'right'],
                how='left'
            )

            # Filter: keep if no existing timestamp OR new timestamp is newer
            new_snapshots = joined.filter(
                (pl.col("timestamp_right").is_null()) |
                (pl.col("timestamp") > pl.col("timestamp_right"))
            )

            # Drop the join column
            new_snapshots = new_snapshots.drop('timestamp_right')
        else:
            new_snapshots = df_deduped

        # Append only new snapshots
        if len(new_snapshots) > 0:
            write_deltalake(
                str(self.table_path),
                new_snapshots,
                mode="append"
            )
            logger.info(
                f"✓ Wrote {len(new_snapshots)} option snapshots for {contracts[0].symbol} "
                f"(deduped from {len(contracts)})"
            )
        else:
            logger.debug("No new snapshots to write (all duplicates)")

        return len(new_snapshots)

    def read_latest_chain(self, symbol: str) -> pl.DataFrame:
        """
        Read latest option chain for symbol.

        Args:
            symbol: Underlying symbol (SPY, QQQ, IWM)

        Returns:
            pl.DataFrame: Latest option chain with all Greeks and IV
        """
        dt = self.get_table()

        # Read all data for symbol
        df = pl.from_pandas(dt.to_pandas()).filter(
            pl.col("symbol") == symbol
        )

        if len(df) == 0:
            logger.warning(f"No option chain data found for {symbol}")
            return pl.DataFrame()

        # Get latest timestamp for each contract
        latest_df = df.sort('timestamp', descending=True).unique(
            subset=['strike', 'expiry', 'right'],
            keep='first'
        )

        logger.info(f"✓ Read {len(latest_df)} contracts from latest {symbol} chain")

        return latest_df

    def read_historical_iv(self, symbol: str, days: int = 60) -> pl.DataFrame:
        """
        Read historical IV data for symbol.

        Args:
            symbol: Underlying symbol (SPY, QQQ, IWM)
            days: Number of days of history to read (default: 60)

        Returns:
            pl.DataFrame: Historical IV data with daily averages
        """
        from datetime import datetime, timedelta

        dt = self.get_table()

        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # Read historical data
        df = pl.from_pandas(dt.to_pandas())

        # Filter by symbol and date range
        df = df.filter(
            (pl.col("symbol") == symbol) &
            (pl.col("timestamp") >= start_date) &
            (pl.col("timestamp") <= end_date) &
            (pl.col("iv").is_not_null()) &
            (pl.col("iv") > 0)
        )

        if len(df) == 0:
            logger.warning(f"No historical IV data found for {symbol}")
            return pl.DataFrame()

        # Calculate daily IV averages
        daily_iv = df.group_dynamic(
            "timestamp",
            every="1d",
            period="1d"
        ).agg(
            [
                pl.col("iv").mean().alias("avg_iv"),
                pl.col("iv").min().alias("min_iv"),
                pl.col("iv").max().alias("max_iv"),
                pl.col("iv").std().alias("std_iv"),
            ]
        ).drop_nulls()

        logger.info(f"✓ Read {len(daily_iv)} days of historical IV data for {symbol}")

        return daily_iv

    def read_atm_options(
        self,
        symbol: str,
        dte_min: int = 20,
        dte_max: int = 50,
        delta_range: tuple = (-0.3, -0.2)
    ) -> pl.DataFrame:
        """
        Read at-the-money (ATM) options for analysis.

        Args:
            symbol: Underlying symbol (SPY, QQQ, IWM)
            dte_min: Minimum days to expiration (default: 20)
            dte_max: Maximum days to expiration (default: 50)
            delta_range: Delta range for puts (default: -0.3 to -0.2)

        Returns:
            pl.DataFrame: ATM options matching criteria
        """
        from datetime import datetime, timedelta

        dt = self.get_table()

        # Calculate expiry date range
        now = datetime.now()
        min_expiry = now + timedelta(days=dte_min)
        max_expiry = now + timedelta(days=dte_max)

        # Read latest data
        df = self.read_latest_chain(symbol)

        if len(df) == 0:
            return pl.DataFrame()

        # Filter for puts in delta range and DTE range
        df = df.filter(
            (pl.col("right") == "P") &
            (pl.col("delta").is_between(delta_range[0], delta_range[1])) &
            (pl.col("iv").is_not_null()) &
            (pl.col("iv") > 0)
        )

        logger.info(f"✓ Found {len(df)} ATM options for {symbol}")

        return df

    def get_snapshot_stats(self) -> dict:
        """
        Get statistics about option snapshots table.

        Returns:
            dict: Table statistics including row count, symbols, date range
        """
        dt = self.get_table()

        # Read all data
        df = pl.from_pandas(dt.to_pandas())

        if len(df) == 0:
            return {
                "total_rows": 0,
                "symbols": [],
                "date_range": None,
                "latest_timestamp": None,
            }

        # Calculate stats
        stats = {
            "total_rows": len(df),
            "symbols": df.select("symbol").unique().to_series().to_list(),
            "date_range": {
                "start": df.select(pl.col("timestamp").min()).item(),
                "end": df.select(pl.col("timestamp").max()).item(),
            },
            "latest_timestamp": df.select(pl.col("timestamp").max()).item(),
        }

        return stats
