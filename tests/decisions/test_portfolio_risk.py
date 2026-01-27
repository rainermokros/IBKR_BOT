"""
Unit tests for PortfolioRiskCalculator

Tests portfolio risk calculations including Greek aggregation,
exposure metrics, and limit checking.
"""

from datetime import datetime
from unittest.mock import Mock

import polars as pl
import pytest

from src.v6.data.repositories.positions import PositionsRepository
from src.v6.decisions.portfolio_risk import (
    ExposureMetrics,
    PortfolioGreeks,
    PortfolioRisk,
    PortfolioRiskCalculator,
)


@pytest.fixture
def mock_position_repo():
    """Create a mock position repository."""
    repo = Mock(spec=PositionsRepository)
    return repo


@pytest.fixture
def empty_portfolio_df():
    """Create empty portfolio DataFrame."""
    schema = {
        "strategy_id": pl.String,
        "strategy_type": pl.String,
        "symbol": pl.String,
        "status": pl.String,
        "entry_date": pl.Datetime("us"),
        "exit_date": pl.Datetime("us"),
        "entry_price": pl.Float64,
        "exit_price": pl.Float64,
        "quantity": pl.Int32,
        "delta": pl.Float64,
        "gamma": pl.Float64,
        "theta": pl.Float64,
        "vega": pl.Float64,
        "unrealized_pnl": pl.Float64,
        "realized_pnl": pl.Float64,
        "timestamp": pl.Datetime("us"),
    }
    return pl.DataFrame(schema=schema)


@pytest.fixture
def single_position_df():
    """Create DataFrame with single position."""
    data = {
        "strategy_id": ["STRAT001"],
        "strategy_type": ["iron_condor"],
        "symbol": ["SPY"],
        "status": ["open"],
        "entry_date": [datetime(2026, 1, 26, 9, 30)],
        "exit_date": [None],
        "entry_price": [1.50],
        "exit_price": [None],
        "quantity": [1],
        "strike": [400.0],
        "delta": [0.5],
        "gamma": [0.02],
        "theta": [-10.0],
        "vega": [50.0],
        "unrealized_pnl": [0.0],
        "realized_pnl": [0.0],
        "timestamp": [datetime.now()],
    }
    return pl.DataFrame(data)


@pytest.fixture
def multi_position_df():
    """Create DataFrame with multiple positions."""
    data = {
        "strategy_id": ["STRAT001", "STRAT002", "STRAT003"],
        "strategy_type": ["iron_condor", "iron_condor", "vertical_spread"],
        "symbol": ["SPY", "QQQ", "SPY"],
        "status": ["open", "open", "open"],
        "entry_date": [
            datetime(2026, 1, 26, 9, 30),
            datetime(2026, 1, 26, 9, 30),
            datetime(2026, 1, 26, 9, 30),
        ],
        "exit_date": [None, None, None],
        "entry_price": [1.50, 2.00, 1.00],
        "exit_price": [None, None, None],
        "quantity": [1, 1, 1],
        "strike": [400.0, 450.0, 395.0],
        "delta": [0.5, 0.3, 0.2],
        "gamma": [0.02, 0.015, 0.01],
        "theta": [-10.0, -8.0, -5.0],
        "vega": [50.0, 40.0, 30.0],
        "unrealized_pnl": [0.0, 0.0, 0.0],
        "realized_pnl": [0.0, 0.0, 0.0],
        "timestamp": [datetime.now(), datetime.now(), datetime.now()],
    }
    return pl.DataFrame(data)


@pytest.mark.asyncio
async def test_empty_portfolio_returns_zeros(mock_position_repo, empty_portfolio_df):
    """Test that empty portfolio returns all zeros."""
    # Setup mock
    mock_position_repo.get_open_positions.return_value = empty_portfolio_df

    # Create calculator and calculate risk
    calc = PortfolioRiskCalculator(mock_position_repo)
    risk = await calc.calculate_portfolio_risk()

    # Assert all values are zero
    assert risk.position_count == 0
    assert risk.symbol_count == 0
    assert risk.greeks.delta == 0.0
    assert risk.greeks.gamma == 0.0
    assert risk.greeks.theta == 0.0
    assert risk.greeks.vega == 0.0
    assert risk.exposure.total_exposure == 0.0
    assert risk.exposure.max_single_position == 0.0
    assert len(risk.greeks.delta_per_symbol) == 0
    assert len(risk.greeks.gamma_per_symbol) == 0


