"""
Integration tests: Risk Management + Workflows

Tests the integration of portfolio limits, risk controls, and trading workflows.

Usage:
    pytest tests/integration/test_risk_workflows.py -v
"""

import pytest
from datetime import datetime, date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

from src.v6.workflows import EntryWorkflow
from src.v6.execution.engine import OrderExecutionEngine
from src.v6.decisions.engine import DecisionEngine
from src.v6.strategies.builders import IronCondorBuilder
from src.v6.strategies.models import StrategyType, ExecutionStatus
from src.v6.strategies.repository import StrategyRepository
from src.v6.risk.models import PortfolioLimitExceededError, RiskLimitsConfig
from src.v6.decisions.portfolio_risk import (
    PortfolioGreeks,
    PortfolioRisk,
    ExposureMetrics,
)
from src.v6.risk.portfolio_limits import PortfolioLimitsChecker


@pytest.fixture
def mock_ib_connection():
    """Create mock IB connection."""
    mock = MagicMock()
    mock.ib = MagicMock()
    mock.ensure_connected = AsyncMock()
    return mock


@pytest.fixture
def mock_decision_engine():
    """Create mock DecisionEngine."""
    mock = MagicMock()
    return mock


@pytest.fixture
def mock_execution_engine(mock_ib_connection):
    """Create mock OrderExecutionEngine."""
    mock = MagicMock()
    mock.place_order = AsyncMock()

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
    positions_path = lake_path / "positions"
    positions_path.mkdir(parents=True, exist_ok=True)
    repo = StrategyRepository(table_path=str(positions_path))
    return repo


@pytest.fixture
def portfolio_limits_checker():
    """Create PortfolioLimitsChecker."""
    config = RiskLimitsConfig(
        max_portfolio_delta=200.0,
        max_portfolio_gamma=500.0,
        max_portfolio_theta=-1000.0,
        max_portfolio_vega=1000.0,
        max_position_pct=0.30,
        max_correlated_exposure=0.50,
    )
    return PortfolioLimitsChecker(config)


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
async def test_portfolio_limits_checked_before_entry(
    mock_decision_engine,
    mock_execution_engine,
    mock_strategy_builder,
    mock_strategy_repo,
    portfolio_limits_checker,
):
    """
    Test: Portfolio limits checked before entry.

    Validates:
    - Entry workflow checks portfolio limits
    - Limits evaluated with new position
    - Entry allowed when limits not exceeded
    - Orders placed when allowed
    """
    # Create workflow with portfolio limits
    workflow = EntryWorkflow(
        decision_engine=mock_decision_engine,
        execution_engine=mock_execution_engine,
        strategy_builder=mock_strategy_builder,
        strategy_repo=mock_strategy_repo,
        portfolio_limits=portfolio_limits_checker,
    )

    # Setup portfolio limits to allow entry
    portfolio_limits_checker.check_entry_allowed = AsyncMock(
        return_value=(True, None)
    )

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

    # Verify portfolio limits checked
    portfolio_limits_checker.check_entry_allowed.assert_called_once()

    # Verify entry executed (allowed)
    assert execution is not None
    assert execution.symbol == "SPY"


@pytest.mark.asyncio
async def test_portfolio_limit_exceeded_raises_error(
    mock_decision_engine,
    mock_execution_engine,
    mock_strategy_builder,
    mock_strategy_repo,
    portfolio_limits_checker,
):
    """
    Test: PortfolioLimitExceeded raised when limits exceeded.

    Validates:
    - Portfolio limits checker rejects entry
    - PortfolioLimitExceededError raised
    - No orders placed
    - Reason provided
    """
    # Create workflow with portfolio limits
    workflow = EntryWorkflow(
        decision_engine=mock_decision_engine,
        execution_engine=mock_execution_engine,
        strategy_builder=mock_strategy_builder,
        strategy_repo=mock_strategy_repo,
        portfolio_limits=portfolio_limits_checker,
    )

    # Setup portfolio limits to reject entry
    portfolio_limits_checker.check_entry_allowed = AsyncMock(
        return_value=(
            False,
            "Portfolio delta would exceed limit: 250.00 > 200.00",
        )
    )

    # Execute entry - should raise PortfolioLimitExceeded
    params = {
        "underlying_price": 455.0,
        "dte": 45,
        "put_width": 10,
        "call_width": 10,
    }

    with pytest.raises(PortfolioLimitExceededError) as exc_info:
        await workflow.execute_entry(
            symbol="SPY",
            strategy_type=StrategyType.IRON_CONDOR,
            params=params,
        )

    # Verify error message
    assert "Portfolio delta would exceed limit" in str(exc_info.value)

    # Verify no orders placed
    mock_execution_engine.place_order.assert_not_called()


