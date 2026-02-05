"""
Dashboard Components Package

This package contains reusable UI components for the dashboard.
Components are widgets that can be shared across multiple pages.
"""

from v6.system_monitor.dashboard.components.alert_card import (
    alert_card,
    alert_list as alert_table,
    severity_badge as alert_severity_badge,
    status_badge as alert_status_badge,
)
from v6.system_monitor.dashboard.components.alert_list import alert_list_view
from v6.system_monitor.dashboard.components.metric_card import metric_card
from v6.system_monitor.dashboard.components.status_badge import status_badge

__all__ = [
    "alert_card",
    "alert_table",
    "alert_list_view",
    "alert_severity_badge",
    "alert_status_badge",
    "status_badge",
    "metric_card",
]
