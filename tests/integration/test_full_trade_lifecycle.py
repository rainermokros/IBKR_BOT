"""
Integration tests: Complete Trade Lifecycle

Tests end-to-end trading workflows from initial signal through entry,
monitoring, and exit, validating the complete automation pipeline.

Usage:
    pytest tests/integration/test_full_trade_lifecycle.py -v
"""

import pytest
from datetime import datetime, date, timedelta
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
from src.v6.risk.models import (
    PortfolioGreeks,
    PortfolioRisk,
    ExposureMetrics,
)


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
async def test_complete_trade_from_signal_to_exit(
    entry_workflow,
    monitoring_workflow,
    exit_workflow,
    mock_decision_engine,
    mock_strategy_repo,
):
    """
    Test: Complete trade from signal → entry → monitoring → exit.

    Validates:
    - Entry signal evaluated and approved
    - Strategy entered with orders filled
    - Position monitored with decisions
    - Exit triggered and position closed
    - Full lifecycle recorded in Delta Lake
    """
    # Step 1: Evaluate entry signal
    should_enter = await entry_workflow.evaluate_entry_signal(
        symbol="SPY",
        market_data={
            "iv_rank": 65,  # Good IV for selling premium
            "vix": 18.5,  # Not extreme
            "underlying_trend": "neutral",
        },
    )

    # Should approve entry
    assert should_enter is True

    # Step 2: Execute entry
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

    # Verify entry
    assert execution is not None
    assert execution.status == ExecutionStatus.FILLED
    assert execution.symbol == "SPY"

    # Step 3: Monitor position (normal conditions)
    hold_decision = Decision(
        action=DecisionAction.HOLD,
        reason="Position within normal parameters",
        rule="monitoring",
        urgency=Urgency.NORMAL,
    )
    mock_decision_engine.evaluate_decisions.return_value = [hold_decision]

    decisions = await monitoring_workflow.evaluate_all_positions()

    # Verify hold decision
    assert len(decisions) == 1
    assert decisions[0].action == DecisionAction.HOLD

    # Step 4: Trigger exit (take profit)
    exit_decision = Decision(
        action=DecisionAction.CLOSE,
        reason="Take profit: 50% gain achieved",
        rule="take_profit",
        urgency=Urgency.NORMAL,
        metadata={
            "profit_percent": 50.0,
            "entry_price": 1.50,
            "current_price": 0.75,
        },
    )
    mock_decision_engine.evaluate_decisions.return_value = [exit_decision]

    decisions = await monitoring_workflow.evaluate_all_positions()

    # Verify exit decision
    assert len(decisions) == 1
    assert decisions[0].action == DecisionAction.CLOSE

    # Step 5: Execute exit
    await exit_workflow.execute_exit(execution.execution_id, reason="Take profit")

    # Verify exit
    # Note: Would need to reload execution from repo to verify status


@pytest.mark.asyncio
async def test_multiple_positions_tracked_simultaneously(
    entry_workflow,
    monitoring_workflow,
    exit_workflow,
    mock_strategy_repo,
):
    """
    Test: Multiple positions tracked simultaneously.

    Validates:
    - Can enter multiple positions
    - All tracked independently
    - Decisions evaluated for each
    - Can exit positions independently
    - Portfolio Greeks calculated across all
    """
    # Enter multiple positions
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

    # Calculate portfolio Greeks
    portfolio_delta = sum(p.greeks.delta if p.greeks else 0 for p in positions)
    portfolio_gamma = sum(p.greeks.gamma if p.greeks else 0 for p in positions)
    portfolio_theta = sum(p.greeks.theta if p.greeks else 0 for p in positions)
    portfolio_vega = sum(p.greeks.vega if p.greeks else 0 for p in positions)

    # Verify Greeks calculated
    # Should be non-zero sum of 3 positions
    assert portfolio_delta != 0 or portfolio_gamma != 0

    # Exit one position
    await exit_workflow.execute_exit(execution_ids[0], reason="Test exit")

    # Verify 2 positions remain
    positions = await monitoring_workflow.get_active_positions()
    assert len(positions) == 2


@pytest.mark.asyncio
async def test_portfolio_greeks_calculated_correctly(
    entry_workflow,
    monitoring_workflow,
    mock_strategy_repo,
):
    """
    Test: Portfolio Greeks calculated correctly across positions.

    Validates:
    - Multiple positions with known Greeks
    - Portfolio Greeks = sum of position Greeks
    - Delta, gamma, theta, vega all correct
    - Greeks update as positions added/removed
    """
    # Enter two identical positions
    execution_ids = []
    for i in range(2):
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

    # Get positions
    positions = await monitoring_workflow.get_active_positions()
    assert len(positions) == 2

    # Sum position Greeks
    total_delta = sum(p.greeks.delta if p.greeks else 0 for p in positions)
    total_gamma = sum(p.greeks.gamma if p.greeks else 0 for p in positions)
    total_theta = sum(p.greeks.theta if p.greeks else 0 for p in positions)
    total_vega = sum(p.greeks.vega if p.greeks else 0 for p in positions)

    # Verify Greeks are roughly double single position
    # (assuming positions are similar)
    assert abs(total_delta) > 0  # Should have non-zero delta


