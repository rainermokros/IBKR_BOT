"""
Alert data loading functions for dashboard.

This module provides functions to load alerts from AlertManager/Delta Lake
for display in the monitoring dashboard.

Key patterns:
- Streamlit caching with TTL (60s for alerts)
- Pandas DataFrames for easy display
- Filter by severity, status, time range
- Summary metrics calculation
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st
from deltalake import DeltaTable
from loguru import logger

from v6.system_monitor.alert_system.models import AlertSeverity, AlertStatus


@st.cache_data(ttl=60)
def load_alerts(
    delta_lake_path: str = "data/lake/alerts"
) -> pd.DataFrame:
    """
    Load alerts from Delta Lake with caching.

    Args:
        delta_lake_path: Path to Delta Lake alerts table

    Returns:
        DataFrame with all alert fields, or empty DataFrame if table doesn't exist
    """
    table_path = Path(delta_lake_path)

    # Check if table exists
    if not DeltaTable.is_deltatable(str(table_path)):
        logger.warning(f"Alert table does not exist: {table_path}")
        return pd.DataFrame(columns=[
            "alert_id", "type", "severity", "status", "title",
            "message", "rule", "symbol", "strategy_id", "metadata",
            "created_at", "acknowledged_at", "resolved_at"
        ])

    # Load table
    try:
        table = DeltaTable(str(table_path))
        df = table.to_pandas()

        # Calculate derived columns
        if not df.empty:
            df["created_at"] = pd.to_datetime(df["created_at"])
            df["acknowledged_at"] = pd.to_datetime(df["acknowledged_at"], errors="coerce")
            df["resolved_at"] = pd.to_datetime(df["resolved_at"], errors="coerce")

            # Calculate age (time since creation)
            now = pd.Timestamp.now()
            df["age_seconds"] = (now - df["created_at"]).dt.total_seconds()
            df["age_minutes"] = (df["age_seconds"] / 60).round(1)

            # Calculate response time (acknowledged_at - created_at)
            df["response_time_seconds"] = (
                df["acknowledged_at"] - df["created_at"]
            ).dt.total_seconds().round(1)

        logger.debug(f"Loaded {len(df)} alerts from Delta Lake")

        return df

    except Exception as e:
        logger.error(f"Failed to load alerts: {e}")
        return pd.DataFrame(columns=[
            "alert_id", "type", "severity", "status", "title",
            "message", "rule", "symbol", "strategy_id", "metadata",
            "created_at", "acknowledged_at", "resolved_at"
        ])


def get_alert_summary(alerts_df: pd.DataFrame) -> dict:
    """
    Calculate alert summary metrics.

    Args:
        alerts_df: DataFrame from load_alerts()

    Returns:
        Dict with summary metrics (active_count, resolved_today, avg_response_time)
    """
    if alerts_df.empty:
        return {
            "active_count": 0,
            "acknowledged_count": 0,
            "resolved_today": 0,
            "avg_response_time": 0,
            "critical_count": 0,
            "warning_count": 0,
            "info_count": 0,
        }

    # Active alerts (status = ACTIVE)
    active_count = len(alerts_df[alerts_df["status"] == "ACTIVE"])

    # Acknowledged alerts
    acknowledged_count = len(alerts_df[alerts_df["status"] == "ACKNOWLEDGED"])

    # Resolved today
    today = datetime.now().date()
    resolved_today_df = alerts_df[
        (alerts_df["status"] == "RESOLVED") &
        (alerts_df["resolved_at"].dt.date == today)
    ]
    resolved_today = len(resolved_today_df)

    # Average response time (for acknowledged alerts)
    acknowledged_df = alerts_df[alerts_df["status"].isin(["ACKNOWLEDGED", "RESOLVED", "DISMISSED"])]
    if not acknowledged_df.empty and "response_time_seconds" in acknowledged_df.columns:
        avg_response_time = acknowledged_df["response_time_seconds"].mean()
        # Convert to minutes
        avg_response_time = (avg_response_time / 60).round(1)
    else:
        avg_response_time = 0

    # Count by severity
    critical_count = len(alerts_df[
        (alerts_df["severity"] == "IMMEDIATE") &
        (alerts_df["status"] == "ACTIVE")
    ])
    warning_count = len(alerts_df[
        (alerts_df["severity"].isin(["HIGH", "NORMAL"])) &
        (alerts_df["status"] == "ACTIVE")
    ])
    info_count = len(alerts_df[
        (alerts_df["severity"] == "LOW") &
        (alerts_df["status"] == "ACTIVE")
    ])

    return {
        "active_count": active_count,
        "acknowledged_count": acknowledged_count,
        "resolved_today": resolved_today,
        "avg_response_time": avg_response_time,
        "critical_count": critical_count,
        "warning_count": warning_count,
        "info_count": info_count,
    }


def filter_alerts(
    alerts_df: pd.DataFrame,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> pd.DataFrame:
    """
    Filter alerts by severity, status, and time range.

    Args:
        alerts_df: DataFrame from load_alerts()
        severity: Filter by severity (IMMEDIATE, HIGH, NORMAL, LOW, or None for all)
        status: Filter by status (ACTIVE, ACKNOWLEDGED, RESOLVED, DISMISSED, or None for all)
        start_time: Filter by created_at >= start_time
        end_time: Filter by created_at <= end_time

    Returns:
        Filtered DataFrame
    """
    filtered_df = alerts_df.copy()

    # Filter by severity
    if severity:
        filtered_df = filtered_df[filtered_df["severity"] == severity]

    # Filter by status
    if status:
        filtered_df = filtered_df[filtered_df["status"] == status]

    # Filter by time range
    if start_time:
        filtered_df = filtered_df[filtered_df["created_at"] >= start_time]

    if end_time:
        filtered_df = filtered_df[filtered_df["created_at"] <= end_time]

    return filtered_df


async def acknowledge_alert_dashboard(
    alert_id: str,
    delta_lake_path: str = "data/lake/alerts"
) -> bool:
    """
    Acknowledge an alert via AlertManager.

    This function is called from the dashboard when user clicks "Acknowledge".

    Args:
        alert_id: Alert ID to acknowledge
        delta_lake_path: Path to Delta Lake alerts table

    Returns:
        True if successful, False otherwise
    """
    try:
        from v6.system_monitor.alert_system.manager import AlertManager

        # Initialize AlertManager
        manager = AlertManager(delta_lake_path=delta_lake_path)
        await manager.initialize()

        # Acknowledge alert
        await manager.acknowledge_alert(alert_id)

        # Clear cache to force refresh
        load_alerts.clear()

        logger.info(f"Dashboard: Acknowledged alert {alert_id[:8]}...")
        return True

    except Exception as e:
        logger.error(f"Failed to acknowledge alert: {e}")
        return False


async def resolve_alert_dashboard(
    alert_id: str,
    delta_lake_path: str = "data/lake/alerts"
) -> bool:
    """
    Resolve an alert via AlertManager.

    This function is called from the dashboard when user clicks "Resolve".

    Args:
        alert_id: Alert ID to resolve
        delta_lake_path: Path to Delta Lake alerts table

    Returns:
        True if successful, False otherwise
    """
    try:
        from v6.system_monitor.alert_system.manager import AlertManager

        # Initialize AlertManager
        manager = AlertManager(delta_lake_path=delta_lake_path)
        await manager.initialize()

        # Resolve alert
        await manager.resolve_alert(alert_id)

        # Clear cache to force refresh
        load_alerts.clear()

        logger.info(f"Dashboard: Resolved alert {alert_id[:8]}...")
        return True

    except Exception as e:
        logger.error(f"Failed to resolve alert: {e}")
        return False
