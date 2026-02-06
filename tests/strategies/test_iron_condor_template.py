"""
Tests for Iron Condor strategy template.
"""

import pytest
from datetime import date, timedelta

from v6.strategies.models import LegAction, OptionRight, StrategyType
from v6.strategies.strategy_templates import IronCondorTemplate


class TestIronCondorTemplate:
    """Tests for IronCondorTemplate."""

    @pytest.fixture
    def template(self):
        """Return IronCondorTemplate instance."""
        return IronCondorTemplate()

    @pytest.fixture
    def valid_params(self):
        """Return valid IC parameters."""
        return {
            'short_put_strike': 380.0,
            'short_call_strike': 420.0,
            'long_put_strike': 375.0,
            'long_call_strike': 425.0,
            'expiry': date.today() + timedelta(days=35),
            'quantity': 1,
            'min_wing_width': 5.0
        }

    def test_generate_legs(self, template, valid_params):
        """Test generating iron condor legs."""
        legs = template.generate_legs("SPY", "neutral", valid_params)

        assert len(legs) == 4

        # Long put (lower wing)
        assert legs[0].right == OptionRight.PUT
        assert legs[0].strike == 375.0
        assert legs[0].action == LegAction.BUY
        assert legs[0].quantity == 1

        # Short put (body)
        assert legs[1].right == OptionRight.PUT
        assert legs[1].strike == 380.0
        assert legs[1].action == LegAction.SELL

        # Short call (body)
        assert legs[2].right == OptionRight.CALL
        assert legs[2].strike == 420.0
        assert legs[2].action == LegAction.SELL

        # Long call (upper wing)
        assert legs[3].right == OptionRight.CALL
        assert legs[3].strike == 425.0
        assert legs[3].action == LegAction.BUY

    def test_generate_legs_invalid_strike_relationships(self, template):
        """Test that invalid strike relationships raise error."""
        invalid_params = {
            'short_put_strike': 380.0,
            'short_call_strike': 420.0,
            'long_put_strike': 385.0,  # Greater than short_put - INVALID
            'long_call_strike': 425.0,
            'expiry': date.today() + timedelta(days=35),
            'quantity': 1,
            'min_wing_width': 5.0
        }

        with pytest.raises(ValueError, match="Invalid strike relationships"):
            template.generate_legs("SPY", "neutral", invalid_params)

    def test_generate_legs_wing_width_too_small(self, template):
        """Test that wing width below minimum raises error."""
        invalid_params = {
            'short_put_strike': 380.0,
            'short_call_strike': 420.0,
            'long_put_strike': 379.0,  # Wing width = 1 (too small)
            'long_call_strike': 421.0,
            'expiry': date.today() + timedelta(days=35),
            'quantity': 1,
            'min_wing_width': 5.0
        }

        with pytest.raises(ValueError, match="Put wing width.*< min_wing_width"):
            template.generate_legs("SPY", "neutral", invalid_params)

    def test_calculate_greeks(self, template, valid_params):
        """Test calculating iron condor greeks."""
        legs = template.generate_legs("SPY", "neutral", valid_params)
        greeks = template.calculate_greeks(legs)

        # Iron condor should have balanced greeks
        assert greeks.delta == pytest.approx(0.0, abs=0.1)
        assert greeks.gamma == pytest.approx(0.0, abs=0.1)
        assert greeks.theta > 0  # Positive theta (time decay works in favor)
        assert greeks.vega == pytest.approx(0.0, abs=0.1)

    def test_validate_params_valid(self, template, valid_params):
        """Test validating valid parameters."""
        assert template.validate_params(valid_params) is True

    def test_validate_params_missing_required(self, template):
        """Test that missing required params raise error."""
        incomplete_params = {
            'short_put_strike': 380.0,
            'short_call_strike': 420.0,
            # Missing long_put_strike, long_call_strike, expiry, quantity
        }

        with pytest.raises(ValueError, match="Missing required parameter"):
            template.validate_params(incomplete_params)

    def test_validate_params_invalid_strike(self, template):
        """Test that invalid strike values raise error."""
        invalid_params = {
            'short_put_strike': -10.0,  # Negative strike
            'short_call_strike': 420.0,
            'long_put_strike': 375.0,
            'long_call_strike': 425.0,
            'expiry': date.today() + timedelta(days=35),
            'quantity': 1
        }

        with pytest.raises(ValueError, match="must be positive"):
            template.validate_params(invalid_params)

    def test_validate_params_invalid_quantity(self, template):
        """Test that invalid quantity raises error."""
        invalid_params = {
            'short_put_strike': 380.0,
            'short_call_strike': 420.0,
            'long_put_strike': 375.0,
            'long_call_strike': 425.0,
            'expiry': date.today() + timedelta(days=35),
            'quantity': 0  # Invalid quantity
        }

        with pytest.raises(ValueError, match="quantity must be positive"):
            template.validate_params(invalid_params)

    def test_validate_params_invalid_expiry(self, template):
        """Test that past expiry raises error."""
        invalid_params = {
            'short_put_strike': 380.0,
            'short_call_strike': 420.0,
            'long_put_strike': 375.0,
            'long_call_strike': 425.0,
            'expiry': date.today() - timedelta(days=1),  # Past date
            'quantity': 1
        }

        with pytest.raises(ValueError, match="expiry must be in future"):
            template.validate_params(invalid_params)

    def test_get_default_params(self, template):
        """Test getting default parameters."""
        defaults = template.get_default_params()

        assert 'wing_width' in defaults
        assert 'DTE' in defaults
        assert 'delta_target' in defaults
        assert 'min_wing_width' in defaults
        assert 'quantity' in defaults

        # Check reasonable defaults
        assert defaults['wing_width'] == 10.0
        assert 30 <= defaults['DTE'] <= 45
        assert 0.15 <= defaults['delta_target'] <= 0.30
        assert defaults['min_wing_width'] >= 5.0

    def test_estimate_risk_reward(self, template):
        """Test estimating risk/reward."""
        params = {
            'net_premium': 1.50,  # $1.50 credit
            'wing_width': 10.0,
            'quantity': 1
        }

        max_profit, max_loss = template.estimate_risk_reward(params)

        # Max profit: premium collected
        assert max_profit == pytest.approx(150.0)  # $1.50 * 100

        # Max loss: (wing_width - premium) * 100
        assert max_loss == pytest.approx(850.0)  # (10 - 1.50) * 100

    def test_estimate_risk_reward_multiple_contracts(self, template):
        """Test risk/reward with multiple contracts."""
        params = {
            'net_premium': 1.50,
            'wing_width': 10.0,
            'quantity': 3
        }

        max_profit, max_loss = template.estimate_risk_reward(params)

        assert max_profit == pytest.approx(450.0)  # $1.50 * 3 * 100
        assert max_loss == pytest.approx(2550.0)  # (10 - 1.50) * 3 * 100

    def test_get_strategy_type(self, template):
        """Test getting strategy type."""
        assert template.get_strategy_type() == StrategyType.IRON_CONDOR

    def test_create_strategy(self, template, valid_params):
        """Test creating a complete strategy."""
        strategy = template.create_strategy("SPY", "neutral", valid_params)

        assert strategy.symbol == "SPY"
        assert strategy.strategy_type == StrategyType.IRON_CONDOR
        assert len(strategy.legs) == 4
        assert "IronCondorTemplate" in strategy.metadata["template"]
        assert strategy.metadata["params"] == valid_params

    def test_wing_width_validation_respects_min_wing_width(self, template):
        """Test that min_wing_width parameter is respected."""
        params = {
            'short_put_strike': 380.0,
            'short_call_strike': 420.0,
            'long_put_strike': 376.0,  # Wing width = 4
            'long_call_strike': 424.0,
            'expiry': date.today() + timedelta(days=35),
            'quantity': 1,
            'min_wing_width': 5.0  # Requires at least 5
        }

        with pytest.raises(ValueError, match="Put wing width"):
            template.generate_legs("SPY", "neutral", params)
