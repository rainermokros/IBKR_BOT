"""
Tests for ExitWorkflow Trailing Stop Integration

Tests the integration of trailing stops with the exit workflow.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.v6.decisions.models import Decision, DecisionAction, Urgency
from src.v6.execution.engine import OrderExecutionEngine
from src.v6.execution.models import ExecutionResult
from src.v6.strategies.repository import StrategyRepository
from src.v6.strategies.models import StrategyType, ExecutionStatus, LegStatus
from src.v6.workflows.exit import ExitWorkflow
from src.v6.risk import TrailingStopManager

from datetime import date, datetime


@pytest.fixture
def mock_execution_engine():
    """Create mock execution engine."""
    engine = AsyncMock(spec=OrderExecutionEngine)
    return engine


@pytest.fixture
def mock_strategy_repo():
    """Create mock strategy repository."""
    repo = AsyncMock(spec=StrategyRepository)
    return repo


@pytest.fixture
def trailing_stop_manager():
    """Create trailing stop manager."""
    manager = TrailingStopManager()
    # Add a trailing stop for testing
    manager.add_trailing_stop("abc123def456", 250.0)
    return manager


@pytest.fixture
def sample_strategy_execution():
    """Create sample strategy execution."""
    # Create a leg execution with future expiration
    from datetime import timedelta
    future_date = date.today() + timedelta(days=30)

    leg_exec = MagicMock()
    leg_exec.leg_id = "leg1"
    leg_exec.right = "CALL"
    leg_exec.strike = 140.0
    leg_exec.expiration = future_date
    leg_exec.quantity = 1
    leg_exec.action = MagicMock(value="SELL")
    leg_exec.status = LegStatus.FILLED

    execution = MagicMock()
    execution.execution_id = "abc123def456"
    execution.strategy_id = 1
    execution.symbol = "SPY"
    execution.strategy_type = StrategyType.IRON_CONDOR
    execution.status = ExecutionStatus.FILLED
    execution.legs = [leg_exec]
    execution.entry_params = {"premium_received": 250.0}
    execution.entry_time = datetime.now()
    execution.fill_time = datetime.now()
    return execution


@pytest.fixture
def exit_workflow_with_trailing_stops(
    mock_execution_engine, mock_strategy_repo, trailing_stop_manager
):
    """Create exit workflow with trailing stop manager."""
    return ExitWorkflow(
        execution_engine=mock_execution_engine,
        strategy_repo=mock_strategy_repo,
        trailing_stops=trailing_stop_manager,
    )


@pytest.fixture
def exit_workflow_without_trailing_stops(mock_execution_engine, mock_strategy_repo):
    """Create exit workflow without trailing stop manager."""
    return ExitWorkflow(
        execution_engine=mock_execution_engine,
        strategy_repo=mock_strategy_repo,
        trailing_stops=None,
    )


class TestTrailingStopCleanup:
    """Tests for trailing stop cleanup in ExitWorkflow."""

    @pytest.mark.asyncio
    async def test_trailing_stop_removed_on_close(
        self,
        exit_workflow_with_trailing_stops,
        mock_strategy_repo,
        mock_execution_engine,
        sample_strategy_execution,
        trailing_stop_manager,
    ):
        """Test that trailing stop is removed after successful CLOSE."""
        # Setup
        mock_strategy_repo.get_execution.return_value = sample_strategy_execution
        mock_execution_engine.close_position.return_value = ExecutionResult(
            success=True,
            action_taken="CLOSED",
            order_ids=["order1"],
            error_message=None,
        )

        # Verify trailing stop exists
        assert trailing_stop_manager.get_stop("abc123def456") is not None

        # Execute CLOSE decision
        decision = Decision(
            action=DecisionAction.CLOSE,
            reason="Take profit",
            rule="test_rule",
            urgency=Urgency.NORMAL,
        )

        result = await exit_workflow_with_trailing_stops.execute_exit_decision(
            "abc123def456", decision
        )

        # Verify execution succeeded
        assert result.success is True

        # Verify trailing stop was removed
        assert trailing_stop_manager.get_stop("abc123def456") is None

    @pytest.mark.asyncio
    async def test_trailing_stop_removed_on_roll(
        self,
        exit_workflow_with_trailing_stops,
        mock_strategy_repo,
        mock_execution_engine,
        sample_strategy_execution,
        trailing_stop_manager,
    ):
        """Test that trailing stop is removed after successful ROLL."""
        # Setup
        mock_strategy_repo.get_execution.return_value = sample_strategy_execution
        mock_execution_engine.roll_position.return_value = ExecutionResult(
            success=True,
            action_taken="ROLLED",
            order_ids=["order1", "order2"],
            error_message=None,
        )

        # Verify trailing stop exists
        assert trailing_stop_manager.get_stop("abc123def456") is not None

        # Execute ROLL decision
        decision = Decision(
            action=DecisionAction.ROLL,
            reason="Roll to new DTE",
            rule="test_rule",
            urgency=Urgency.NORMAL,
            metadata={"roll_to_dte": 45},
        )

        result = await exit_workflow_with_trailing_stops.execute_exit_decision(
            "abc123def456", decision
        )

        # Verify execution succeeded
        assert result.success is True

        # Verify trailing stop was removed
        assert trailing_stop_manager.get_stop("abc123def456") is None

    @pytest.mark.asyncio
    async def test_trailing_stop_not_removed_on_hold(
        self,
        exit_workflow_with_trailing_stops,
        sample_strategy_execution,
        trailing_stop_manager,
    ):
        """Test that trailing stop is NOT removed on HOLD decision."""
        # Trailing stop already added in fixture, so we don't need to add it again
        # Setup is done in fixture

        # Verify trailing stop exists
        assert trailing_stop_manager.get_stop("abc123def456") is not None

        # Execute HOLD decision
        decision = Decision(
            action=DecisionAction.HOLD,
            reason="No action needed",
            rule="test_rule",
            urgency=Urgency.NORMAL,
        )

        result = await exit_workflow_with_trailing_stops.execute_exit_decision(
            "abc123def456", decision
        )

        # Verify execution succeeded (no action taken)
        assert result.success is True

        # Verify trailing stop still exists
        assert trailing_stop_manager.get_stop("abc123def456") is not None

    @pytest.mark.asyncio
    async def test_trailing_stop_not_removed_on_failed_close(
        self,
        exit_workflow_with_trailing_stops,
        mock_strategy_repo,
        mock_execution_engine,
        sample_strategy_execution,
        trailing_stop_manager,
    ):
        """Test that trailing stop is NOT removed if CLOSE fails."""
        # Setup
        mock_strategy_repo.get_execution.return_value = sample_strategy_execution
        mock_execution_engine.close_position.return_value = ExecutionResult(
            success=False,  # Failed
            action_taken="FAILED",
            order_ids=[],
            error_message="Order rejected",
        )

        # Verify trailing stop exists
        assert trailing_stop_manager.get_stop("abc123def456") is not None

        # Execute CLOSE decision
        decision = Decision(
            action=DecisionAction.CLOSE,
            reason="Take profit",
            rule="test_rule",
            urgency=Urgency.NORMAL,
        )

        result = await exit_workflow_with_trailing_stops.execute_exit_decision(
            "abc123def456", decision
        )

        # Verify execution failed
        assert result.success is False

        # Verify trailing stop still exists (not removed on failure)
        assert trailing_stop_manager.get_stop("abc123def456") is not None

    @pytest.mark.asyncio
    async def test_trailing_stop_cleanup_with_missing_stop(
        self,
        exit_workflow_with_trailing_stops,
        mock_strategy_repo,
        mock_execution_engine,
        sample_strategy_execution,
        trailing_stop_manager,
    ):
        """Test cleanup when trailing stop doesn't exist (should not error)."""
        # Remove trailing stop first
        trailing_stop_manager.remove_stop("abc123def456")

        # Setup
        mock_strategy_repo.get_execution.return_value = sample_strategy_execution
        mock_execution_engine.close_position.return_value = ExecutionResult(
            success=True,
            action_taken="CLOSED",
            order_ids=["order1"],
            error_message=None,
        )

        # Execute CLOSE decision
        decision = Decision(
            action=DecisionAction.CLOSE,
            reason="Take profit",
            rule="test_rule",
            urgency=Urgency.NORMAL,
        )

        # Should not raise error
        result = await exit_workflow_with_trailing_stops.execute_exit_decision(
            "abc123def456", decision
        )

        # Verify execution succeeded
        assert result.success is True


