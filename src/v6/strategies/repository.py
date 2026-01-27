"""
Strategy Repository with Delta Lake Persistence

This module provides Delta Lake persistence for strategy executions.
Implements async repository pattern for CRUD operations on strategy executions.

Key patterns:
- Async/await for I/O operations
- Delta Lake for ACID transactions and time-travel
- Protocol-based interfaces (from Phase 3)
- Batch writes to avoid small files problem
"""

import asyncio
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import polars as pl
import pyarrow as pa
from deltalake import DeltaTable, write_deltalake
from loguru import logger

from src.v6.strategies.models import (
    Strategy,
    StrategyExecution,
    LegExecution,
    StrategyType,
    ExecutionStatus,
    LegStatus,
    OptionRight,
    LegAction,
)


class StrategyRepository:
    """
    Repository for strategy executions with Delta Lake persistence.

    Provides async CRUD operations for strategy executions.
    Delta Lake provides ACID transactions and time-travel for analytics.
    """

    def __init__(self, table_path: str = "data/lake/strategy_executions"):
        """
        Initialize repository.

        Args:
            table_path: Path to Delta Lake table (default: data/lake/strategy_executions)
        """
        self.table_path = Path(table_path)
        self._initialized = False

    async def initialize(self) -> None:
        """
        Initialize repository and create Delta Lake table if needed.

        Creates table with proper schema if it doesn't exist.
        """
        if self._initialized:
            return

        # Create table if it doesn't exist
        if not DeltaTable.is_deltatable(str(self.table_path)):
            # Create a sample row with all fields set to establish schema
            # Then use an impossible filter to create empty table with correct schema
            sample_data = {
                'execution_id': ['__placeholder__'],
                'strategy_id': [0],
                'symbol': ['__placeholder__'],
                'strategy_type': ['__placeholder__'],
                'status': ['__placeholder__'],
                'entry_params': ['{}'],
                'entry_time': [datetime.now()],
                'fill_time': [datetime(2000, 1, 1)],  # Use placeholder for nullable timestamp
                'close_time': [datetime(2000, 1, 1)],  # Use placeholder for nullable timestamp
                'legs_json': ['[]'],
            }

            df = pl.DataFrame(sample_data)

            # Filter out the placeholder row to get empty table with schema
            df_empty = df.filter(pl.col('execution_id') == '__impossible__')

            write_deltalake(
                str(self.table_path),
                df_empty,
                mode="overwrite",
            )

            logger.info(f"✓ Created Delta Lake table: {self.table_path}")
        else:
            logger.info(f"✓ Delta Lake table exists: {self.table_path}")

        self._initialized = True

    async def save_execution(self, execution: StrategyExecution) -> None:
        """
        Save a strategy execution to Delta Lake.

        Args:
            execution: StrategyExecution to save

        Raises:
            ValueError: If repository not initialized
        """
        if not self._initialized:
            await self.initialize()

        # Convert legs to JSON
        legs_json = json.dumps([
            {
                'leg_id': leg.leg_id,
                'conid': leg.conid,
                'right': leg.right.value,
                'strike': leg.strike,
                'expiration': leg.expiration.isoformat(),
                'quantity': leg.quantity,
                'action': leg.action.value,
                'status': leg.status.value,
                'fill_price': leg.fill_price,
                'order_id': leg.order_id,
                'fill_time': leg.fill_time.isoformat() if leg.fill_time else None,
            }
            for leg in execution.legs
        ])

        # Convert entry_params to JSON
        entry_params_json = json.dumps(execution.entry_params)

        # Create DataFrame with explicit schema to handle None values properly
        # Use a placeholder datetime for None values to avoid null type issues
        # Use year 2000 as placeholder (easily identifiable)
        fill_time_val = execution.fill_time if execution.fill_time else datetime(2000, 1, 1)
        close_time_val = execution.close_time if execution.close_time else datetime(2000, 1, 1)

        data = {
            'execution_id': [execution.execution_id],
            'strategy_id': [execution.strategy_id],
            'symbol': [execution.symbol],
            'strategy_type': [execution.strategy_type.value],
            'status': [execution.status.value],
            'entry_params': [entry_params_json],
            'entry_time': [execution.entry_time],
            'fill_time': [fill_time_val],
            'close_time': [close_time_val],
            'legs_json': [legs_json],
        }

        df = pl.DataFrame(data)

        # Write to Delta Lake
        write_deltalake(
            str(self.table_path),
            df,
            mode="append"
        )

        logger.info(f"✓ Saved execution {execution.execution_id} to Delta Lake")

    async def get_execution(self, execution_id: str) -> StrategyExecution | None:
        """
        Get a strategy execution by ID.

        Args:
            execution_id: Execution ID to retrieve

        Returns:
            StrategyExecution if found, None otherwise

        Raises:
            ValueError: If repository not initialized
        """
        if not self._initialized:
            await self.initialize()

        dt = DeltaTable(str(self.table_path))
        df = pl.from_pandas(dt.to_pandas())

        # Filter by execution_id
        result = df.filter(pl.col("execution_id") == execution_id)

        if result.is_empty():
            return None

        row = result.row(0, named=True)

        # Parse legs JSON
        legs_data = json.loads(row["legs_json"])
        legs = [
            LegExecution(
                leg_id=leg["leg_id"],
                conid=leg["conid"],
                right=OptionRight[leg["right"]],
                strike=leg["strike"],
                expiration=date.fromisoformat(leg["expiration"]),
                quantity=leg["quantity"],
                action=LegAction[leg["action"]],
                status=LegStatus(leg["status"]),  # Use value lookup
                fill_price=leg["fill_price"],
                order_id=leg["order_id"],
                fill_time=datetime.fromisoformat(leg["fill_time"]) if leg["fill_time"] else None,
            )
            for leg in legs_data
        ]

        # Parse entry_params
        entry_params = json.loads(row["entry_params"])

        # Convert placeholder (year 2000) back to None
        PLACEHOLDER_DATETIME = datetime(2000, 1, 1)
        fill_time_raw = row["fill_time"]
        close_time_raw = row["close_time"]

        # Check if it's the placeholder (within same year to handle any microsecond differences)
        fill_time = fill_time_raw if fill_time_raw and fill_time_raw.year > 2000 else None
        close_time = close_time_raw if close_time_raw and close_time_raw.year > 2000 else None

        # Create execution
        execution = StrategyExecution(
            execution_id=row["execution_id"],
            strategy_id=row["strategy_id"],
            symbol=row["symbol"],
            strategy_type=StrategyType(row["strategy_type"]),  # Use value lookup
            status=ExecutionStatus(row["status"]),  # Use value lookup
            legs=legs,
            entry_params=entry_params,
            entry_time=row["entry_time"],
            fill_time=fill_time,
            close_time=close_time,
        )

        return execution

    async def get_open_strategies(
        self,
        symbol: str | None = None
    ) -> list[StrategyExecution]:
        """
        Get all open strategy executions.

        Args:
            symbol: Optional symbol filter (if None, returns all symbols)

        Returns:
            List of open StrategyExecution objects

        Raises:
            ValueError: If repository not initialized
        """
        if not self._initialized:
            await self.initialize()

        dt = DeltaTable(str(self.table_path))
        df = pl.from_pandas(dt.to_pandas())

        # Filter by status (not closed or failed) - use lowercase since that's how enum values are stored
        result = df.filter(
            ~pl.col("status").is_in(["closed", "failed"])
        )

        # Filter by symbol if provided
        if symbol:
            result = result.filter(pl.col("symbol") == symbol)

        # Convert to list of executions
        executions = []
        for row in result.iter_rows(named=True):
            # Parse legs JSON
            legs_data = json.loads(row["legs_json"])
            legs = [
                LegExecution(
                    leg_id=leg["leg_id"],
                    conid=leg["conid"],
                    right=OptionRight[leg["right"]],
                    strike=leg["strike"],
                    expiration=date.fromisoformat(leg["expiration"]),
                    quantity=leg["quantity"],
                    action=LegAction[leg["action"]],
                    status=LegStatus(leg["status"]),  # Use value lookup
                    fill_price=leg["fill_price"],
                    order_id=leg["order_id"],
                    fill_time=datetime.fromisoformat(leg["fill_time"]) if leg["fill_time"] else None,
                )
                for leg in legs_data
            ]

            # Parse entry_params
            entry_params = json.loads(row["entry_params"])

            # Convert placeholder (year 2000) back to None
            fill_time_raw = row["fill_time"]
            close_time_raw = row["close_time"]

            # Check if it's the placeholder (within same year to handle any microsecond differences)
            fill_time = fill_time_raw if fill_time_raw and fill_time_raw.year > 2000 else None
            close_time = close_time_raw if close_time_raw and close_time_raw.year > 2000 else None

            # Create execution
            execution = StrategyExecution(
                execution_id=row["execution_id"],
                strategy_id=row["strategy_id"],
                symbol=row["symbol"],
                strategy_type=StrategyType(row["strategy_type"]),  # Use value lookup
                status=ExecutionStatus(row["status"]),  # Use value lookup
                legs=legs,
                entry_params=entry_params,
                entry_time=row["entry_time"],
                fill_time=fill_time,
                close_time=close_time,
            )

            executions.append(execution)

        return executions

    async def update_execution_status(
        self,
        execution_id: str,
        status: ExecutionStatus
    ) -> None:
        """
        Update the status of a strategy execution.

        Args:
            execution_id: Execution ID to update
            status: New status

        Raises:
            ValueError: If repository not initialized or execution not found
        """
        if not self._initialized:
            await self.initialize()

        dt = DeltaTable(str(self.table_path))
        df = pl.from_pandas(dt.to_pandas())

        # Find existing execution
        existing = df.filter(pl.col("execution_id") == execution_id)

        if existing.is_empty():
            raise ValueError(f"Execution {execution_id} not found")

        # Update status
        existing = existing.with_columns(
            pl.lit(status.value).alias("status")
        )

        # If status is FILLED, set fill_time to now
        if status == ExecutionStatus.FILLED:
            existing = existing.with_columns(
                pl.lit(datetime.now()).alias("fill_time")
            )

        # Delete old record and write new one (Delta Lake doesn't support UPDATE directly)
        # In production, would use MERGE or partition-level operations
        # For now, we'll overwrite (simple but not optimal for concurrent writes)
        df_updated = df.filter(pl.col("execution_id") != execution_id)
        df_updated = pl.concat([df_updated, existing])

        write_deltalake(
            str(self.table_path),
            df_updated,
            mode="overwrite"
        )

        logger.info(f"✓ Updated execution {execution_id} status to {status.value}")

    async def update_leg_status(
        self,
        leg_id: str,
        status: LegStatus,
        fill_price: float | None = None
    ) -> None:
        """
        Update the status of a leg within an execution.

        Args:
            leg_id: Leg ID to update
            status: New status
            fill_price: Fill price (if status is FILLED)

        Raises:
            ValueError: If repository not initialized or leg not found
        """
        if not self._initialized:
            await self.initialize()

        dt = DeltaTable(str(self.table_path))
        df = pl.from_pandas(dt.to_pandas())

        # Find execution containing this leg
        updated = False
        updated_rows = []

        for row in df.iter_rows(named=True):
            legs_data = json.loads(row["legs_json"])

            # Check if this row contains the leg
            for leg in legs_data:
                if leg["leg_id"] == leg_id:
                    # Update leg status
                    leg["status"] = status.value
                    if fill_price is not None:
                        leg["fill_price"] = fill_price
                    if status == LegStatus.FILLED:
                        leg["fill_time"] = datetime.now().isoformat()

                    updated = True
                    break

            # Update legs_json
            row["legs_json"] = json.dumps(legs_data)
            updated_rows.append(row)

        if not updated:
            raise ValueError(f"Leg {leg_id} not found")

        # Write updated data
        df_updated = pl.DataFrame(updated_rows)
        write_deltalake(
            str(self.table_path),
            df_updated,
            mode="overwrite"
        )

        logger.info(f"✓ Updated leg {leg_id} status to {status.value}")
