#!/usr/bin/env python3
"""
Initialize Delta Lake tables for options trading data.

Creates 4 tables:
- positions: Strategy positions (Iron Condor, spreads)
- legs: Individual option legs
- greeks: Greeks snapshots for time-travel analytics
- transactions: Trade executions (entry, exit, adjustments)

Critical pattern: Partition by symbol (NOT timestamp) to avoid small files problem.
"""

from deltalake import DeltaTable, write_deltalake
import polars as pl
from pathlib import Path
from loguru import logger

# Base path for Delta Lake tables
LAKE_BASE = Path("src/v6/data/lake")


def create_positions_table() -> None:
    """Create Delta Lake table for strategy positions."""
    table_path = LAKE_BASE / "positions"

    # Schema for positions table - define with proper types
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

    # Create empty DataFrame with schema
    df = pl.DataFrame(schema=schema)

    # Write to Delta Lake with symbol partitioning
    write_deltalake(
        table_path,
        df,
        mode="overwrite",
        partition_by=["symbol"]  # CRITICAL: partition by symbol, NOT timestamp
    )

    logger.info(f"Created positions table at {table_path} with symbol partitioning")


def create_legs_table() -> None:
    """Create Delta Lake table for individual option legs."""
    table_path = LAKE_BASE / "legs"

    # Schema for legs table
    schema = pl.Schema({
        "leg_id": pl.String,
        "strategy_id": pl.String,
        "symbol": pl.String,
        "strike": pl.Float64,
        "expiry": pl.Date,
        "right": pl.String,  # "C" or "P"
        "quantity": pl.Int32,
        "open_price": pl.Float64,
        "current_price": pl.Float64,
        "delta": pl.Float64,
        "gamma": pl.Float64,
        "theta": pl.Float64,
        "vega": pl.Float64,
        "status": pl.String,  # "open", "closed"
        "timestamp": pl.Datetime("us"),
    })

    # Create empty DataFrame with schema
    df = pl.DataFrame(schema=schema)

    # Write to Delta Lake with symbol partitioning
    write_deltalake(
        table_path,
        df,
        mode="overwrite",
        partition_by=["symbol"]  # CRITICAL: partition by symbol, NOT timestamp
    )

    logger.info(f"Created legs table at {table_path} with symbol partitioning")


def create_greeks_table() -> None:
    """Create Delta Lake table for Greeks snapshots (time-travel analytics)."""
    table_path = LAKE_BASE / "greeks"

    # Schema for Greeks table
    schema = pl.Schema({
        "strategy_id": pl.String,
        "symbol": pl.String,
        "delta": pl.Float64,
        "gamma": pl.Float64,
        "theta": pl.Float64,
        "vega": pl.Float64,
        "portfolio_delta": pl.Float64,
        "portfolio_gamma": pl.Float64,
        "timestamp": pl.Datetime("us"),
    })

    # Create empty DataFrame with schema
    df = pl.DataFrame(schema=schema)

    # Write to Delta Lake with symbol partitioning
    write_deltalake(
        table_path,
        df,
        mode="overwrite",
        partition_by=["symbol"]  # CRITICAL: partition by symbol, NOT timestamp
    )

    logger.info(f"Created greeks table at {table_path} with symbol partitioning")


def create_transactions_table() -> None:
    """Create Delta Lake table for trade executions."""
    table_path = LAKE_BASE / "transactions"

    # Schema for transactions table
    schema = pl.Schema({
        "transaction_id": pl.String,
        "strategy_id": pl.String,
        "leg_id": pl.String,
        "action": pl.String,  # "BUY", "SELL", "OPEN", "CLOSE"
        "quantity": pl.Int32,
        "price": pl.Float64,
        "commission": pl.Float64,
        "timestamp": pl.Datetime("us"),
    })

    # Create empty DataFrame with schema
    df = pl.DataFrame(schema=schema)

    # Write to Delta Lake (no partitioning for high-frequency transaction data)
    write_deltalake(
        table_path,
        df,
        mode="overwrite"
    )

    logger.info(f"Created transactions table at {table_path}")


def verify_tables() -> bool:
    """Verify all tables exist and are readable."""
    tables = ["positions", "legs", "greeks", "transactions"]

    for table_name in tables:
        table_path = LAKE_BASE / table_name

        # Check if table exists
        if not table_path.exists():
            logger.error(f"Table {table_name} does not exist at {table_path}")
            return False

        # Try to read table
        try:
            dt = DeltaTable(str(table_path))
            # Use to_pandas() then convert to polars
            df_pandas = dt.to_pandas()
            df = pl.from_pandas(df_pandas)

            # Verify schema
            logger.info(f"Table {table_name}: {df.shape} rows, columns: {df.columns}")

            # Verify time-travel works
            dt_version_0 = DeltaTable(str(table_path), version=0)
            df_v0_pandas = dt_version_0.to_pandas()
            df_v0 = pl.from_pandas(df_v0_pandas)
            logger.info(f"Table {table_name} time-travel test: version=0 returns {df_v0.shape} rows")

        except Exception as e:
            logger.error(f"Failed to read table {table_name}: {e}")
            return False

    return True


def main():
    """Create all Delta Lake tables."""
    logger.info("Creating Delta Lake tables for options trading data")

    # Create lake base directory
    LAKE_BASE.mkdir(parents=True, exist_ok=True)

    # Create all tables
    create_positions_table()
    create_legs_table()
    create_greeks_table()
    create_transactions_table()

    # Verify tables
    if verify_tables():
        logger.info("All Delta Lake tables created successfully!")
        return 0
    else:
        logger.error("Table verification failed!")
        return 1


if __name__ == "__main__":
    exit(main())
