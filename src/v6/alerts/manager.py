"""
Alert Manager with Delta Lake Persistence

This module provides the AlertManager class for generating, persisting,
and managing alerts from decision rules.

Key patterns:
- Delta Lake for persistence (from Phase 2)
- Decision → Alert mapping based on action and urgency
- Async design for consistency with Phase 2
- Polars for efficient querying

Alert lifecycle:
1. Decision rules trigger → AlertManager.create_alert()
2. Alert persisted to Delta Lake
3. Alert can be acknowledged, resolved, or dismissed
4. Alerts can be queried by symbol, status, type, severity
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import polars as pl
from deltalake import DeltaTable, write_deltalake
from loguru import logger

from src.v6.alerts.models import (
    Alert,
    AlertQuery,
    AlertSeverity,
    AlertStatus,
    AlertType,
    generate_alert_id,
)
from src.v6.decisions.models import Decision, DecisionAction, Urgency


class AlertManager:
    """
    Manage alert generation, persistence, and queries.

    **Delta Lake Persistence:**
    - All alerts persisted to Delta Lake table
    - Schema matching Alert model
    - Supports time-travel queries

    **Decision → Alert Mapping:**
    - CLOSE + IMMEDIATE → CRITICAL + IMMEDIATE
    - CLOSE + HIGH → WARNING + HIGH
    - ROLL → INFO + NORMAL
    - HOLD → No alert (skip)

    **Alert Lifecycle:**
    - ACTIVE: Default state when created
    - ACKNOWLEDGED: User has seen the alert
    - RESOLVED: Alert has been resolved
    - DISMISSED: Alert has been dismissed

    Attributes:
        table_path: Path to Delta Lake table
        _table: DeltaTable instance

    Example:
        ```python
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

    def __init__(self, delta_lake_path: str = "data/lake/alerts"):
        """
        Initialize alert manager.

        Args:
            delta_lake_path: Path to Delta Lake table (default: data/lake/alerts)
        """
        self.table_path = Path(delta_lake_path)
        self._table: Optional[DeltaTable] = None

    async def initialize(self) -> None:
        """
        Initialize alert manager and create Delta Lake table if needed.

        Creates table with schema matching Alert model if it doesn't exist.
        """
        if DeltaTable.is_deltatable(str(self.table_path)):
            self._table = DeltaTable(str(self.table_path))
            logger.info(f"✓ Loaded existing Delta Lake table: {self.table_path}")
            return

        # Create table with schema matching Alert model
        # Use PyArrow schema for proper Delta Lake compatibility
        import pyarrow as pa
        schema = pa.schema([
            ('alert_id', pa.string()),
            ('type', pa.string()),
            ('severity', pa.string()),
            ('status', pa.string()),
            ('title', pa.string()),
            ('message', pa.string()),
            ('rule', pa.string()),
            ('symbol', pa.string()),
            ('strategy_id', pa.int64()),
            ('metadata', pa.string()),
            ('created_at', pa.timestamp('us')),
            ('acknowledged_at', pa.timestamp('us')),
            ('resolved_at', pa.timestamp('us')),
        ])

        # Create empty table with PyArrow schema
        table = pa.Table.from_pylist([], schema=schema)
        write_deltalake(
            str(self.table_path),
            table,
            mode="overwrite",
        )

        self._table = DeltaTable(str(self.table_path))
        logger.info(f"✓ Created Delta Lake table: {self.table_path}")

    async def create_alert(
        self,
        decision: Decision,
        snapshot: Optional[Any] = None
    ) -> Optional[Alert]:
        """
        Create alert from decision.

        Maps Decision to Alert based on action and urgency:
        - CLOSE + IMMEDIATE → AlertType.CRITICAL, severity=IMMEDIATE
        - CLOSE + HIGH → AlertType.WARNING, severity=HIGH
        - CLOSE + NORMAL → AlertType.WARNING, severity=NORMAL
        - ROLL → AlertType.INFO, severity=NORMAL
        - HOLD → No alert (skip)

        Args:
            decision: Decision from DecisionEngine
            snapshot: Optional position snapshot (for symbol, strategy_id)

        Returns:
            Created Alert, or None if decision.action == HOLD
        """
        # Skip HOLD decisions
        if decision.action == DecisionAction.HOLD:
            logger.debug("Skipping alert creation for HOLD decision")
            return None

        # Map decision to alert type and severity
        alert_type, alert_severity = self._map_decision_to_alert(decision)

        # Extract symbol and strategy_id from snapshot if available
        symbol = None
        strategy_id = None
        if snapshot is not None:
            symbol = getattr(snapshot, 'symbol', None)
            strategy_id = getattr(snapshot, 'strategy_id', None)

        # Generate alert
        alert = Alert(
            alert_id=generate_alert_id(),
            type=alert_type,
            severity=alert_severity,
            status=AlertStatus.ACTIVE,
            title=self._generate_title(decision),
            message=decision.reason,
            rule=decision.rule,
            symbol=symbol,
            strategy_id=strategy_id,
            metadata=decision.metadata.copy(),
            created_at=datetime.now(),
        )

        # Persist to Delta Lake
        await self._write_alert(alert)

        logger.info(
            f"✓ Created alert: {alert.alert_id[:8]}... "
            f"({alert.type.value}, {alert.severity.value}, {alert.status.value})"
        )

        return alert

    def _map_decision_to_alert(self, decision: Decision) -> tuple[AlertType, AlertSeverity]:
        """
        Map decision to alert type and severity.

        Mapping:
        - CLOSE + IMMEDIATE → CRITICAL, IMMEDIATE
        - CLOSE + HIGH → WARNING, HIGH
        - CLOSE + NORMAL → WARNING, NORMAL
        - ROLL → INFO, NORMAL

        Args:
            decision: Decision to map

        Returns:
            Tuple of (AlertType, AlertSeverity)
        """
        # Handle CLOSE actions
        if decision.action == DecisionAction.CLOSE:
            if decision.urgency == Urgency.IMMEDIATE:
                return (AlertType.CRITICAL, AlertSeverity.IMMEDIATE)
            elif decision.urgency == Urgency.HIGH:
                return (AlertType.WARNING, AlertSeverity.HIGH)
            else:
                return (AlertType.WARNING, AlertSeverity.NORMAL)

        # Handle ROLL actions
        if decision.action == DecisionAction.ROLL:
            return (AlertType.INFO, AlertSeverity.NORMAL)

        # Handle other actions (ADJUST, HEDGE, REDUCE)
        if decision.urgency == Urgency.IMMEDIATE:
            return (AlertType.WARNING, AlertSeverity.IMMEDIATE)
        elif decision.urgency == Urgency.HIGH:
            return (AlertType.INFO, AlertSeverity.HIGH)
        else:
            return (AlertType.INFO, AlertSeverity.NORMAL)

    def _generate_title(self, decision: Decision) -> str:
        """
        Generate alert title from decision.

        Args:
            decision: Decision to generate title from

        Returns:
            Short title string
        """
        action_map = {
            DecisionAction.CLOSE: "Close Position",
            DecisionAction.ROLL: "Roll Position",
            DecisionAction.ADJUST: "Adjust Position",
            DecisionAction.HEDGE: "Hedge Position",
            DecisionAction.REDUCE: "Reduce Position",
        }

        action_str = action_map.get(decision.action, decision.action.value.title())
        return f"{action_str}: {decision.rule}"

    async def acknowledge_alert(self, alert_id: str) -> Alert:
        """
        Acknowledge an alert.

        Updates alert status to ACKNOWLEDGED and sets acknowledged_at timestamp.

        Args:
            alert_id: Alert ID to acknowledge

        Returns:
            Updated Alert

        Raises:
            ValueError: If alert not found
        """
        # Find alert
        alerts = await self.query_alerts(
            AlertQuery(limit=1000)
        )
        alert = next((a for a in alerts if a.alert_id == alert_id), None)

        if alert is None:
            raise ValueError(f"Alert not found: {alert_id}")

        # Update alert
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_at = datetime.now()

        # Write updated alert to Delta Lake (append new version)
        await self._write_alert(alert)

        logger.info(f"✓ Acknowledged alert: {alert_id[:8]}...")

        return alert

    async def resolve_alert(self, alert_id: str) -> Alert:
        """
        Resolve an alert.

        Updates alert status to RESOLVED and sets resolved_at timestamp.

        Args:
            alert_id: Alert ID to resolve

        Returns:
            Updated Alert

        Raises:
            ValueError: If alert not found
        """
        # Find alert
        alerts = await self.query_alerts(
            AlertQuery(limit=1000)
        )
        alert = next((a for a in alerts if a.alert_id == alert_id), None)

        if alert is None:
            raise ValueError(f"Alert not found: {alert_id}")

        # Update alert
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now()

        # Write updated alert to Delta Lake (append new version)
        await self._write_alert(alert)

        logger.info(f"✓ Resolved alert: {alert_id[:8]}...")

        return alert

    async def dismiss_alert(self, alert_id: str) -> Alert:
        """
        Dismiss an alert.

        Updates alert status to DISMISSED and sets resolved_at timestamp.

        Args:
            alert_id: Alert ID to dismiss

        Returns:
            Updated Alert

        Raises:
            ValueError: If alert not found
        """
        # Find alert
        alerts = await self.query_alerts(
            AlertQuery(limit=1000)
        )
        alert = next((a for a in alerts if a.alert_id == alert_id), None)

        if alert is None:
            raise ValueError(f"Alert not found: {alert_id}")

        # Update alert
        alert.status = AlertStatus.DISMISSED
        alert.resolved_at = datetime.now()

        # Write updated alert to Delta Lake (append new version)
        await self._write_alert(alert)

        logger.info(f"✓ Dismissed alert: {alert_id[:8]}...")

        return alert

    async def query_alerts(self, query: AlertQuery) -> list[Alert]:
        """
        Query alerts from Delta Lake.

        Filters by query fields using Polars for efficiency.

        Args:
            query: AlertQuery with filters

        Returns:
            List of Alert objects matching query
        """
        # Read all alerts from Delta Lake
        df = pl.from_pandas(self._table.to_pandas())

        # Apply filters
        if query.symbol:
            df = df.filter(pl.col("symbol") == query.symbol)

        if query.strategy_id:
            df = df.filter(pl.col("strategy_id") == query.strategy_id)

        if query.status:
            df = df.filter(pl.col("status") == query.status.value)

        if query.type:
            df = df.filter(pl.col("type") == query.type.value)

        if query.severity:
            df = df.filter(pl.col("severity") == query.severity.value)

        if query.start_time:
            df = df.filter(pl.col("created_at") >= query.start_time)

        if query.end_time:
            df = df.filter(pl.col("created_at") <= query.end_time)

        # Sort by created_at descending (newest first)
        df = df.sort("created_at", descending=True)

        # Limit results
        df = df.head(query.limit)

        # Convert to Alert objects
        alerts = []
        for row in df.iter_rows(named=True):
            alert = Alert.from_dict(row)
            alerts.append(alert)

        logger.debug(f"Query returned {len(alerts)} alerts")

        return alerts

    async def get_active_alerts(self) -> list[Alert]:
        """
        Get all active alerts.

        Returns:
            List of Alert objects with status=ACTIVE
        """
        query = AlertQuery(status=AlertStatus.ACTIVE, limit=1000)
        return await self.query_alerts(query)

    async def get_alert_count(self, status: Optional[AlertStatus] = None) -> int:
        """
        Get count of alerts by status.

        Args:
            status: Optional status to filter by (None = all alerts)

        Returns:
            Count of alerts
        """
        # Read all alerts from Delta Lake
        df = pl.from_pandas(self._table.to_pandas())

        # Filter by status if specified
        if status:
            df = df.filter(pl.col("status") == status.value)

        count = len(df)
        logger.debug(f"Alert count (status={status.value if status else 'all'}): {count}")

        return count

    async def _write_alert(self, alert: Alert) -> None:
        """
        Write alert to Delta Lake.

        Args:
            alert: Alert to write
        """
        # Convert to dict
        alert_dict = alert.to_dict()

        # Create PyArrow Table directly (avoid Polars None/Null issues)
        import pyarrow as pa

        # Create arrays for each field
        data = {
            'alert_id': [alert_dict['alert_id']],
            'type': [alert_dict['type']],
            'severity': [alert_dict['severity']],
            'status': [alert_dict['status']],
            'title': [alert_dict['title']],
            'message': [alert_dict['message']],
            'rule': [alert_dict['rule']],
            'symbol': [alert_dict['symbol']],
            'strategy_id': [alert_dict['strategy_id']],
            'metadata': [alert_dict['metadata']],
            'created_at': [alert_dict['created_at']],
            'acknowledged_at': [alert_dict['acknowledged_at']],
            'resolved_at': [alert_dict['resolved_at']],
        }

        # Create PyArrow table
        table = pa.table(data)

        # Append to Delta Lake
        write_deltalake(
            str(self.table_path),
            table,
            mode="append",
        )

        # Refresh the table to see new data
        if self._table:
            self._table.update_incremental()

        logger.debug(f"Wrote alert to Delta Lake: {alert.alert_id[:8]}...")
