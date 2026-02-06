"""
Tests for Wheel strategy template.
"""

import pytest
from datetime import date, timedelta

from v6.strategies.models import LegAction, OptionRight, StrategyType
from v6.strategies.strategy_templates import WheelTemplate


class TestWheelTemplate:
    """Tests for WheelTemplate."""

    @pytest.fixture
    def template(self):
        """Return WheelTemplate instance."""
        return WheelTemplate()

    @pytest.fixture
    def valid_put_params(self):
        """Return valid wheel put phase parameters."""
        return {
            'strike': 380.0,
            'expiry': date.today() + timedelta(days=30),
            'quantity': 100,  # 1 contract
            'phase': 'put'
        }

    @pytest.fixture
    def valid_covered_call_params(self):
        """Return valid wheel covered call phase parameters."""
        return {
            'strike': 420.0,
            'expiry': date.today() + timedelta(days=30),
            'quantity': 100,  # 1 contract
            'phase': 'covered_call',
            'share_price': 400.0
        }

    def test_generate_legs_put_phase(self, template, valid_put_params):
        """Test generating wheel put phase legs."""
        legs = template.generate_legs("SPY", "bullish", valid_put_params)

        assert len(legs) == 1

        # Short put (cash-secured put)
        assert legs[0].right == OptionRight.PUT
        assert legs[0].strike == 380.0
        assert legs[0].action == LegAction.SELL
        assert legs[0].quantity == 100

    def test_generate_legs_covered_call_phase(self, template, valid_covered_call_params):
        """Test generating wheel covered call phase legs."""
        legs = template.generate_legs("SPY", "bullish", valid_covered_call_params)

        assert len(legs) == 2

        # Long shares (simulated)
        assert legs[0].right == OptionRight.CALL
        assert legs[0].strike == 400.0  # share_price
        assert legs[0].action == LegAction.BUY
        assert legs[0].quantity == 100 * 100  # 100 shares per contract

        # Short covered call
        assert legs[1].right == OptionRight.CALL
        assert legs[1].strike == 420.0
        assert legs[1].action == LegAction.SELL
        assert legs[1].quantity == 100

    def test_generate_legs_invalid_phase(self, template, valid_put_params):
        """Test that invalid phase raises error."""
        invalid_params = valid_put_params.copy()
        invalid_params['phase'] = 'invalid_phase'

        with pytest.raises(ValueError, match="Invalid phase"):
            template.generate_legs("SPY", "bullish", invalid_params)

    def test_generate_legs_covered_call_missing_share_price(self, template):
        """Test that missing share_price for covered call raises error."""
        invalid_params = {
            'strike': 420.0,
            'expiry': date.today() + timedelta(days=30),
            'quantity': 100,
            'phase': 'covered_call'
            # Missing share_price
        }

        with pytest.raises(ValueError, match="share_price must be provided"):
            template.generate_legs("SPY", "bullish", invalid_params)

    def test_calculate_greeks_put_phase(self, template, valid_put_params):
        """Test calculating wheel put phase greeks."""
        legs = template.generate_legs("SPY", "bullish", valid_put_params)
        greeks = template.calculate_greeks(legs)

        # Short put: negative delta, positive theta, positive vega
        assert greeks.delta < 0
        assert greeks.theta > 0
        assert greeks.vega > 0

    def test_calculate_greeks_covered_call_phase(self, template, valid_covered_call_params):
        """Test calculating wheel covered call phase greeks."""
        legs = template.generate_legs("SPY", "bullish", valid_covered_call_params)
        greeks = template.calculate_greeks(legs)

        # Covered call: reduced negative delta, positive theta, negative vega
        assert greeks.delta < 0
        assert abs(greeks.delta) < 0.15  # Reduced delta
        assert greeks.theta > 0
        assert greeks.vega < 0

    def test_validate_params_valid_put(self, template, valid_put_params):
        """Test validating valid put phase parameters."""
        assert template.validate_params(valid_put_params) is True

    def test_validate_params_valid_covered_call(self, template, valid_covered_call_params):
        """Test validating valid covered call phase parameters."""
        assert template.validate_params(valid_covered_call_params) is True

    def test_validate_params_missing_required(self, template):
        """Test that missing required params raise error."""
        incomplete_params = {
            'strike': 380.0,
            # Missing expiry, quantity
        }

        with pytest.raises(ValueError, match="Missing required parameter"):
            template.validate_params(incomplete_params)

    def test_validate_params_invalid_strike(self, template):
        """Test that invalid strike raises error."""
        invalid_params = {
            'strike': -10.0,  # Negative strike
            'expiry': date.today() + timedelta(days=30),
            'quantity': 100
        }

        with pytest.raises(ValueError, match="strike must be positive"):
            template.validate_params(invalid_params)

    def test_validate_params_quantity_not_multiple_of_100(self, template):
        """Test that quantity not multiple of 100 raises error."""
        invalid_params = {
            'strike': 380.0,
            'expiry': date.today() + timedelta(days=30),
            'quantity': 150  # Not multiple of 100
        }

        with pytest.raises(ValueError, match="quantity must be in multiples of 100"):
            template.validate_params(invalid_params)

    def test_validate_params_invalid_quantity(self, template):
        """Test that invalid quantity raises error."""
        invalid_params = {
            'strike': 380.0,
            'expiry': date.today() + timedelta(days=30),
            'quantity': 0  # Invalid quantity
        }

        with pytest.raises(ValueError, match="quantity must be positive"):
            template.validate_params(invalid_params)

    def test_validate_params_invalid_expiry(self, template):
        """Test that past expiry raises error."""
        invalid_params = {
            'strike': 380.0,
            'expiry': date.today() - timedelta(days=1),  # Past date
            'quantity': 100
        }

        with pytest.raises(ValueError, match="expiry must be in future"):
            template.validate_params(invalid_params)

    def test_validate_params_invalid_phase(self, template):
        """Test that invalid phase raises error."""
        invalid_params = {
            'strike': 380.0,
            'expiry': date.today() + timedelta(days=30),
            'quantity': 100,
            'phase': 'invalid_phase'
        }

        with pytest.raises(ValueError, match="Invalid phase"):
            template.validate_params(invalid_params)

    def test_validate_params_covered_call_missing_share_price(self, template):
        """Test that missing share_price for covered call raises error."""
        invalid_params = {
            'strike': 380.0,
            'expiry': date.today() + timedelta(days=30),
            'quantity': 100,
            'phase': 'covered_call'
            # Missing share_price
        }

        with pytest.raises(ValueError, match="share_price must be provided"):
            template.validate_params(invalid_params)

    def test_get_default_params(self, template):
        """Test getting default parameters."""
        defaults = template.get_default_params()

        assert 'DTE_target' in defaults
        assert 'delta_target' in defaults
        assert 'roll_threshold' in defaults
        assert 'capital_allocation' in defaults
        assert 'quantity' in defaults
        assert 'phase' in defaults

        # Check reasonable defaults
        assert 20 <= defaults['DTE_target'] <= 45
        assert 0.15 <= defaults['delta_target'] <= 0.30
        assert defaults['roll_threshold'] > 0
        assert 0 < defaults['capital_allocation'] <= 1
        assert defaults['quantity'] == 100
        assert defaults['phase'] == 'put'

    def test_estimate_risk_reward_put_phase(self, template):
        """Test estimating risk/reward for put phase."""
        params = {
            'strike': 380.0,
            'premium': 2.00,
            'quantity': 100,
            'phase': 'put'
        }

        max_profit, max_loss = template.estimate_risk_reward(params)

        # Max profit: premium collected
        assert max_profit == pytest.approx(200.0)  # $2.00 * 100

        # Max loss: strike * quantity - premium
        expected_max_loss = (380.0 * 100) - 200.0
        assert max_loss == pytest.approx(expected_max_loss)

    def test_estimate_risk_reward_covered_call_phase(self, template):
        """Test estimating risk/reward for covered call phase."""
        params = {
            'strike': 420.0,
            'premium': 2.00,
            'quantity': 100,
            'phase': 'covered_call'
        }

        max_profit, max_loss = template.estimate_risk_reward(params)

        # Covered call: estimate ongoing income
        assert max_profit > 0  # Positive monthly premium estimate
        assert max_loss > 0    # Positive downside

    def test_get_strategy_type(self, template):
        """Test getting strategy type."""
        assert template.get_strategy_type() == StrategyType.CUSTOM

    def test_create_strategy_put_phase(self, template, valid_put_params):
        """Test creating a complete put phase strategy."""
        strategy = template.create_strategy("SPY", "bullish", valid_put_params)

        assert strategy.symbol == "SPY"
        assert strategy.strategy_type == StrategyType.CUSTOM
        assert len(strategy.legs) == 1
        assert "WheelTemplate" in strategy.metadata["template"]
        assert strategy.metadata["params"] == valid_put_params

    def test_create_strategy_covered_call_phase(self, template, valid_covered_call_params):
        """Test creating a complete covered call phase strategy."""
        strategy = template.create_strategy("SPY", "bullish", valid_covered_call_params)

        assert strategy.symbol == "SPY"
        assert strategy.strategy_type == StrategyType.CUSTOM
        assert len(strategy.legs) == 2
        assert "WheelTemplate" in strategy.metadata["template"]
        assert strategy.metadata["params"] == valid_covered_call_params

    def test_phase_defaults_to_put(self, template):
        """Test that phase defaults to 'put' if not specified."""
        params = {
            'strike': 380.0,
            'expiry': date.today() + timedelta(days=30),
            'quantity': 100
            # No phase specified
        }

        legs = template.generate_legs("SPY", "bullish", params)

        # Should generate put phase leg
        assert len(legs) == 1
        assert legs[0].right == OptionRight.PUT
        assert legs[0].action == LegAction.SELL

    def test_capital_allocation_in_defaults(self, template):
        """Test that capital_allocation is in default params."""
        defaults = template.get_default_params()

        assert 'capital_allocation' in defaults
        assert 0 < defaults['capital_allocation'] <= 1

    def test_roll_threshold_in_defaults(self, template):
        """Test that roll_threshold is in default params."""
        defaults = template.get_default_params()

        assert 'roll_threshold' in defaults
        assert defaults['roll_threshold'] > 0
