#!/usr/bin/env python
"""
Add Backfill Worker to Scheduler

Adds the backfill_option_snapshots task to the existing scheduler config table.
Run this once to enable backfill processing.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import polars as pl
from deltalake import write_deltalake, DeltaTable
from datetime import datetime
from loguru import logger

from v6.system_monitor.data.scheduler_config import SchedulerConfigTable, SchedulerTask


def main():
    """Add backfill task to scheduler config table."""

    logger.info("=" * 70)
    logger.info("ADDING BACKFILL WORKER TO SCHEDULER")
    logger.info("=" * 70)

    config = SchedulerConfigTable()

    # Check if already exists
    tasks = config.get_all_tasks()
    existing = tasks.filter(pl.col("task_name") == "backfill_option_snapshots")

    if len(existing) > 0:
        logger.warning("⚠️  Backfill task already exists in scheduler")
        logger.info("Updating task...")

        # Update existing task
        config.update_task(
            "backfill_option_snapshots",
            {
                "enabled": True,
                "frequency": "10min",
                "market_phase": "market_open",
                "priority": 32,
                "max_retries": 1,
                "timeout_seconds": 300
            }
        )

        logger.success("✓ Backfill task updated in scheduler")
    else:
        logger.info("Adding new backfill task to scheduler...")

        # Create new task
        task_data = {
            "task_name": "backfill_option_snapshots",
            "description": "Backfill missed option data collections",
            "script_path": "scripts/backfill_option_snapshots.py",
            "enabled": True,
            "frequency": "10min",
            "schedule_time": None,  # No specific time
            "market_phase": "market_open",
            "require_market_open": True,
            "priority": 32,
            "max_retries": 1,
            "timeout_seconds": 300,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        # Create DataFrame with explicit schema
        df = pl.DataFrame({
            "task_name": ["backfill_option_snapshots"],
            "description": ["Backfill missed option data collections"],
            "script_path": ["scripts/backfill_option_snapshots.py"],
            "enabled": [True],
            "frequency": ["10min"],
            "schedule_time": [None],
            "market_phase": ["market_open"],
            "require_market_open": [True],
            "priority": [32],
            "max_retries": [1],
            "timeout_seconds": [300],
            "created_at": [datetime.now()],
            "updated_at": [datetime.now()],
        })

        # Add to table
        write_deltalake(
            str(config.table_path),
            df,
            mode="append"
        )

        logger.success("✓ Backfill task added to scheduler")

    # Verify
    logger.info("\nVerifying task was added...")
    tasks = config.get_all_tasks()
    backfill = tasks.filter(pl.col("task_name") == "backfill_option_snapshots")

    if len(backfill) > 0:
        logger.success("✅ VERIFICATION SUCCESSFUL")
        logger.info(f"Task config:")
        logger.info(f"  - Name: {backfill['task_name'][0]}")
        logger.info(f"  - Description: {backfill['description'][0]}")
        logger.info(f"  - Script: {backfill['script_path'][0]}")
        logger.info(f"  - Frequency: {backfill['frequency'][0]}")
        logger.info(f"  - Priority: {backfill['priority'][0]}")
        logger.info(f"  - Enabled: {backfill['enabled'][0]}")
        logger.info("\nThe backfill worker will now run every 10 minutes during market hours.")
        logger.info("Monitor logs: tail -f logs/scheduler/scheduler.log")
        return 0
    else:
        logger.error("❌ VERIFICATION FAILED - Task not found after adding")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
