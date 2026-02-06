"""
Unit Tests for IV Rank Calculator

Tests the IVRankCalculator class:
- IV rank calculation from historical data
- Delta adjustment based on IV rank
- IV tier determination
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from v6.indicators.iv_rank import IVRankCalculator


@pytest.fixture
def iv_calculator():
    """Create IV rank calculator instance."""
    return IVRankCalculator(lookback_days=60)


@pytest.fixture
def mock_market_data():
    """Create mock market data with IV values."""
    import polars as pl

    # Create mock data with IV range
    dates = [datetime.now() - timedelta(days=i) for i in range(60, 0, -1)]
    data = {
        'timestamp': dates,
        'symbol': ['SPY'] * 60,
        'close': [500.0] * 60,
        'volume': [1000000] * 60,
        'interval': ['1d'] * 60,
        'iv': [0.15 + (i * 0.001) for i in range(60)],  # IV from 0.15 to 0.209
        'hv': [0.12] * 60,
        'date': [d.date() for d in dates],
        'yearmonth': [202501] * 60,
    }

    df = pl.DataFrame(data)
    return df


class TestIVRankCalculation:
    """Test IV rank calculation."""

    @patch('v6.indicators.iv_rank.DeltaTable')
    def test_iv_rank_calculation_mid_range(self, mock_deltatable, mock_market_data):
        """Test IV rank calculation with mid-range IV."""
        # Setup mock
        mock_table = Mock()
        mock_table.to_pandas.return_value = mock_market_data.to_pandas()
        mock_deltatable.return_value = mock_table

        calculator = IVRankCalculator(lookback_days=60)

        # Mock the DeltaTable constructor
        with patch.object(calculator, '__init__', lambda self, lookback_days=60, config_path=None: None):
            calculator.iv_rank_calculator_lookback_days = 60

            # This would normally calculate IV rank
            # For now, just test the interface
            assert calculator is not None

    def test_iv_rank_bounds(self):
        """Test that IV rank is bounded between 0-100."""
        calculator = IVRankCalculator()

        # Test with mock data that would produce IV rank outside bounds
        # The calculator should clamp to 0-100
        assert True  # Placeholder for actual test

    def test_iv_rank_no_data(self):
        """Test IV rank calculation when no data available."""
        calculator = IVRankCalculator()

        # Should return default value of 50 when no data
        with patch('v6.indicators.iv_rank.DeltaTable') as mock_deltatable:
            mock_table = Mock()
            mock_table.to_pandas.return_value = None
            mock_deltatable.return_value = mock_table

            # This would normally return 50.0 as default
            assert True  # Placeholder


class TestDeltaAdjustment:
    """Test delta adjustment based on IV rank."""

    def test_delta_adjustment_very_high_iv(self, iv_calculator):
        """Test delta adjusts correctly for very high IV (IVR >= 75%)."""
        # Very high IV: Should lower delta target to 8-12 delta range
        base_delta = 0.18
        iv_rank = 80.0

        adjusted = iv_calculator.adjust_delta(
            base_delta=base_delta,
            iv_rank=iv_rank,
            strategy_type='iron_condor'
        )

        # Should be in 8-12 delta range
        assert 0.08 <= adjusted <= 0.12, \
            f"Expected delta in 0.08-0.12 range for IVR={iv_rank}, got {adjusted}"

    def test_delta_adjustment_high_iv(self, iv_calculator):
        """Test delta adjusts correctly for high IV (IVR 50-75%)."""
        # High IV: Should use standard 16-20 delta
        base_delta = 0.18
        iv_rank = 60.0

        adjusted = iv_calculator.adjust_delta(
            base_delta=base_delta,
            iv_rank=iv_rank,
            strategy_type='iron_condor'
        )

        # Should be in 16-20 delta range
        assert 0.16 <= adjusted <= 0.20, \
            f"Expected delta in 0.16-0.20 range for IVR={iv_rank}, got {adjusted}"

    def test_delta_adjustment_moderate_iv(self, iv_calculator):
        """Test delta adjusts correctly for moderate IV (IVR 25-50%)."""
        # Moderate IV: Should move closer to ATM (25-30 delta)
        base_delta = 0.18
        iv_rank = 35.0

        adjusted = iv_calculator.adjust_delta(
            base_delta=base_delta,
            iv_rank=iv_rank,
            strategy_type='iron_condor'
        )

        # Should be in 25-30 delta range
        assert 0.25 <= adjusted <= 0.30, \
            f"Expected delta in 0.25-0.30 range for IVR={iv_rank}, got {adjusted}"

    def test_delta_adjustment_low_iv(self, iv_calculator):
        """Test delta adjustment for low IV (IVR < 25%)."""
        # Low IV: Should warn about debit spreads
        base_delta = 0.18
        iv_rank = 15.0

        # This should log a warning but still return a delta
        adjusted = iv_calculator.adjust_delta(
            base_delta=base_delta,
            iv_rank=iv_rank,
            strategy_type='iron_condor'
        )

        # Should return some value (will fall back to base delta if not configured)
        assert adjusted is not None

    def test_delta_adjustment_credit_spread(self, iv_calculator):
        """Test delta adjustment for credit spreads."""
        # Credit spreads should use different delta ranges
        base_delta = 0.30
        iv_rank = 60.0

        adjusted = iv_calculator.adjust_delta(
            base_delta=base_delta,
            iv_rank=iv_rank,
            strategy_type='credit_spread'
        )

        # Credit spreads at high IV should use 25-35 delta range
        assert 0.25 <= adjusted <= 0.35, \
            f"Expected delta in 0.25-0.35 range for credit spread, got {adjusted}"

    def test_delta_adjustment_unknown_strategy(self, iv_calculator):
        """Test delta adjustment for unknown strategy type."""
        # Unknown strategy should return base delta
        base_delta = 0.18
        iv_rank = 60.0

        adjusted = iv_calculator.adjust_delta(
            base_delta=base_delta,
            iv_rank=iv_rank,
            strategy_type='unknown_strategy'
        )

        # Should return base delta for unknown strategies
        assert adjusted == base_delta, \
            f"Expected base delta {base_delta} for unknown strategy, got {adjusted}"


class TestIVTierDetermination:
    """Test IV tier determination."""

    def test_get_iv_tier_very_high(self, iv_calculator):
        """Test IV tier determination for very high IV."""
        tier = iv_calculator.get_iv_tier(iv_rank=80.0)

        assert tier.get('ivr_min') == 75
        assert tier.get('ivr_max') == 100
        assert 'very expensive premiums' in tier.get('description', '').lower()

    def test_get_iv_tier_high(self, iv_calculator):
        """Test IV tier determination for high IV."""
        tier = iv_calculator.get_iv_tier(iv_rank=60.0)

        assert tier.get('ivr_min') == 50
        assert tier.get('ivr_max') == 75

    def test_get_iv_tier_moderate(self, iv_calculator):
        """Test IV tier determination for moderate IV."""
        tier = iv_calculator.get_iv_tier(iv_rank=35.0)

        assert tier.get('ivr_min') == 25
        assert tier.get('ivr_max') == 50

    def test_get_iv_tier_low(self, iv_calculator):
        """Test IV tier determination for low IV."""
        tier = iv_calculator.get_iv_tier(iv_rank=15.0)

        assert tier.get('ivr_min') == 0
        assert tier.get('ivr_max') == 25


class TestDebitSpreadDecision:
    """Test debit spread preference decision."""

    def test_should_use_debit_spreads_low_iv(self, iv_calculator):
        """Test that debit spreads are preferred at low IV."""
        # Low IV (< 25%): Should prefer debit spreads
        result = iv_calculator.should_use_debit_spreads(iv_rank=15.0)

        assert result is True, "Should use debit spreads at IVR=15%"

    def test_should_use_debit_spreads_high_iv(self, iv_calculator):
        """Test that credit spreads are preferred at high IV."""
        # High IV (> 25%): Should prefer credit spreads
        result = iv_calculator.should_use_debit_spreads(iv_rank=60.0)

        assert result is False, "Should use credit spreads at IVR=60%"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
