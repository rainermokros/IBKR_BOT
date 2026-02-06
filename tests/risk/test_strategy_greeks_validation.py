"""
Tests for Strategy-Specific Greeks Validation

Tests that strategies have appropriate Greeks profiles:
- Iron Condors should be delta-neutral (small delta)
- Vertical spreads can have directional exposure
- Strategy-specific validation before entry

Usage:
    pytest tests/risk/test_strategy_greeks_validation.py
"""

import pytest
from unittest.mock import MagicMock
from datetime import date

from src.v6.strategies.models import (
    LegAction,
    LegSpec,
    OptionRight,
    Strategy,
    StrategyType,
)
from src.v6.risk.strategy_greeks_validator import StrategyGreeksValidator
from src.v6.risk.models import StrategyGreeksLimits


# Module-level fixtures (shared across all test classes)


@pytest.fixture
def delta_neutral_iron_condor():
    """Create a properly delta-neutral Iron Condor."""
    return Strategy(
        strategy_id="ic-neutral-spy-001",
        symbol="SPY",
        strategy_type=StrategyType.IRON_CONDOR,
        legs=[
            LegSpec(right=OptionRight.PUT, strike=440.0, quantity=1, action=LegAction.SELL, expiration=date(2026, 3, 20)),
            LegSpec(right=OptionRight.PUT, strike=430.0, quantity=1, action=LegAction.BUY, expiration=date(2026, 3, 20)),
            LegSpec(right=OptionRight.CALL, strike=460.0, quantity=1, action=LegAction.SELL, expiration=date(2026, 3, 20)),
            LegSpec(right=OptionRight.CALL, strike=470.0, quantity=1, action=LegAction.BUY, expiration=date(2026, 3, 20)),
        ],
        metadata={"underlying_price": 450.0},
    )


@pytest.fixture
def skewed_iron_condor_bearish():
    """Create a BEARISH-skewed Iron Condor (like the IWM position -11.94 delta)."""
    return Strategy(
        strategy_id="ic-bearish-iwm-bad",
        symbol="IWM",
        strategy_type=StrategyType.IRON_CONDOR,
        legs=[
            LegSpec(right=OptionRight.PUT, strike=210.0, quantity=1, action=LegAction.SELL, expiration=date(2026, 3, 20)),
            LegSpec(right=OptionRight.PUT, strike=200.0, quantity=1, action=LegAction.BUY, expiration=date(2026, 3, 20)),
            LegSpec(right=OptionRight.CALL, strike=242.0, quantity=1, action=LegAction.SELL, expiration=date(2026, 3, 20)),
            LegSpec(right=OptionRight.CALL, strike=252.0, quantity=1, action=LegAction.BUY, expiration=date(2026, 3, 20)),
        ],
        metadata={"underlying_price": 225.87},
    )


@pytest.fixture
def validator_config():
    """Create strategy Greeks validation config."""
    return StrategyGreeksLimits(
        iron_condor_max_abs_delta=5.0,  # Iron Condors must have |delta| < 5
        vertical_spread_max_abs_delta=30.0,
    )


@pytest.fixture
def mock_greeks_calculator():
    """Create mock Greeks calculator."""
    return MagicMock()


class TestIronCondorDeltaNeutral:
    """Test Iron Condor delta-neutral validation."""

    def test_accepts_delta_neutral_iron_condor(
        self, delta_neutral_iron_condor, validator_config, mock_greeks_calculator
    ):
        """Test that delta-neutral Iron Condor is accepted."""
        # Return small delta (neutral)
        mock_greeks_calculator.calculate_position_greeks.return_value = {
            "delta": 2.5,
            "gamma": 0.5,
            "theta": -10.0,
            "vega": 50.0,
        }

        validator = StrategyGreeksValidator(mock_greeks_calculator, validator_config)
        is_valid, violations = validator.validate_strategy(delta_neutral_iron_condor)

        assert is_valid, f"Delta-neutral Iron Condor should be valid, got violations: {violations}"
        assert len(violations) == 0

    def test_rejects_bearish_skewed_iron_condor(
        self, skewed_iron_condor_bearish, validator_config, mock_greeks_calculator
    ):
        """Test that bearish-skewed Iron Condor (-11.94 delta) is rejected."""
        # Return large negative delta (like the IWM position)
        mock_greeks_calculator.calculate_position_greeks.return_value = {
            "delta": -11.94,
            "gamma": 0.5,
            "theta": -10.0,
            "vega": 50.0,
        }

        validator = StrategyGreeksValidator(mock_greeks_calculator, validator_config)
        is_valid, violations = validator.validate_strategy(skewed_iron_condor_bearish)

        assert not is_valid, "Bearish-skewed Iron Condor should be rejected"
        assert len(violations) > 0

        # Check violation message
        violation_text = " ".join(violations)
        assert "11.94" in violation_text or "11" in violation_text
        assert "5.0" in violation_text or "5" in violation_text

    def test_iron_condor_delta_at_threshold(
        self, delta_neutral_iron_condor, validator_config, mock_greeks_calculator
    ):
        """Test Iron Condor with delta exactly at threshold."""
        mock_greeks_calculator.calculate_position_greeks.return_value = {
            "delta": 5.0,
            "gamma": 0.5,
            "theta": -10.0,
            "vega": 50.0,
        }

        validator = StrategyGreeksValidator(mock_greeks_calculator, validator_config)
        is_valid, violations = validator.validate_strategy(delta_neutral_iron_condor)

        assert is_valid, "Iron Condor at threshold should be valid"


