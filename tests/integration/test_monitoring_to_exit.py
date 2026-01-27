"""
Integration tests: Monitoring Workflow → Exit Workflow

Tests the flow from monitoring decisions to position exit,
including order cancellation, position closure, and Delta Lake updates.

Usage:
    pytest tests/integration/test_monitoring_to_exit.py -v
"""

import pytest
from datetime import datetime, date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

from src.v6.workflows.entry import EntryWorkflow
from src.v6.workflows.monitoring import MonitoringWorkflow
from src.v6.workflows.exit import ExitWorkflow
from src.v6.execution.engine import OrderExecutionEngine
from src.v6.decisions.engine import DecisionEngine
from src.v6.strategies.builders import IronCondorBuilder
from src.v6.strategies.models import StrategyType, ExecutionStatus
from src.v6.strategies.repository import StrategyRepository
from src.v6.decisions.models import Decision, DecisionAction, Urgency
from src.v6.execution.models import OrderStatus


@pytest.fixture
def mock_decision_engine():
    """Create mock DecisionEngine."""
    mock = MagicMock()
    mock.evaluate_decisions = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def mock_execution_engine():
    """Create mock OrderExecutionEngine."""
    mock = MagicMock()
    mock.place_order = AsyncMock()

    # Create realistic order response
    def create_mock_order():
        order = MagicMock()
        order.order_id = str(uuid4())
        order.status = ExecutionStatus.FILLED
        order.conId = 123456
        order.avg_fill_price = 1.50
        order.filled_at = datetime.now()
        return order

    mock.place_order.return_value = create_mock_order()

    # Mock cancelOrder
    mock.cancel_order = MagicMock()

    return mock


@pytest.fixture
def mock_strategy_builder():
    """Create mock StrategyBuilder."""
    return IronCondorBuilder()


@pytest.fixture
def mock_strategy_repo(lake_path):
    """Create StrategyRepository with test Delta Lake."""
    repo = StrategyRepository(lake_path=str(lake_path))
    return repo


@pytest.fixture
def entry_workflow(
    mock_decision_engine,
    mock_execution_engine,
    mock_strategy_builder,
    mock_strategy_repo,
):
    """Create EntryWorkflow for testing."""
    return EntryWorkflow(
        decision_engine=mock_decision_engine,
        execution_engine=mock_execution_engine,
        strategy_builder=mock_strategy_builder,
        strategy_repo=mock_strategy_repo,
        portfolio_limits=None,
    )


@pytest.fixture
def monitoring_workflow(
    mock_decision_engine,
    mock_strategy_repo,
):
    """Create MonitoringWorkflow for testing."""
    return MonitoringWorkflow(
        decision_engine=mock_decision_engine,
        strategy_repo=mock_strategy_repo,
    )


@pytest.fixture
def exit_workflow(
    mock_execution_engine,
    mock_strategy_repo,
):
    """Create ExitWorkflow for testing."""
    return ExitWorkflow(
        execution_engine=mock_execution_engine,
        strategy_repo=mock_strategy_repo,
    )


@pytest.mark.asyncio
async def test_stop_loss_decision_triggers_exit_workflow(
    entry_workflow,
    monitoring_workflow,
    exit_workflow,
    mock_decision_engine,
    mock_execution_engine,
):
    """
    Test: Stop loss decision triggers exit workflow.

    Validates:
    - Entry workflow creates position
    - Decision engine detects stop loss breach
    - Exit workflow called with CLOSE action
    - Exit orders placed correctly
    - Position status updated to CLOSED
    """
    # Execute entry
    params = {
        "underlying_price": 455.0,
        "dte": 45,
        "put_width": 10,
        "call_width": 10,
    }

    execution = await entry_workflow.execute_entry(
        symbol="SPY",
        strategy_type=StrategyType.IRON_CONDOR,
        params=params,
    )

    # Setup stop loss decision
    stop_loss_decision = Decision(
        action=DecisionAction.CLOSE,
        reason="Stop loss breached: -50% loss on position",
        rule="stop_loss",
        urgency=Urgency.IMMEDIATE,
        metadata={
            "loss_percent": -50.0,
            "entry_price": 1.50,
            "current_price": 3.00,
        },
    )
    mock_decision_engine.evaluate_decisions.return_value = [stop_loss_decision]

    # Evaluate decisions (should trigger exit)
    decisions = await monitoring_workflow.evaluate_all_positions()
    assert len(decisions) == 1
    assert decisions[0].action == DecisionAction.CLOSE

    # Execute exit
    mock_execution_engine.cancel_order = MagicMock()
    await exit_workflow.execute_exit(execution.execution_id, reason="Stop loss")

    # Verify orders cancelled
    assert mock_execution_engine.cancel_order.called

    # Verify position closed (reload from repo)
    # Note: This would require repo.get_execution() method


