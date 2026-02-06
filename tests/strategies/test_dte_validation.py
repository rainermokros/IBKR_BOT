"""
Tests for DTE validation in strategies models.
"""

import pytest
from datetime import date, timedelta
from src.v6.strategies.models import (
    validate_dte_range,
    validate_strike_price,
    LegSpec,
    OptionRight,
    LegAction,
    DTE_MIN_DAYS,
    DTE_MAX_DAYS,
)


class TestDTEValidation:
    """Test DTE range validation."""

    def test_validate_dte_range_valid(self):
        """Test valid DTE range is accepted."""
        today = date.today()

        # Test minimum DTE (21 days)
        min_expiration = today + timedelta(days=DTE_MIN_DAYS)
        dte = validate_dte_range(min_expiration)
        assert dte == DTE_MIN_DAYS

        # Test maximum DTE (45 days)
        max_expiration = today + timedelta(days=DTE_MAX_DAYS)
        dte = validate_dte_range(max_expiration)
        assert dte == DTE_MAX_DAYS

        # Test middle of range (30 days)
        mid_expiration = today + timedelta(days=30)
        dte = validate_dte_range(mid_expiration)
        assert dte == 30

    def test_validate_dte_range_too_short(self):
        """Test DTE below minimum raises error."""
        today = date.today()

        # Test 20 days (below minimum)
        short_expiration = today + timedelta(days=DTE_MIN_DAYS - 1)
        with pytest.raises(ValueError, match="DTE 20 days is too short"):
            validate_dte_range(short_expiration)

        # Test very short (1 day)
        very_short = today + timedelta(days=1)
        with pytest.raises(ValueError, match="DTE 1 days is too short"):
            validate_dte_range(very_short)

    def test_validate_dte_range_too_long(self):
        """Test DTE above maximum raises error."""
        today = date.today()

        # Test 46 days (above maximum)
        long_expiration = today + timedelta(days=DTE_MAX_DAYS + 1)
        with pytest.raises(ValueError, match="DTE 46 days is too long"):
            validate_dte_range(long_expiration)

        # Test very long (100 days)
        very_long = today + timedelta(days=100)
        with pytest.raises(ValueError, match="DTE 100 days is too long"):
            validate_dte_range(very_long)

    def test_validate_dte_range_past_expiration(self):
        """Test past expiration raises error."""
        today = date.today()
        past_expiration = today - timedelta(days=1)

        with pytest.raises(ValueError, match="DTE -1 days is too short"):
            validate_dte_range(past_expiration)


class TestStrikePriceValidation:
    """Test strike price validation."""

    def test_validate_strike_price_valid(self):
        """Test valid strike prices are accepted."""
        # Test normal strike prices
        validate_strike_price(400.0)  # SPY around $400
        validate_strike_price(150.0)  # QQQ around $150
        validate_strike_price(180.0)  # IWM around $180

    def test_validate_strike_price_negative(self):
        """Test negative strike price raises error."""
        with pytest.raises(ValueError, match="Strike price must be positive"):
            validate_strike_price(-100.0)

    def test_validate_strike_price_zero(self):
        """Test zero strike price raises error."""
        with pytest.raises(ValueError, match="Strike price must be positive"):
            validate_strike_price(0.0)

    def test_validate_strike_price_too_high(self):
        """Test unreasonably high strike price raises error."""
        with pytest.raises(ValueError, match="Strike price unreasonably high"):
            validate_strike_price(15000.0)

    def test_validate_strike_price_with_underlying(self):
        """Test strike price validation with underlying price."""
        underlying = 400.0

        # Test valid range (50-150% of underlying)
        validate_strike_price(200.0, underlying)  # 50%
        validate_strike_price(400.0, underlying)  # 100%
        validate_strike_price(600.0, underlying)  # 150%

        # Test below range
        with pytest.raises(ValueError, match="too far from underlying"):
            validate_strike_price(100.0, underlying)  # 25%

        # Test above range
        with pytest.raises(ValueError, match="too far from underlying"):
            validate_strike_price(1000.0, underlying)  # 250%


class TestLegSpecValidation:
    """Test LegSpec validation with DTE."""

    def test_leg_spec_valid_dte(self):
        """Test LegSpec accepts valid DTE range."""
        today = date.today()
        expiration = today + timedelta(days=30)  # Valid: 30 days

        leg = LegSpec(
            right=OptionRight.CALL,
            strike=400.0,
            quantity=1,
            action=LegAction.BUY,
            expiration=expiration,
        )

        assert leg.expiration == expiration

    def test_leg_spec_rejects_short_dte(self):
        """Test LegSpec rejects DTE below minimum."""
        today = date.today()
        short_expiration = today + timedelta(days=10)  # Invalid: 10 days

        with pytest.raises(ValueError, match="DTE 10 days is too short"):
            LegSpec(
                right=OptionRight.CALL,
                strike=400.0,
                quantity=1,
                action=LegAction.BUY,
                expiration=short_expiration,
            )

    def test_leg_spec_rejects_long_dte(self):
        """Test LegSpec rejects DTE above maximum."""
        today = date.today()
        long_expiration = today + timedelta(days=60)  # Invalid: 60 days

        with pytest.raises(ValueError, match="DTE 60 days is too long"):
            LegSpec(
                right=OptionRight.CALL,
                strike=400.0,
                quantity=1,
                action=LegAction.BUY,
                expiration=long_expiration,
            )

    def test_leg_spec_rejects_invalid_strike(self):
        """Test LegSpec rejects invalid strike price."""
        today = date.today()
        expiration = today + timedelta(days=30)

        # Test negative strike
        with pytest.raises(ValueError, match="Strike price must be positive"):
            LegSpec(
                right=OptionRight.CALL,
                strike=-100.0,
                quantity=1,
                action=LegAction.BUY,
                expiration=expiration,
            )

        # Test unreasonably high strike
        with pytest.raises(ValueError, match="Strike price unreasonably high"):
            LegSpec(
                right=OptionRight.CALL,
                strike=15000.0,
                quantity=1,
                action=LegAction.BUY,
                expiration=expiration,
            )
