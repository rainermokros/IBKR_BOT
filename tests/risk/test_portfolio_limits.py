"""
Tests for PortfolioLimitsChecker

Tests portfolio-level limit checking including:
- Delta limits (portfolio and per-symbol)
- Concentration limits
- Exposure limits
- Empty portfolio handling
- Edge cases
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from src.v6.decisions.portfolio_risk import (
    PortfolioGreeks,
    PortfolioRisk,
    ExposureMetrics,
)
from src.v6.risk.models import RiskLimitsConfig
from src.v6.risk.portfolio_limits import PortfolioLimitsChecker


@pytest.fixture
def risk_limits_config():
    """Create standard risk limits configuration for testing."""
    return RiskLimitsConfig(
        max_portfolio_delta=50.0,
        max_portfolio_gamma=10.0,
        max_single_position_pct=0.02,  # 2%
        max_per_symbol_delta=20.0,
        max_correlated_pct=0.05,  # 5%
        total_exposure_cap=1000000.0,  # $1M
    )


@pytest.fixture
def mock_risk_calculator():
    """Create mock PortfolioRiskCalculator."""
    mock_calc = MagicMock()
    return mock_calc


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


@pytest.fixture
def moderate_portfolio_risk():
    """Create PortfolioRisk with moderate existing positions."""
    return PortfolioRisk(
        greeks=PortfolioGreeks(
            delta=25.0,  # 50% of limit
            gamma=5.0,  # 50% of limit
            theta=-100.0,
            vega=500.0,
            delta_per_symbol={"SPY": 15.0, "IWM": 10.0},
            gamma_per_symbol={"SPY": 3.0, "IWM": 2.0},
        ),
        exposure=ExposureMetrics(
            total_exposure=50000.0,  # $50K
            max_single_position=0.015,  # 1.5%
            correlated_exposure={"SPY": 0.03, "IWM": 0.02},
            buying_power_used=0.1,  # 10%
            buying_power_available=90000.0,
        ),
        position_count=5,
        symbol_count=2,
        calculated_at=datetime.now(),
    )


@pytest.fixture
def high_delta_portfolio_risk():
    """Create PortfolioRisk with high delta exposure."""
    return PortfolioRisk(
        greeks=PortfolioGreeks(
            delta=45.0,  # Near limit (50)
            gamma=3.0,
            theta=-50.0,
            vega=200.0,
            delta_per_symbol={"SPY": 45.0},
            gamma_per_symbol={"SPY": 3.0},
        ),
        exposure=ExposureMetrics(
            total_exposure=80000.0,
            max_single_position=0.01,
            correlated_exposure={"SPY": 0.04},
            buying_power_used=0.15,
            buying_power_available=85000.0,
        ),
        position_count=3,
        symbol_count=1,
        calculated_at=datetime.now(),
    )


class TestPortfolioLimitsChecker:
    """Test suite for PortfolioLimitsChecker."""

    @pytest.mark.asyncio
    async def test_check_entry_allowed_empty_portfolio(
        self,
        mock_risk_calculator,
        risk_limits_config,
        empty_portfolio_risk,
    ):
        """Test entry allowed with empty portfolio."""
        # Setup mock
        mock_risk_calculator.calculate_portfolio_risk = AsyncMock(
            return_value=empty_portfolio_risk
        )

        # Create checker with higher concentration limit for empty portfolio
        config = RiskLimitsConfig(
            max_portfolio_delta=50.0,
            max_portfolio_gamma=10.0,
            max_single_position_pct=1.0,  # 100% - allow first position
            max_per_symbol_delta=20.0,
            max_correlated_pct=1.0,  # 100% - allow first position
            total_exposure_cap=1000000.0,
        )
        checker = PortfolioLimitsChecker(mock_risk_calculator, config)

        # Test entry allowed
        allowed, reason = await checker.check_entry_allowed(
            new_position_delta=5.0,
            symbol="SPY",
            position_value=10000.0,
        )

        assert allowed is True
        assert reason is None
        mock_risk_calculator.calculate_portfolio_risk.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_entry_allowed_moderate_portfolio(
        self,
        mock_risk_calculator,
        risk_limits_config,
        moderate_portfolio_risk,
    ):
        """Test entry allowed with moderate existing positions."""
        # Setup mock
        mock_risk_calculator.calculate_portfolio_risk = AsyncMock(
            return_value=moderate_portfolio_risk
        )

        # Create checker with higher concentration limit
        config = RiskLimitsConfig(
            max_portfolio_delta=50.0,
            max_portfolio_gamma=10.0,
            max_single_position_pct=0.20,  # 20% - allow moderate positions
            max_per_symbol_delta=20.0,
            max_correlated_pct=0.20,  # 20% - allow new symbol
            total_exposure_cap=1000000.0,
        )
        checker = PortfolioLimitsChecker(mock_risk_calculator, config)

        # Test entry allowed (5.0 delta + 25.0 = 30.0 < 50.0)
        allowed, reason = await checker.check_entry_allowed(
            new_position_delta=5.0,
            symbol="QQQ",  # New symbol
            position_value=10000.0,
        )

        assert allowed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_check_entry_rejected_portfolio_delta_limit(
        self,
        mock_risk_calculator,
        risk_limits_config,
        high_delta_portfolio_risk,
    ):
        """Test entry rejected when portfolio delta would exceed limit."""
        # Setup mock
        mock_risk_calculator.calculate_portfolio_risk = AsyncMock(
            return_value=high_delta_portfolio_risk
        )

        # Create checker
        checker = PortfolioLimitsChecker(mock_risk_calculator, risk_limits_config)

        # Test entry rejected (10.0 delta + 45.0 = 55.0 > 50.0)
        allowed, reason = await checker.check_entry_allowed(
            new_position_delta=10.0,
            symbol="SPY",
            position_value=10000.0,
        )

        assert allowed is False
        assert reason is not None
        assert "Portfolio delta would exceed limit" in reason
        assert "55.00" in reason
        assert "50.00" in reason

    @pytest.mark.asyncio
    async def test_check_entry_rejected_symbol_delta_limit(
        self,
        mock_risk_calculator,
        risk_limits_config,
        moderate_portfolio_risk,
    ):
        """Test entry rejected when symbol delta would exceed limit."""
        # Setup mock
        mock_risk_calculator.calculate_portfolio_risk = AsyncMock(
            return_value=moderate_portfolio_risk
        )

        # Create checker
        checker = PortfolioLimitsChecker(mock_risk_calculator, risk_limits_config)

        # Test entry rejected (SPY has 15.0, adding 10.0 = 25.0 > 20.0)
        allowed, reason = await checker.check_entry_allowed(
            new_position_delta=10.0,
            symbol="SPY",
            position_value=10000.0,
        )

        assert allowed is False
        assert reason is not None
        assert "Symbol SPY delta would exceed limit" in reason
        assert "25.00" in reason
        assert "20.00" in reason

    @pytest.mark.asyncio
    async def test_check_entry_rejected_concentration_limit(
        self,
        mock_risk_calculator,
        risk_limits_config,
        moderate_portfolio_risk,
    ):
        """Test entry rejected when position concentration would exceed limit."""
        # Setup mock
        mock_risk_calculator.calculate_portfolio_risk = AsyncMock(
            return_value=moderate_portfolio_risk
        )

        # Create checker
        checker = PortfolioLimitsChecker(mock_risk_calculator, risk_limits_config)

        # Test entry rejected ($2K position / $52K total = 3.8% > 2%)
        # Note: position_concentration = position_value / new_total_exposure
        # 2000 / (50000 + 2000) = 2000 / 52000 = 3.8%
        allowed, reason = await checker.check_entry_allowed(
            new_position_delta=5.0,
            symbol="QQQ",
            position_value=2000.0,
        )

        # With max_single_position_pct=0.02 (2%)
        # position_concentration = 2000 / (50000 + 2000) = 0.038 = 3.8% > 2%
        # This should be rejected
        assert allowed is False
        assert reason is not None
        assert "concentration" in reason.lower()

    @pytest.mark.asyncio
    async def test_check_entry_allowed_small_concentration(
        self,
        mock_risk_calculator,
        risk_limits_config,
        moderate_portfolio_risk,
    ):
        """Test entry allowed when position concentration is within limit."""
        # Setup mock
        mock_risk_calculator.calculate_portfolio_risk = AsyncMock(
            return_value=moderate_portfolio_risk
        )

        # Create checker
        checker = PortfolioLimitsChecker(mock_risk_calculator, risk_limits_config)

        # Test entry allowed ($500 position / $50.5K total = 1% < 2%)
        allowed, reason = await checker.check_entry_allowed(
            new_position_delta=5.0,
            symbol="QQQ",
            position_value=500.0,
        )

        assert allowed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_check_entry_rejected_total_exposure_cap(
        self,
        mock_risk_calculator,
        moderate_portfolio_risk,
    ):
        """Test entry rejected when total exposure cap would be exceeded."""
        # Setup config with low exposure cap
        config = RiskLimitsConfig(
            max_portfolio_delta=100.0,
            max_portfolio_gamma=10.0,
            max_single_position_pct=1.0,  # Allow large positions
            max_per_symbol_delta=100.0,
            max_correlated_pct=1.0,
            total_exposure_cap=55000.0,  # Cap at $55K (just above $50K current)
        )

        # Setup mock with moderate portfolio
        mock_calc = MagicMock()
        mock_calc.calculate_portfolio_risk = AsyncMock(return_value=moderate_portfolio_risk)

        # Create checker
        checker = PortfolioLimitsChecker(mock_calc, config)

        # Test entry rejected ($50K + $10K = $60K > $55K cap)
        allowed, reason = await checker.check_entry_allowed(
            new_position_delta=5.0,
            symbol="QQQ",  # New symbol to avoid symbol delta limit
            position_value=10000.0,
        )

        assert allowed is False
        assert reason is not None
        assert "exposure" in reason.lower()

    @pytest.mark.asyncio
    async def test_check_portfolio_health_empty(
        self,
        mock_risk_calculator,
        risk_limits_config,
        empty_portfolio_risk,
    ):
        """Test portfolio health check with empty portfolio."""
        # Setup mock
        mock_risk_calculator.calculate_portfolio_risk = AsyncMock(
            return_value=empty_portfolio_risk
        )

        # Create checker
        checker = PortfolioLimitsChecker(mock_risk_calculator, risk_limits_config)

        # Check health
        warnings = await checker.check_portfolio_health()

        assert warnings == []

    @pytest.mark.asyncio
    async def test_check_portfolio_health_warnings(
        self,
        mock_risk_calculator,
        risk_limits_config,
    ):
        """Test portfolio health check generates warnings for exceeded limits."""
        # Create portfolio risk with exceeded limits
        high_risk = PortfolioRisk(
            greeks=PortfolioGreeks(
                delta=60.0,  # Exceeds limit of 50
                gamma=12.0,  # Exceeds limit of 10
                theta=-100.0,
                vega=500.0,
                delta_per_symbol={"SPY": 25.0},  # Exceeds limit of 20
                gamma_per_symbol={"SPY": 5.0},
            ),
            exposure=ExposureMetrics(
                total_exposure=100000.0,
                max_single_position=0.03,  # Exceeds limit of 0.02
                correlated_exposure={"SPY": 0.06},  # Exceeds limit of 0.05
                buying_power_used=0.5,
                buying_power_available=50000.0,
            ),
            position_count=3,
            symbol_count=1,
            calculated_at=datetime.now(),
        )

        # Setup mock
        mock_risk_calculator.calculate_portfolio_risk = AsyncMock(return_value=high_risk)

        # Create checker
        checker = PortfolioLimitsChecker(mock_risk_calculator, risk_limits_config)

        # Check health
        warnings = await checker.check_portfolio_health()

        # Should have warnings for all exceeded limits
        assert len(warnings) > 0
        assert any("delta" in w.lower() for w in warnings)
        assert any("gamma" in w.lower() for w in warnings)
        assert any("concentration" in w.lower() or "position" in w.lower() for w in warnings)

    @pytest.mark.asyncio
    async def test_get_remaining_capacity(
        self,
        mock_risk_calculator,
        risk_limits_config,
        moderate_portfolio_risk,
    ):
        """Test calculation of remaining capacity for new entries."""
        # Setup mock
        mock_risk_calculator.calculate_portfolio_risk = AsyncMock(
            return_value=moderate_portfolio_risk
        )

        # Create checker
        checker = PortfolioLimitsChecker(mock_risk_calculator, risk_limits_config)

        # Get capacity for SPY
        capacity = await checker.get_remaining_capacity("SPY")

        # Verify capacity calculations
        assert "delta" in capacity
        assert "symbol_delta" in capacity
        assert "exposure" in capacity
        assert "position_count" in capacity

        # Delta capacity: 50 - 25 = 25
        assert capacity["delta"] == pytest.approx(25.0, rel=0.1)

        # Symbol delta capacity: 20 - 15 = 5
        assert capacity["symbol_delta"] == pytest.approx(5.0, rel=0.1)

        # Exposure capacity should be positive
        assert capacity["exposure"] > 0

    @pytest.mark.asyncio
    async def test_get_remaining_capacity_empty_portfolio(
        self,
        mock_risk_calculator,
        risk_limits_config,
        empty_portfolio_risk,
    ):
        """Test remaining capacity with empty portfolio."""
        # Setup mock
        mock_risk_calculator.calculate_portfolio_risk = AsyncMock(
            return_value=empty_portfolio_risk
        )

        # Create checker
        checker = PortfolioLimitsChecker(mock_risk_calculator, risk_limits_config)

        # Get capacity
        capacity = await checker.get_remaining_capacity("SPY")

        # Should have full capacity
        assert capacity["delta"] == pytest.approx(50.0, rel=0.1)
        assert capacity["symbol_delta"] == pytest.approx(20.0, rel=0.1)

    @pytest.mark.asyncio
    async def test_negative_delta_handling(
        self,
        mock_risk_calculator,
        risk_limits_config,
        empty_portfolio_risk,
    ):
        """Test handling of negative delta (short positions)."""
        # Setup mock
        mock_risk_calculator.calculate_portfolio_risk = AsyncMock(
            return_value=empty_portfolio_risk
        )

        # Create checker with higher concentration limit
        config = RiskLimitsConfig(
            max_portfolio_delta=50.0,
            max_portfolio_gamma=10.0,
            max_single_position_pct=1.0,  # 100% - allow first position
            max_per_symbol_delta=20.0,
            max_correlated_pct=1.0,  # 100% - allow first position
            total_exposure_cap=None,
        )
        checker = PortfolioLimitsChecker(mock_risk_calculator, config)

        # Test with negative delta (short position)
        allowed, reason = await checker.check_entry_allowed(
            new_position_delta=-5.0,  # Short position
            symbol="SPY",
            position_value=10000.0,
        )

        assert allowed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_portfolio_gamma_limit_check(
        self,
        mock_risk_calculator,
        risk_limits_config,
    ):
        """Test that portfolio gamma limit is checked."""
        # Create portfolio with exceeded gamma
        high_gamma = PortfolioRisk(
            greeks=PortfolioGreeks(
                delta=0.0,
                gamma=12.0,  # Exceeds limit of 10
                theta=-100.0,
                vega=500.0,
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

        # Setup mock
        mock_risk_calculator.calculate_portfolio_risk = AsyncMock(return_value=high_gamma)

        # Create checker
        checker = PortfolioLimitsChecker(mock_risk_calculator, risk_limits_config)

        # Should reject entry when gamma already exceeds limit
        allowed, reason = await checker.check_entry_allowed(
            new_position_delta=5.0,
            symbol="SPY",
            position_value=10000.0,
        )

        assert allowed is False
        assert reason is not None
        assert "gamma" in reason.lower()

    @pytest.mark.asyncio
    async def test_no_exposure_cap_when_none(
        self,
        mock_risk_calculator,
        empty_portfolio_risk,
    ):
        """Test that no exposure cap check when total_exposure_cap is None."""
        # Create config without exposure cap
        config = RiskLimitsConfig(
            max_portfolio_delta=50.0,
            max_portfolio_gamma=10.0,
            max_single_position_pct=0.02,
            max_per_symbol_delta=20.0,
            max_correlated_pct=0.05,
            total_exposure_cap=None,  # No cap
        )

        # Setup mock with high exposure
        high_exposure = PortfolioRisk(
            greeks=PortfolioGreeks(
                delta=0.0,
                gamma=0.0,
                theta=0.0,
                vega=0.0,
                delta_per_symbol={},
                gamma_per_symbol={},
            ),
            exposure=ExposureMetrics(
                total_exposure=10000000.0,  # $10M - very high
                max_single_position=0.01,
                correlated_exposure={},
                buying_power_used=0.5,
                buying_power_available=50000.0,
            ),
            position_count=10,
            symbol_count=5,
            calculated_at=datetime.now(),
        )

        mock_risk_calculator.calculate_portfolio_risk = AsyncMock(return_value=high_exposure)

        # Create checker
        checker = PortfolioLimitsChecker(mock_risk_calculator, config)

        # Should allow entry even with huge exposure (no cap)
        allowed, reason = await checker.check_entry_allowed(
            new_position_delta=5.0,
            symbol="SPY",
            position_value=100000.0,  # $100K position
        )

        # Should be allowed (delta is within limits, no exposure cap)
        assert allowed is True
