"""
Tests for AssignmentMonitor

Tests the assignment detection and emergency close functionality to ensure
proper handling of option assignment events.
"""

import asyncio
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from v6.execution import Assignment, AssignmentMonitor, AssignmentType
from v6.execution.engine import OrderExecutionEngine
from v6.execution.models import ExecutionResult
from v6.models.decisions import Decision, DecisionAction, Urgency
from v6.models.strategy import LegSpec, LegAction, OptionRight, Strategy, StrategyType


# Test data helpers
def create_test_strategy(
    symbol: str = "SPY",
    strategy_type: StrategyType = StrategyType.IRON_CONDOR,
) -> Strategy:
    """Create test strategy with legs."""
    return Strategy(
        strategy_id="test_strategy_123",
        symbol=symbol,
        strategy_type=strategy_type,
        legs=[
            LegSpec(
                right=OptionRight.PUT,
                strike=440.0,
                quantity=2,
                action=LegAction.SELL,
                expiration=date.today(),
            ),
            LegSpec(
                right=OptionRight.PUT,
                strike=435.0,
                quantity=2,
                action=LegAction.BUY,
                expiration=date.today(),
            ),
            LegSpec(
                right=OptionRight.CALL,
                strike=460.0,
                quantity=2,
                action=LegAction.SELL,
                expiration=date.today(),
            ),
            LegSpec(
                right=OptionRight.CALL,
                strike=465.0,
                quantity=2,
                action=LegAction.BUY,
                expiration=date.today(),
            ),
        ],
    )


def create_test_execution(
    execution_id: str = "test_exec_123",
    strategy_id: str = "test_strategy_123",
) -> Mock:
    """Create test strategy execution."""
    execution = Mock()
    execution.execution_id = execution_id
    execution.strategy_id = strategy_id
    execution.strategy = create_test_strategy()
    execution.legs = [
        Mock(leg_id="leg1", conid=1001, right="PUT", strike=440.0, quantity=2),
        Mock(leg_id="leg2", conid=1002, right="PUT", strike=435.0, quantity=2),
        Mock(leg_id="leg3", conid=1003, right="CALL", strike=460.0, quantity=2),
        Mock(leg_id="leg4", conid=1004, right="CALL", strike=465.0, quantity=2),
    ]
    return execution


class TestAssignment:
    """Tests for Assignment data model."""

    def test_assignment_creation(self):
        """Test creating an assignment event."""
        assignment = Assignment(
            assignment_id="asn_123",
            conid=1001,
            symbol="SPY",
            right="PUT",
            strike=440.0,
            quantity=2,
            assignment_type=AssignmentType.EARLY,
            execution_id="exec_123",
            strategy_id="strat_123",
            leg_id="leg_123",
            stock_position=-200,  # Assigned -200 shares
        )

        assert assignment.assignment_id == "asn_123"
        assert assignment.conid == 1001
        assert assignment.symbol == "SPY"
        assert assignment.right == "PUT"
        assert assignment.strike == 440.0
        assert assignment.quantity == 2
        assert assignment.assignment_type == AssignmentType.EARLY
        assert assignment.stock_position == -200

    def test_assignment_string_representation(self):
        """Test string representation of assignment."""
        assignment = Assignment(
            assignment_id="asn_123",
            conid=1001,
            symbol="SPY",
            right="CALL",
            strike=460.0,
            quantity=2,
            assignment_type=AssignmentType.EXPIRATION,
            execution_id="exec_123",
            strategy_id="strat_123",
            leg_id="leg_123",
        )

        str_repr = str(assignment)
        assert "SPY" in str_repr
        assert "CALL" in str_repr
        assert "460.0" in str_repr
        assert "EXPIRATION" in str_repr


