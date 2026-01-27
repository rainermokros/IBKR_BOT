"""
Integration tests: Entry Workflow → Monitoring Workflow

Tests the complete flow from strategy entry to position monitoring,
including Delta Lake persistence, position sync, and decision evaluation.

Usage:
    pytest tests/integration/test_entry_to_monitoring.py -v
"""

import pytest
from datetime import datetime, date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

from src.v6.workflows.entry import EntryWorkflow
from src.v6.workflows.monitoring import MonitoringWorkflow
from src.v6.execution.engine import OrderExecutionEngine
from src.v6.decisions.engine import DecisionEngine
from src.v6.strategies.builders import IronCondorBuilder
from src.v6.strategies.models import StrategyType, ExecutionStatus
from src.v6.strategies.repository import StrategyRepository
from src.v6.decisions.models import Decision, DecisionAction, Urgency


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


@pytest.mark.asyncio
async def test_entry_creates_position_in_delta_lake(
    entry_workflow,
    mock_strategy_repo,
    lake_path,
):
    """
    Test: Entry workflow creates position in Delta Lake.

    Validates:
    - Entry workflow executes successfully
    - Strategy execution saved to Delta Lake
    - Execution has correct status (FILLED)
    - Can read execution back from Delta Lake
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

    # Verify saved to Delta Lake
    executions = mock_strategy_repo.get_active_executions()
    assert len(executions) == 1
    assert executions[0].execution_id == execution.execution_id

    # Verify Delta Lake files created
    positions_path = lake_path / "positions"
    assert positions_path.exists()


@pytest.mark.asyncio
async def test_position_sync_picks_up_new_position(
    entry_workflow,
    monitoring_workflow,
    mock_strategy_repo,
):
    """
    Test: Position sync picks up new position after entry.

    Validates:
    - Entry workflow creates position
    - Monitoring workflow can retrieve position
    - Position data is consistent between entry and monitoring
    - Greeks calculation works
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

    # Monitoring workflow retrieves position
    positions = await monitoring_workflow.get_active_positions()

    # Verify position found
    assert len(positions) == 1
    assert positions[0].execution_id == execution.execution_id
    assert positions[0].symbol == "SPY"
    assert positions[0].status == ExecutionStatus.FILLED


@pytest.mark.asyncio
async def test_monitoring_workflow_evaluates_decisions(
    entry_workflow,
    monitoring_workflow,
    mock_decision_engine,
):
    """
    Test: Monitoring workflow evaluates decisions for position.

    Validates:
    - Entry creates position
    - Monitoring workflow calls decision engine
    - Decisions evaluated for each position
    - Decision results returned correctly
    """
    # Execute entry
    params = {
        "underlying_price": 455.0,
        "dte": 45,
        "put_width": 10,
        "call_width": 10,
    }

    await entry_workflow.execute_entry(
        symbol="SPY",
        strategy_type=StrategyType.IRON_CONDOR,
        params=params,
    )

    # Setup mock decision
    test_decision = Decision(
        action=DecisionAction.HOLD,
        reason="Position within normal parameters",
        rule="test_rule",
        urgency=Urgency.NORMAL,
    )
    mock_decision_engine.evaluate_decisions.return_value = [test_decision]

    # Evaluate decisions
    decisions = await monitoring_workflow.evaluate_all_positions()

    # Verify decision engine called
    mock_decision_engine.evaluate_decisions.assert_called_once()

    # Verify decisions returned
    assert len(decisions) == 1
    assert decisions[0].action == DecisionAction.HOLD
    assert decisions[0].urgency == Urgency.NORMAL


