"""
Unit Tests for Delta Adjustment in Strategy Builders

Tests delta-based strike selection and IV adjustment:
- Iron Condor delta balance validation
- Credit Spread delta selection
- Wing width calculations
"""

import pytest
from datetime import date, datetime

from v6.strategies.iron_condor_builder_45_21 import IronCondorBuilder45_21
from v6.strategies.credit_spread_builder_45_21 import CreditSpreadBuilder45_21
from v6.strategies.models import StrategyType, OptionRight, LegAction


@pytest.fixture
def sample_option_chain():
    """Create sample option chain with Greeks."""
    return [
        # Puts
        {'strike': 440, 'right': 'P', 'delta': -0.05, 'gamma': 0.01, 'theta': -0.02, 'vega': 0.10},
        {'strike': 450, 'right': 'P', 'delta': -0.08, 'gamma': 0.02, 'theta': -0.03, 'vega': 0.15},
        {'strike': 460, 'right': 'P', 'delta': -0.12, 'gamma': 0.03, 'theta': -0.04, 'vega': 0.20},
        {'strike': 470, 'right': 'P', 'delta': -0.16, 'gamma': 0.04, 'theta': -0.05, 'vega': 0.25},
        {'strike': 480, 'right': 'P', 'delta': -0.20, 'gamma': 0.05, 'theta': -0.06, 'vega': 0.30},
        {'strike': 490, 'right': 'P', 'delta': -0.25, 'gamma': 0.06, 'theta': -0.07, 'vega': 0.35},
        {'strike': 500, 'right': 'P', 'delta': -0.30, 'gamma': 0.07, 'theta': -0.08, 'vega': 0.40},
        # Calls
        {'strike': 510, 'right': 'C', 'delta': 0.30, 'gamma': 0.07, 'theta': -0.08, 'vega': 0.40},
        {'strike': 520, 'right': 'C', 'delta': 0.25, 'gamma': 0.06, 'theta': -0.07, 'vega': 0.35},
        {'strike': 530, 'right': 'C', 'delta': 0.20, 'gamma': 0.05, 'theta': -0.06, 'vega': 0.30},
        {'strike': 540, 'right': 'C', 'delta': 0.16, 'gamma': 0.04, 'theta': -0.05, 'vega': 0.25},
        {'strike': 550, 'right': 'C', 'delta': 0.12, 'gamma': 0.03, 'theta': -0.04, 'vega': 0.20},
        {'strike': 560, 'right': 'C', 'delta': 0.08, 'gamma': 0.02, 'theta': -0.03, 'vega': 0.15},
        {'strike': 570, 'right': 'C', 'delta': 0.05, 'gamma': 0.01, 'theta': -0.02, 'vega': 0.10},
    ]