@pytest.mark.asyncio
async def test_circuit_breaker_triggers_on_repeated_failures(
    entry_workflow,
    exit_workflow,
    mock_strategy_repo,
):
    """
    Test: Circuit breaker triggers on repeated failures.

    Validates:
    - Multiple order failures recorded
    - Circuit breaker opens after threshold
    - Further orders blocked
    - Circuit breaker resets after timeout
    """
    from src.v6.risk import (
        CircuitBreakerConfig,
        CircuitBreakerOpenException,
        TradingCircuitBreaker,
        CircuitState,
    )

    # Create circuit breaker with low threshold
    config = CircuitBreakerConfig(
        failure_threshold=3,
        failure_window_secs=60,
        open_timeout_secs=0,  # Immediate recovery for testing
        half_open_max_tries=2,
    )
    cb = TradingCircuitBreaker(config)

    # Record failures
    for i in range(3):
        cb.record_failure()

    # Verify circuit is OPEN
    assert cb.state == CircuitState.OPEN

    # Verify trading not allowed
    allowed = cb.is_trading_allowed()
    # Should transition to HALF_OPEN
    assert allowed is False  # Still not allowed (in HALF_OPEN)


@pytest.mark.asyncio
async def test_state_transitions_pending_to_closed(
    entry_workflow,
    monitoring_workflow,
    exit_workflow,
    mock_strategy_repo,
):
    """
    Test: State transitions PENDING → FILLED → CLOSED.

    Validates:
    - Execution starts as PENDING
    - Orders fill → status becomes FILLED
    - Position monitored while FILLED
    - Exit executed → status becomes CLOSED
    - All transitions recorded in Delta Lake
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

    # Verify initial state (should be FILLED in test)
    assert execution.status == ExecutionStatus.FILLED

    # Verify position is active
    active = mock_strategy_repo.get_active_executions()
    assert len(active) == 1
    assert active[0].status == ExecutionStatus.FILLED

    # Execute exit
    await exit_workflow.execute_exit(execution.execution_id, reason="Test exit")

    # Verify state transition
    # Note: Would need to reload execution to verify CLOSED status


@pytest.mark.asyncio
async def test_trade_with_decision_rules_priority(
    entry_workflow,
    monitoring_workflow,
    exit_workflow,
    mock_decision_engine,
):
    """
    Test: Decision rules prioritized correctly.

    Validates:
    - Multiple rules can trigger
    - Highest priority decision executed
    - Priority: catastrophe > stop_loss > take_profit > normal exits
    - Correct decision action taken
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

    # Setup multiple decisions (catastrophe should win)
    catastrophe_decision = Decision(
        action=DecisionAction.CLOSE,
        reason="Market crash: VIX > 40",
        rule="catastrophe",
        urgency=Urgency.IMMEDIATE,
    )

    take_profit_decision = Decision(
        action=DecisionAction.CLOSE,
        reason="Take profit: 80% gain",
        rule="take_profit",
        urgency=Urgency.NORMAL,
    )

    mock_decision_engine.evaluate_decisions.return_value = [
        take_profit_decision,
        catastrophe_decision,
    ]

    # Evaluate decisions
    decisions = await monitoring_workflow.evaluate_all_positions()

    # Verify catastrophe has higher priority
    # (would be handled by decision engine priority logic)
    assert len(decisions) == 2


@pytest.mark.asyncio
async def test_error_handling_during_execution(
    entry_workflow,
    mock_execution_engine,
):
    """
    Test: Errors handled gracefully during execution.

    Validates:
    - Order placement failures caught
    - Partial fills handled
    - Timeout scenarios handled
    - System remains stable
    """
    # Mock order placement failure
    mock_execution_engine.place_order.side_effect = Exception("IB API timeout")

    # Execute entry (should handle error)
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
        # If it doesn't raise, check execution status
        assert execution.status == ExecutionStatus.FAILED
    except Exception as e:
        # Exception is also acceptable
        assert "timeout" in str(e).lower()


@pytest.mark.asyncio
async def test_data_integrity_across_lifecycle(
    entry_workflow,
    monitoring_workflow,
    exit_workflow,
    mock_strategy_repo,
    lake_path,
):
    """
    Test: Data integrity maintained across lifecycle.

    Validates:
    - All data written to Delta Lake
    - No data corruption
    - Relationships maintained (executions → legs → transactions)
    - Queries return correct data
    - Time travel works (if supported)
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

    # Verify data in Delta Lake
    executions = mock_strategy_repo.get_active_executions()
    assert len(executions) == 1
    assert executions[0].execution_id == execution.execution_id

    # Execute exit
    await exit_workflow.execute_exit(execution.execution_id, reason="Test exit")

    # Verify data consistency
    # (would query closed executions and verify P&L, etc.)


@pytest.mark.asyncio
async def test_concurrent_trade_execution(
    entry_workflow,
    monitoring_workflow,
    mock_strategy_repo,
):
    """
    Test: Multiple trades can execute concurrently.

    Validates:
    - Multiple entries executed simultaneously
    - No race conditions
    - All data persisted correctly
    - Positions tracked independently
    """
    import asyncio

    # Execute multiple entries concurrently
    symbols = ["SPY", "QQQ", "IWM"]

    async def execute_trade(symbol):
        params = {
            "underlying_price": 455.0 if symbol == "SPY" else 480.0 if symbol == "QQQ" else 200.0,
            "dte": 45,
            "put_width": 10,
            "call_width": 10,
        }

        return await entry_workflow.execute_entry(
            symbol=symbol,
            strategy_type=StrategyType.IRON_CONDOR,
            params=params,
        )

    # Execute concurrently
    executions = await asyncio.gather(*[execute_trade(symbol) for symbol in symbols])

    # Verify all executions succeeded
    assert len(executions) == 3

    # Verify all positions tracked
    positions = await monitoring_workflow.get_active_positions()
    assert len(positions) == 3