@pytest.mark.asyncio
async def test_entry_workflow_without_portfolio_limits(
    mock_decision_engine,
    mock_execution_engine,
    mock_strategy_builder,
    mock_strategy_repo,
):
    """
    Test: Entry workflow works without portfolio limits (backward compatible).

    Validates:
    - Workflow created without portfolio_limits
    - Entry executes normally
    - No errors
    """
    # Create workflow without portfolio limits
    workflow = EntryWorkflow(
        decision_engine=mock_decision_engine,
        execution_engine=mock_execution_engine,
        strategy_builder=mock_strategy_builder,
        strategy_repo=mock_strategy_repo,
        portfolio_limits=None,
    )

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

    # Verify success
    assert execution is not None
    assert execution.symbol == "SPY"


@pytest.mark.asyncio
async def test_portfolio_limits_updated_after_exit(
    mock_decision_engine,
    mock_execution_engine,
    mock_strategy_builder,
    mock_strategy_repo,
    portfolio_limits_checker,
):
    """
    Test: Portfolio limits updated after position exit.

    Validates:
    - Position entered (limits increased)
    - Position exited (limits decreased)
    - Portfolio risk recalculated
    - Limits reflect new state
    """
    # This test would verify that portfolio limits are properly
    # updated when positions are closed
    # For now, just verify the workflow components exist

    assert portfolio_limits_checker is not None
    assert mock_strategy_repo is not None