class TestIronCondorDeltaAdjustment:
    """Test Iron Condor delta-based strike selection."""

    @pytest.fixture
    def builder(self):
        """Create Iron Condor builder instance."""
        return IronCondorBuilder45_21()

    def test_iron_condor_build_with_18_delta(self, builder, sample_option_chain):
        """Test Iron Condor built with 18 delta target."""
        symbol = "SPY"
        underlying_price = 500.0

        strategy = builder.build(
            symbol=symbol,
            underlying_price=underlying_price,
            option_chain=sample_option_chain,
            quantity=1
        )

        # Verify strategy structure
        assert strategy.strategy_type == StrategyType.IRON_CONDOR
        assert len(strategy.legs) == 4
        assert strategy.symbol == symbol

        # Verify metadata
        assert 'framework' in strategy.metadata
        assert strategy.metadata['framework'] == '45_21'
        assert 'target_delta' in strategy.metadata
        assert 'iv_rank' in strategy.metadata

    def test_iron_condor_delta_balance(self, builder, sample_option_chain):
        """Test Iron Condor delta balance validation."""
        symbol = "SPY"
        underlying_price = 500.0

        strategy = builder.build(
            symbol=symbol,
            underlying_price=underlying_price,
            option_chain=sample_option_chain,
            quantity=1
        )

        # Check delta balance (should be ≤ 0.05)
        delta_balance = strategy.metadata.get('delta_balance', 1.0)
        assert delta_balance <= 0.05, \
            f"Delta balance {delta_balance} exceeds threshold 0.05"

        # Check both deltas exist
        assert 'short_put_delta' in strategy.metadata
        assert 'short_call_delta' in strategy.metadata

        # Verify deltas are in reasonable range
        put_delta = abs(strategy.metadata['short_put_delta'])
        call_delta = strategy.metadata['short_call_delta']

        # Should be in 16-20 delta range (or IV-adjusted)
        assert 0.08 <= put_delta <= 0.30, \
            f"Put delta {put_delta} outside reasonable range"
        assert 0.08 <= call_delta <= 0.30, \
            f"Call delta {call_delta} outside reasonable range"

    def test_iron_condor_strike_structure(self, builder, sample_option_chain):
        """Test Iron Condor strike structure is valid."""
        symbol = "SPY"
        underlying_price = 500.0

        strategy = builder.build(
            symbol=symbol,
            underlying_price=underlying_price,
            option_chain=sample_option_chain,
            quantity=1
        )

        # Extract strikes from metadata
        lp = strategy.metadata['long_put_strike']
        sp = strategy.metadata['short_put_strike']
        sc = strategy.metadata['short_call_strike']
        lc = strategy.metadata['long_call_strike']

        # Verify strike order: LP < SP < SC < LC
        assert lp < sp, f"Long put {lp} should be < short put {sp}"
        assert sp < sc, f"Short put {sp} should be < short call {sc}"
        assert sc < lc, f"Short call {sc} should be < long call {lc}"

    def test_iron_condor_wing_widths(self, builder, sample_option_chain):
        """Test Iron Condor wing width calculations."""
        symbol = "SPY"
        underlying_price = 500.0

        strategy = builder.build(
            symbol=symbol,
            underlying_price=underlying_price,
            option_chain=sample_option_chain,
            quantity=1
        )

        # Check wing widths
        put_wing = strategy.metadata['put_wing_width']
        call_wing = strategy.metadata['call_wing_width']
        target_wing = strategy.metadata['target_wing_width']

        # Wing widths should be close to target (within 2 points)
        assert abs(put_wing - target_wing) <= 2.0, \
            f"Put wing {put_wing} too far from target {target_wing}"
        assert abs(call_wing - target_wing) <= 2.0, \
            f"Call wing {call_wing} too far from target {target_wing}"

        # Wing widths should be positive
        assert put_wing > 0
        assert call_wing > 0

    def test_iron_condor_validation(self, builder, sample_option_chain):
        """Test Iron Condor validation."""
        symbol = "SPY"
        underlying_price = 500.0

        strategy = builder.build(
            symbol=symbol,
            underlying_price=underlying_price,
            option_chain=sample_option_chain,
            quantity=1
        )

        # Validate should pass
        assert builder.validate(strategy) is True

    def test_iron_condor_invalid_strikes_raises_error(self, builder):
        """Test that invalid strike structure raises error."""
        # Create option chain that would produce invalid structure
        bad_chain = [
            {'strike': 400, 'right': 'P', 'delta': -0.16},
            {'strike': 600, 'right': 'C', 'delta': 0.16},
        ]

        with pytest.raises(ValueError, match="No.*strikes available"):
            builder.build(
                symbol="SPY",
                underlying_price=500.0,
                option_chain=bad_chain,
                quantity=1
            )


