"""
V6 Monitoring Package

This package provides monitoring and alerting capabilities for the v6 trading system including:
- Data quality monitoring with anomaly detection
- Alert routing to Slack/email
- System health monitoring
"""

from .alerts import (
    Alert,
    AlertManager,
)
from .data_quality import (
    DataQualityMonitor,
    DataQualityReport,
)

__all__ = [
    # Alerts
    "Alert",
    "AlertManager",
    # Data quality
    "DataQualityMonitor",
    "DataQualityReport",
]
