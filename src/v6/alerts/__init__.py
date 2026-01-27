"""
Alert Management System

This package provides alert generation and management for decision rules.

Exports:
- AlertManager: Main class for creating and managing alerts
- Alert, AlertType, AlertSeverity, AlertStatus: Alert models
- AlertQuery: Query model for filtering alerts
- generate_alert_id: Helper function for generating alert IDs

Example:
    ```python
    from src.v6.alerts import AlertManager, AlertQuery, AlertStatus

    # Initialize
    manager = AlertManager()
    await manager.initialize()

    # Create alert from decision
    alert = await manager.create_alert(decision, snapshot)

    # Query alerts
    alerts = await manager.query_alerts(
        AlertQuery(symbol='SPY', status=AlertStatus.ACTIVE)
    )
    ```
"""

from src.v6.alerts.manager import AlertManager
from src.v6.alerts.models import (
    Alert,
    AlertQuery,
    AlertSeverity,
    AlertStatus,
    AlertType,
    generate_alert_id,
)

__all__ = [
    "AlertManager",
    "Alert",
    "AlertType",
    "AlertSeverity",
    "AlertStatus",
    "AlertQuery",
    "generate_alert_id",
]