class TestStrategyGreeksLimitsConfig:
    """Test StrategyGreeksLimits configuration."""

    def test_default_iron_condor_limits(self):
        """Test default Iron Condor delta limits."""
        limits = StrategyGreeksLimits()
        assert limits.iron_condor_max_abs_delta == 5.0

    def test_custom_iron_condor_limits(self):
        """Test custom Iron Condor delta limits."""
        limits = StrategyGreeksLimits(iron_condor_max_abs_delta=3.0)
        assert limits.iron_condor_max_abs_delta == 3.0

    def test_vertical_spread_allows_more_delta(self):
        """Test that vertical spreads can have more directional delta."""
        limits = StrategyGreeksLimits()
        assert limits.vertical_spread_max_abs_delta > limits.iron_condor_max_abs_delta


class TestIntegrationWithPortfolioLimits:
    """Test integration with portfolio-level limits."""

    def test_portfolio_limits_use_abs_delta(self):
        """Test that portfolio limits properly use abs(delta) for protection."""
        from src.v6.risk.models import RiskLimitsConfig

        limits = RiskLimitsConfig(
            max_portfolio_delta=50.0,
            max_per_symbol_delta=20.0,
        )

        # Test skewed position like IWM
        skewed_delta = -11.94

        # Portfolio limits check abs value
        portfolio_ok = abs(skewed_delta) < limits.max_portfolio_delta
        symbol_ok = abs(skewed_delta) < limits.max_per_symbol_delta

        # Should pass portfolio limits (but fail strategy-specific checks)
        assert portfolio_ok, "Portfolio limits use abs(delta)"
        assert symbol_ok, "Symbol limits use abs(delta)"

    def test_strategy_validation_catches_what_portfolio_limits_miss(
        self, skewed_iron_condor_bearish, validator_config, mock_greeks_calculator
    ):
        """
        Test that strategy validation catches skewed positions
        that pass portfolio limits.

        Scenario:
        - IWM Iron Condor with -11.94 delta
        - Passes portfolio limits (abs(-11.94) < 20)
        - But FAILS strategy validation (abs(-11.94) > 5 for Iron Condor)
        """
        from src.v6.risk.models import RiskLimitsConfig

        # Portfolio limits (would ALLOW this position)
        portfolio_limits = RiskLimitsConfig(
            max_portfolio_delta=50.0,
            max_per_symbol_delta=20.0,
        )

        skewed_delta = -11.94
        passes_portfolio = abs(skewed_delta) < portfolio_limits.max_per_symbol_delta
        assert passes_portfolio, "Position passes portfolio limits"

        # Strategy limits (should REJECT this position)
        passes_strategy = abs(skewed_delta) < validator_config.iron_condor_max_abs_delta
        assert not passes_strategy, "Position fails strategy validation"

        # Verify with actual validator
        mock_greeks_calculator.calculate_position_greeks.return_value = {
            "delta": -11.94,
            "gamma": 0.5,
            "theta": -10.0,
            "vega": 50.0,
        }

        validator = StrategyGreeksValidator(mock_greeks_calculator, validator_config)
        is_valid, violations = validator.validate_strategy(skewed_iron_condor_bearish)

        assert not is_valid, "Strategy validator should reject this position"
        assert len(violations) > 0, "Should have violations"