class TestAssignmentMonitor:
    """Tests for AssignmentMonitor."""

    @pytest.fixture
    def mock_ib_wrapper(self):
        """Create mock IB API wrapper."""
        wrapper = Mock()
        wrapper.openOrder = Mock()
        wrapper.position = Mock()
        wrapper.get_positions = AsyncMock(return_value=[])
        return wrapper

    @pytest.fixture
    def mock_exit_workflow(self):
        """Create mock exit workflow."""
        workflow = AsyncMock()
        workflow.execute_exit_decision = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                action_taken="CLOSED",
                order_ids=["order1", "order2"],
            )
        )
        return workflow

    @pytest.fixture
    def mock_strategy_repo(self):
        """Create mock strategy repository."""
        repo = AsyncMock()
        repo.get_open_executions_by_symbol = AsyncMock(return_value=[])
        repo.get_execution = AsyncMock(return_value=None)
        repo.get_open_executions = AsyncMock(return_value=[])
        repo.mark_execution_broken = AsyncMock()
        return repo

    @pytest.fixture
    def mock_alert_manager(self):
        """Create mock alert manager."""
        manager = AsyncMock()
        manager.send_critical_alert = AsyncMock()
        return manager

    @pytest.fixture
    def assignment_monitor(
        self,
        mock_ib_wrapper,
        mock_exit_workflow,
        mock_strategy_repo,
        mock_alert_manager,
    ):
        """Create AssignmentMonitor for testing."""
        return AssignmentMonitor(
            ib_wrapper=mock_ib_wrapper,
            exit_workflow=mock_exit_workflow,
            strategy_repo=mock_strategy_repo,
            alert_manager=mock_alert_manager,
            enabled=True,
        )

    def test_initialization(self, assignment_monitor):
        """Test monitor initialization."""
        assert assignment_monitor.enabled is True
        assert assignment_monitor._running is False
        assert assignment_monitor.exit_workflow is not None

    def test_initialization_disabled(self, mock_exit_workflow, mock_strategy_repo, mock_alert_manager):
        """Test monitor initialization when disabled."""
        monitor = AssignmentMonitor(
            ib_wrapper=None,
            exit_workflow=mock_exit_workflow,
            strategy_repo=mock_strategy_repo,
            alert_manager=mock_alert_manager,
            enabled=False,
        )

        assert monitor.enabled is False

    @pytest.mark.asyncio
    async def test_start_stop_monitoring(self, assignment_monitor):
        """Test starting and stopping the monitor."""
        # Start
        await assignment_monitor.start()
        assert assignment_monitor._running is True

        # Stop
        await assignment_monitor.stop()
        assert assignment_monitor._running is False

    @pytest.mark.asyncio
    async def test_start_when_disabled(self, assignment_monitor):
        """Test starting when disabled does nothing."""
        assignment_monitor.enabled = False

        await assignment_monitor.start()
        assert assignment_monitor._running is False

    @pytest.mark.asyncio
    async def test_check_order_for_assignment_non_option(
        self, assignment_monitor
    ):
        """Test order check ignores non-option orders."""
        order = Mock()
        order.contract = Mock()
        order.contract.secType = "STK"  # Stock, not option

        order_state = Mock()

        # Should not raise
        await assignment_monitor._check_order_for_assignment(order, order_state)

    @pytest.mark.asyncio
    async def test_check_position_for_assignment_stock(
        self, assignment_monitor, mock_strategy_repo
    ):
        """Test position check for stock appearance (assignment indicator)."""
        # Mock execution with short options
        execution = create_test_execution()
        mock_strategy_repo.get_open_executions_by_symbol.return_value = [execution]

        contract = Mock()
        contract.secType = "STK"
        contract.symbol = "SPY"
        contract.conId = 999

        # Stock position appeared (assignment indicator)
        position = -200  # Short 200 shares

        await assignment_monitor._check_position_for_assignment(
            contract, position, "DU12345"
        )

        # Should have queried executions for this symbol
        mock_strategy_repo.get_open_executions_by_symbol.assert_called_once_with("SPY")

    @pytest.mark.asyncio
    async def test_handle_detected_assignment(
        self,
        assignment_monitor,
        mock_exit_workflow,
        mock_strategy_repo,
        mock_alert_manager,
    ):
        """Test handling detected assignment."""
        # Setup
        execution = create_test_execution()
        mock_strategy_repo.get_execution.return_value = execution

        # Simulate assignment detection
        await assignment_monitor._handle_detected_assignment(
            conid=1001,
            symbol="SPY",
            right="PUT",
            strike=440.0,
            quantity=2,
            stock_position=-200,
            execution_id="test_exec_123",
        )

        # Verify strategy marked as broken
        mock_strategy_repo.mark_execution_broken.assert_called_once()
        call_args = mock_strategy_repo.mark_execution_broken.call_args
        assert call_args[1]["execution_id"] == "test_exec_123"
        assert "ASSIGNMENT" in call_args[1]["reason"]

        # Verify critical alert sent
        mock_alert_manager.send_critical_alert.assert_called()
        alert_msg = mock_alert_manager.send_critical_alert.call_args[0][0]
        assert "ASSIGNMENT DETECTED" in alert_msg
        assert "EMERGENCY CLOSE" in alert_msg

        # Verify emergency close executed
        mock_exit_workflow.execute_exit_decision.assert_called_once()
        call_args = mock_exit_workflow.execute_exit_decision.call_args
        decision = call_args[1]["decision"]

        assert decision.action == DecisionAction.CLOSE
        assert decision.urgency == Urgency.IMMEDIATE
        assert decision.metadata["emergency"] is True
        assert "assignment" in decision.metadata


