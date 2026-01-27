---
phase: 1-architecture-infrastructure
plan: 02
type: execute
depends_on: ["1-01"]
files_modified: [src/v6/data/lake/positions/_delta_log/*.json, src/v6/data/lake/legs/_delta_log/*.json, src/v6/data/repositories/__init__.py, src/v6/data/repositories/positions.py]
---

<objective>
Design and implement Delta Lake schema for options trading data with ACID transactions and time-travel support.

Purpose: Create the data foundation for storing positions, legs, Greeks, and transactions with Delta Lake's ACID guarantees and time-travel capabilities for analytics.
Output: Working Delta Lake tables with proper schema, partitioning, and repository access layer.
</objective>

<execution_context>
~/.claude/get-shit-done/workflows/execute-plan.md
./summary.md
</execution_context>

<context>
@v6/.planning/PROJECT.md
@v6/.planning/ROADMAP.md
@v6/.planning/phases/1-architecture-infrastructure/1-RESEARCH.md
@v6/.planning/phases/1-architecture-infrastructure/1-01-SUMMARY.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create Delta Lake tables for positions, legs, Greeks, and transactions</name>
  <files>src/v6/data/lake/positions/_delta_log/*.json, src/v6/data/lake/legs/_delta_log/*.json, src/v6/data/lake/greeks/_delta_log/*.json, src/v6/data/lake/transactions/_delta_log/*.json</files>
  <action>
Create Delta Lake tables following research-based patterns:

**Directory structure:**
```
src/v6/data/lake/
├── positions/          # Strategy positions (Iron Condor, spreads)
├── legs/               # Individual option legs
├── greeks/             # Greeks snapshots for time-travel
└── transactions/       # Trade executions (entry, exit, adjustments)
```

**Positions table schema:**
```python
from deltalake import DeltaTable, write_deltalake
import polars as pl

# Initial schema with proper types
schema = {
    "strategy_id": pl.String,
    "strategy_type": pl.String,  # "iron_condor", "vertical_spread", etc.
    "symbol": pl.String,
    "status": pl.String,          # "open", "closed", "rolling"
    "entry_date": pl.Datetime,
    "exit_date": pl.Datetime,
    "entry_price": pl.Float64,
    "exit_price": pl.Float64,
    "quantity": pl.Int32,
    "delta": pl.Float64,
    "gamma": pl.Float64,
    "theta": pl.Float64,
    "vega": pl.Float64,
    "unrealized_pnl": pl.Float64,
    "realized_pnl": pl.Float64,
    "timestamp": pl.Datetime,
}

# Create empty table
df = pl.DataFrame(schema)
write_deltalake(
    "src/v6/data/lake/positions",
    df,
    mode="overwrite",
    schema=schema
)
```

**Legs table schema:**
```python
schema = {
    "leg_id": pl.String,
    "strategy_id": pl.String,
    "symbol": pl.String,
    "strike": pl.Float64,
    "expiry": pl.Date,
    "right": pl.String,          # "C" or "P"
    "quantity": pl.Int32,
    "open_price": pl.Float64,
    "current_price": pl.Float64,
    "delta": pl.Float64,
    "gamma": pl.Float64,
    "theta": pl.Float64,
    "vega": pl.Float64,
    "status": pl.String,          # "open", "closed"
    "timestamp": pl.Datetime,
}
```

**Greeks table schema:** (for time-travel analytics)
```python
schema = {
    "strategy_id": pl.String,
    "symbol": pl.String,
    "delta": pl.Float64,
    "gamma": pl.Float64,
    "theta": pl.Float64,
    "vega": pl.Float64,
    "portfolio_delta": pl.Float64,
    "portfolio_gamma": pl.Float64,
    "timestamp": pl.Datetime,
}
```

**Transactions table schema:**
```python
schema = {
    "transaction_id": pl.String,
    "strategy_id": pl.String,
    "leg_id": pl.String,
    "action": pl.String,         # "BUY", "SELL", "OPEN", "CLOSE"
    "quantity": pl.Int32,
    "price": pl.Float64,
    "commission": pl.Float64,
    "timestamp": pl.Datetime,
}
```

**Critical pattern - partition by symbol, NOT timestamp:**
```python
# BAD: partition_by=["timestamp"] creates 86400 partitions/day
# GOOD: partition_by=["symbol"] creates manageable partitions
write_deltalake(
    "src/v6/data/lake/positions",
    df,
    mode="append",
    partition_by=["symbol"]  # Partition by symbol, NOT timestamp
)
```

**Why this partitioning:**
- Partition by symbol: Low cardinality, manageable folders
- Never partition by timestamp: High cardinality = thousands of partitions
- Filter by timestamp in queries instead: `df.filter(pl.col("timestamp") > start_time)`

**Time-travel examples:**
```python
# Read latest state
dt = DeltaTable("src/v6/data/lake/positions")
df = dt.to_polars()

# Time travel to version 5
dt = DeltaTable("src/v6/data/lake/positions", version=5)
historical_state = dt.to_polars()

# Time travel to timestamp
dt.as_at_datetime("2026-01-26 09:30:00")
state_at_time = dt.to_polars()
```

**Don't hand-roll:**
- Use `write_deltalake()` for writes (not custom Parquet + versioning)
- Use `DeltaTable()` for reads (not manual file management)
- Use `partition_by=["symbol"]` (not by timestamp - see research Pitfall 6)
- Use Delta Lake's OPTIMIZE later for small file problem (not manual compaction)
  </action>
  <verify>
    All 4 Delta Lake tables exist with correct schemas
    DeltaTable("src/v6/data/lake/positions").to_polars() returns empty DataFrame with correct schema
    DeltaTable("src/v6/data/lake/positions", version=0).to_polars() works (time-travel)
    ls src/v6/data/lake/positions/ shows symbol folders (partitioning)
  </verify>
  <done>
    positions/ table created with schema and symbol partitioning
    legs/ table created with schema
    greeks/ table created with schema
    transactions/ table created with schema
    Time-travel works (version=0, as_at_datetime)
  </done>
</task>

<task type="auto">
  <name>Task 2: Implement repository pattern for Delta Lake data access</name>
  <files>src/v6/data/repositories/__init__.py, src/v6/data/repositories/positions.py</files>
  <action>
Create repository layer for Delta Lake operations:

**File: src/v6/data/repositories/positions.py**
```python
from deltalake import DeltaTable, write_deltalake
import polars as pl
from pathlib import Path
from typing import Optional
from loguru import logger

class PositionsRepository:
    """Repository for options positions with Delta Lake backend."""

    def __init__(self, table_path: str = "src/v6/data/lake/positions"):
        self.table_path = table_path
        self._ensure_table_exists()

    def _ensure_table_exists(self) -> None:
        """Initialize table if it doesn't exist."""
        if not Path(self.table_path).exists():
            logger.info(f"Initializing positions table at {self.table_path}")
            # Create with schema (from research)
            schema = {
                "strategy_id": pl.String,
                "strategy_type": pl.String,
                "symbol": pl.String,
                "status": pl.String,
                "entry_date": pl.Datetime,
                "exit_date": pl.Datetime,
                "entry_price": pl.Float64,
                "exit_price": pl.Float64,
                "quantity": pl.Int32,
                "delta": pl.Float64,
                "gamma": pl.Float64,
                "theta": pl.Float64,
                "vega": pl.Float64,
                "unrealized_pnl": pl.Float64,
                "realized_pnl": pl.Float64,
                "timestamp": pl.Datetime,
            }
            df = pl.DataFrame(schema)
            write_deltalake(self.table_path, df, mode="overwrite", schema=schema)

    def get_latest(self) -> pl.DataFrame:
        """Get latest positions."""
        dt = DeltaTable(self.table_path)
        return dt.to_polars()

    def get_at_version(self, version: int) -> pl.DataFrame:
        """Time travel to specific version."""
        dt = DeltaTable(self.table_path, version=version)
        return dt.to_polars()

    def get_at_time(self, timestamp: str) -> pl.DataFrame:
        """Time travel to specific timestamp."""
        dt = DeltaTable(self.table_path)
        dt.as_at_datetime(timestamp)
        return dt.to_polars()

    def append(self, df: pl.DataFrame) -> None:
        """Append new positions (batch write to avoid small files problem)."""
        write_deltalake(
            self.table_path,
            df,
            mode="append",
            partition_by=["symbol"]
        )

    def update_position(self, strategy_id: str, updates: dict) -> None:
        """Update specific position fields."""
        dt = DeltaTable(self.table_path)
        # Merge updates - Delta Lake handles this
        # (Implementation depends on deltalake merge support)
        pass  # Placeholder - full implementation would use merge

    def get_by_symbol(self, symbol: str) -> pl.DataFrame:
        """Get positions for specific symbol."""
        dt = DeltaTable(self.table_path)
        df = dt.to_polars()
        return df.filter(pl.col("symbol") == symbol)

    def get_open_positions(self) -> pl.DataFrame:
        """Get all open positions."""
        dt = DeltaTable(self.table_path)
        df = dt.to_polars()
        return df.filter(pl.col("status") == "open")
```

**File: src/v6/data/repositories/__init__.py**
```python
from .positions import PositionsRepository

__all__ = ["PositionsRepository"]
```

**Why repository pattern:**
- Encapsulates Delta Lake operations
- Provides clean API for position data access
- Makes testing easier (can mock repository)
- Follows separation of concerns

**Pattern from research:** Use write_deltalake() for writes, DeltaTable() for reads
  </action>
  <verify>
    PositionsRepository can be imported from src.v6.data.repositories
    PositionsRepository().get_latest() returns DataFrame with correct schema
    PositionsRepository().get_at_version(0) works
    PositionsRepository().get_by_symbol("SPY") filters correctly
  </verify>
  <done>
    PositionsRepository class created with Delta Lake operations
    Repository pattern encapsulates data access
    Methods for CRUD operations and time-travel
  </done>
</task>

</tasks>

<verification>
Before declaring plan complete:
- [ ] All 4 Delta Lake tables exist with correct schemas
- [ ] Delta Lake tables are partitioned by symbol (NOT timestamp)
- [ ] Time-travel works: version query and timestamp query both function
- [ ] PositionsRepository provides clean API for data access
- [ ] Repository methods are tested (get_latest, get_at_version, append, get_by_symbol)
</verification>

<success_criteria>
- All tasks completed
- Delta Lake schema designed for options trading (positions, legs, Greeks, transactions)
- Tables use proper partitioning (by symbol) to avoid small files problem
- Repository layer provides clean API for data access
- Time-travel queries work correctly
- Ready for next plan (IB connection manager)
</success_criteria>

<output>
After completion, create `v6/.planning/phases/1-architecture-infrastructure/1-02-SUMMARY.md`:

# Phase 1 Plan 2: Delta Lake Schema Summary

**Implemented Delta Lake data foundation with ACID transactions and time-travel for options trading analytics.**

## Accomplishments

- Created 4 Delta Lake tables: positions/, legs/, greeks/, transactions/
- Designed schemas for options trading data (strategies, legs, Greeks, executions)
- Implemented partitioning by symbol (NOT timestamp - critical for performance)
- Created PositionsRepository with repository pattern
- Time-travel queries working (version-based and timestamp-based)

## Files Created/Modified

- `src/v6/data/lake/positions/` - Delta Lake table for strategy positions
- `src/v6/data/lake/legs/` - Delta Lake table for option legs
- `src/v6/data/lake/greeks/` - Delta Lake table for Greeks snapshots
- `src/v6/data/lake/transactions/` - Delta Lake table for trade executions
- `src/v6/data/repositories/__init__.py` - Repository package
- `src/v6/data/repositories/positions.py` - Positions repository class

## Decisions Made

- **Partition by symbol**: Low cardinality, avoids small files problem (Pitfall 6 from research)
- **Repository pattern**: Encapsulates Delta Lake operations, clean API
- **Time-travel support**: Version and timestamp-based queries for analytics
- **Batch writes**: Repository batches writes to avoid creating thousands of small files (Pitfall 1)

## Issues Encountered

None

## Next Step

Ready for 01-03-PLAN.md (IB connection manager)
</output>
