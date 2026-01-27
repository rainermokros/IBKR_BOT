"""
Unit tests for AlertManager

Tests alert creation, persistence, querying, and lifecycle management.
"""

from datetime import datetime

import pytest

from src.v6.alerts.manager import AlertManager
from src.v6.alerts.models import (
    AlertQuery,
    AlertSeverity,
    AlertStatus,
    AlertType,
)
from src.v6.decisions.models import Decision, DecisionAction, Urgency


@pytest.fixture
async def alert_manager():
    """Create AlertManager instance for testing."""
    manager = AlertManager("data/lake/test_alerts")
    await manager.initialize()

    # Clean table before each test
    dt = manager._table
    df = dt.to_pandas()
    if len(df) > 0:
        # Delete all rows by filtering on impossible condition
        import polars as pl
        empty_df = pl.DataFrame(df)
        empty_df = empty_df.filter(pl.lit(False))
        from deltalake import write_deltalake
        write_deltalake(str(manager.table_path), empty_df, mode="overwrite")

    yield manager

    # Cleanup
    import shutil
    if manager.table_path.exists():
        shutil.rmtree(manager.table_path)


@pytest.mark.asyncio
async def test_create_alert_from_decision(alert_manager):
    """Test creating alert from CLOSE decision creates CRITICAL type."""
    decision = Decision(
        action=DecisionAction.CLOSE,
        reason="Market crash detected",
        rule="catastrophe_protection",
        urgency=Urgency.IMMEDIATE,
        metadata={"market_change": -0.05},
    )

    alert = await alert_manager.create_alert(decision)

    assert alert is not None
    assert alert.type == AlertType.CRITICAL
    assert alert.severity == AlertSeverity.IMMEDIATE
    assert alert.status == AlertStatus.ACTIVE
    assert alert.title == "Close Position: catastrophe_protection"
    assert alert.message == "Market crash detected"
    assert alert.rule == "catastrophe_protection"
    assert alert.metadata == {"market_change": -0.05}


@pytest.mark.asyncio
async def test_roll_decision_creates_info_alert(alert_manager):
    """Test creating alert from ROLL decision creates INFO type."""
    decision = Decision(
        action=DecisionAction.ROLL,
        reason="DTE at 23, rolling to 45 DTE",
        rule="dte_roll",
        urgency=Urgency.NORMAL,
        metadata={"current_dte": 23, "roll_to_dte": 45},
    )

    alert = await alert_manager.create_alert(decision)

    assert alert is not None
    assert alert.type == AlertType.INFO
    assert alert.severity == AlertSeverity.NORMAL
    assert alert.status == AlertStatus.ACTIVE
    assert alert.title == "Roll Position: dte_roll"


@pytest.mark.asyncio
async def test_hold_decision_skips_alert(alert_manager):
    """Test creating alert from HOLD decision returns None."""
    decision = Decision(
        action=DecisionAction.HOLD,
        reason="No rule triggered",
        rule="none",
        urgency=Urgency.NORMAL,
        metadata={"rules_evaluated": 12},
    )

    alert = await alert_manager.create_alert(decision)

    assert alert is None


@pytest.mark.asyncio
async def test_acknowledge_alert(alert_manager):
    """Test acknowledging an alert updates status and timestamp."""
    decision = Decision(
        action=DecisionAction.CLOSE,
        reason="Test alert",
        rule="test_rule",
        urgency=Urgency.IMMEDIATE,
    )

    alert = await alert_manager.create_alert(decision)
    assert alert.status == AlertStatus.ACTIVE
    assert alert.acknowledged_at is None

    # Acknowledge the alert
    acknowledged_alert = await alert_manager.acknowledge_alert(alert.alert_id)

    assert acknowledged_alert.status == AlertStatus.ACKNOWLEDGED
    assert acknowledged_alert.acknowledged_at is not None
    assert isinstance(acknowledged_alert.acknowledged_at, datetime)