@pytest.mark.asyncio
async def test_single_position_aggregation(mock_position_repo, single_position_df):
    """Test that single position Greeks are aggregated correctly."""
    # Setup mock
    mock_position_repo.get_open_positions.return_value = single_position_df

    # Create calculator and calculate risk
    calc = PortfolioRiskCalculator(mock_position_repo)
    risk = await calc.calculate_portfolio_risk()

    # Assert Greeks match the single position
    assert risk.position_count == 1
    assert risk.symbol_count == 1
    assert risk.greeks.delta == 0.5
    assert risk.greeks.gamma == 0.02
    assert risk.greeks.theta == -10.0
    assert risk.greeks.vega == 50.0
    assert "SPY" in risk.greeks.delta_per_symbol
    assert risk.greeks.delta_per_symbol["SPY"] == 0.5


@pytest.mark.asyncio
async def test_multi_position_greeks(mock_position_repo, multi_position_df):
    """Test that multiple position Greeks are summed correctly."""
    # Setup mock
    mock_position_repo.get_open_positions.return_value = multi_position_df

    # Create calculator and calculate risk
    calc = PortfolioRiskCalculator(mock_position_repo)
    risk = await calc.calculate_portfolio_risk()

    # Assert Greeks are summed (0.5 + 0.3 + 0.2 = 1.0)
    assert risk.position_count == 3
    assert risk.greeks.delta == 1.0
    assert risk.greeks.gamma == pytest.approx(0.045)  # 0.02 + 0.015 + 0.01 (floating point)
    assert risk.greeks.theta == -23.0  # -10 + -8 + -5
    assert risk.greeks.vega == 120.0  # 50 + 40 + 30


@pytest.mark.asyncio
async def test_per_symbol_aggregation(mock_position_repo, multi_position_df):
    """Test that Greeks are aggregated correctly per symbol."""
    # Setup mock
    mock_position_repo.get_open_positions.return_value = multi_position_df

    # Create calculator and calculate risk
    calc = PortfolioRiskCalculator(mock_position_repo)
    risk = await calc.calculate_portfolio_risk()

    # Assert per-symbol aggregation
    # SPY: 0.5 + 0.2 = 0.7
    # QQQ: 0.3
    assert "SPY" in risk.greeks.delta_per_symbol
    assert "QQQ" in risk.greeks.delta_per_symbol
    assert risk.greeks.delta_per_symbol["SPY"] == 0.7
    assert risk.greeks.delta_per_symbol["QQQ"] == 0.3
    assert risk.greeks.gamma_per_symbol["SPY"] == 0.03  # 0.02 + 0.01
    assert risk.greeks.gamma_per_symbol["QQQ"] == 0.015


@pytest.mark.asyncio
async def test_delta_limits_check(mock_position_repo, multi_position_df):
    """Test that delta limits check returns over-limit symbols."""
    # Setup mock
    mock_position_repo.get_open_positions.return_value = multi_position_df

    # Create calculator
    calc = PortfolioRiskCalculator(mock_position_repo)

    # Check with limit of 0.5 (SPY at 0.7 should exceed)
    over_limit = await calc.check_delta_limits(max_delta=0.5)

    # Assert SPY is over limit
    assert "SPY" in over_limit
    assert "QQQ" not in over_limit  # QQQ at 0.3 is under limit


@pytest.mark.asyncio
async def test_exposure_limits_check(mock_position_repo, multi_position_df):
    """Test that exposure limits check returns over-limit symbols."""
    # Setup mock
    mock_position_repo.get_open_positions.return_value = multi_position_df

    # Create calculator
    calc = PortfolioRiskCalculator(mock_position_repo)

    # Check with limit of 1% (should catch large positions)
    # Position 1: 1 * 400 * 100 = 40,000
    # Position 2: 1 * 450 * 100 = 45,000
    # Position 3: 1 * 395 * 100 = 39,500
    # Total: 124,500
    # Max position: 45,000 / 124,500 = 36.1%
    over_limit = await calc.check_exposure_limits(max_position_pct=0.01)

    # All positions should be over 1% limit
    assert len(over_limit) > 0