class TestWorkflowBackwardCompatibility:
    """Tests for backward compatibility without trailing stops."""

    @pytest.mark.asyncio
    async def test_exit_workflow_works_without_trailing_stop_manager(
        self,
        exit_workflow_without_trailing_stops,
        mock_strategy_repo,
        mock_execution_engine,
        sample_strategy_execution,
    ):
        """Test that exit workflow works without trailing stop manager."""
        # Setup
        mock_strategy_repo.get_execution.return_value = sample_strategy_execution
        mock_execution_engine.close_position.return_value = ExecutionResult(
            success=True,
            action_taken="CLOSED",
            order_ids=["order1"],
            error_message=None,
        )

        # Execute CLOSE decision
        decision = Decision(
            action=DecisionAction.CLOSE,
            reason="Take profit",
            rule="test_rule",
            urgency=Urgency.NORMAL,
        )

        # Should not raise error
        result = await exit_workflow_without_trailing_stops.execute_exit_decision(
            "abc123def456", decision
        )

        # Verify execution succeeded
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_close_all_without_trailing_stop_manager(
        self,
        exit_workflow_without_trailing_stops,
        mock_strategy_repo,
        mock_execution_engine,
        sample_strategy_execution,
    ):
        """Test execute_close_all without trailing stop manager."""
        # Setup
        mock_strategy_repo.get_open_strategies.return_value = [
            sample_strategy_execution
        ]
        mock_strategy_repo.get_execution.return_value = sample_strategy_execution
        mock_execution_engine.close_position.return_value = ExecutionResult(
            success=True,
            action_taken="CLOSED",
            order_ids=["order1"],
            error_message=None,
        )

        # Execute close all
        results = await exit_workflow_without_trailing_stops.execute_close_all(
            symbol="SPY"
        )

        # Verify execution succeeded
        assert len(results) == 1
        assert results["abc123def456"].success is True


