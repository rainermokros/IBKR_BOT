"""
Tests for EntryWorkflow with portfolio limits integration

Tests the integration of PortfolioLimitsChecker with EntryWorkflow,
ensuring that entries are properly validated against portfolio limits
before orders are placed.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock
from datetime import datetime, date
from uuid import uuid4

from src.v6.workflows.entry import EntryWorkflow
from src.v6.strategies.models import (
    LegAction,
    LegSpec,
    OptionRight,
    Strategy,
    StrategyType,
    ExecutionStatus,
    LegStatus,
)
from src.v6.risk.models import PortfolioLimitExceededError, RiskLimitsConfig
from src.v6.decisions.portfolio_risk import (
    PortfolioGreeks,
    PortfolioRisk,
    ExposureMetrics,
)

# Alias for backward compatibility
PortfolioLimitExceeded = PortfolioLimitExceededError


@pytest.fixture
def mock_decision_engine():
    """Create mock DecisionEngine."""
    mock = MagicMock()
    return mock


@pytest.fixture
def mock_execution_engine():
    """Create mock OrderExecutionEngine."""
    mock = MagicMock()
    mock.place_order = AsyncMock()
    return mock


@pytest.fixture
def mock_strategy_builder():
    """Create mock StrategyBuilder."""
    mock = MagicMock()

    # Create sample strategy
    strategy = Strategy(
        strategy_id="test-strategy-1",
        symbol="SPY",
        strategy_type=StrategyType.IRON_CONDOR,
        legs=[
            LegSpec(
                right=OptionRight.PUT,
                strike=450.0,
                quantity=1,
                action=LegAction.SELL,
                expiration=date(2026, 3, 20),
            ),
            LegSpec(
                right=OptionRight.PUT,
                strike=440.0,
                quantity=1,
                action=LegAction.BUY,
                expiration=date(2026, 3, 20),
            ),
            LegSpec(
                right=OptionRight.CALL,
                strike=460.0,
                quantity=1,
                action=LegAction.SELL,
                expiration=date(2026, 3, 20),
            ),
            LegSpec(
                right=OptionRight.CALL,
                strike=470.0,
                quantity=1,
                action=LegAction.BUY,
                expiration=date(2026, 3, 20),
            ),
        ],
    )
    mock.build = Mock(return_value=strategy)
    mock.validate = Mock(return_value=True)
    return mock


@pytest.fixture
def mock_strategy_repo():
    """Create mock StrategyRepository."""
    mock = MagicMock()
    mock.save_execution = AsyncMock()
    return mock


@pytest.fixture
def mock_portfolio_limits_checker():
    """Create mock PortfolioLimitsChecker."""
    mock = MagicMock()
    mock.check_entry_allowed = AsyncMock(return_value=(True, None))
    return mock


@pytest.fixture
def empty_portfolio_risk():
    """Create PortfolioRisk for empty portfolio."""
    return PortfolioRisk(
        greeks=PortfolioGreeks(
            delta=0.0,
            gamma=0.0,
            theta=0.0,
            vega=0.0,
            delta_per_symbol={},
            gamma_per_symbol={},
        ),
        exposure=ExposureMetrics(
            total_exposure=0.0,
            max_single_position=0.0,
            correlated_exposure={},
            buying_power_used=0.0,
            buying_power_available=100000.0,
        ),
        position_count=0,
        symbol_count=0,
        calculated_at=datetime.now(),
    )


@pytest.mark.asyncio
async def test_entry_workflow_without_portfolio_limits(
    mock_decision_engine,
    mock_execution_engine,
    mock_strategy_builder,
    mock_strategy_repo,
):
    """Test that EntryWorkflow works without portfolio_limits (backward compatible)."""
    # Create workflow without portfolio limits
    workflow = EntryWorkflow(
        decision_engine=mock_decision_engine,
        execution_engine=mock_execution_engine,
        strategy_builder=mock_strategy_builder,
        strategy_repo=mock_strategy_repo,
        portfolio_limits=None,  # No portfolio limits checker
    )

    # Mock successful order placement
    mock_order = MagicMock()
    mock_order.order_id = str(uuid4())
    mock_order.status = MagicMock()
    mock_order.conId = 123456
    mock_order.avg_fill_price = 1.50
    mock_order.filled_at = datetime.now()
    mock_execution_engine.place_order.return_value = mock_order

    # Execute entry
    params = {
        "underlying_price": 455.0,
        "dte": 45,
        "put_width": 10,
        "call_width": 10,
    }

    execution = await workflow.execute_entry(
        symbol="SPY",
        strategy_type=StrategyType.IRON_CONDOR,
        params=params,
    )

    # Verify execution was created
    assert execution is not None
    assert execution.symbol == "SPY"
    assert execution.strategy_type == StrategyType.IRON_CONDOR

    # Verify strategy builder was called
    mock_strategy_builder.build.assert_called_once()
    mock_strategy_builder.validate.assert_called_once()

    # Verify orders were placed (4 legs for iron condor)
    assert mock_execution_engine.place_order.call_count == 4

    # Verify execution was saved
    mock_strategy_repo.save_execution.assert_called_once()


@pytest.mark.asyncio
async def test_entry_allowed_by_portfolio_limits(
    mock_decision_engine,
    mock_execution_engine,
    mock_strategy_builder,
    mock_strategy_repo,
    mock_portfolio_limits_checker,
):
    """Test that entry proceeds when portfolio limits allow it."""
    # Setup portfolio limits checker to allow entry
    mock_portfolio_limits_checker.check_entry_allowed = AsyncMock(
        return_value=(True, None)
    )

    # Create workflow with portfolio limits
    workflow = EntryWorkflow(
        decision_engine=mock_decision_engine,
        execution_engine=mock_execution_engine,
        strategy_builder=mock_strategy_builder,
        strategy_repo=mock_strategy_repo,
        portfolio_limits=mock_portfolio_limits_checker,
    )

    # Mock successful order placement
    mock_order = MagicMock()
    mock_order.order_id = str(uuid4())
    mock_order.status = MagicMock()
    mock_order.conId = 123456
    mock_order.avg_fill_price = 1.50
    mock_order.filled_at = datetime.now()
    mock_execution_engine.place_order.return_value = mock_order

    # Execute entry
    params = {
        "underlying_price": 455.0,
        "dte": 45,
        "put_width": 10,
        "call_width": 10,
    }

    execution = await workflow.execute_entry(
        symbol="SPY",
        strategy_type=StrategyType.IRON_CONDOR,
        params=params,
    )

    # Verify portfolio limits were checked
    mock_portfolio_limits_checker.check_entry_allowed.assert_called_once()

    # Get the call arguments
    call_args = mock_portfolio_limits_checker.check_entry_allowed.call_args
    assert call_args is not None

    # Verify the check was called with reasonable parameters
    # position_delta should be sum of SELL legs (2 SELL legs in iron condor)
    # position_value should be sum of strike * quantity * 100
    assert call_args[1]["symbol"] == "SPY"
    assert "new_position_delta" in call_args[1]
    assert "position_value" in call_args[1]
    assert "symbol" in call_args[1]

    # Verify execution was created (entry allowed)
    assert execution is not None
    assert execution.symbol == "SPY"

    # Verify orders were placed
    assert mock_execution_engine.place_order.call_count == 4


@pytest.mark.asyncio
async def test_entry_rejected_by_portfolio_limits(
    mock_decision_engine,
    mock_execution_engine,
    mock_strategy_builder,
    mock_strategy_repo,
    mock_portfolio_limits_checker,
):
    """Test that entry is rejected when portfolio limits are exceeded."""
    # Setup portfolio limits checker to reject entry
    mock_portfolio_limits_checker.check_entry_allowed = AsyncMock(
        return_value=(
            False,
            "Portfolio delta would exceed limit: 55.00 > 50.00",
        )
    )

    # Create workflow with portfolio limits
    workflow = EntryWorkflow(
        decision_engine=mock_decision_engine,
        execution_engine=mock_execution_engine,
        strategy_builder=mock_strategy_builder,
        strategy_repo=mock_strategy_repo,
        portfolio_limits=mock_portfolio_limits_checker,
    )

    # Execute entry - should raise PortfolioLimitExceeded
    params = {
        "underlying_price": 455.0,
        "dte": 45,
        "put_width": 10,
        "call_width": 10,
    }

    with pytest.raises(PortfolioLimitExceeded) as exc_info:
        await workflow.execute_entry(
            symbol="SPY",
            strategy_type=StrategyType.IRON_CONDOR,
            params=params,
        )

    # Verify exception contains rejection reason
    assert "Portfolio delta would exceed limit" in str(exc_info.value)

    # Verify portfolio limits were checked
    mock_portfolio_limits_checker.check_entry_allowed.assert_called_once()

    # Verify no orders were placed
    mock_execution_engine.place_order.assert_not_called()

    # Verify execution was NOT saved
    mock_strategy_repo.save_execution.assert_not_called()


@pytest.mark.asyncio
async def test_entry_portfolio_limits_delta_calculation(
    mock_decision_engine,
    mock_execution_engine,
    mock_strategy_builder,
    mock_strategy_repo,
    mock_portfolio_limits_checker,
):
    """Test that delta is correctly calculated for portfolio limits check."""
    # Create workflow with portfolio limits
    workflow = EntryWorkflow(
        decision_engine=mock_decision_engine,
        execution_engine=mock_execution_engine,
        strategy_builder=mock_strategy_builder,
        strategy_repo=mock_strategy_repo,
        portfolio_limits=mock_portfolio_limits_checker,
    )

    # Mock successful order placement
    mock_order = MagicMock()
    mock_order.order_id = str(uuid4())
    mock_order.status = MagicMock()
    mock_execution_engine.place_order.return_value = mock_order

    # Execute entry
    params = {
        "underlying_price": 455.0,
        "dte": 45,
        "put_width": 10,
        "call_width": 10,
    }

    await workflow.execute_entry(
        symbol="SPY",
        strategy_type=StrategyType.IRON_CONDOR,
        params=params,
    )

    # Get the call arguments
    call_args = mock_portfolio_limits_checker.check_entry_allowed.call_args
    position_delta = call_args[1]["new_position_delta"]

    # For iron condor: 2 SELL legs - 2 BUY legs
    # Delta calculation: SELL legs add positive delta, BUY legs subtract
    # Expected: 1 (SELL PUT) + 1 (SELL CALL) - 1 (BUY PUT) - 1 (BUY CALL) = 0
    assert position_delta == 0.0


@pytest.mark.asyncio
async def test_entry_portfolio_limits_position_value_calculation(
    mock_decision_engine,
    mock_execution_engine,
    mock_strategy_builder,
    mock_strategy_repo,
    mock_portfolio_limits_checker,
):
    """Test that position value is correctly calculated for portfolio limits check."""
    # Create workflow with portfolio limits
    workflow = EntryWorkflow(
        decision_engine=mock_decision_engine,
        execution_engine=mock_execution_engine,
        strategy_builder=mock_strategy_builder,
        strategy_repo=mock_strategy_repo,
        portfolio_limits=mock_portfolio_limits_checker,
    )

    # Mock successful order placement
    mock_order = MagicMock()
    mock_order.order_id = str(uuid4())
    mock_order.status = MagicMock()
    mock_execution_engine.place_order.return_value = mock_order

    # Execute entry
    params = {
        "underlying_price": 455.0,
        "dte": 45,
        "put_width": 10,
        "call_width": 10,
    }

    await workflow.execute_entry(
        symbol="SPY",
        strategy_type=StrategyType.IRON_CONDOR,
        params=params,
    )

    # Get the call arguments
    call_args = mock_portfolio_limits_checker.check_entry_allowed.call_args
    position_value = call_args[1]["position_value"]

    # Position value = sum(strike * quantity * 100) for all legs
    # Iron condor legs: 450 PUT, 440 PUT, 460 CALL, 470 CALL
    # Each with quantity 1
    # Expected: (450 + 440 + 460 + 470) * 1 * 100 = 182,000
    expected_value = (450.0 + 440.0 + 460.0 + 470.0) * 100
    assert position_value == pytest.approx(expected_value, rel=0.01)


@pytest.mark.asyncio
async def test_entry_rejection_before_order_placement(
    mock_decision_engine,
    mock_execution_engine,
    mock_strategy_builder,
    mock_strategy_repo,
    mock_portfolio_limits_checker,
):
    """Test that when portfolio limits reject entry, no orders are placed."""
    # Setup portfolio limits checker to reject entry
    rejection_reason = "Symbol SPY delta would exceed limit: 25.00 > 20.00"
    mock_portfolio_limits_checker.check_entry_allowed = AsyncMock(
        return_value=(False, rejection_reason)
    )

    # Create workflow with portfolio limits
    workflow = EntryWorkflow(
        decision_engine=mock_decision_engine,
        execution_engine=mock_execution_engine,
        strategy_builder=mock_strategy_builder,
        strategy_repo=mock_strategy_repo,
        portfolio_limits=mock_portfolio_limits_checker,
    )

    # Execute entry - should raise PortfolioLimitExceeded
    params = {
        "underlying_price": 455.0,
        "dte": 45,
        "put_width": 10,
        "call_width": 10,
    }

    with pytest.raises(PortfolioLimitExceeded):
        await workflow.execute_entry(
            symbol="SPY",
            strategy_type=StrategyType.IRON_CONDOR,
            params=params,
        )

    # Verify strategy was built and validated
    mock_strategy_builder.build.assert_called_once()
    mock_strategy_builder.validate.assert_called_once()

    # Verify NO orders were placed (rejection happened before orders)
    mock_execution_engine.place_order.assert_not_called()

    # Verify execution was NOT saved
    mock_strategy_repo.save_execution.assert_not_called()


@pytest.mark.asyncio
async def test_entry_workflow_backward_compatibility(
    mock_decision_engine,
    mock_execution_engine,
    mock_strategy_builder,
    mock_strategy_repo,
):
    """Test that EntryWorkflow works exactly as before when portfolio_limits is None."""
    # Create workflow without portfolio limits (old API)
    workflow = EntryWorkflow(
        decision_engine=mock_decision_engine,
        execution_engine=mock_execution_engine,
        strategy_builder=mock_strategy_builder,
        strategy_repo=mock_strategy_repo,
        # Note: portfolio_limits parameter not provided (defaults to None)
    )

    # Mock successful order placement
    mock_order = MagicMock()
    mock_order.order_id = str(uuid4())
    mock_order.status = MagicMock()
    mock_order.conId = 123456
    mock_order.avg_fill_price = 1.50
    mock_order.filled_at = datetime.now()
    mock_execution_engine.place_order.return_value = mock_order

    # Execute entry
    params = {
        "underlying_price": 455.0,
        "dte": 45,
        "put_width": 10,
        "call_width": 10,
    }

    execution = await workflow.execute_entry(
        symbol="SPY",
        strategy_type=StrategyType.IRON_CONDOR,
        params=params,
    )

    # Verify execution was created successfully
    assert execution is not None
    assert execution.symbol == "SPY"

    # Verify orders were placed
    assert mock_execution_engine.place_order.call_count == 4

    # Verify execution was saved
    mock_strategy_repo.save_execution.assert_called_once()
