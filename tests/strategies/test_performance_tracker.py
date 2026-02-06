"""
Tests for Strategy Performance Tracker.
"""

import pytest
from datetime import datetime, timedelta

from v6.strategies.performance_tracker import StrategyPerformanceTracker
from v6.system_monitor.data.performance_metrics_persistence import (
    Greeks,
    PerformanceMetricsTable,
    PerformanceWriter,
)


@pytest.fixture
def metrics_table(tmp_path):
    """Create a temporary performance metrics table."""
    table_path = tmp_path / "performance_metrics"
    return PerformanceMetricsTable(str(table_path))


@pytest.fixture
def metrics_writer(metrics_table):
    """Create a performance metrics writer."""
    return PerformanceWriter(metrics_table, batch_interval=1)


@pytest.fixture
def tracker(metrics_writer, metrics_table):
    """Create a strategy performance tracker."""
    return StrategyPerformanceTracker(
        strategy_id="test_strategy",
        metrics_writer=metrics_writer,
        metrics_table=metrics_table
    )


@pytest.fixture
def sample_greeks():
    """Return sample Greeks object."""
    return Greeks(delta=0.5, gamma=0.1, theta=-0.05, vega=0.2)


class TestStrategyPerformanceTracker:
    """Tests for StrategyPerformanceTracker."""

    def test_initialization(self, tracker):
        """Test tracker initialization."""
        assert tracker.strategy_id == "test_strategy"
        assert tracker.writer is not None
        assert tracker.table is not None
        assert len(tracker._active_trades) == 0

    @pytest.mark.asyncio
    async def test_track_trade_entry(self, tracker, sample_greeks):
        """Test tracking trade entry."""
        entry_data = {
            'timestamp': datetime.now(),
            'entry_time': datetime.now(),
            'entry_price': 2.50,
            'quantity': 1,
            'premium_collected': 2.50,
            'premium_paid': 0.0,
            'net_premium': 2.50,
            'max_profit': 250.0,
            'max_loss': 750.0,
            'greeks_at_entry': sample_greeks,
            'metadata': {'strategy': 'iron_condor'}
        }

        await tracker.track_trade_entry("trade_001", entry_data)

        # Check trade is in active trades
        assert "trade_001" in tracker._active_trades
        assert tracker._active_trades["trade_001"]['entry'] == entry_data

    @pytest.mark.asyncio
    async def test_track_trade_entry_defaults(self, tracker):
        """Test tracking trade entry with default values."""
        entry_data = {
            'entry_price': 2.50,
            'quantity': 1,
            'premium_collected': 2.50,
        }

        await tracker.track_trade_entry("trade_002", entry_data)

        # Check trade is in active trades
        assert "trade_002" in tracker._active_trades

    @pytest.mark.asyncio
    async def test_track_trade_exit(self, tracker, sample_greeks):
        """Test tracking trade exit."""
        # First, enter a trade
        entry_time = datetime.now() - timedelta(days=10)
        entry_data = {
            'entry_time': entry_time,
            'entry_price': 2.50,
            'quantity': 1,
            'premium_collected': 2.50,
            'premium_paid': 0.0,
            'net_premium': 2.50,
            'max_profit': 250.0,
            'max_loss': 750.0,
            'greeks_at_entry': sample_greeks,
        }

        await tracker.track_trade_entry("trade_003", entry_data)

        # Now exit the trade
        exit_data = {
            'exit_time': datetime.now(),
            'exit_price': 0.50,  # Closed for profit
            'exit_reason': 'expiry',
            'greeks_at_exit': sample_greeks
        }

        await tracker.track_trade_exit("trade_003", exit_data)

        # Check trade is removed from active trades
        assert "trade_003" not in tracker._active_trades

    @pytest.mark.asyncio
    async def test_track_trade_exit_nonexistent_trade(self, tracker):
        """Test that exiting nonexistent trade raises error."""
        exit_data = {
            'exit_time': datetime.now(),
            'exit_price': 0.50,
            'exit_reason': 'manual'
        }

        with pytest.raises(ValueError, match="not found in active trades"):
            await tracker.track_trade_exit("nonexistent_trade", exit_data)

    @pytest.mark.asyncio
    async def test_calculate_unrealized_pnl(self, tracker, sample_greeks):
        """Test calculating unrealized P&L."""
        # Enter a trade
        entry_data = {
            'entry_time': datetime.now(),
            'entry_price': 2.50,
            'quantity': 1,
            'premium_collected': 2.50,
            'premium_paid': 0.0,
            'net_premium': 2.50,  # Credit (short)
        }

        await tracker.track_trade_entry("trade_004", entry_data)

        # Calculate unrealized P&L with current prices
        current_prices = {
            'trade_004': 1.00  # Option value decreased (profit for short)
        }

        unrealized_pnl = tracker.calculate_unrealized_pnl(current_prices)

        # For short: (entry_price - current_price) * quantity * 100
        expected_pnl = (2.50 - 1.00) * 1 * 100
        assert unrealized_pnl['trade_004'] == pytest.approx(expected_pnl)

    @pytest.mark.asyncio
    async def test_calculate_unrealized_pnl_missing_price(self, tracker, sample_greeks):
        """Test calculating unrealized P&L with missing current price."""
        entry_data = {
            'entry_time': datetime.now(),
            'entry_price': 2.50,
            'quantity': 1,
            'premium_collected': 2.50,
        }

        await tracker.track_trade_entry("trade_005", entry_data)

        # Calculate with empty current_prices (should use entry price)
        current_prices = {}
        unrealized_pnl = tracker.calculate_unrealized_pnl(current_prices)

        # Should default to entry price, resulting in 0 P&L
        assert unrealized_pnl['trade_005'] == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_calculate_unrealized_pnl_black_scholes(self, tracker, sample_greeks):
        """Test calculating unrealized P&L using Black-Scholes model."""
        entry_data = {
            'entry_time': datetime.now(),
            'entry_price': 2.50,
            'quantity': 1,
            'premium_collected': 2.50,
            'net_premium': 2.50,
        }

        await tracker.track_trade_entry("trade_006", entry_data)

        # Calculate using Black-Scholes
        market_data = {
            'trade_006': {
                'underlying_price': 400.0,
                'strike': 380.0,
                'time_to_expiry': 0.08,  # ~30 days
                'risk_free_rate': 0.05,
                'volatility': 0.20
            }
        }

        unrealized_pnl = tracker.calculate_unrealized_pnl_black_scholes(market_data)

        # Should return a P&L value (Black-Scholes approximation)
        assert 'trade_006' in unrealized_pnl
        assert isinstance(unrealized_pnl['trade_006'], float)

    @pytest.mark.asyncio
    async def test_get_strategy_performance_empty(self, tracker):
        """Test getting performance when no trades exist."""
        time_range = (datetime.min, datetime.now())
        performance = tracker.get_strategy_performance(time_range)

        assert performance['total_trades'] == 0
        assert performance['win_rate'] == 0.0
        assert performance['avg_realized_pnl'] == 0.0
        assert performance['total_realized_pnl'] == 0.0
        assert performance['avg_hold_duration'] == 0.0
        assert performance['max_drawdown'] == 0.0

    @pytest.mark.asyncio
    async def test_get_strategy_performance_with_trades(self, tracker, sample_greeks):
        """Test getting performance with completed trades."""
        # Enter and exit multiple trades
        trades = [
            {'id': 'trade_007', 'entry_price': 2.50, 'exit_price': 0.50, 'pnl': 200.0},
            {'id': 'trade_008', 'entry_price': 2.00, 'exit_price': 3.00, 'pnl': -100.0},
            {'id': 'trade_009', 'entry_price': 1.50, 'exit_price': 0.00, 'pnl': 150.0},
        ]

        for trade in trades:
            # Entry
            entry_data = {
                'entry_time': datetime.now() - timedelta(days=30),
                'entry_price': trade['entry_price'],
                'quantity': 1,
                'premium_collected': trade['entry_price'],
                'greeks_at_entry': sample_greeks,
            }
            await tracker.track_trade_entry(trade['id'], entry_data)

            # Exit
            exit_data = {
                'exit_time': datetime.now(),
                'exit_price': trade['exit_price'],
                'exit_reason': 'expiry'
            }
            await tracker.track_trade_exit(trade['id'], exit_data)

        # Flush buffer to ensure metrics are written
        await tracker.writer.stop_batch_writing()

        # Get performance
        time_range = (datetime.min, datetime.now())
        performance = tracker.get_strategy_performance(time_range)

        assert performance['total_trades'] == 3
        assert 0 <= performance['win_rate'] <= 1
        assert performance['avg_realized_pnl'] > 0  # Overall profitable
        assert performance['total_realized_pnl'] == pytest.approx(250.0)  # 200 - 100 + 150

    @pytest.mark.asyncio
    async def test_get_strategy_performance_by_exit_reason(self, tracker, sample_greeks):
        """Test getting performance breakdown by exit reason."""
        # Enter and exit trades with different reasons
        trades = [
            {'id': 'trade_010', 'exit_reason': 'expiry', 'pnl': 200.0},
            {'id': 'trade_011', 'exit_reason': 'expiry', 'pnl': 150.0},
            {'id': 'trade_012', 'exit_reason': 'manual', 'pnl': -50.0},
            {'id': 'trade_013', 'exit_reason': 'take_profit', 'pnl': 100.0},
        ]

        for trade in trades:
            entry_data = {
                'entry_time': datetime.now() - timedelta(days=30),
                'entry_price': 2.0,
                'quantity': 1,
                'premium_collected': 2.0,
                'greeks_at_entry': sample_greeks,
            }
            await tracker.track_trade_entry(trade['id'], entry_data)

            exit_data = {
                'exit_time': datetime.now(),
                'exit_price': 0.0,
                'exit_reason': trade['exit_reason']
            }
            await tracker.track_trade_exit(trade['id'], exit_data)

        # Flush buffer
        await tracker.writer.stop_batch_writing()

        # Get performance
        time_range = (datetime.min, datetime.now())
        performance = tracker.get_strategy_performance(time_range)

        # Check exit reason breakdown
        pnl_by_exit = performance['pnl_by_exit_reason']
        assert 'expiry' in pnl_by_exit
        assert pnl_by_exit['expiry']['count'] == 2
        assert 'manual' in pnl_by_exit
        assert pnl_by_exit['manual']['count'] == 1
        assert 'take_profit' in pnl_by_exit
        assert pnl_by_exit['take_profit']['count'] == 1

    def test_get_regime_performance_placeholder(self, tracker):
        """Test that regime performance returns placeholder (not yet implemented)."""
        performance = tracker.get_regime_performance('bullish')

        # Should return performance dict (placeholder for now)
        assert 'total_trades' in performance
        assert 'win_rate' in performance

    def test_get_active_trades(self, tracker):
        """Test getting list of active trades."""
        # Initially empty
        assert tracker.get_active_trades() == []

    @pytest.mark.asyncio
    async def test_get_active_trades_with_entries(self, tracker):
        """Test getting active trades after entries."""
        # Enter multiple trades
        for i in range(3):
            entry_data = {
                'entry_time': datetime.now(),
                'entry_price': 2.0,
                'quantity': 1,
                'premium_collected': 2.0,
            }
            await tracker.track_trade_entry(f"trade_{i}", entry_data)

        active_trades = tracker.get_active_trades()
        assert len(active_trades) == 3
        assert 'trade_0' in active_trades
        assert 'trade_1' in active_trades
        assert 'trade_2' in active_trades

    @pytest.mark.asyncio
    async def test_get_active_trades_after_exit(self, tracker, sample_greeks):
        """Test that active trades updates after exit."""
        # Enter trade
        entry_data = {
            'entry_time': datetime.now(),
            'entry_price': 2.0,
            'quantity': 1,
            'premium_collected': 2.0,
            'greeks_at_entry': sample_greeks,
        }
        await tracker.track_trade_entry("trade_active", entry_data)

        assert len(tracker.get_active_trades()) == 1

        # Exit trade
        exit_data = {
            'exit_time': datetime.now(),
            'exit_price': 0.0,
            'exit_reason': 'manual'
        }
        await tracker.track_trade_exit("trade_active", exit_data)

        assert len(tracker.get_active_trades()) == 0

    def test_black_scholes_price_calculation(self, tracker):
        """Test Black-Scholes price calculation."""
        # At-the-money call option
        S = 100.0  # Underlying price
        K = 100.0  # Strike
        T = 0.25   # 3 months to expiry
        r = 0.05   # 5% risk-free rate
        sigma = 0.20  # 20% volatility

        call_price = tracker._black_scholes_price(S, K, T, r, sigma, is_call=True)
        put_price = tracker._black_scholes_price(S, K, T, r, sigma, is_call=False)

        # Call price should be positive
        assert call_price > 0

        # Put price should be positive
        assert put_price > 0

        # Call-put parity: C - P = S - K * exp(-rT)
        parity_diff = call_price - put_price - (S - K * tracker._exp(-r * T))
        assert abs(parity_diff) < 0.01  # Should approximately satisfy parity

    def test_black_scholes_at_expiry(self, tracker):
        """Test Black-Scholes at expiry (T=0)."""
        S = 105.0
        K = 100.0

        # At expiry, call value = max(S - K, 0)
        call_price = tracker._black_scholes_price(S, K, 0, 0.05, 0.20, is_call=True)
        assert call_price == pytest.approx(5.0)

        # At expiry, put value = max(K - S, 0)
        put_price = tracker._black_scholes_price(S, K, 0, 0.05, 0.20, is_call=False)
        assert put_price == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_hold_duration_calculation(self, tracker, sample_greeks):
        """Test that hold duration is calculated correctly."""
        # Enter trade
        entry_time = datetime.now() - timedelta(hours=6, minutes=30)
        entry_data = {
            'entry_time': entry_time,
            'entry_price': 2.0,
            'quantity': 1,
            'premium_collected': 2.0,
            'greeks_at_entry': sample_greeks,
        }
        await tracker.track_trade_entry("trade_duration", entry_data)

        # Exit trade
        exit_time = datetime.now()
        exit_data = {
            'exit_time': exit_time,
            'exit_price': 0.0,
            'exit_reason': 'manual'
        }
        await tracker.track_trade_exit("trade_duration", exit_data)

        # Flush buffer
        await tracker.writer.stop_batch_writing()

        # Check duration in minutes (6h 30m = 390 minutes)
        time_range = (datetime.min, datetime.now())
        performance = tracker.get_strategy_performance(time_range)
        assert performance['avg_hold_duration'] == pytest.approx(390.0, abs=1)

    @pytest.mark.asyncio
    async def test_max_drawdown_calculation(self, tracker, sample_greeks):
        """Test that max drawdown is calculated correctly."""
        # Create sequence of trades with known P&L
        trades_pnl = [100, -50, 150, -30, 200]  # Cumulative: 100, 50, 200, 170, 370

        for i, pnl in enumerate(trades_pnl):
            entry_data = {
                'entry_time': datetime.now() - timedelta(days=30 - i),
                'entry_price': 2.0,
                'quantity': 1,
                'premium_collected': 2.0,
                'greeks_at_entry': sample_greeks,
            }
            await tracker.track_trade_entry(f"trade_dd_{i}", entry_data)

            # Set exit price to achieve desired P&L
            exit_price = (2.0 - (pnl / 100)) if pnl >= 0 else (2.0 + abs(pnl) / 100)
            exit_data = {
                'exit_time': datetime.now() - timedelta(days=29 - i),
                'exit_price': exit_price,
                'exit_reason': 'expiry'
            }
            await tracker.track_trade_exit(f"trade_dd_{i}", exit_data)

        # Flush buffer
        await tracker.writer.stop_batch_writing()

        # Get performance
        time_range = (datetime.min, datetime.now())
        performance = tracker.get_strategy_performance(time_range)

        # Max drawdown should be > 0 (there were drawdowns)
        assert performance['max_drawdown'] > 0

    @pytest.mark.asyncio
    async def test_win_rate_calculation(self, tracker, sample_greeks):
        """Test that win rate is calculated correctly."""
        # Create trades: 3 winners, 2 losers
        trades = [
            {'id': 'win_1', 'entry': 2.0, 'exit': 0.5},  # +$150
            {'id': 'win_2', 'entry': 1.5, 'exit': 0.0},  # +$150
            {'id': 'lose_1', 'entry': 2.0, 'exit': 3.0},  # -$100
            {'id': 'win_3', 'entry': 1.8, 'exit': 0.3},  # +$150
            {'id': 'lose_2', 'entry': 2.5, 'exit': 4.0},  # -$150
        ]

        for trade in trades:
            entry_data = {
                'entry_time': datetime.now() - timedelta(days=30),
                'entry_price': trade['entry'],
                'quantity': 1,
                'premium_collected': trade['entry'],
                'greeks_at_entry': sample_greeks,
            }
            await tracker.track_trade_entry(trade['id'], entry_data)

            exit_data = {
                'exit_time': datetime.now(),
                'exit_price': trade['exit'],
                'exit_reason': 'expiry'
            }
            await tracker.track_trade_exit(trade['id'], exit_data)

        # Flush buffer
        await tracker.writer.stop_batch_writing()

        # Get performance
        time_range = (datetime.min, datetime.now())
        performance = tracker.get_strategy_performance(time_range)

        # Win rate should be 3/5 = 0.6
        assert performance['win_rate'] == pytest.approx(0.6)