class TestCreditSpreadDeltaAdjustment:
    """Test Credit Spread delta-based strike selection."""

    @pytest.fixture
    def builder(self):
        """Create Credit Spread builder instance."""
        return CreditSpreadBuilder45_21()

    def test_bull_put_spread_build(self, builder, sample_option_chain):
        """Test bull put spread built with 30 delta target."""
        symbol = "SPY"
        underlying_price = 500.0

        strategy = builder.build_bull_put_spread(
            symbol=symbol,
            underlying_price=underlying_price,
            option_chain=sample_option_chain,
            quantity=1
        )

        # Verify strategy structure
        assert strategy.strategy_type == StrategyType.VERTICAL_SPREAD
        assert len(strategy.legs) == 2
        assert strategy.symbol == symbol

        # Verify direction
        assert strategy.metadata['direction'] == 'bullish'
        assert strategy.metadata['spread_type'] == 'bull_put_spread'

    def test_bull_put_spread_deltas(self, builder, sample_option_chain):
        """Test bull put spread delta selection."""
        symbol = "SPY"
        underlying_price = 500.0

        strategy = builder.build_bull_put_spread(
            symbol=symbol,
            underlying_price=underlying_price,
            option_chain=sample_option_chain,
            quantity=1
        )

        # Check short put delta
        short_delta = strategy.metadata.get('short_put_delta')
        assert short_delta is not None

        # Should be in reasonable range (25-35 delta or IV-adjusted)
        assert 0.15 <= abs(short_delta) <= 0.40, \
            f"Short put delta {short_delta} outside reasonable range"

    def test_bull_put_spread_width(self, builder, sample_option_chain):
        """Test bull put spread width calculation."""
        symbol = "SPY"
        underlying_price = 500.0

        strategy = builder.build_bull_put_spread(
            symbol=symbol,
            underlying_price=underlying_price,
            option_chain=sample_option_chain,
            quantity=1
        )

        # Check spread width
        spread_width = strategy.metadata['spread_width']
        target_width = strategy.metadata['target_spread_width']

        # Should be close to target (within 2 points)
        assert abs(spread_width - target_width) <= 2.0, \
            f"Spread width {spread_width} too far from target {target_width}"

        # Should be positive
        assert spread_width > 0

    def test_bear_call_spread_build(self, builder, sample_option_chain):
        """Test bear call spread built with 30 delta target."""
        symbol = "SPY"
        underlying_price = 500.0

        strategy = builder.build_bear_call_spread(
            symbol=symbol,
            underlying_price=underlying_price,
            option_chain=sample_option_chain,
            quantity=1
        )

        # Verify strategy structure
        assert strategy.strategy_type == StrategyType.VERTICAL_SPREAD
        assert len(strategy.legs) == 2
        assert strategy.symbol == symbol

        # Verify direction
        assert strategy.metadata['direction'] == 'bearish'
        assert strategy.metadata['spread_type'] == 'bear_call_spread'

    def test_bear_call_spread_deltas(self, builder, sample_option_chain):
        """Test bear call spread delta selection."""
        symbol = "SPY"
        underlying_price = 500.0

        strategy = builder.build_bear_call_spread(
            symbol=symbol,
            underlying_price=underlying_price,
            option_chain=sample_option_chain,
            quantity=1
        )

        # Check short call delta
        short_delta = strategy.metadata.get('short_call_delta')
        assert short_delta is not None

        # Should be in reasonable range (25-35 delta or IV-adjusted)
        assert 0.15 <= short_delta <= 0.40, \
            f"Short call delta {short_delta} outside reasonable range"

    def test_credit_spread_validation(self, builder, sample_option_chain):
        """Test credit spread validation."""
        symbol = "SPY"
        underlying_price = 500.0

        # Test bull put spread
        strategy_bull = builder.build_bull_put_spread(
            symbol=symbol,
            underlying_price=underlying_price,
            option_chain=sample_option_chain,
            quantity=1
        )
        assert builder.validate(strategy_bull) is True

        # Test bear call spread
        strategy_bear = builder.build_bear_call_spread(
            symbol=symbol,
            underlying_price=underlying_price,
            option_chain=sample_option_chain,
            quantity=1
        )
        assert builder.validate(strategy_bear) is True


class TestWingWidthCalculations:
    """Test wing width percentage calculations."""

    @pytest.fixture
    def builder(self):
        """Create Iron Condor builder instance."""
        return IronCondorBuilder45_21()

    def test_wing_width_percentage_spy(self, builder, sample_option_chain):
        """Test wing width is ~2% for SPY at $500."""
        symbol = "SPY"
        underlying_price = 500.0

        strategy = builder.build(
            symbol=symbol,
            underlying_price=underlying_price,
            option_chain=sample_option_chain,
            quantity=1
        )

        target_wing = strategy.metadata['target_wing_width']

        # 2% of $500 = $10
        expected_width = underlying_price * 0.02
        assert abs(target_wing - expected_width) <= 1.0, \
            f"Expected wing width ~${expected_width}, got ${target_wing}"

    def test_wing_width_min_max_limits(self, builder, sample_option_chain):
        """Test that wing widths respect min/max limits."""
        # Test with very low underlying price
        low_price_chain = [
            {'strike': 45, 'right': 'P', 'delta': -0.16},
            {'strike': 50, 'right': 'P', 'delta': -0.18},
            {'strike': 55, 'right': 'C', 'delta': 0.18},
            {'strike': 60, 'right': 'C', 'delta': 0.16},
        ]

        strategy = builder.build(
            symbol="IWM",
            underlying_price=50.0,
            option_chain=low_price_chain,
            quantity=1
        )

        # Wing width should still be reasonable
        target_wing = strategy.metadata['target_wing_width']
        assert target_wing > 0
        # Should be at least 1% of underlying
        assert target_wing >= 50.0 * 0.01


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
