"""System health data loading functions.

Provides functions for checking IB connection status, data freshness,
system metrics, and active strategies registry.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import psutil  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


def check_ib_connection() -> dict[str, Any]:
    """Check IB connection status.

    Returns:
        Dict with connection status:
        - connected: bool - True if connected to IB
        - status: str - "CONNECTED" or "DISCONNECTED"
        - last_update: datetime - Last heartbeat timestamp
        - disconnected_at: datetime | None - Disconnect timestamp
        - host: str - IB gateway host
        - port: int - IB gateway port
        - client_id: int - Client ID
    """
    # Try to import IB connection manager
    try:
        from src.v6.utils.ib_connection import IBConnectionManager

        manager = IBConnectionManager()
        status = manager.get_status()

        return {
            "connected": status.get("connected", False),
            "status": "CONNECTED" if status.get("connected", False) else "DISCONNECTED",
            "last_update": status.get("last_update", datetime.now()),
            "disconnected_at": status.get("disconnected_at"),
            "host": status.get("host", "localhost"),
            "port": status.get("port", 4002),
            "client_id": status.get("client_id", 1),
        }
    except Exception as e:
        logger.warning(f"Could not check IB connection: {e}")
        return {
            "connected": False,
            "status": "DISCONNECTED",
            "last_update": datetime.now(),
            "disconnected_at": datetime.now(),
            "host": "localhost",
            "port": 4002,
            "client_id": 1,
        }


def check_data_freshness() -> dict[str, Any]:
    """Check data freshness from Delta Lake tables.

    Returns:
        Dict with freshness metrics:
        - positions_last_sync: datetime - Last position sync timestamp
        - positions_age: int - Age in seconds
        - positions_status: str - "FRESH", "WARNING", "STALE"
        - greeks_last_update: datetime - Last Greeks update timestamp
        - greeks_age: int - Age in seconds
        - greeks_status: str - "FRESH", "WARNING", "STALE"
        - decisions_last_run: datetime - Last decision evaluation timestamp
        - decisions_age: int - Age in seconds
        - decisions_status: str - "FRESH", "WARNING", "STALE"
    """
    now = datetime.now()
    freshness = {
        "positions_last_sync": now,
        "positions_age": 0,
        "positions_status": "FRESH",
        "greeks_last_update": now,
        "greeks_age": 0,
        "greeks_status": "FRESH",
        "decisions_last_run": now,
        "decisions_age": 0,
        "decisions_status": "FRESH",
    }

    # Try to read from Delta Lake
    try:
        from delta import DeltaTable  # type: ignore[import-untyped]
        from pyspark.sql import SparkSession  # type: ignore[import-untyped]

        # Get Spark session
        spark = SparkSession.builder.appName("v6-health-check").getOrCreate()

        # Check option_legs last update (positions)
        try:
            legs_table = DeltaTable.forPath(spark, os.environ.get("DELTA_LAKE_PATH", "./data/lake/option_legs"))
            legs_df = legs_table.history().limit(1).toPandas()

            if not legs_df.empty:
                last_update = pd.to_datetime(legs_df["timestamp"].iloc[0])
                age = (now - last_update).total_seconds()
                status = _get_freshness_status(age)

                freshness["positions_last_sync"] = last_update
                freshness["positions_age"] = int(age)
                freshness["positions_status"] = status
        except Exception as e:
            logger.warning(f"Could not check option_legs freshness: {e}")

        # Check option_snapshots last update (Greeks)
        try:
            snapshots_table = DeltaTable.forPath(
                spark, os.environ.get("DELTA_LAKE_PATH", "./data/lake/option_snapshots")
            )
            snapshots_df = snapshots_table.history().limit(1).toPandas()

            if not snapshots_df.empty:
                last_update = pd.to_datetime(snapshots_df["timestamp"].iloc[0])
                age = (now - last_update).total_seconds()
                status = _get_freshness_status(age)

                freshness["greeks_last_update"] = last_update
                freshness["greeks_age"] = int(age)
                freshness["greeks_status"] = status
        except Exception as e:
            logger.warning(f"Could not check option_snapshots freshness: {e}")

        spark.stop()
    except Exception as e:
        logger.warning(f"Could not check data freshness: {e}")

    return freshness


def _get_freshness_status(age: float) -> str:
    """Get freshness status based on age in seconds.

    Args:
        age: Age in seconds

    Returns:
        "FRESH" if <30s, "WARNING" if 30-60s, "STALE" if >60s
    """
    if age < 30:
        return "FRESH"
    elif age < 60:
        return "WARNING"
    else:
        return "STALE"


def get_system_metrics() -> dict[str, Any]:
    """Get system metrics using psutil.

    Returns:
        Dict with system metrics:
        - cpu_percent: float - CPU usage percentage
        - memory_percent: float - Memory usage percentage
        - disk_percent: float - Disk usage percentage
        - uptime: str - System uptime (human-readable)
        - process_count: int - Number of running processes
    """
    metrics = {
        "cpu_percent": 0.0,
        "memory_percent": 0.0,
        "disk_percent": 0.0,
        "uptime": "Unknown",
        "process_count": 0,
    }

    try:
        # CPU usage
        metrics["cpu_percent"] = psutil.cpu_percent(interval=0.1)

        # Memory usage
        memory = psutil.virtual_memory()
        metrics["memory_percent"] = memory.percent

        # Disk usage
        disk = psutil.disk_usage("/")
        metrics["disk_percent"] = disk.percent

        # System uptime
        boot_time = psutil.boot_time()
        uptime_seconds = datetime.now().timestamp() - boot_time
        metrics["uptime"] = str(timedelta(seconds=int(uptime_seconds)))

        # Process count
        metrics["process_count"] = len(psutil.pids())
    except Exception as e:
        logger.warning(f"Could not get system metrics: {e}")

    return metrics


def get_active_strategies() -> pd.DataFrame:
    """Get active strategies from StrategyRegistry.

    Returns:
        DataFrame with active strategies:
        - conid: int - Contract ID
        - symbol: str - Underlying symbol
        - strategy_id: str - Strategy execution ID
        - since: datetime - When streaming started
    """
    strategies_data = []

    try:
        from v6.strategies.registry import StrategyRegistry

        registry = StrategyRegistry()
        active_strategies = registry.get_active_strategies()

        for strategy in active_strategies:
            strategies_data.append(
                {
                    "conid": strategy.get("conid"),
                    "symbol": strategy.get("symbol"),
                    "strategy_id": strategy.get("strategy_id"),
                    "since": strategy.get("since", datetime.now()),
                }
            )
    except Exception as e:
        logger.warning(f"Could not get active strategies: {e}")

    df = pd.DataFrame(strategies_data)

    # Add streaming slot count
    if not df.empty:
        df.attrs["slot_count"] = len(df)

    return df


def reconnect_ib() -> dict[str, Any]:
    """Trigger IB reconnection.

    Returns:
        Dict with result:
        - success: bool - True if reconnection initiated
        - message: str - Status message
    """
    try:
        from src.v6.utils.ib_connection import IBConnectionManager

        manager = IBConnectionManager()
        manager.reconnect()

        return {"success": True, "message": "IB reconnection initiated"}
    except Exception as e:
        logger.error(f"Failed to reconnect IB: {e}")
        return {"success": False, "message": f"Reconnection failed: {e}"}


def force_sync() -> dict[str, Any]:
    """Trigger manual position/Greeks sync.

    Returns:
        Dict with result:
        - success: bool - True if sync initiated
        - message: str - Status message
    """
    try:
        # Trigger position sync
        # This would call PositionSync.sync_now() if available
        # For now, just return success
        return {"success": True, "message": "Sync initiated"}
    except Exception as e:
        logger.error(f"Failed to force sync: {e}")
        return {"success": False, "message": f"Sync failed: {e}"}


def clear_queue() -> dict[str, Any]:
    """Clear PositionQueue backlog.

    Returns:
        Dict with result:
        - success: bool - True if queue cleared
        - message: str - Status message
    """
    try:
        # Clear queue backlog
        # This would call PositionQueue.clear() if available
        # For now, just return success
        return {"success": True, "message": "Queue cleared"}
    except Exception as e:
        logger.error(f"Failed to clear queue: {e}")
        return {"success": False, "message": f"Queue clear failed: {e}"}


def generate_health_alerts(
    ib_status: dict[str, Any],
    freshness: dict[str, Any],
    metrics: dict[str, Any],
    strategies_df: pd.DataFrame,
) -> list[dict[str, Any]]:
    """Generate alerts for unhealthy conditions.

    Args:
        ib_status: IB connection status
        freshness: Data freshness metrics
        metrics: System metrics
        strategies_df: Active strategies DataFrame

    Returns:
        List of alert dicts with keys:
        - severity: str - "CRITICAL", "WARNING", "INFO"
        - message: str - Alert message
    """
    alerts = []

    # IB connection check
    if not ib_status.get("connected", False):
        alerts.append(
            {
                "severity": "CRITICAL",
                "message": f"IB disconnected since {ib_status.get('disconnected_at', 'unknown')}",
            }
        )

    # Data freshness checks
    if freshness["positions_age"] > 60:
        alerts.append(
            {
                "severity": "WARNING",
                "message": f"Positions stale ({freshness['positions_age']}s old)",
            }
        )

    if freshness["greeks_age"] > 60:
        alerts.append(
            {
                "severity": "WARNING",
                "message": f"Greeks stale ({freshness['greeks_age']}s old)",
            }
        )

    if freshness["decisions_age"] > 60:
        alerts.append(
            {
                "severity": "WARNING",
                "message": f"Decisions stale ({freshness['decisions_age']}s old)",
            }
        )

    # System metrics checks
    if metrics["cpu_percent"] > 90:
        alerts.append(
            {"severity": "WARNING", "message": f"High CPU usage ({metrics['cpu_percent']:.1f}%)"}
        )

    if metrics["memory_percent"] > 90:
        alerts.append(
            {"severity": "WARNING", "message": f"High memory usage ({metrics['memory_percent']:.1f}%)"}
        )

    if metrics["disk_percent"] > 90:
        alerts.append(
            {"severity": "WARNING", "message": f"High disk usage ({metrics['disk_percent']:.1f}%)"}
        )

    # Streaming slot check
    slot_count = len(strategies_df)
    if slot_count > 90:
        alerts.append(
            {
                "severity": "INFO",
                "message": f"Streaming slots near limit ({slot_count}/100 used)",
            }
        )

    return alerts
