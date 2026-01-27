"""
Tests for PositionMonitoringWorkflow Trailing Stop Integration

Tests the integration of trailing stops with the position monitoring workflow.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.v6.decisions.models import Decision, DecisionAction, Urgency
from src.v6.decisions.engine import DecisionEngine
from src.v6.alerts import AlertManager
from src.v6.strategies.repository import StrategyRepository
from src.v6.strategies.models import (
    StrategyType,
    ExecutionStatus,
    LegExecution,
    OptionRight,
    LegAction,
    LegStatus,
)
from src.v6.workflows.monitoring import PositionMonitoringWorkflow
from src.v6.risk import (
    TrailingStopManager,
    TrailingStopConfig,
    TrailingStopAction,
)

from datetime import date, datetime


@pytest.fixture
def mock_strategy_repo():
    """Create mock strategy repository."""
    repo = AsyncMock(spec=StrategyRepository)
    return repo


@pytest.fixture
def mock_decision_engine():
    """Create mock decision engine."""
    engine = AsyncMock(spec=DecisionEngine)
    return engine


@pytest.fixture
def mock_alert_manager():
    """Create mock alert manager."""
    manager = MagicMock(spec=AlertManager)
    return manager


@pytest.fixture
def trailing_stop_manager():
    """Create trailing stop manager."""
    return TrailingStopManager()


@pytest.fixture
def sample_execution():
    """Create sample strategy execution."""
    return MagicMock(
        execution_id="abc123def456",
        strategy_id=1,
        symbol="SPY",
        strategy_type=StrategyType.IRON_CONDOR,
        status=ExecutionStatus.FILLED,
        legs=[
            MagicMock(
                leg_id="leg1",
                right=OptionRight.CALL,
                strike=140.0,
                expiration=date(2024, 3, 15),
                quantity=1,
                action=LegAction.SELL,
                status=LegStatus.FILLED,
                fill_price=2.50,
                fill_time=datetime.now(),
            )
        ],
        entry_params={"premium_received": 250.0},
        entry_time=datetime.now(),
        fill_time=datetime.now(),
    )


@pytest.fixture
def monitoring_workflow(
    mock_decision_engine, mock_alert_manager, mock_strategy_repo, trailing_stop_manager
):
    """Create position monitoring workflow with trailing stop manager."""
    return PositionMonitoringWorkflow(
        decision_engine=mock_decision_engine,
        alert_manager=mock_alert_manager,
        strategy_repo=mock_strategy_repo,
        trailing_stops=trailing_stop_manager,
    )


class TestTrailingStopIntegration:
    """Tests for trailing stop integration with PositionMonitoringWorkflow."""

    @pytest.mark.asyncio
    async def test_monitor_position_without_trailing_stop(
        self, monitoring_workflow, mock_strategy_repo, sample_execution,
        mock_decision_engine
    ):
        """Test monitoring position without trailing stop enabled."""
        # Setup
        mock_strategy_repo.get_execution.return_value = sample_execution
        mock_decision_engine.evaluate.return_value = Decision(
            action=DecisionAction.HOLD,
            reason="No action needed",
            rule="test_rule",
            urgency=Urgency.NORMAL,
        )

        # Execute
        decision = await monitoring_workflow.monitor_position("abc123def456")

        # Verify
        assert decision.action == DecisionAction.HOLD
        mock_decision_engine.evaluate.assert_called_once()

    @pytest.mark.asyncio
    async def test_monitor_position_with_trailing_stop_activate(
        self, monitoring_workflow, mock_strategy_repo, sample_execution,
        mock_decision_engine, trailing_stop_manager
    ):
        """Test monitoring position with trailing stop activation."""
        # Enable trailing stop
        trailing_stop_manager.add_trailing_stop("abc123def456", 250.0)

        # Setup
        mock_strategy_repo.get_execution.return_value = sample_execution

        # Mock snapshot to return current premium
        with patch.object(
            monitoring_workflow, '_create_snapshot', return_value={
                "strategy_execution_id": "abc123def456",
                "current_premium": 255.0,  # 2% gain (activates stop)
                "symbol": "SPY",
            }
        ):
            mock_decision_engine.evaluate.return_value = Decision(
                action=DecisionAction.HOLD,
                reason="No action needed",
                rule="test_rule",
                urgency=Urgency.NORMAL,
            )

            # Execute
            decision = await monitoring_workflow.monitor_position("abc123def456")

            # Verify decision engine was still called
            # (trailing stop activated but didn't trigger)
            assert decision.action == DecisionAction.HOLD

    @pytest.mark.asyncio
    async def test_monitor_position_with_trailing_stop_trigger(
        self, monitoring_workflow, mock_strategy_repo, sample_execution,
        trailing_stop_manager
    ):
        """Test monitoring position with trailing stop trigger."""
        # Enable and activate trailing stop
        trailing_stop_manager.add_trailing_stop("abc123def456", 250.0)
        stop = trailing_stop_manager.get_stop("abc123def456")
        _, _ = stop.update(255.0)  # Activate

        # Setup
        mock_strategy_repo.get_execution.return_value = sample_execution

        # Mock snapshot to return current premium below stop
        with patch.object(
            monitoring_workflow, '_create_snapshot', return_value={
                "strategy_execution_id": "abc123def456",
                "current_premium": 251.0,  # Below stop at ~251.2
                "symbol": "SPY",
            }
        ):
            # Execute
            decision = await monitoring_workflow.monitor_position("abc123def456")

            # Verify CLOSE decision created
            assert decision.action == DecisionAction.CLOSE
            assert decision.rule == "TrailingStop"
            assert decision.urgency == Urgency.IMMEDIATE
            assert "Trailing stop triggered" in decision.reason

    @pytest.mark.asyncio
    async def test_monitor_position_with_trailing_stop_update(
        self, monitoring_workflow, mock_strategy_repo, sample_execution,
        mock_decision_engine, trailing_stop_manager
    ):
        """Test monitoring position with trailing stop update."""
        # Enable and activate trailing stop
        trailing_stop_manager.add_trailing_stop("abc123def456", 250.0)
        stop = trailing_stop_manager.get_stop("abc123def456")
        _, _ = stop.update(255.0)  # Activate

        # Setup
        mock_strategy_repo.get_execution.return_value = sample_execution

        # Mock snapshot to return current premium at new peak
        with patch.object(
            monitoring_workflow, '_create_snapshot', return_value={
                "strategy_execution_id": "abc123def456",
                "current_premium": 260.0,  # New peak
                "symbol": "SPY",
            }
        ):
            mock_decision_engine.evaluate.return_value = Decision(
                action=DecisionAction.HOLD,
                reason="No action needed",
                rule="test_rule",
                urgency=Urgency.NORMAL,
            )

            # Execute
            decision = await monitoring_workflow.monitor_position("abc123def456")

            # Verify decision engine was called
            assert decision.action == DecisionAction.HOLD

            # Verify stop was updated
            stop = trailing_stop_manager.get_stop("abc123def456")
            assert stop.highest_premium == 260.0

    @pytest.mark.asyncio
    async def test_enable_trailing_stop(
        self, monitoring_workflow, trailing_stop_manager
    ):
        """Test enabling trailing stop for position."""
        # Execute
        monitoring_workflow.enable_trailing_stop("abc123def456", 250.0)

        # Verify
        stop = trailing_stop_manager.get_stop("abc123def456")
        assert stop is not None
        assert stop.entry_premium == 250.0

    @pytest.mark.asyncio
    async def test_enable_trailing_stop_with_custom_config(
        self, monitoring_workflow, trailing_stop_manager
    ):
        """Test enabling trailing stop with custom configuration."""
        config = TrailingStopConfig(activation_pct=3.0, trailing_pct=2.0)

        # Execute
        monitoring_workflow.enable_trailing_stop(
            "abc123def456", 250.0, config=config
        )

        # Verify
        stop = trailing_stop_manager.get_stop("abc123def456")
        assert stop.config.activation_pct == 3.0
        assert stop.config.trailing_pct == 2.0

    def test_enable_trailing_stop_without_manager(self, mock_decision_engine, mock_alert_manager, mock_strategy_repo):
        """Test that enabling trailing stop without manager raises error."""
        # Create workflow without trailing stop manager
        workflow = PositionMonitoringWorkflow(
            decision_engine=mock_decision_engine,
            alert_manager=mock_alert_manager,
            strategy_repo=mock_strategy_repo,
            trailing_stops=None,  # No manager
        )

        # Execute and verify
        with pytest.raises(RuntimeError, match="TrailingStopManager not configured"):
            workflow.enable_trailing_stop("abc123def456", 250.0)


class TestWorkflowBackwardCompatibility:
    """Tests for backward compatibility without trailing stops."""

    @pytest.mark.asyncio
    async def test_workflow_works_without_trailing_stop_manager(
        self, mock_decision_engine, mock_alert_manager, mock_strategy_repo, sample_execution
    ):
        """Test that workflow works without trailing stop manager."""
        # Create workflow without trailing stop manager
        workflow = PositionMonitoringWorkflow(
            decision_engine=mock_decision_engine,
            alert_manager=mock_alert_manager,
            strategy_repo=mock_strategy_repo,
            trailing_stops=None,  # No manager
        )

        # Setup
        mock_strategy_repo.get_execution.return_value = sample_execution
        mock_decision_engine.evaluate.return_value = Decision(
            action=DecisionAction.HOLD,
            reason="No action needed",
            rule="test_rule",
            urgency=Urgency.NORMAL,
        )

        # Execute
        decision = await workflow.monitor_position("abc123def456")

        # Verify
        assert decision.action == DecisionAction.HOLD
        mock_decision_engine.evaluate.assert_called_once()

    @pytest.mark.asyncio
    async def test_monitor_positions_without_trailing_stop_manager(
        self, mock_decision_engine, mock_alert_manager, mock_strategy_repo, sample_execution
    ):
        """Test monitoring multiple positions without trailing stop manager."""
        # Create workflow without trailing stop manager
        workflow = PositionMonitoringWorkflow(
            decision_engine=mock_decision_engine,
            alert_manager=mock_alert_manager,
            strategy_repo=mock_strategy_repo,
            trailing_stops=None,
        )

        # Setup
        mock_strategy_repo.get_open_strategies.return_value = [sample_execution]
        mock_strategy_repo.get_execution.return_value = sample_execution
        mock_decision_engine.evaluate.return_value = Decision(
            action=DecisionAction.HOLD,
            reason="No action needed",
            rule="test_rule",
            urgency=Urgency.NORMAL,
        )

        # Execute
        decisions = await workflow.monitor_positions()

        # Verify
        assert len(decisions) == 1
        assert decisions["abc123def456"].action == DecisionAction.HOLD


class TestTrailingStopScenarios:
    """Test realistic trailing stop scenarios."""

    @pytest.mark.asyncio
    async def test_profitable_position_protection(
        self, monitoring_workflow, mock_strategy_repo, sample_execution,
        trailing_stop_manager
    ):
        """
        Test trailing stop protecting profits on profitable position.

        Scenario:
        1. Enter at $250 premium
        2. Position moves to $275 (10% gain) - stop activates at $270.9
        3. Position peaks at $280 - stop updates to $275.8
        4. Position drops to $273 - stop triggers, locking in ~$23 profit
        """
        # Enable trailing stop
        trailing_stop_manager.add_trailing_stop("abc123def456", 250.0)

        # Setup
        mock_strategy_repo.get_execution.return_value = sample_execution

        # Position moves to 275 (activates stop)
        with patch.object(
            monitoring_workflow, '_create_snapshot', return_value={
                "strategy_execution_id": "abc123def456",
                "current_premium": 275.0,
                "symbol": "SPY",
            }
        ):
            decision = await monitoring_workflow.monitor_position("abc123def456")
            assert decision.action != DecisionAction.CLOSE  # Not triggered yet

        # Position peaks at 280 (updates stop)
        with patch.object(
            monitoring_workflow, '_create_snapshot', return_value={
                "strategy_execution_id": "abc123def456",
                "current_premium": 280.0,
                "symbol": "SPY",
            }
        ):
            decision = await monitoring_workflow.monitor_position("abc123def456")
            assert decision.action != DecisionAction.CLOSE  # Not triggered yet

        # Position drops to 273 (triggers stop - below 275.8)
        with patch.object(
            monitoring_workflow, '_create_snapshot', return_value={
                "strategy_execution_id": "abc123def456",
                "current_premium": 273.0,
                "symbol": "SPY",
            }
        ):
            decision = await monitoring_workflow.monitor_position("abc123def456")

            # Verify stop triggered
            assert decision.action == DecisionAction.CLOSE
            assert decision.rule == "TrailingStop"
            assert decision.urgency == Urgency.IMMEDIATE

            # Verify profit locked in
            stop = trailing_stop_manager.get_stop("abc123def456")
            profit = stop.stop_premium - stop.entry_premium
            assert profit == pytest.approx(25.8, rel=0.1)  # ~10% gain protected

    @pytest.mark.asyncio
    async def test_choppy_market_whipsaw_protection(
        self, monitoring_workflow, mock_strategy_repo, sample_execution,
        trailing_stop_manager
    ):
        """
        Test whipsaw protection in choppy market.

        Scenario:
        1. Enter at $250 premium
        2. Price oscillates but stays above trailing stop
        3. Stop should activate but not trigger on small drops
        4. Minimum move threshold prevents excessive updates
        """
        # Enable trailing stop with tighter thresholds
        config = TrailingStopConfig(activation_pct=2.0, trailing_pct=1.0, min_move_pct=0.5)
        trailing_stop_manager.add_trailing_stop("abc123def456", 250.0, config=config)

        # Setup
        mock_strategy_repo.get_execution.return_value = sample_execution

        # Oscillating price sequence - all above stop level
        # At 255: stop activates at 252.45 (255 * 0.99)
        # At 257: stop updates to 254.43 (257 * 0.99), move from 252.45 = 0.78%
        # At 255: above stop at 254.43, so no trigger
        # At 256: new peak, stop would be 253.44, move from 254.43 = -0.39% (below min_move)
        # At 255: above stop at 254.43, so no trigger
        premiums = [255.0, 257.0, 255.0, 256.0, 255.0]
        actions = []

        for premium in premiums:
            with patch.object(
                monitoring_workflow, '_create_snapshot', return_value={
                    "strategy_execution_id": "abc123def456",
                    "current_premium": premium,
                    "symbol": "SPY",
                }
            ):
                decision = await monitoring_workflow.monitor_position("abc123def456")

                if decision.action == DecisionAction.CLOSE:
                    actions.append("CLOSE")
                elif decision.rule == "TrailingStop":
                    actions.append("TRAILING_UPDATE")
                else:
                    actions.append("NORMAL")

        # Verify stop didn't trigger in choppy market (price stayed above stop)
        assert "CLOSE" not in actions

        # Verify stop is active
        stop = trailing_stop_manager.get_stop("abc123def456")
        assert stop.is_active is True