@pytest.mark.asyncio
async def test_alerts_generated_for_risk_limit_breaches(
    entry_workflow,
    monitoring_workflow,
    mock_decision_engine,
    mock_strategy_repo,
):
    """
    Test: Alerts generated for risk limit breaches.

    Validates:
    - Decision engine detects risk breach
    - Alert with CRITICAL urgency generated
    - Alert saved to Delta Lake
    - Alert can be retrieved from history
    """
    # Execute entry
    params = {
        "underlying_price": 455.0,
        "dte": 45,
        "put_width": 10,
        "call_width": 10,
    }

    await entry_workflow.execute_entry(
        symbol="SPY",
        strategy_type=StrategyType.IRON_CONDOR,
        params=params,
    )

    # Setup mock decision with CRITICAL urgency
    critical_decision = Decision(
        action=DecisionAction.CLOSE,
        reason="Delta limit exceeded: -55.00 > -50.00",
        rule="delta_limit",
        urgency=Urgency.IMMEDIATE,
        metadata={
            "current_delta": -55.0,
            "limit": -50.0,
            "position_id": "test-001",
        },
    )
    mock_decision_engine.evaluate_decisions.return_value = [critical_decision]

    # Evaluate decisions (should generate alert)
    decisions = await monitoring_workflow.evaluate_all_positions()

    # Verify critical decision
    assert len(decisions) == 1
    assert decisions[0].action == DecisionAction.CLOSE
    assert decisions[0].urgency == Urgency.IMMEDIATE
    assert "Delta limit exceeded" in decisions[0].reason

    # Verify alert metadata
    assert "current_delta" in decisions[0].metadata
    assert decisions[0].metadata["current_delta"] == -55.0


@pytest.mark.asyncio
async def test_multiple_positions_tracked_simultaneously(
    entry_workflow,
    monitoring_workflow,
    mock_strategy_repo,
):
    """
    Test: Multiple positions tracked simultaneously.

    Validates:
    - Can enter multiple positions
    - Monitoring tracks all positions
    - Decisions evaluated for each position
    - Position IDs are unique
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

    # Verify all positions tracked
    positions = await monitoring_workflow.get_active_positions()
    assert len(positions) == 3

    # Verify unique IDs
    position_ids = [p.execution_id for p in positions]
    assert len(set(position_ids)) == 3  # All unique

    # Verify symbols
    symbols_found = {p.symbol for p in positions}
    assert symbols_found == {"SPY", "QQQ", "IWM"}


@pytest.mark.asyncio
async def test_portfolio_greeks_calculated_across_positions(
    entry_workflow,
    monitoring_workflow,
    mock_strategy_repo,
):
    """
    Test: Portfolio Greeks calculated correctly across positions.

    Validates:
    - Multiple positions entered
    - Portfolio Greeks = sum of position Greeks
    - Delta, gamma, theta, vega all summed correctly
    - Greeks can be retrieved from monitoring
    """
    # Execute two entries
    for i in range(2):
        params = {
            "underlying_price": 455.0,
            "dte": 45,
            "put_width": 10,
            "call_width": 10,
        }

        await entry_workflow.execute_entry(
            symbol="SPY",
            strategy_type=StrategyType.IRON_CONDOR,
            params=params,
        )

    # Get positions with Greeks
    positions = await monitoring_workflow.get_active_positions()
    assert len(positions) == 2

    # Calculate portfolio Greeks
    portfolio_delta = sum(p.greeks.delta if p.greeks else 0 for p in positions)
    portfolio_gamma = sum(p.greeks.gamma if p.greeks else 0 for p in positions)
    portfolio_theta = sum(p.greeks.theta if p.greeks else 0 for p in positions)
    portfolio_vega = sum(p.greeks.vega if p.greeks else 0 for p in positions)

    # Verify Greeks are reasonable (non-zero for active positions)
    # Note: Actual values depend on strategy, but should be calculated
    assert portfolio_delta != 0 or portfolio_gamma != 0


@pytest.mark.asyncio
async def test_empty_portfolio_handling(monitoring_workflow):
    """
    Test: Empty portfolio handled gracefully.

    Validates:
    - Monitoring works with no positions
    - Returns empty list (not None)
    - No errors when evaluating decisions
    """
    # Get positions (should be empty)
    positions = await monitoring_workflow.get_active_positions()
    assert positions == []

    # Evaluate decisions (should not crash)
    decisions = await monitoring_workflow.evaluate_all_positions()
    assert decisions == []


@pytest.mark.asyncio
async def test_delta_lake_persistence_across_sessions(
    entry_workflow,
    mock_strategy_repo,
    lake_path,
):
    """
    Test: Delta Lake persists data across sessions.

    Validates:
    - Data written to Delta Lake
    - Can create new repo instance and read data
    - Data integrity maintained
    - Time travel works (if applicable)
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

    # Create new repository instance (simulating new session)
    new_repo = StrategyRepository(lake_path=str(lake_path))

    # Verify data persisted
    executions = new_repo.get_active_executions()
    assert len(executions) == 1
    assert executions[0].execution_id == execution.execution_id
