"""
Tests for Call/Put Spread strategy templates.
"""

import pytest
from datetime import date, timedelta

from v6.strategies.models import LegAction, OptionRight, StrategyType
from v6.strategies.strategy_templates import CallSpreadTemplate, PutSpreadTemplate


class TestCallSpreadTemplate:
    """Tests for CallSpreadTemplate."""

    @pytest.fixture
    def template(self):
        """Return CallSpreadTemplate instance."""
        return CallSpreadTemplate()

    @pytest.fixture
    def valid_params(self):
        """Return valid call spread parameters."""
        return {
            'short_call_strike': 420.0,
            'long_call_strike': 425.0,
            'expiry': date.today() + timedelta(days=35),
            'quantity': 1,
            'min_spread': 5.0
        }

    def test_generate_bullish_call_spread(self, template, valid_params):
        """Test generating bullish call spread (debit spread)."""
        legs = template.generate_legs("SPY", "bullish", valid_params)

        assert len(legs) == 2

        # Long lower strike (debit spread)
        assert legs[0].right == OptionRight.CALL
        assert legs[0].strike == 420.0
        assert legs[0].action == LegAction.BUY

        # Short higher strike
        assert legs[1].right == OptionRight.CALL
        assert legs[1].strike == 425.0
        assert legs[1].action == LegAction.SELL

    def test_generate_bearish_call_spread(self, template, valid_params):
        """Test generating bearish call spread (credit spread)."""
        legs = template.generate_legs("SPY", "bearish", valid_params)

        assert len(legs) == 2

        # Short lower strike (credit spread)
        assert legs[0].right == OptionRight.CALL
        assert legs[0].strike == 420.0
        assert legs[0].action == LegAction.SELL

        # Long higher strike
        assert legs[1].right == OptionRight.CALL
        assert legs[1].strike == 425.0
        assert legs[1].action == LegAction.BUY

    def test_generate_legs_invalid_strike_order(self, template):
        """Test that invalid strike order raises error."""
        invalid_params = {
            'short_call_strike': 425.0,  # Higher than long_call
            'long_call_strike': 420.0,
            'expiry': date.today() + timedelta(days=35),
            'quantity': 1
        }

        with pytest.raises(ValueError, match="short_call_strike.*must be <"):
            template.generate_legs("SPY", "bullish", invalid_params)

    def test_generate_legs_spread_too_small(self, template):
        """Test that spread below minimum raises error."""
        invalid_params = {
            'short_call_strike': 420.0,
            'long_call_strike': 422.0,  # Spread = 2 (too small)
            'expiry': date.today() + timedelta(days=35),
            'quantity': 1,
            'min_spread': 5.0
        }

        with pytest.raises(ValueError, match="Spread width.*< min_spread"):
            template.generate_legs("SPY", "bullish", invalid_params)

    def test_calculate_greeks_bullish(self, template, valid_params):
        """Test calculating bullish call spread greeks."""
        legs = template.generate_legs("SPY", "bullish", valid_params)
        greeks = template.calculate_greeks(legs)

        # Bullish call spread: positive delta, negative theta, negative vega
        assert greeks.delta > 0
        assert greeks.theta < 0
        assert greeks.vega < 0

    def test_calculate_greeks_bearish(self, template, valid_params):
        """Test calculating bearish call spread greeks."""
        legs = template.generate_legs("SPY", "bearish", valid_params)
        greeks = template.calculate_greeks(legs)

        # Bearish call spread: negative delta, positive theta, positive vega
        assert greeks.delta < 0
        assert greeks.theta > 0
        assert greeks.vega > 0

    def test_validate_params_valid(self, template, valid_params):
        """Test validating valid parameters."""
        assert template.validate_params(valid_params) is True

    def test_validate_params_missing_required(self, template):
        """Test that missing required params raise error."""
        incomplete_params = {
            'short_call_strike': 420.0,
            # Missing long_call_strike, expiry, quantity
        }

        with pytest.raises(ValueError, match="Missing required parameter"):
            template.validate_params(incomplete_params)

    def test_get_default_params(self, template):
        """Test getting default parameters."""
        defaults = template.get_default_params()

        assert 'spread_width' in defaults
        assert 'DTE' in defaults
        assert 'delta_target' in defaults
        assert 'min_spread' in defaults

        assert defaults['spread_width'] == 5.0
        assert 30 <= defaults['DTE'] <= 45
        assert 0.25 <= defaults['delta_target'] <= 0.40

    def test_estimate_risk_reward_bullish(self, template):
        """Test risk/reward for bullish call spread."""
        params = {
            'net_premium': -1.50,  # Paid $1.50 (debit)
            'spread_width': 5.0,
            'quantity': 1,
            'direction': 'bullish'
        }

        max_profit, max_loss = template.estimate_risk_reward(params)

        # Bullish: max_loss = debit paid, max_profit = spread - debit
        assert max_loss == pytest.approx(150.0)  # $1.50 * 100
        assert max_profit == pytest.approx(350.0)  # (5 - 1.50) * 100

    def test_estimate_risk_reward_bearish(self, template):
        """Test risk/reward for bearish call spread."""
        params = {
            'net_premium': 1.50,  # Received $1.50 (credit)
            'spread_width': 5.0,
            'quantity': 1,
            'direction': 'bearish'
        }

        max_profit, max_loss = template.estimate_risk_reward(params)

        # Bearish: max_profit = credit, max_loss = spread - credit
        assert max_profit == pytest.approx(150.0)  # $1.50 * 100
        assert max_loss == pytest.approx(350.0)  # (5 - 1.50) * 100

    def test_get_strategy_type(self, template):
        """Test getting strategy type."""
        assert template.get_strategy_type() == StrategyType.VERTICAL_SPREAD


