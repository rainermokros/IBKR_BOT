"""
V6 Unified Scheduler - Delta Lake Configuration Version

This is THE ONLY script in crontab. It reads task schedules from
Delta Lake table and handles all NYSE specifics (holidays, hours).

Crontab Entry:
* * * * * cd /home/bigballs/project/bot/v6 && python -m v6.scheduler.scheduler

Configuration:
- Edit via dashboard: data/lake/scheduler_config table
- Or directly in code: v6/data/scheduler_config.py

Features:
- NYSE calendar aware (trading days, holidays)
- Market hours aware (pre-market, market open, post-market)
- Reads schedule from Delta Lake table
- Executes tasks at configured times
- Comprehensive logging
"""

import asyncio
import signal
import subprocess
import sys
from datetime import datetime, time
from pathlib import Path
from typing import Optional

from loguru import logger

from v6.system_monitor.scheduler.nyse_calendar import NYSECalendar
from v6.system_monitor.data.scheduler_config import SchedulerConfigTable


class UnifiedScheduler:
    """
    Unified scheduler that reads from Delta Lake config table.

    Handles all NYSE specifics:
    - Trading days (excludes weekends/holidays)
    - Market phases (pre-market, market open, post-market)
    - Task scheduling based on config table
    """

    def __init__(self):
        """Initialize scheduler."""
        self.nyse = NYSECalendar()
        self.running = True
        self.last_run = {}  # Track when each task last ran

        # Load configuration from Delta Lake
        self.config_table = SchedulerConfigTable()

        # Setup logging
        self._setup_logging()

        logger.info("=" * 70)
        logger.info("V6 UNIFIED SCHEDULER - DELTA LAKE CONFIG")
        logger.info("=" * 70)

    def _setup_logging(self):
        """Configure logging."""
        log_dir = Path("logs/scheduler")
        log_dir.mkdir(parents=True, exist_ok=True)

        logger.remove()
        logger.add(
            sys.stderr,
            level="INFO",
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>"
        )
        logger.add(
            log_dir / "scheduler.log",
            rotation="10 MB",
            level="DEBUG",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"
        )

    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info("Received shutdown signal")
        self.running = False

    def should_run_task(
        self,
        task: dict,
        current_time: datetime,
        current_phase: str
    ) -> bool:
        """
        Check if a task should run now.

        Args:
            task: Task configuration dict
            current_time: Current datetime
            current_phase: Current market phase

        Returns:
            True if task should run
        """
        # Check if enabled
        if not task.get("enabled", False):
            return False

        # Check trading day requirement
        if not self.nyse.is_trading_day():
            logger.debug("Not a trading day - skipping all tasks")
            return False

        # Check market open requirement
        if task.get("require_market_open", False):
            if not self.nyse.is_market_open():
                return False

        # Check market phase
        task_phase = task.get("market_phase", "any")
        if task_phase != "any" and task_phase != current_phase:
            return False

        # Check if already ran recently
        task_name = task["task_name"]
        if task_name in self.last_run:
            last_run = self.last_run[task_name]
            minutes_since = (current_time - last_run).total_seconds() / 60

            # Get interval based on frequency
            frequency = task.get("frequency", "once")
            interval_minutes = self._get_interval_minutes(frequency)

            # For daily/weekly tasks, check if already ran today
            if frequency in ["daily", "weekly", "once"]:
                # Check if last run was on the same calendar day
                if last_run.date() == current_time.date():
                    logger.debug(f"  {task_name} already ran today at {last_run.strftime('%H:%M:%S')}")
                    return False

            if interval_minutes and minutes_since < interval_minutes:
                return False

        # Check specific schedule time (for daily/weekly tasks)
        schedule_time = task.get("schedule_time")
        if schedule_time:
            try:
                hour, minute = map(int, schedule_time.split(":"))
                schedule_datetime = current_time.replace(
                    hour=hour,
                    minute=minute,
                    second=0,
                    microsecond=0
                )

                # Allow 2 minute window
                time_diff = abs((current_time - schedule_datetime).total_seconds() / 60)
                if time_diff > 2:
                    return False

            except (ValueError, AttributeError) as e:
                logger.warning(f"Invalid schedule_time for {task_name}: {schedule_time}")

        return True

    def _get_interval_minutes(self, frequency: str) -> Optional[int]:
        """Get interval in minutes from frequency string."""
        intervals = {
            "once": None,  # Runs once per day based on schedule_time
            "hourly": 60,
            "5min": 5,
            "15min": 15,
            "daily": None,  # Uses schedule_time
            "weekly": None,  # Uses schedule_time
        }
        return intervals.get(frequency)

    def execute_task(self, task: dict) -> bool:
        """
        Execute a task script.

        Args:
            task: Task configuration dict

        Returns:
            True if successful
        """
        task_name = task["task_name"]
        script_path = task["script_path"]
        timeout = task.get("timeout_seconds", 600)

        logger.info(f"→ Executing: {task_name}")
        logger.info(f"  Script: {script_path}")
        logger.info(f"  Timeout: {timeout}s")

        try:
            # Run script directly (not as module) - scripts are standalone files
            script_full_path = Path("/home/bigballs/project/bot/v6") / script_path

            if not script_full_path.exists():
                logger.warning(f"  ⚠ Script file not found: {script_full_path}")
                logger.warning(f"  Skipping (may not be implemented yet)")
                return True  # Don't count as failure

            result = subprocess.run(
                [sys.executable, str(script_full_path)],
                cwd="/home/bigballs/project/bot/v6",
                timeout=timeout,
                capture_output=True,
                text=True,
            )

            # Log output
            if result.stdout:
                logger.info(f"  Output: {result.stdout[:200]}")

            if result.stderr:
                # Filter out common warnings
                errors = result.stderr[:500]
                if "No module named" not in errors:
                    logger.warning(f"  Errors: {errors}")

            if result.returncode == 0:
                logger.info(f"  ✓ Success")
                self.last_run[task_name] = datetime.now()
                return True
            else:
                # Check if it's just a missing script
                if "No module named" in result.stderr:
                    logger.warning(f"  ⚠ Script not found: {script_path}")
                    logger.warning(f"  Skipping (may not be implemented yet)")
                    return True  # Don't count as failure
                else:
                    logger.error(f"  ✗ Failed (exit code: {result.returncode})")
                    return False

        except subprocess.TimeoutExpired:
            logger.error(f"  ✗ Timeout after {timeout}s")
            return False
        except Exception as e:
            logger.error(f"  ✗ Error: {e}")
            return False

    def run_cycle(self):
        """Run one scheduler cycle (called every minute by cron)."""
        current_time = datetime.now()
        current_phase = self.nyse.get_market_phase()

        logger.info("=" * 70)
        logger.info(f"SCHEDULER CHECK - {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 70)
        logger.info(f"Day: {current_time.strftime('%Y-%m-%d')} (Trading: {self.nyse.is_trading_day()})")
        logger.info(f"Time: {current_time.strftime('%H:%M:%S')} (Phase: {current_phase})")
        logger.info("-" * 70)

        # Load tasks from Delta Lake
        try:
            tasks_df = self.config_table.get_enabled_tasks()

            if len(tasks_df) == 0:
                logger.warning("No enabled tasks found")
                return

            tasks = tasks_df.to_dicts()

            # Check each task
            for task in tasks:
                if self.should_run_task(task, current_time, current_phase):
                    logger.info(f"Running task: {task['task_name']}")
                    self.execute_task(task)

        except Exception as e:
            logger.error(f"✗ Error loading tasks: {e}")

    def run_forever(self):
        """
        Run scheduler continuously (for testing).

        In production, use cron to run this script every minute.
        """
        # Setup signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        logger.info("Scheduler started in continuous mode")
        logger.info("Press Ctrl+C to stop")

        while self.running:
            self.run_cycle()

            # Wait until next minute
            now = datetime.now()
            next_minute = (now.second // 60 + 1) * 60
            sleep_seconds = 60 - now.second

            if sleep_seconds > 0:
                logger.debug(f"Sleeping {sleep_seconds}s until next check...")
                import time
                time.sleep(sleep_seconds)


def main():
    """Main entry point."""
    scheduler = UnifiedScheduler()

    # Check if running in cron or interactive mode
    if sys.stdin.isatty():
        # Interactive mode - run continuously
        scheduler.run_forever()
    else:
        # Cron mode - run once and exit
        scheduler.run_cycle()


if __name__ == "__main__":
    main()