@pytest.mark.asyncio
async def test_query_alerts_by_type(alert_manager):
    """Test querying alerts by type filter."""
    # Create alerts of different types
    decisions = [
        Decision(
            action=DecisionAction.CLOSE,
            reason="Test alert 1",
            rule="test_rule",
            urgency=Urgency.IMMEDIATE,  # CRITICAL
        ),
        Decision(
            action=DecisionAction.CLOSE,
            reason="Test alert 2",
            rule="test_rule",
            urgency=Urgency.IMMEDIATE,  # CRITICAL
        ),
        Decision(
            action=DecisionAction.ROLL,
            reason="Test alert 3",
            rule="test_rule",
            urgency=Urgency.NORMAL,  # INFO
        ),
    ]

    for decision in decisions:
        await alert_manager.create_alert(decision)

    # Query for CRITICAL type alerts
    query = AlertQuery(type=AlertType.CRITICAL, limit=10)
    critical_alerts = await alert_manager.query_alerts(query)

    # Should return 2 CRITICAL alerts
    assert len(critical_alerts) >= 2


@pytest.mark.asyncio
async def test_query_alerts_by_status(alert_manager):
    """Test querying alerts by status filter."""
    # Create an alert
    decision = Decision(
        action=DecisionAction.CLOSE,
        reason="Test alert",
        rule="test_rule",
        urgency=Urgency.IMMEDIATE,
    )

    alert = await alert_manager.create_alert(decision)
    await alert_manager.resolve_alert(alert.alert_id)

    # Query for ACTIVE alerts
    query = AlertQuery(status=AlertStatus.ACTIVE, limit=10)
    active_alerts = await alert_manager.query_alerts(query)

    # Should not include resolved alert
    assert all(a.status == AlertStatus.ACTIVE for a in active_alerts)


@pytest.mark.asyncio
async def test_get_active_alerts(alert_manager):
    """Test getting only active alerts."""
    # Create multiple alerts
    decisions = [
        Decision(
            action=DecisionAction.CLOSE,
            reason=f"Test alert {i}",
            rule="test_rule",
            urgency=Urgency.IMMEDIATE,
        )
        for i in range(3)
    ]

    alert_ids = []
    for decision in decisions:
        alert = await alert_manager.create_alert(decision)
        alert_ids.append(alert.alert_id)

    # Resolve one alert
    await alert_manager.resolve_alert(alert_ids[0])

    # Get active alerts
    active_alerts = await alert_manager.get_active_alerts()

    # Should have 2 active alerts
    assert len(active_alerts) >= 2
    assert all(a.status == AlertStatus.ACTIVE for a in active_alerts)


@pytest.mark.asyncio
async def test_metadata_serialization(alert_manager):
    """Test that metadata dict is correctly serialized and deserialized."""
    metadata = {
        "delta": 0.28,
        "limit": 0.30,
        "position_value": 1500.50,
        "nested": {"key": "value"},
    }

    decision = Decision(
        action=DecisionAction.CLOSE,
        reason="Delta limit approaching",
        rule="delta_risk",
        urgency=Urgency.HIGH,
        metadata=metadata,
    )

    alert = await alert_manager.create_alert(decision)

    # Query the alert back
    query = AlertQuery(limit=10)
    alerts = await alert_manager.query_alerts(query)
    retrieved_alert = [a for a in alerts if a.alert_id == alert.alert_id][0]

    # Metadata should match
    assert retrieved_alert.metadata == metadata


@pytest.mark.asyncio
async def test_delta_lake_persistence(alert_manager):
    """Test that alerts persist correctly to Delta Lake."""
    decision = Decision(
        action=DecisionAction.CLOSE,
        reason="Test persistence",
        rule="test_rule",
        urgency=Urgency.IMMEDIATE,
        metadata={"test_key": "test_value"},
    )

    # Create alert
    alert = await alert_manager.create_alert(decision)
    alert_id = alert.alert_id

    # Query from Delta Lake
    query = AlertQuery(limit=10)
    alerts = await alert_manager.query_alerts(query)

    # Find the alert
    retrieved_alert = [a for a in alerts if a.alert_id == alert_id][0]

    # Verify all fields match
    assert retrieved_alert.alert_id == alert_id
    assert retrieved_alert.type == AlertType.CRITICAL
    assert retrieved_alert.severity == AlertSeverity.IMMEDIATE
    assert retrieved_alert.status == AlertStatus.ACTIVE
    assert retrieved_alert.title == alert.title
    assert retrieved_alert.message == alert.message
    assert retrieved_alert.rule == alert.rule
    assert retrieved_alert.metadata == alert.metadata