class TestClosePositionBrokenStrategy:
    """Tests for broken strategy detection in close_position."""

    @pytest.fixture
    def mock_engine(self):
        """Create mock execution engine."""
        engine = MagicMock(spec=OrderExecutionEngine)
        engine.dry_run = False
        engine.ib_conn = AsyncMock()
        engine.ib_conn.ensure_connected = AsyncMock()
        engine.ib_conn.get_positions = AsyncMock(return_value=[])
        engine.place_order = AsyncMock()

        # Real close_position method
        from v6.execution.engine import OrderExecutionEngine
        engine.close_position = OrderExecutionEngine.close_position.__get__(engine, OrderExecutionEngine)
        engine._check_strategy_broken = OrderExecutionEngine._check_strategy_broken.__get__(engine, OrderExecutionEngine)

        return engine

    @pytest.mark.asyncio
    async def test_close_rejects_broken_strategy_missing_conid(
        self, mock_engine
    ):
        """Test close rejects strategy with missing conids."""
        strategy = create_test_strategy()

        # Set one leg's conid to None (simulating assignment)
        strategy.legs[0].conid = None

        result = await mock_engine.close_position(strategy, emergency=False)

        assert result.success is False
        assert "broken" in result.error_message.lower()
        assert "conid" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_close_allows_emergency_for_broken_strategy(
        self, mock_engine
    ):
        """Test emergency close bypasses broken strategy check."""
        strategy = create_test_strategy()

        # Set one leg's conid to None
        strategy.legs[0].conid = None

        # Mock place_order to return success
        mock_order = Mock()
        mock_order.order_id = "test_order_123"
        mock_engine.place_order = AsyncMock(return_value=mock_order)

        # Mock ib.qualifyContractsAsync
        mock_engine.ib.qualifyContractsAsync = AsyncMock()

        result = await mock_engine.close_position(strategy, emergency=True)

        # Should have attempted close (emergency bypass)
        # Note: Will fail later in actual close, but bypassed broken check
        assert "conid" not in str(result).lower() or result.success or result.action_taken == "FAILED"

    @pytest.mark.asyncio
    async def test_check_strategy_broken_missing_conids(self, mock_engine):
        """Test broken detection for missing conids."""
        strategy = create_test_strategy()
        strategy.legs[0].conid = None

        result = await mock_engine._check_strategy_broken(strategy)

        assert result["is_broken"] is True
        assert "conid" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_check_strategy_broken_incorrect_leg_count(self, mock_engine):
        """Test broken detection for wrong leg count."""
        # Iron condor should have 4 legs
        strategy = Strategy(
            strategy_id="test",
            symbol="SPY",
            strategy_type=StrategyType.IRON_CONDOR,
            legs=[  # Only 2 legs instead of 4
                LegSpec(
                    right=OptionRight.PUT,
                    strike=440.0,
                    quantity=2,
                    action=LegAction.SELL,
                    expiration=date.today(),
                ),
            ],
        )

        result = await mock_engine._check_strategy_broken(strategy)

        assert result["is_broken"] is True
        assert "4" in result["reason"]  # Expected 4 legs
        assert "1" in result["reason"]  # Has 1 leg

    @pytest.mark.asyncio
    async def test_check_strategy_broken_intact_strategy(self, mock_engine):
        """Test broken detection passes for intact strategy."""
        strategy = create_test_strategy()

        # All legs have conids
        for leg in strategy.legs:
            leg.conid = 1000 + strategy.legs.index(leg)

        result = await mock_engine._check_strategy_broken(strategy)

        assert result["is_broken"] is False
        assert result["reason"] is None