@pytest.mark.asyncio
async def test_get_greeks_by_symbol(mock_position_repo, multi_position_df):
    """Test getting Greeks for a specific symbol."""
    # Setup mock
    mock_position_repo.get_by_symbol.return_value = multi_position_df.filter(
        pl.col("symbol") == "SPY"
    )

    # Create calculator
    calc = PortfolioRiskCalculator(mock_position_repo)

    # Get SPY Greeks
    greeks = await calc.get_greeks_by_symbol("SPY")

    # Assert SPY Greeks are correct (0.5 + 0.2 = 0.7)
    assert greeks.delta == 0.7
    assert greeks.gamma == 0.03
    assert greeks.theta == -15.0  # -10 + -5
    assert greeks.vega == 80.0  # 50 + 30
    assert "SPY" in greeks.delta_per_symbol


@pytest.mark.asyncio
async def test_buying_power_calculation(mock_position_repo, multi_position_df):
    """Test that buying power metrics are calculated correctly."""
    # Setup mock
    mock_position_repo.get_open_positions.return_value = multi_position_df

    # Create calculator
    calc = PortfolioRiskCalculator(mock_position_repo)
    risk = await calc.calculate_portfolio_risk()

    # Currently returns 0.0 (TODO: integrate with IB account data)
    assert risk.exposure.buying_power_used == 0.0
    assert risk.exposure.buying_power_available == 0.0


def test_portfolio_greeks_validation():
    """Test PortfolioGreeks validation."""
    # Valid Greeks
    greeks = PortfolioGreeks(
        delta=0.5,
        gamma=0.02,
        theta=-10.0,
        vega=50.0,
        delta_per_symbol={},
        gamma_per_symbol={},
    )
    assert greeks.delta == 0.5

    # Invalid delta (out of bounds)
    with pytest.raises(ValueError, match="delta.*exceeds reasonable bounds"):
        PortfolioGreeks(
            delta=150.0,  # Too high
            gamma=0.02,
            theta=-10.0,
            vega=50.0,
        )

    # Invalid per-symbol delta
    with pytest.raises(ValueError, match="delta.*exceeds bounds"):
        PortfolioGreeks(
            delta=0.5,
            gamma=0.02,
            theta=-10.0,
            vega=50.0,
            delta_per_symbol={"SPY": 150.0},  # Too high
        )


def test_exposure_metrics_validation():
    """Test ExposureMetrics validation."""
    # Valid metrics
    exposure = ExposureMetrics(
        total_exposure=100000.0,
        max_single_position=0.02,
        correlated_exposure={},
        buying_power_used=0.3,
        buying_power_available=70000.0,
    )
    assert exposure.total_exposure == 100000.0

    # Invalid max_single_position (not in [0, 1])
    with pytest.raises(ValueError, match="max_single_position.*must be in"):
        ExposureMetrics(
            total_exposure=100000.0,
            max_single_position=1.5,  # Too high
            correlated_exposure={},
            buying_power_used=0.3,
            buying_power_available=70000.0,
        )

    # Invalid buying_power_used
    with pytest.raises(ValueError, match="buying_power_used.*must be in"):
        ExposureMetrics(
            total_exposure=100000.0,
            max_single_position=0.02,
            correlated_exposure={},
            buying_power_used=1.5,  # Too high
            buying_power_available=70000.0,
        )


def test_portfolio_risk_validation():
    """Test PortfolioRisk validation."""
    # Valid risk
    greeks = PortfolioGreeks(
        delta=0.5,
        gamma=0.02,
        theta=-10.0,
        vega=50.0,
    )
    exposure = ExposureMetrics(
        total_exposure=100000.0,
        max_single_position=0.02,
        correlated_exposure={},
        buying_power_used=0.3,
        buying_power_available=70000.0,
    )
    risk = PortfolioRisk(
        greeks=greeks,
        exposure=exposure,
        position_count=5,
        symbol_count=3,
        calculated_at=datetime.now(),
    )
    assert risk.position_count == 5

    # Invalid position_count (negative)
    with pytest.raises(ValueError, match="position_count.*must be >= 0"):
        PortfolioRisk(
            greeks=greeks,
            exposure=exposure,
            position_count=-1,
            symbol_count=3,
            calculated_at=datetime.now(),
        )

    # Invalid: symbol_count > position_count
    with pytest.raises(ValueError, match="symbol_count.*cannot exceed"):
        PortfolioRisk(
            greeks=greeks,
            exposure=exposure,
            position_count=2,
            symbol_count=5,  # Can't have more symbols than positions
            calculated_at=datetime.now(),
        )