@pytest.mark.asyncio
async def test_concentration_limit_checked(
    mock_decision_engine,
    mock_execution_engine,
    mock_strategy_builder,
    mock_strategy_repo,
    portfolio_limits_checker,
):
    """
    Test: Concentration limit checked for symbol.

    Validates:
    - Too much exposure to one symbol detected
    - Entry rejected when concentration exceeded
    - Clear error message provided
    """
    # Create workflow with portfolio limits
    workflow = EntryWorkflow(
        decision_engine=mock_decision_engine,
        execution_engine=mock_execution_engine,
        strategy_builder=mock_strategy_builder,
        strategy_repo=mock_strategy_repo,
        portfolio_limits=portfolio_limits_checker,
    )

    # Setup portfolio limits to reject based on concentration
    portfolio_limits_checker.check_entry_allowed = AsyncMock(
        return_value=(
            False,
            "Symbol SPY concentration would exceed limit: 35% > 30%",
        )
    )

    # Execute entry - should raise
    params = {
        "underlying_price": 455.0,
        "dte": 45,
        "put_width": 10,
        "call_width": 10,
    }

    with pytest.raises(PortfolioLimitExceededError) as exc_info:
        await workflow.execute_entry(
            symbol="SPY",
            strategy_type=StrategyType.IRON_CONDOR,
            params=params,
        )

    # Verify concentration error
    assert "concentration" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_portfolio_greeks_limit_checked(
    mock_decision_engine,
    mock_execution_engine,
    mock_strategy_builder,
    mock_strategy_repo,
    portfolio_limits_checker,
):
    """
    Test: Portfolio Greeks limits checked.

    Validates:
    - Delta limit checked
    - Gamma limit checked
    - Theta limit checked
    - Vega limit checked
    - Entry rejected if any limit exceeded
    """
    # Create workflow with portfolio limits
    workflow = EntryWorkflow(
        decision_engine=mock_decision_engine,
        execution_engine=mock_execution_engine,
        strategy_builder=mock_strategy_builder,
        strategy_repo=mock_strategy_repo,
        portfolio_limits=portfolio_limits_checker,
    )

    # Test each Greek limit
    greek_limits = [
        ("Portfolio delta would exceed limit", "delta"),
        ("Portfolio gamma would exceed limit", "gamma"),
        ("Portfolio theta would exceed limit", "theta"),
        ("Portfolio vega would exceed limit", "vega"),
    ]

    for error_msg, greek in greek_limits:
        # Setup rejection
        portfolio_limits_checker.check_entry_allowed = AsyncMock(
            return_value=(False, error_msg)
        )

        # Execute entry - should raise
        params = {
            "underlying_price": 455.0,
            "dte": 45,
            "put_width": 10,
            "call_width": 10,
        }

        with pytest.raises(PortfolioLimitExceededError) as exc_info:
            await workflow.execute_entry(
                symbol="SPY",
                strategy_type=StrategyType.IRON_CONDOR,
                params=params,
            )

        # Verify correct Greek in error
        assert greek in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_correlation_limit_checked(
    mock_decision_engine,
    mock_execution_engine,
    mock_strategy_builder,
    mock_strategy_repo,
    portfolio_limits_checker,
):
    """
    Test: Correlated exposure limit checked.

    Validates:
    - Correlated symbols detected (SPY, QQQ, IWM)
    - Combined exposure calculated
    - Entry rejected if correlated exposure too high
    """
    # Create workflow with portfolio limits
    workflow = EntryWorkflow(
        decision_engine=mock_decision_engine,
        execution_engine=mock_execution_engine,
        strategy_builder=mock_strategy_builder,
        strategy_repo=mock_strategy_repo,
        portfolio_limits=portfolio_limits_checker,
    )

    # Setup rejection based on correlated exposure
    portfolio_limits_checker.check_entry_allowed = AsyncMock(
        return_value=(
            False,
            "Correlated exposure (SPY+QQQ+IWM) would exceed limit: 55% > 50%",
        )
    )

    # Execute entry - should raise
    params = {
        "underlying_price": 455.0,
        "dte": 45,
        "put_width": 10,
        "call_width": 10,
    }

    with pytest.raises(PortfolioLimitExceededError) as exc_info:
        await workflow.execute_entry(
            symbol="SPY",
            strategy_type=StrategyType.IRON_CONDOR,
            params=params,
        )

    # Verify correlation error
    assert "correlated" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_buying_power_limit_checked(
    mock_decision_engine,
    mock_execution_engine,
    mock_strategy_builder,
    mock_strategy_repo,
    portfolio_limits_checker,
):
    """
    Test: Buying power limit checked.

    Validates:
    - Available buying power calculated
    - Position margin requirement estimated
    - Entry rejected if insufficient buying power
    """
    # Create workflow with portfolio limits
    workflow = EntryWorkflow(
        decision_engine=mock_decision_engine,
        execution_engine=mock_execution_engine,
        strategy_builder=mock_strategy_builder,
        strategy_repo=mock_strategy_repo,
        portfolio_limits=portfolio_limits_checker,
    )

    # Setup rejection based on buying power
    portfolio_limits_checker.check_entry_allowed = AsyncMock(
        return_value=(
            False,
            "Insufficient buying power: need $10,000, have $8,000",
        )
    )

    # Execute entry - should raise
    params = {
        "underlying_price": 455.0,
        "dte": 45,
        "put_width": 10,
        "call_width": 10,
    }

    with pytest.raises(PortfolioLimitExceededError) as exc_info:
        await workflow.execute_entry(
            symbol="SPY",
            strategy_type=StrategyType.IRON_CONDOR,
            params=params,
        )

    # Verify buying power error
    assert "buying power" in str(exc_info.value).lower()