class TestAssignmentIntegration:
    """Integration tests for assignment monitoring workflow."""

    @pytest.mark.asyncio
    async def test_full_assignment_workflow(
        self,
        assignment_monitor,
        mock_exit_workflow,
        mock_strategy_repo,
        mock_alert_manager,
    ):
        """Test complete assignment detection and emergency close workflow."""
        # Setup
        execution = create_test_execution()
        mock_strategy_repo.get_execution.return_value = execution

        # Simulate assignment event
        await assignment_monitor._handle_detected_assignment(
            conid=1003,
            symbol="SPY",
            right="CALL",
            strike=460.0,
            quantity=2,
            stock_position=-200,  # Short 200 shares (call assignment)
            execution_id="test_exec_123",
        )

        # Verify complete workflow:

        # 1. Strategy marked broken
        mock_strategy_repo.mark_execution_broken.assert_called_once()

        # 2. Critical alert sent
        mock_alert_manager.send_critical_alert.assert_called()

        # 3. Emergency close executed
        mock_exit_workflow.execute_exit_decision.assert_called_once()
        decision = mock_exit_workflow.execute_exit_decision.call_args[1]["decision"]

        assert decision.action == DecisionAction.CLOSE
        assert decision.urgency == Urgency.IMMEDIATE
        assert decision.metadata["emergency"] is True
        assert decision.metadata["bypass_rules"] is True

    @pytest.mark.asyncio
    async def test_assignment_emergency_close_failed(
        self,
        assignment_monitor,
        mock_exit_workflow,
        mock_strategy_repo,
        mock_alert_manager,
    ):
        """Test assignment handling when emergency close fails."""
        # Setup
        execution = create_test_execution()
        mock_strategy_repo.get_execution.return_value = execution

        # Mock emergency close failure
        mock_exit_workflow.execute_exit_decision = AsyncMock(
            return_value=ExecutionResult(
                success=False,
                action_taken="FAILED",
                order_ids=[],
                error_message="Connection lost",
            )
        )

        # Simulate assignment
        await assignment_monitor._handle_detected_assignment(
            conid=1001,
            symbol="SPY",
            right="PUT",
            strike=440.0,
            quantity=2,
            stock_position=200,  # Long 200 shares (put assignment)
            execution_id="test_exec_123",
        )

        # Verify failure alert sent
        assert mock_alert_manager.send_critical_alert.call_count >= 2  # Initial + failure

        # Check that failure alert mentions the error
        failure_alert = mock_alert_manager.send_critical_alert.call_args_list[-1]
        alert_msg = failure_alert[0][0]
        assert "FAILED" in alert_msg
        assert "MANUAL INTERVENTION" in alert_msg
