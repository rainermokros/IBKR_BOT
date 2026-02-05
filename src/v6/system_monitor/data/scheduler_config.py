"""
Scheduler Configuration Delta Lake Table

Stores all task schedules in Delta Lake for dashboard editing.

Schema:
- task_name: Unique identifier
- description: Human-readable description
- script_path: Python script to execute
- enabled: Whether task is active
- frequency: once, hourly, 5min, 15min, daily, weekly
- schedule_time: HH:MM format (for daily/weekly)
- market_phase: pre_market, market_open, post_market, any
- require_market_open: Must market be open
- priority: Execution order (lower = higher priority)
- max_retries: Retry attempts
- timeout_seconds: Max execution time
- created_at: Timestamp when created
- updated_at: Timestamp when last modified
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import polars as pl
from deltalake import DeltaTable, write_deltalake
from loguru import logger


@dataclass
class SchedulerTask:
    """Scheduled task configuration."""
    task_name: str
    description: str
    script_path: str
    enabled: bool = True
    frequency: str = "once"  # once, hourly, 5min, 15min, daily, weekly
    schedule_time: Optional[str] = None  # HH:MM format
    market_phase: str = "any"  # pre_market, market_open, post_market, any
    require_market_open: bool = False
    priority: int = 100  # Lower = higher priority
    max_retries: int = 2
    timeout_seconds: int = 600

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "task_name": self.task_name,
            "description": self.description,
            "script_path": self.script_path,
            "enabled": self.enabled,
            "frequency": self.frequency,
            "schedule_time": self.schedule_time,
            "market_phase": self.market_phase,
            "require_market_open": self.require_market_open,
            "priority": self.priority,
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }


class SchedulerConfigTable:
    """
    Delta Lake table for scheduler configuration.

    All task schedules are stored here and can be edited via dashboard.
    """

    def __init__(self, table_path: str = "data/lake/scheduler_config"):
        """Initialize scheduler config table."""
        self.table_path = Path(table_path)
        self._ensure_table_exists()

    def _ensure_table_exists(self) -> None:
        """Create table if it doesn't exist."""
        if DeltaTable.is_deltatable(str(self.table_path)):
            return

        schema = pl.Schema({
            'task_name': pl.String,
            'description': pl.String,
            'script_path': pl.String,
            'enabled': pl.Boolean,
            'frequency': pl.String,  # once, hourly, 5min, 15min, daily, weekly
            'schedule_time': pl.String,  # HH:MM format or null
            'market_phase': pl.String,  # pre_market, market_open, post_market, any
            'require_market_open': pl.Boolean,
            'priority': pl.Int32,
            'max_retries': pl.Int32,
            'timeout_seconds': pl.Int32,
            'created_at': pl.Datetime("us"),
            'updated_at': pl.Datetime("us"),
        })

        empty_df = pl.DataFrame(schema=schema)
        write_deltalake(
            str(self.table_path),
            empty_df.limit(0),
            mode="overwrite",
        )

        logger.info(f"✓ Created scheduler config table: {self.table_path}")

        # Load default tasks
        self._load_default_tasks()

    def _load_default_tasks(self) -> None:
        """Load default task schedule."""
        default_tasks = [
            # Pre-Market Tasks (Before 9:30 AM ET)
            SchedulerTask(
                task_name="load_historical_data",
                description="Load historical market data from IB Gateway",
                script_path="scripts/load_historical_data.py",
                enabled=True,
                frequency="daily",
                schedule_time="08:00",  # 8:00 AM ET
                market_phase="pre_market",
                priority=10,
                max_retries=2,
                timeout_seconds=1200,
            ),
            SchedulerTask(
                task_name="validate_ib_connection",
                description="Verify IB Gateway is ready",
                script_path="scripts/validate_ib_connection.py",
                enabled=True,
                frequency="daily",
                schedule_time="08:45",  # 8:45 AM ET
                market_phase="pre_market",
                priority=20,
                max_retries=1,
                timeout_seconds=60,
            ),

            # Market Hours Tasks (9:30 AM - 4:00 PM ET)
            SchedulerTask(
                task_name="collect_option_data",
                description="Collect option chain snapshots",
                script_path="scripts/collect_option_snapshots.py",
                enabled=True,
                frequency="5min",
                market_phase="market_open",
                priority=30,
                max_retries=2,
                timeout_seconds=300,
            ),
            SchedulerTask(
                task_name="collect_futures_data",
                description="Collect futures snapshots",
                script_path="scripts/collect_futures_snapshots.py",
                enabled=True,
                frequency="5min",
                market_phase="market_open",
                priority=31,
                max_retries=2,
                timeout_seconds=60,
            ),
            SchedulerTask(
                task_name="backfill_option_snapshots",
                description="Backfill missed option data collections",
                script_path="scripts/backfill_option_snapshots.py",
                enabled=True,
                frequency="10min",
                market_phase="market_open",
                priority=32,
                max_retries=1,
                timeout_seconds=300,
            ),

            # Post-Market Tasks (After 4:00 PM ET)
            SchedulerTask(
                task_name="calculate_daily_statistics",
                description="Calculate end-of-day statistics",
                script_path="scripts/calculate_daily_statistics.py",
                enabled=True,
                frequency="daily",
                schedule_time="16:30",  # 4:30 PM ET
                market_phase="post_market",
                priority=40,
                max_retries=2,
                timeout_seconds=600,
            ),
            SchedulerTask(
                task_name="validate_data_quality",
                description="Data quality checks",
                script_path="scripts/validate_data_quality.py",
                enabled=True,
                frequency="daily",
                schedule_time="18:00",  # 6:00 PM ET
                market_phase="post_market",
                priority=50,
                max_retries=1,
                timeout_seconds=120,
            ),

            # Weekly/Maintenance Tasks
            SchedulerTask(
                task_name="audit_data_integrity",
                description="Weekly data audit",
                script_path="scripts/audit_data_integrity.py",
                enabled=True,
                frequency="weekly",
                schedule_time="10:00",  # 10:00 AM ET
                market_phase="any",
                priority=90,
                max_retries=1,
                timeout_seconds=300,
            ),
            SchedulerTask(
                task_name="health_check",
                description="System health check",
                script_path="scripts/health_check.py",
                enabled=True,
                frequency="hourly",
                market_phase="any",
                priority=100,
                max_retries=1,
                timeout_seconds=60,
            ),
            # Position Sync (7/24)
            SchedulerTask(
                task_name="position_sync",
                description="Sync IB positions to Delta Lake",
                script_path="scripts/sync_positions.py",
                enabled=True,
                frequency="5min",
                market_phase="any",
                priority=15,  # High priority - runs frequently
                max_retries=2,
                timeout_seconds=60,
            ),
        ]

        # Write default tasks
        tasks_data = [task.to_dict() for task in default_tasks]
        df = pl.DataFrame(tasks_data)
        write_deltalake(str(self.table_path), df, mode="append")

        logger.info(f"✓ Loaded {len(default_tasks)} default tasks")

    def get_table(self) -> DeltaTable:
        """Get DeltaTable instance."""
        return DeltaTable(str(self.table_path))

    def get_all_tasks(self) -> pl.DataFrame:
        """Get all tasks ordered by priority."""
        dt = self.get_table()
        df = pl.from_pandas(dt.to_pandas())
        return df.sort("priority")

    def get_enabled_tasks(self) -> pl.DataFrame:
        """Get only enabled tasks."""
        dt = self.get_table()
        df = pl.from_pandas(dt.to_pandas())
        return df.filter(pl.col("enabled") == True).sort("priority")

    def update_task(self, task_name: str, updates: dict) -> bool:
        """
        Update a task configuration.

        Args:
            task_name: Task to update
            updates: Dictionary of fields to update

        Returns:
            True if successful
        """
        try:
            dt = self.get_table()
            df = pl.from_pandas(dt.to_pandas())

            # Find the task
            task_filter = pl.col("task_name") == task_name
            existing = df.filter(task_filter)

            if len(existing) == 0:
                logger.error(f"Task not found: {task_name}")
                return False

            # Update fields
            updates["updated_at"] = datetime.now()

            # Delete old row
            df_filtered = df.filter(~task_filter)

            # Update and append
            updated_task = existing.with_columns(**{
                k: pl.lit(v) for k, v in updates.items()
            })

            # Write back
            write_deltalake(str(self.table_path), df_filtered, mode="overwrite")
            write_deltalake(str(self.table_path), updated_task, mode="append")

            logger.info(f"✓ Updated task: {task_name}")
            return True

        except Exception as e:
            logger.error(f"✗ Failed to update task {task_name}: {e}")
            return False

    def enable_task(self, task_name: str) -> bool:
        """Enable a task."""
        return self.update_task(task_name, {"enabled": True})

    def disable_task(self, task_name: str) -> bool:
        """Disable a task."""
        return self.update_task(task_name, {"enabled": False})

    def set_schedule_time(self, task_name: str, schedule_time: str) -> bool:
        """Set task schedule time (HH:MM format)."""
        return self.update_task(task_name, {"schedule_time": schedule_time})

    def set_frequency(self, task_name: str, frequency: str) -> bool:
        """Set task frequency."""
        valid_freqs = ["once", "hourly", "5min", "15min", "daily", "weekly"]
        if frequency not in valid_freqs:
            logger.error(f"Invalid frequency: {frequency}. Must be one of {valid_freqs}")
            return False
        return self.update_task(task_name, {"frequency": frequency})