class TestTrailingStopLifecycle:
    """Integration tests for complete trailing stop lifecycle."""

    @pytest.mark.asyncio
    async def test_complete_lifecycle(
        self,
        exit_workflow_with_trailing_stops,
        mock_strategy_repo,
        mock_execution_engine,
        sample_strategy_execution,
        trailing_stop_manager,
    ):
        """
        Test complete lifecycle:
        1. Add trailing stop
        2. Trigger trailing stop (creates CLOSE decision)
        3. Execute CLOSE decision
        4. Verify trailing stop removed
        """
        # 1. Trailing stop already added in fixture
        assert trailing_stop_manager.get_stop("abc123def456") is not None

        # 2. Trigger trailing stop
        stop = trailing_stop_manager.get_stop("abc123def456")
        _, _ = stop.update(255.0)  # Activate
        new_stop, action = stop.update(251.0)  # Trigger

        from src.v6.risk import TrailingStopAction
        assert action == TrailingStopAction.TRIGGER

        # 3. Execute CLOSE decision
        mock_strategy_repo.get_execution.return_value = sample_strategy_execution
        mock_execution_engine.close_position.return_value = ExecutionResult(
            success=True,
            action_taken="CLOSED",
            order_ids=["order1"],
            error_message=None,
        )

        decision = Decision(
            action=DecisionAction.CLOSE,
            reason=f"Trailing stop triggered at {new_stop:.2f}",
            rule="TrailingStop",
            urgency=Urgency.IMMEDIATE,
        )

        result = await exit_workflow_with_trailing_stops.execute_exit_decision(
            "abc123def456", decision
        )

        # 4. Verify trailing stop removed
        assert result.success is True
        assert trailing_stop_manager.get_stop("abc123def456") is None

    @pytest.mark.asyncio
    async def test_multiple_positions_with_trailing_stops(
        self,
        exit_workflow_with_trailing_stops,
        mock_strategy_repo,
        mock_execution_engine,
        trailing_stop_manager,
    ):
        """Test closing multiple positions with trailing stops."""
        from datetime import timedelta
        future_date = date.today() + timedelta(days=30)

        # Add multiple trailing stops
        trailing_stop_manager.add_trailing_stop("pos1", 100.0)
        trailing_stop_manager.add_trailing_stop("pos2", 200.0)
        trailing_stop_manager.add_trailing_stop("pos3", 300.0)

        # Create a leg for mock executions
        def create_mock_leg():
            leg = MagicMock()
            leg.leg_id = "leg1"
            leg.right = "CALL"
            leg.strike = 140.0
            leg.expiration = future_date
            leg.quantity = 1
            leg.action = MagicMock(value="SELL")
            leg.status = LegStatus.FILLED
            return leg

        # Setup mock executions
        mock_execution1 = MagicMock()
        mock_execution1.execution_id = "pos1"
        mock_execution1.symbol = "SPY"
        mock_execution1.strategy_type = StrategyType.IRON_CONDOR
        mock_execution1.status = ExecutionStatus.FILLED
        mock_execution1.legs = [create_mock_leg()]
        mock_execution1.entry_params = {}
        mock_execution1.entry_time = datetime.now()
        mock_execution1.fill_time = datetime.now()

        mock_execution2 = MagicMock()
        mock_execution2.execution_id = "pos2"
        mock_execution2.symbol = "SPY"
        mock_execution2.strategy_type = StrategyType.IRON_CONDOR
        mock_execution2.status = ExecutionStatus.FILLED
        mock_execution2.legs = [create_mock_leg()]
        mock_execution2.entry_params = {}
        mock_execution2.entry_time = datetime.now()
        mock_execution2.fill_time = datetime.now()

        mock_execution3 = MagicMock()
        mock_execution3.execution_id = "pos3"
        mock_execution3.symbol = "SPY"
        mock_execution3.strategy_type = StrategyType.IRON_CONDOR
        mock_execution3.status = ExecutionStatus.FILLED
        mock_execution3.legs = [create_mock_leg()]
        mock_execution3.entry_params = {}
        mock_execution3.entry_time = datetime.now()
        mock_execution3.fill_time = datetime.now()

        mock_strategy_repo.get_open_strategies.return_value = [
            mock_execution1,
            mock_execution2,
            mock_execution3,
        ]

        # Mock get_execution to return appropriate execution based on ID
        async def mock_get_exec(exec_id):
            if exec_id == "pos1":
                return mock_execution1
            elif exec_id == "pos2":
                return mock_execution2
            elif exec_id == "pos3":
                return mock_execution3
            return None

        mock_strategy_repo.get_execution.side_effect = mock_get_exec
        mock_execution_engine.close_position.return_value = ExecutionResult(
            success=True,
            action_taken="CLOSED",
            order_ids=["order1"],
            error_message=None,
        )

        # Execute close all
        results = await exit_workflow_with_trailing_stops.execute_close_all(
            symbol="SPY"
        )

        # Verify all trailing stops removed
        assert trailing_stop_manager.get_stop("pos1") is None
        assert trailing_stop_manager.get_stop("pos2") is None
        assert trailing_stop_manager.get_stop("pos3") is None