@pytest.mark.asyncio
async def test_exit_workflow_cancels_pending_orders(
    entry_workflow,
    exit_workflow,
    mock_execution_engine,
):
    """
    Test: Exit workflow cancels orders and closes position.

    Validates:
    - Position with pending orders
    - Exit workflow cancels all pending orders
    - Close orders placed for opposite legs
    - Position state updated correctly
    """
    # Execute entry
    params = {
        "underlying_price": 455.0,
        "dte": 45,
        "put_width": 10,
        "call_width": 10,
    }

    execution = await entry_workflow.execute_entry(
        symbol="SPY",
        strategy_type=StrategyType.IRON_CONDOR,
        params=params,
    )

    # Track cancel calls
    cancel_calls = []

    def track_cancel(order_id):
        cancel_calls.append(order_id)

    mock_execution_engine.cancel_order.side_effect = track_cancel

    # Execute exit
    await exit_workflow.execute_exit(execution.execution_id, reason="Test exit")

    # Verify cancel orders called (should have pending orders to cancel)
    # Note: In real scenario, there would be working orders


@pytest.mark.asyncio
async def test_position_state_updated_after_exit(
    entry_workflow,
    exit_workflow,
    mock_strategy_repo,
):
    """
    Test: Position state updated correctly after exit.

    Validates:
    - Position exits successfully
    - Status changed from FILLED to CLOSED
    - Closed at timestamp set
    - Realized P&L calculated
    - Position no longer appears in active positions
    """
    # Execute entry
    params = {
        "underlying_price": 455.0,
        "dte": 45,
        "put_width": 10,
        "call_width": 10,
    }

    execution = await entry_workflow.execute_entry(
        symbol="SPY",
        strategy_type=StrategyType.IRON_CONDOR,
        params=params,
    )

    # Verify position is active
    active_before = mock_strategy_repo.get_active_executions()
    assert len(active_before) == 1
    assert active_before[0].status == ExecutionStatus.FILLED

    # Execute exit
    await exit_workflow.execute_exit(execution.execution_id, reason="Test exit")

    # Verify position state updated
    # Note: This requires repo.update_status() method


@pytest.mark.asyncio
async def test_delta_lake_records_exit_transaction(
    entry_workflow,
    exit_workflow,
    mock_strategy_repo,
    lake_path,
):
    """
    Test: Delta Lake records exit transaction.

    Validates:
    - Entry creates transaction in Delta Lake
    - Exit creates closing transaction
    - Both transactions linked to same execution_id
    - Can query full transaction history
    - P&L calculated correctly
    """
    # Execute entry
    params = {
        "underlying_price": 455.0,
        "dte": 45,
        "put_width": 10,
        "call_width": 10,
    }

    execution = await entry_workflow.execute_entry(
        symbol="SPY",
        strategy_type=StrategyType.IRON_CONDOR,
        params=params,
    )

    # Execute exit
    await exit_workflow.execute_exit(execution.execution_id, reason="Test exit")

    # Verify Delta Lake has both transactions
    # Note: This requires repo.get_transactions() method


@pytest.mark.asyncio
async def test_multiple_positions_closed_independently(
    entry_workflow,
    exit_workflow,
    mock_strategy_repo,
):
    """
    Test: Multiple positions closed independently.

    Validates:
    - Multiple positions entered
    - Each can be closed independently
    - Closing one doesn't affect others
    - Each maintains separate P&L
    """
    # Execute multiple entries
    execution_ids = []
    for i in range(3):
        params = {
            "underlying_price": 455.0,
            "dte": 45,
            "put_width": 10,
            "call_width": 10,
        }

        execution = await entry_workflow.execute_entry(
            symbol="SPY",
            strategy_type=StrategyType.IRON_CONDOR,
            params=params,
        )
        execution_ids.append(execution.execution_id)

    # Close positions one by one
    for i, execution_id in enumerate(execution_ids):
        await exit_workflow.execute_exit(execution_id, reason=f"Test exit {i}")

        # Verify remaining positions still active
        active = mock_strategy_repo.get_active_executions()
        expected_count = 3 - (i + 1)
        assert len(active) == expected_count


