#!/usr/bin/env python
"""
Health Check Script

Checks the health of all critical system components and returns
an exit code indicating system status.

Exit codes:
- 0: Healthy
- 1: Degraded (some components unhealthy but system operational)
- 2: Unhealthy (critical components failed)
"""

import asyncio
import sys
from datetime import datetime, time

import httpx
import psutil
from loguru import logger


def check_ib_connection() -> tuple[bool, str]:
    """
    Check IB connection status.

    Returns:
        Tuple of (is_healthy, message)
    """
    try:
        # Try to connect to IB
        from ib_async import IB

        async def check():
            ib = IB()
            try:
                await ib.connectAsync(host="127.0.0.1", port=4002, clientId=999, timeout=5)
                # Successfully connected
                ib.disconnect()
                return True, "IB connection OK"
            except Exception as e:
                return False, f"IB connection failed: {e}"

        result = asyncio.run(check())
        return result
    except Exception as e:
        return False, f"IB check error: {e}"


def is_market_hours() -> bool:
    """
    Check if current time is during market hours (9:30 AM - 4:00 PM ET, weekdays).

    Returns:
        True if during market hours, False otherwise
    """
    now = datetime.now()
    # Weekend check
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False

    # Time check (9:30 AM - 4:00 PM)
    market_open = time(9, 30)
    market_close = time(16, 0)
    current_time = now.time()

    return market_open <= current_time <= market_close


def check_position_sync() -> tuple[bool, str]:
    """
    Check position sync status.

    Returns:
        Tuple of (is_healthy, message)
    """
    try:
        # Check last sync time from Delta Lake
        from deltalake import DeltaTable
        import polars as pl

        delta_path = "data/lake/position_updates"
        if not DeltaTable.is_deltatable(delta_path):
            return True, "Position sync: No data yet (first run)"

        dt = DeltaTable(delta_path)

        # Read the table to get last update
        df = pl.read_delta(delta_path)

        if len(df) == 0:
            return True, "Position sync: No data yet (first run)"

        # Get last timestamp
        last_update = df.select(pl.col("timestamp").max()).item()

        # Calculate lag
        now = datetime.now()
        lag_seconds = (now - last_update).total_seconds()

        # Use different thresholds based on market hours
        if is_market_hours():
            # Stricter during market hours
            ok_threshold = 300  # 5 minutes
            degraded_threshold = 600  # 10 minutes
        else:
            # More lenient during pre/post-market
            ok_threshold = 1800  # 30 minutes
            degraded_threshold = 3600  # 60 minutes

        market_status = "market hours" if is_market_hours() else "pre/post-market"

        if lag_seconds < ok_threshold:
            return True, f"Position sync: OK (lag: {lag_seconds:.0f}s, {market_status})"
        elif lag_seconds < degraded_threshold:
            return False, f"Position sync: Degraded (lag: {lag_seconds:.0f}s, {market_status})"
        else:
            return False, f"Position sync: Failed (lag: {lag_seconds:.0f}s, {market_status})"

    except Exception as e:
        return False, f"Position sync check error: {e}"


def check_dashboard() -> tuple[bool, str]:
    """
    Check dashboard accessibility.

    Returns:
        Tuple of (is_healthy, message)
    """
    try:
        response = httpx.get("http://localhost:8501", timeout=2.0)
        if response.status_code == 200:
            return True, "Dashboard: Accessible"
        else:
            return False, f"Dashboard: HTTP {response.status_code}"
    except Exception as e:
        return False, f"Dashboard check error: {e}"


def check_system_resources() -> tuple[bool, str]:
    """
    Check system resources (disk, memory, CPU).

    Returns:
        Tuple of (is_healthy, message)
    """
    issues = []

    # Check disk space
    disk = psutil.disk_usage("/")
    disk_percent = disk.percent
    if disk_percent > 95:
        issues.append(f"Disk space critical: {disk_percent}% used")
    elif disk_percent > 90:
        issues.append(f"Disk space warning: {disk_percent}% used")

    # Check memory
    memory = psutil.virtual_memory()
    mem_percent = memory.percent
    if mem_percent > 95:
        issues.append(f"Memory critical: {mem_percent}% used")
    elif mem_percent > 90:
        issues.append(f"Memory warning: {mem_percent}% used")

    # Check CPU
    cpu = psutil.cpu_percent(interval=1)
    if cpu > 95:
        issues.append(f"CPU critical: {cpu}% used")
    elif cpu > 90:
        issues.append(f"CPU warning: {cpu}% used")

    if issues:
        return False, "System resources: " + ", ".join(issues)
    else:
        return True, f"System resources: OK (disk: {disk_percent}%, mem: {mem_percent}%, CPU: {cpu}%)"


def main() -> int:
    """
    Main health check entry point.

    Returns:
        Exit code (0=healthy, 1=degraded, 2=unhealthy)
    """
    logger.info("=" * 60)
    logger.info("V6 Trading Bot - Health Check")
    logger.info("=" * 60)

    checks = [
        ("IB Connection", check_ib_connection, True),  # Critical
        ("Position Sync", check_position_sync, True),  # Critical
        ("Dashboard", check_dashboard, False),  # Optional (monitoring only)
        ("System Resources", check_system_resources, True),  # Critical
    ]

    results = []
    optional_results = []
    critical_failures = 0

    for name, check_func, is_critical in checks:
        logger.info(f"Checking {name}...")
        try:
            healthy, message = check_func()

            if healthy:
                logger.success(f"✓ {message}")
                if is_critical:
                    results.append((name, healthy, message))
                else:
                    optional_results.append((name, healthy, message))
            else:
                logger.warning(f"⚠ {message}")
                if is_critical:
                    results.append((name, healthy, message))
                    if name in ["IB Connection"]:
                        critical_failures += 1
                else:
                    optional_results.append((name, healthy, message))
        except Exception as e:
            logger.error(f"✗ {name} check failed: {e}")
            if is_critical:
                results.append((name, False, str(e)))
                critical_failures += 1
            else:
                optional_results.append((name, False, str(e)))

    # Print summary
    logger.info("=" * 60)
    logger.info("Health Check Summary")
    logger.info("=" * 60)

    for name, healthy, message in results:
        status = "✓" if healthy else "✗"
        logger.info(f"{status} {name}: {message}")

    if optional_results:
        logger.info("-" * 60)
        logger.info("Optional Checks (for monitoring only):")
        for name, healthy, message in optional_results:
            status = "✓" if healthy else "✗"
            logger.info(f"{status} {name}: {message}")

    # Determine exit code (based on critical checks only)
    if critical_failures > 0:
        logger.error("Health check: UNHEALTHY (critical failures)")
        return 2
    elif any(not healthy for _, healthy, _ in results):
        logger.warning("Health check: DEGRADED (some issues)")
        return 1
    else:
        logger.success("Health check: HEALTHY")
        return 0


if __name__ == "__main__":
    sys.exit(main())
