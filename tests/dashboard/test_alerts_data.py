"""
Tests for alert data loading functions.
"""

import pandas as pd
import pytest
from datetime import datetime, timedelta

from v6.system_monitor.dashboard.data.alerts import (
    filter_alerts,
    get_alert_summary,
    load_alerts,
)


def test_load_alerts_returns_dataframe():
    """Test that load_alerts returns a pandas DataFrame"""
    df = load_alerts()
    assert isinstance(df, pd.DataFrame)


def test_load_alerts_has_correct_columns():
    """Test that load_alerts returns DataFrame with correct columns"""
    df = load_alerts()

    expected_columns = [
        "alert_id", "type", "severity", "status", "title",
        "message", "rule", "symbol", "strategy_id", "metadata",
        "created_at", "acknowledged_at", "resolved_at"
    ]

    for col in expected_columns:
        assert col in df.columns


def test_load_alerts_handles_empty_table():
    """Test that load_alerts handles non-existent table gracefully"""
    df = load_alerts(delta_lake_path="nonexistent_path")
    assert df.empty
    assert len(df) == 0


def test_get_alert_summary_empty_df():
    """Test get_alert_summary with empty DataFrame"""
    empty_df = pd.DataFrame()
    summary = get_alert_summary(empty_df)

    assert summary["active_count"] == 0
    assert summary["acknowledged_count"] == 0
    assert summary["resolved_today"] == 0
    assert summary["avg_response_time"] == 0
    assert summary["critical_count"] == 0
    assert summary["warning_count"] == 0
    assert summary["info_count"] == 0


def test_get_alert_summary_with_data():
    """Test get_alert_summary with sample data"""
    now = datetime.now()

    data = {
        "status": ["ACTIVE", "ACKNOWLEDGED", "RESOLVED", "ACTIVE"],
        "severity": ["IMMEDIATE", "HIGH", "NORMAL", "LOW"],
        "created_at": [now, now, now, now],
        "acknowledged_at": [None, now, now, None],
        "resolved_at": [None, None, now, None],
    }

    df = pd.DataFrame(data)
    summary = get_alert_summary(df)

    assert summary["active_count"] == 2
    assert summary["acknowledged_count"] == 1  # Only ACKNOWLEDGED status
    assert summary["critical_count"] == 1  # IMMEDIATE + ACTIVE
    assert summary["warning_count"] == 0  # No active HIGH or NORMAL alerts
    assert summary["info_count"] == 1  # LOW + ACTIVE


def test_filter_alerts_by_severity():
    """Test filter_alerts by severity"""
    now = datetime.now()

    data = {
        "severity": ["IMMEDIATE", "HIGH", "NORMAL", "LOW"],
        "status": ["ACTIVE", "ACTIVE", "ACTIVE", "ACTIVE"],
        "created_at": [now, now, now, now],
    }

    df = pd.DataFrame(data)
    filtered = filter_alerts(df, severity="IMMEDIATE")

    assert len(filtered) == 1
    assert filtered.iloc[0]["severity"] == "IMMEDIATE"


def test_filter_alerts_by_status():
    """Test filter_alerts by status"""
    now = datetime.now()

    data = {
        "severity": ["IMMEDIATE", "HIGH", "NORMAL", "LOW"],
        "status": ["ACTIVE", "ACTIVE", "RESOLVED", "ACTIVE"],
        "created_at": [now, now, now, now],
    }

    df = pd.DataFrame(data)
    filtered = filter_alerts(df, status="ACTIVE")

    assert len(filtered) == 3
    assert all(filtered["status"] == "ACTIVE")


def test_filter_alerts_by_time_range():
    """Test filter_alerts by time range"""
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    two_days_ago = now - timedelta(days=2)

    data = {
        "severity": ["IMMEDIATE", "HIGH", "NORMAL"],
        "status": ["ACTIVE", "ACTIVE", "ACTIVE"],
        "created_at": [two_days_ago, yesterday, now],
    }

    df = pd.DataFrame(data)
    filtered = filter_alerts(df, start_time=yesterday)

    assert len(filtered) == 2
    assert all(filtered["created_at"] >= yesterday)


def test_filter_alerts_no_filters():
    """Test filter_alerts with no filters returns all data"""
    now = datetime.now()

    data = {
        "severity": ["IMMEDIATE", "HIGH", "NORMAL"],
        "status": ["ACTIVE", "ACTIVE", "ACTIVE"],
        "created_at": [now, now, now],
    }

    df = pd.DataFrame(data)
    filtered = filter_alerts(df)

    assert len(filtered) == len(df)