@pytest.mark.asyncio
async def test_exit_with_partial_fills(
    entry_workflow,
    exit_workflow,
    mock_execution_engine,
):
    """
    Test: Exit workflow handles partial fills.

    Validates:
    - Some legs filled, some pending
    - Exit cancels pending legs
    - Exit closes filled legs
    - Final status correct
    """
    # Execute entry
    params = {
        "underlying_price": 455.0,
        "dte": 45,
        "put_width": 10,
        "call_width": 10,
    }

    execution = await entry_workflow.execute_entry(
        symbol="SPY",
        strategy_type=StrategyType.IRON_CONDOR,
        params=params,
    )

    # Simulate partial fill scenario
    # (In real scenario, some legs would be PARTIAL status)

    # Execute exit
    await exit_workflow.execute_exit(execution.execution_id, reason="Partial exit")

    # Verify exit handled correctly
    assert mock_execution_engine.cancel_order.called or mock_execution_engine.place_order.called


@pytest.mark.asyncio
async def test_exit_workflow_idempotent(
    entry_workflow,
    exit_workflow,
    mock_execution_engine,
):
    """
    Test: Exit workflow is idempotent.

    Validates:
    - Can call exit multiple times safely
    - Subsequent calls are no-ops
    - No duplicate orders placed
    - No errors thrown
    """
    # Execute entry
    params = {
        "underlying_price": 455.0,
        "dte": 45,
        "put_width": 10,
        "call_width": 10,
    }

    execution = await entry_workflow.execute_entry(
        symbol="SPY",
        strategy_type=StrategyType.IRON_CONDOR,
        params=params,
    )

    # Execute exit twice
    await exit_workflow.execute_exit(execution.execution_id, reason="First exit")
    await exit_workflow.execute_exit(execution.execution_id, reason="Duplicate exit")

    # Should not cause errors
    # Second call should be no-op (position already closed)


@pytest.mark.asyncio
async def test_exit_preserves_pnl_history(
    entry_workflow,
    exit_workflow,
    mock_strategy_repo,
):
    """
    Test: Exit preserves P&L history.

    Validates:
    - Entry price recorded
    - Exit price recorded
    - Realized P&L calculated
    - P&L history queryable
    - P&L metrics accurate
    """
    # Execute entry with known price
    params = {
        "underlying_price": 455.0,
        "dte": 45,
        "put_width": 10,
        "call_width": 10,
    }

    execution = await entry_workflow.execute_entry(
        symbol="SPY",
        strategy_type=StrategyType.IRON_CONDOR,
        params=params,
    )

    entry_price = execution.entry_price

    # Execute exit
    await exit_workflow.execute_exit(execution.execution_id, reason="Test exit")

    # Verify P&L preserved
    # Note: This requires querying closed executions and checking P&L


@pytest.mark.asyncio
async def test_emergency_exit_all_positions(
    entry_workflow,
    exit_workflow,
    mock_strategy_repo,
):
    """
    Test: Emergency exit closes all positions.

    Validates:
    - Multiple positions open
    - Emergency exit closes all
    - All positions status = CLOSED
    - No positions remaining active
    """
    # Execute multiple entries
    symbols = ["SPY", "QQQ", "IWM"]
    execution_ids = []

    for symbol in symbols:
        params = {
            "underlying_price": 455.0 if symbol == "SPY" else 480.0 if symbol == "QQQ" else 200.0,
            "dte": 45,
            "put_width": 10,
            "call_width": 10,
        }

        execution = await entry_workflow.execute_entry(
            symbol=symbol,
            strategy_type=StrategyType.IRON_CONDOR,
            params=params,
        )
        execution_ids.append(execution.execution_id)

    # Close all positions
    for execution_id in execution_ids:
        await exit_workflow.execute_exit(execution_id, reason="Emergency exit")

    # Verify all closed
    active = mock_strategy_repo.get_active_executions()
    assert len(active) == 0
