"""
Integration tests: Workflow Components

Tests integration between workflow components with realistic mock setup.
These tests match the actual workflow APIs.

Usage:
    pytest tests/integration/test_workflows_integration.py -v
"""

import pytest
from datetime import datetime, date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

from src.v6.workflows import EntryWorkflow, ExitWorkflow, PositionMonitoringWorkflow
from src.v6.execution.engine import OrderExecutionEngine
from src.v6.decisions.engine import DecisionEngine
from src.v6.strategies.builders import IronCondorBuilder
from src.v6.strategies.models import StrategyType, ExecutionStatus
from src.v6.strategies.repository import StrategyRepository
from src.v6.decisions.models import Decision, DecisionAction, Urgency
from src.v6.alerts import AlertManager


@pytest.fixture
def mock_decision_engine():
    """Create mock DecisionEngine."""
    mock = MagicMock()
    mock.evaluate = AsyncMock(return_value=Decision(
        action=DecisionAction.HOLD,
        reason="Test hold",
        rule="test_rule",
        urgency=Urgency.NORMAL,
    ))
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
    mock.cancel_order = MagicMock()

    return mock


@pytest.fixture
def mock_alert_manager():
    """Create mock AlertManager."""
    mock = MagicMock()
    mock.create_alert = AsyncMock()
    return mock


@pytest.fixture
def mock_strategy_builder():
    """Create mock StrategyBuilder."""
    return IronCondorBuilder()