class TestPutSpreadTemplate:
    """Tests for PutSpreadTemplate."""

    @pytest.fixture
    def template(self):
        """Return PutSpreadTemplate instance."""
        return PutSpreadTemplate()

    @pytest.fixture
    def valid_params(self):
        """Return valid put spread parameters."""
        return {
            'short_put_strike': 380.0,
            'long_put_strike': 375.0,
            'expiry': date.today() + timedelta(days=35),
            'quantity': 1,
            'min_spread': 5.0
        }

    def test_generate_bullish_put_spread(self, template, valid_params):
        """Test generating bullish put spread (credit spread)."""
        legs = template.generate_legs("SPY", "bullish", valid_params)

        assert len(legs) == 2

        # Short higher strike (credit spread)
        assert legs[0].right == OptionRight.PUT
        assert legs[0].strike == 380.0
        assert legs[0].action == LegAction.SELL

        # Long lower strike
        assert legs[1].right == OptionRight.PUT
        assert legs[1].strike == 375.0
        assert legs[1].action == LegAction.BUY

    def test_generate_bearish_put_spread(self, template, valid_params):
        """Test generating bearish put spread (debit spread)."""
        legs = template.generate_legs("SPY", "bearish", valid_params)

        assert len(legs) == 2

        # Long higher strike (debit spread)
        assert legs[0].right == OptionRight.PUT
        assert legs[0].strike == 380.0
        assert legs[0].action == LegAction.BUY

        # Short lower strike
        assert legs[1].right == OptionRight.PUT
        assert legs[1].strike == 375.0
        assert legs[1].action == LegAction.SELL

    def test_generate_legs_invalid_strike_order(self, template):
        """Test that invalid strike order raises error."""
        invalid_params = {
            'short_put_strike': 375.0,  # Lower than long_put
            'long_put_strike': 380.0,
            'expiry': date.today() + timedelta(days=35),
            'quantity': 1
        }

        with pytest.raises(ValueError, match="short_put_strike.*must be >"):
            template.generate_legs("SPY", "bullish", invalid_params)

    def test_generate_legs_spread_too_small(self, template):
        """Test that spread below minimum raises error."""
        invalid_params = {
            'short_put_strike': 380.0,
            'long_put_strike': 378.0,  # Spread = 2 (too small)
            'expiry': date.today() + timedelta(days=35),
            'quantity': 1,
            'min_spread': 5.0
        }

        with pytest.raises(ValueError, match="Spread width.*< min_spread"):
            template.generate_legs("SPY", "bullish", invalid_params)

    def test_calculate_greeks_bullish(self, template, valid_params):
        """Test calculating bullish put spread greeks."""
        legs = template.generate_legs("SPY", "bullish", valid_params)
        greeks = template.calculate_greeks(legs)

        # Bullish put spread: negative delta, positive theta, negative vega
        assert greeks.delta < 0
        assert greeks.theta > 0
        assert greeks.vega < 0

    def test_calculate_greeks_bearish(self, template, valid_params):
        """Test calculating bearish put spread greeks."""
        legs = template.generate_legs("SPY", "bearish", valid_params)
        greeks = template.calculate_greeks(legs)

        # Bearish put spread: negative delta (larger), negative theta, positive vega
        assert greeks.delta < 0
        assert abs(greeks.delta) > 0.3  # More negative than bullish
        assert greeks.theta < 0
        assert greeks.vega > 0

    def test_validate_params_valid(self, template, valid_params):
        """Test validating valid parameters."""
        assert template.validate_params(valid_params) is True

    def test_validate_params_missing_required(self, template):
        """Test that missing required params raise error."""
        incomplete_params = {
            'short_put_strike': 380.0,
            # Missing long_put_strike, expiry, quantity
        }

        with pytest.raises(ValueError, match="Missing required parameter"):
            template.validate_params(incomplete_params)

    def test_get_default_params(self, template):
        """Test getting default parameters."""
        defaults = template.get_default_params()

        assert 'spread_width' in defaults
        assert 'DTE' in defaults
        assert 'delta_target' in defaults
        assert 'min_spread' in defaults

        assert defaults['spread_width'] == 5.0
        assert 30 <= defaults['DTE'] <= 45
        assert 0.25 <= defaults['delta_target'] <= 0.40

    def test_estimate_risk_reward_bullish(self, template):
        """Test risk/reward for bullish put spread."""
        params = {
            'net_premium': 1.50,  # Received $1.50 (credit)
            'spread_width': 5.0,
            'quantity': 1,
            'direction': 'bullish'
        }

        max_profit, max_loss = template.estimate_risk_reward(params)

        # Bullish: max_profit = credit, max_loss = spread - credit
        assert max_profit == pytest.approx(150.0)  # $1.50 * 100
        assert max_loss == pytest.approx(350.0)  # (5 - 1.50) * 100

    def test_estimate_risk_reward_bearish(self, template):
        """Test risk/reward for bearish put spread."""
        params = {
            'net_premium': -1.50,  # Paid $1.50 (debit)
            'spread_width': 5.0,
            'quantity': 1,
            'direction': 'bearish'
        }

        max_profit, max_loss = template.estimate_risk_reward(params)

        # Bearish: max_loss = debit paid, max_profit = spread - debit
        assert max_loss == pytest.approx(150.0)  # $1.50 * 100
        assert max_profit == pytest.approx(350.0)  # (5 - 1.50) * 100

    def test_get_strategy_type(self, template):
        """Test getting strategy type."""
        assert template.get_strategy_type() == StrategyType.VERTICAL_SPREAD
