"""
Tests for UnrealizedPnLCalculator component

Tests Black-Scholes option pricing, position-level P&L calculation,
strategy aggregation, and historical time series generation.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from v6.system_monitor.dashboard.components.pnl_display import UnrealizedPnLCalculator


class TestBlackScholesPricing:
    """Test Black-Scholes option pricing calculations."""

    @pytest.fixture
    def calculator(self):
        """Create calculator instance."""
        return UnrealizedPnLCalculator()

    def test_call_option_pricing(self, calculator):
        """Test call option pricing with standard inputs."""
        # ATM call option
        price = calculator.black_scholes(
            S=100.0,  # Underlying price
            K=100.0,  # Strike
            T=0.25,   # 3 months to expiry
            r=0.05,   # 5% risk-free rate
            sigma=0.20,  # 20% volatility
            option_type='call'
        )

        # ATM call should have positive value
        assert price > 0
        # ATM call price should be reasonable (typically $3-5 for these params)
        assert 2.0 < price < 8.0

    def test_put_option_pricing(self, calculator):
        """Test put option pricing with standard inputs."""
        # ATM put option
        price = calculator.black_scholes(
            S=100.0,
            K=100.0,
            T=0.25,
            r=0.05,
            sigma=0.20,
            option_type='put'
        )

        # ATM put should have positive value
        assert price > 0
        # ATM put price should be reasonable
        assert 2.0 < price < 8.0

    def test_itm_call_pricing(self, calculator):
        """Test in-the-money call option pricing."""
        # ITM call (strike below underlying)
        price = calculator.black_scholes(
            S=110.0,
            K=100.0,
            T=0.25,
            r=0.05,
            sigma=0.20,
            option_type='call'
        )

        # ITM call should be worth more than intrinsic value
        intrinsic = 110.0 - 100.0
        assert price >= intrinsic

    def test_otm_call_pricing(self, calculator):
        """Test out-of-the-money call option pricing."""
        # OTM call (strike above underlying)
        price = calculator.black_scholes(
            S=90.0,
            K=100.0,
            T=0.25,
            r=0.05,
            sigma=0.20,
            option_type='call'
        )

        # OTM call should be worth less than ATM, but still positive (time value)
        assert price > 0
        assert price < 10.0  # Less than $10 (mostly time value)

    def test_at_expiry(self, calculator):
        """Test option pricing at expiry (T=0)."""
        # ATM option at expiry
        price = calculator.black_scholes(
            S=100.0,
            K=100.0,
            T=0.0,
            r=0.05,
            sigma=0.20,
            option_type='call'
        )

        # At expiry, ATM option is worthless
        assert price == 0.0

    def test_zero_volatility(self, calculator):
        """Test option pricing with zero volatility."""
        # With zero vol, option worth intrinsic value only
        price = calculator.black_scholes(
            S=110.0,
            K=100.0,
            T=0.25,
            r=0.05,
            sigma=0.0,
            option_type='call'
        )

        # Should equal intrinsic value
        intrinsic = 110.0 - 100.0
        assert abs(price - intrinsic) < 0.01


class TestPositionUnrealizedPnL:
    """Test position-level unrealized P&L calculation."""

    @pytest.fixture
    def calculator(self):
        """Create calculator instance."""
        return UnrealizedPnLCalculator()

    @pytest.fixture
    def sample_position(self):
        """Create sample position dict."""
        return {
            'trade_id': 'TEST-001',
            'strategy_id': 'iron_condor_1',
            'symbol': 'SPY',
            'legs': [
                {
                    'right': 'PUT',
                    'strike': 380.0,
                    'expiration': '2026-03-20',
                    'quantity': 1,
                    'action': 'SELL',
                    'fill_price': 2.50
                },
                {
                    'right': 'PUT',
                    'strike': 375.0,
                    'expiration': '2026-03-20',
                    'quantity': 1,
                    'action': 'BUY',
                    'fill_price': 1.80
                }
            ],
            'entry_params': {
                'net_credit': 0.70
            }
        }

    def test_calculate_position_pnl(self, calculator, sample_position):
        """Test calculating unrealized P&L for a position."""
        current_prices = {'SPY': 400.0}

        result = calculator.calculate_position_unrealized_pnl(
            sample_position,
            current_prices
        )

        # Check structure
        assert 'trade_id' in result
        assert 'strategy_id' in result
        assert 'unrealized_pnl' in result
        assert 'unrealized_pnl_pct' in result
        assert 'legs' in result

        # Check values
        assert result['trade_id'] == 'TEST-001'
        assert result['strategy_id'] == 'iron_condor_1'
        assert len(result['legs']) == 2

    def test_leg_breakdown(self, calculator, sample_position):
        """Test leg-level P&L breakdown."""
        current_prices = {'SPY': 400.0}

        result = calculator.calculate_position_unrealized_pnl(
            sample_position,
            current_prices
        )

        # Check leg details
        leg1 = result['legs'][0]
        assert leg1['right'] == 'PUT'
        assert leg1['strike'] == 380.0
        assert leg1['action'] == 'SELL'
        assert 'entry_value' in leg1
        assert 'current_value' in leg1
        assert 'unrealized_pnl' in leg1


class TestStrategyAggregation:
    """Test strategy-level P&L aggregation."""

    @pytest.fixture
    def calculator(self):
        """Create calculator instance."""
        return UnrealizedPnLCalculator()

    @pytest.fixture
    def sample_positions(self):
        """Create sample position list."""
        return [
            {
                'trade_id': 'TEST-001',
                'strategy_id': 'strategy_1',
                'symbol': 'SPY',
                'legs': [
                    {
                        'right': 'PUT',
                        'strike': 380.0,
                        'expiration': '2026-03-20',
                        'quantity': 1,
                        'action': 'SELL',
                        'fill_price': 2.50
                    }
                ],
                'entry_params': {'net_credit': 2.50}
            },
            {
                'trade_id': 'TEST-002',
                'strategy_id': 'strategy_1',
                'symbol': 'SPY',
                'legs': [
                    {
                        'right': 'CALL',
                        'strike': 420.0,
                        'expiration': '2026-03-20',
                        'quantity': 1,
                        'action': 'SELL',
                        'fill_price': 1.80
                    }
                ],
                'entry_params': {'net_credit': 1.80}
            }
        ]

    def test_calculate_strategy_pnl(self, calculator, sample_positions):
        """Test calculating strategy-level P&L."""
        current_prices = {'SPY': 400.0}

        result = calculator.calculate_strategy_unrealized_pnl(
            'strategy_1',
            sample_positions,
            current_prices
        )

        # Check structure
        assert result['strategy_id'] == 'strategy_1'
        assert result['position_count'] == 2
        assert 'total_unrealized_pnl' in result
        assert 'total_unrealized_pnl_pct' in result
        assert 'positions' in result
        assert len(result['positions']) == 2

    def test_best_worst_positions(self, calculator, sample_positions):
        """Test tracking best and worst positions."""
        current_prices = {'SPY': 400.0}

        result = calculator.calculate_strategy_unrealized_pnl(
            'strategy_1',
            sample_positions,
            current_prices
        )

        # Should have best and worst position tracking
        assert 'best_position' in result
        assert 'worst_position' in result


class TestHistoricalPnL:
    """Test historical P&L time series generation."""

    @pytest.fixture
    def calculator(self):
        """Create calculator instance."""
        return UnrealizedPnLCalculator()

    def test_empty_history(self, calculator):
        """Test historical P&L with no data."""
        result = calculator.get_historical_pnl('strategy_1', days=30)

        # Check structure
        assert result['strategy_id'] == 'strategy_1'
        assert result['days'] == 30
        assert result['realized_pnl'] == 0.0
        assert result['unrealized_pnl'] == 0.0
        assert result['total_pnl'] == 0.0
        assert result['daily_pnl_series'] == []

    @patch('v6.dashboard.components.pnl_display.PerformanceReader')
    def test_with_metrics_data(self, mock_reader_class, calculator):
        """Test historical P&L with metrics data."""
        # This test requires actual Delta Lake data, so we skip it
        # The functionality will be verified manually through the dashboard
        pytest.skip("Requires Delta Lake data - will be verified through dashboard integration")


class TestTimeToExpiry:
    """Test time to expiry calculation."""

    @pytest.fixture
    def calculator(self):
        """Create calculator instance."""
        return UnrealizedPnLCalculator()

    def test_parse_yyyymmdd(self, calculator):
        """Test parsing YYYYMMDD format."""
        T = calculator._calculate_time_to_expiry('20260320')

        # Should be positive and less than 1 year
        assert 0.0 < T < 1.0

    def test_parse_yyyy_mm_dd(self, calculator):
        """Test parsing YYYY-MM-DD format."""
        T = calculator._calculate_time_to_expiry('2026-03-20')

        # Should be positive and less than 1 year
        assert 0.0 < T < 1.0

    def test_past_expiry(self, calculator):
        """Test handling of past expiry dates."""
        T = calculator._calculate_time_to_expiry('20200101')

        # Should return 0.0 for past dates
        assert T == 0.0

    def test_invalid_format(self, calculator):
        """Test handling of invalid date format."""
        T = calculator._calculate_time_to_expiry('invalid')

        # Should return default small positive value
        assert T == 0.01