@pytest.mark.asyncio
async def test_resolve_alert(alert_manager):
    """Test resolving an alert updates status and timestamp."""
    decision = Decision(
        action=DecisionAction.CLOSE,
        reason="Test alert",
        rule="test_rule",
        urgency=Urgency.IMMEDIATE,
    )

    alert = await alert_manager.create_alert(decision)
    assert alert.status == AlertStatus.ACTIVE
    assert alert.resolved_at is None

    # Resolve the alert
    resolved_alert = await alert_manager.resolve_alert(alert.alert_id)

    assert resolved_alert.status == AlertStatus.RESOLVED
    assert resolved_alert.resolved_at is not None
    assert isinstance(resolved_alert.resolved_at, datetime)


@pytest.mark.asyncio
async def test_dismiss_alert(alert_manager):
    """Test dismissing an alert updates status and timestamp."""
    decision = Decision(
        action=DecisionAction.CLOSE,
        reason="Test alert",
        rule="test_rule",
        urgency=Urgency.IMMEDIATE,
    )

    alert = await alert_manager.create_alert(decision)
    assert alert.status == AlertStatus.ACTIVE
    assert alert.resolved_at is None

    # Dismiss the alert
    dismissed_alert = await alert_manager.dismiss_alert(alert.alert_id)

    assert dismissed_alert.status == AlertStatus.DISMISSED
    assert dismissed_alert.resolved_at is not None
    assert isinstance(dismissed_alert.resolved_at, datetime)


@pytest.mark.asyncio
async def test_get_alert_count(alert_manager):
    """Test getting alert count by status."""
    # Create 3 alerts
    for i in range(3):
        decision = Decision(
            action=DecisionAction.CLOSE,
            reason=f"Test alert {i}",
            rule="test_rule",
            urgency=Urgency.IMMEDIATE,
        )
        await alert_manager.create_alert(decision)

    # Get total count
    total_count = await alert_manager.get_alert_count()
    assert total_count >= 3

    # Get active count
    active_count = await alert_manager.get_alert_count(AlertStatus.ACTIVE)
    assert active_count >= 3


@pytest.mark.asyncio
async def test_decision_to_alert_mapping_close_immediate(alert_manager):
    """Test CLOSE + IMMEDIATE maps to CRITICAL + IMMEDIATE."""
    decision = Decision(
        action=DecisionAction.CLOSE,
        reason="Immediate close",
        rule="test_rule",
        urgency=Urgency.IMMEDIATE,
    )

    alert = await alert_manager.create_alert(decision)

    assert alert.type == AlertType.CRITICAL
    assert alert.severity == AlertSeverity.IMMEDIATE


@pytest.mark.asyncio
async def test_decision_to_alert_mapping_close_high(alert_manager):
    """Test CLOSE + HIGH maps to WARNING + HIGH."""
    decision = Decision(
        action=DecisionAction.CLOSE,
        reason="High priority close",
        rule="test_rule",
        urgency=Urgency.HIGH,
    )

    alert = await alert_manager.create_alert(decision)

    assert alert.type == AlertType.WARNING
    assert alert.severity == AlertSeverity.HIGH


@pytest.mark.asyncio
async def test_decision_to_alert_mapping_roll(alert_manager):
    """Test ROLL maps to INFO + NORMAL."""
    decision = Decision(
        action=DecisionAction.ROLL,
        reason="Roll position",
        rule="test_rule",
        urgency=Urgency.NORMAL,
    )

    alert = await alert_manager.create_alert(decision)

    assert alert.type == AlertType.INFO
    assert alert.severity == AlertSeverity.NORMAL