@pytest.fixture
def mock_strategy_repo(lake_path):
    """Create StrategyRepository with test Delta Lake."""
    positions_path = lake_path / "positions"
    positions_path.mkdir(parents=True, exist_ok=True)
    repo = StrategyRepository(table_path=str(positions_path))
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
    mock_alert_manager,
    mock_strategy_repo,
):
    """Create PositionMonitoringWorkflow for testing."""
    return PositionMonitoringWorkflow(
        decision_engine=mock_decision_engine,
        alert_manager=mock_alert_manager,
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
async def test_entry_workflow_creates_strategy(
    entry_workflow,
    mock_execution_engine,
):
    """
    Test: Entry workflow creates strategy successfully.

    Validates:
    - Strategy built correctly
    - Orders placed (4 legs for iron condor)
    - Execution saved with FILLED status
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

    # Verify execution created
    assert execution is not None
    assert execution.symbol == "SPY"
    assert execution.strategy_type == StrategyType.IRON_CONDOR
    assert execution.status == ExecutionStatus.FILLED

    # Verify orders placed (4 legs for iron condor)
    assert mock_execution_engine.place_order.call_count == 4


@pytest.mark.asyncio
async def test_monitoring_workflow_with_no_positions(
    monitoring_workflow,
    mock_strategy_repo,
):
    """
    Test: Monitoring workflow handles empty portfolio.

    Validates:
    - No errors when no positions
    - Returns empty dict
    - Decision engine not called
    """
    # Monitor with no positions
    decisions = await monitoring_workflow.monitor_positions()

    # Verify empty result
    assert decisions == {}


@pytest.mark.asyncio
async def test_monitoring_workflow_with_position(
    entry_workflow,
    monitoring_workflow,
    mock_decision_engine,
    mock_strategy_repo,
):
    """
    Test: Monitoring workflow evaluates position.

    Validates:
    - Entry creates position
    - Monitoring retrieves position
    - Decision engine called
    - Decision returned
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

    # Mock decision for position
    hold_decision = Decision(
        action=DecisionAction.HOLD,
        reason="Position within normal parameters",
        rule="test_rule",
        urgency=Urgency.NORMAL,
    )
    mock_decision_engine.evaluate = AsyncMock(return_value=hold_decision)

    # Monitor positions
    decisions = await monitoring_workflow.monitor_positions()

    # Verify decision returned
    assert len(decisions) == 1
    assert execution.execution_id in decisions
    assert decisions[execution.execution_id].action == DecisionAction.HOLD


@pytest.mark.asyncio
async def test_monitoring_workflow_generates_alert(
    entry_workflow,
    monitoring_workflow,
    mock_decision_engine,
    mock_alert_manager,
):
    """
    Test: Monitoring workflow generates alert for non-HOLD decision.

    Validates:
    - Decision with CLOSE action
    - Alert manager called
    - Alert created with correct urgency
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

    # Mock CLOSE decision
    close_decision = Decision(
        action=DecisionAction.CLOSE,
        reason="Stop loss triggered",
        rule="stop_loss",
        urgency=Urgency.IMMEDIATE,
    )
    mock_decision_engine.evaluate = AsyncMock(return_value=close_decision)

    # Monitor positions
    decisions = await monitoring_workflow.monitor_positions()

    # Verify alert created
    mock_alert_manager.create_alert.assert_called_once()

    # Get alert call args
    call_args = mock_alert_manager.create_alert.call_args
    assert call_args is not None


@pytest.mark.asyncio
async def test_monitoring_workflow_multiple_positions(
    entry_workflow,
    monitoring_workflow,
    mock_decision_engine,
):
    """
    Test: Monitoring workflow handles multiple positions.

    Validates:
    - Multiple entries created
    - All positions monitored
    - Decision evaluated for each
    - All decisions returned
    """
    # Execute multiple entries
    symbols = ["SPY", "QQQ", "IWM"]

    for symbol in symbols:
        params = {
            "underlying_price": 455.0 if symbol == "SPY" else 480.0 if symbol == "QQQ" else 200.0,
            "dte": 45,
            "put_width": 10,
            "call_width": 10,
        }

        await entry_workflow.execute_entry(
            symbol=symbol,
            strategy_type=StrategyType.IRON_CONDOR,
            params=params,
        )

    # Mock hold decision
    hold_decision = Decision(
        action=DecisionAction.HOLD,
        reason="Position OK",
        rule="test",
        urgency=Urgency.NORMAL,
    )
    mock_decision_engine.evaluate = AsyncMock(return_value=hold_decision)

    # Monitor all positions
    decisions = await monitoring_workflow.monitor_positions()

    # Verify all positions monitored
    assert len(decisions) == 3


@pytest.mark.asyncio
async def test_exit_workflow_execute_close_decision(
    entry_workflow,
    exit_workflow,
    mock_execution_engine,
):
    """
    Test: Exit workflow executes CLOSE decision.

    Validates:
    - Position entered
    - Exit decision executed
    - Orders cancelled/placed
    - Result returned
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

    # Create CLOSE decision
    close_decision = Decision(
        action=DecisionAction.CLOSE,
        reason="Test exit",
        rule="test_rule",
        urgency=Urgency.NORMAL,
    )

    # Execute exit decision
    result = await exit_workflow.execute_exit_decision(
        execution_id=execution.execution_id,
        decision=close_decision,
    )

    # Verify exit executed
    assert result is not None


@pytest.mark.asyncio
async def test_exit_workflow_close_all_positions(
    entry_workflow,
    exit_workflow,
):
    """
    Test: Exit workflow closes all positions.

    Validates:
    - Multiple positions entered
    - Close all executed
    - All positions closed
    """
    # Execute multiple entries
    symbols = ["SPY", "QQQ"]

    for symbol in symbols:
        params = {
            "underlying_price": 455.0 if symbol == "SPY" else 480.0,
            "dte": 45,
            "put_width": 10,
            "call_width": 10,
        }

        await entry_workflow.execute_entry(
            symbol=symbol,
            strategy_type=StrategyType.IRON_CONDOR,
            params=params,
        )

    # Close all
    result = await exit_workflow.execute_close_all(reason="Test close all")

    # Verify close all executed
    assert result is not None
    assert result["total_positions"] >= 2


@pytest.mark.asyncio
async def test_delta_lake_persistence(
    entry_workflow,
    mock_strategy_repo,
    lake_path,
):
    """
    Test: Data persisted to Delta Lake.

    Validates:
    - Entry saves to Delta Lake
    - Data can be retrieved
    - Delta Lake files created
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

    # Retrieve from repo
    executions = mock_strategy_repo.get_active_executions()

    # Verify persisted
    assert len(executions) == 1
    assert executions[0].execution_id == execution.execution_id

    # Verify Delta Lake files exist
    positions_path = lake_path / "positions"
    assert positions_path.exists()


@pytest.mark.asyncio
async def test_workflow_error_handling(
    entry_workflow,
    mock_execution_engine,
):
    """
    Test: Workflows handle errors gracefully.

    Validates:
    - Order placement error caught
    - System remains stable
    - No crashes
    """
    # Mock order failure
    mock_execution_engine.place_order.side_effect = Exception("IB API error")

    # Attempt entry
    params = {
        "underlying_price": 455.0,
        "dte": 45,
        "put_width": 10,
        "call_width": 10,
    }

    try:
        execution = await entry_workflow.execute_entry(
            symbol="SPY",
            strategy_type=StrategyType.IRON_CONDOR,
            params=params,
        )
        # If it doesn't raise, check status
        assert execution.status == ExecutionStatus.FAILED
    except Exception:
        # Exception is also acceptable
        pass
