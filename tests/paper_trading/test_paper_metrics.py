"""
Tests for Paper Trading Metrics

Tests metrics calculation and accuracy.
"""

import pytest
from datetime import datetime, timedelta

from src.v6.metrics import PaperMetricsTracker


class TestPaperMetricsTracker:
    """Test PaperMetricsTracker metrics calculation."""

    def test_record_trade(self, tmp_path):
        """Test recording a completed trade."""
        tracker = PaperMetricsTracker(table_path=str(tmp_path / "paper_trades"))

        # Record a trade
        tracker.record_trade(
            strategy_id="test_strategy_1",
            symbol="SPY",
            entry_date=datetime.now() - timedelta(days=21),
            exit_date=datetime.now(),
            entry_premium=2.50,
            exit_premium=2.00,
            pnl=-50.0,
            exit_reason="stop_loss",
        )

        # Verify trade was recorded
        summary = tracker.get_trade_summary()
        assert summary['total_trades'] == 1

    def test_get_trade_summary_empty(self, tmp_path):
        """Test trade summary with no trades."""
        tracker = PaperMetricsTracker(table_path=str(tmp_path / "paper_trades"))

        summary = tracker.get_trade_summary()

        assert summary['total_trades'] == 0
        assert summary['win_rate'] == 0.0
        assert summary['avg_pnl'] == 0.0

    def test_get_trade_summary_calculates_correctly(self, tmp_path):
        """Test that trade summary calculations are correct."""
        tracker = PaperMetricsTracker(table_path=str(tmp_path / "paper_trades"))

        # Record 3 trades: 2 winners, 1 loser
        tracker.record_trade(
            strategy_id="win1",
            symbol="SPY",
            entry_date=datetime.now() - timedelta(days=10),
            exit_date=datetime.now(),
            entry_premium=2.00,
            exit_premium=1.00,
            pnl=100.0,  # Winner
            exit_reason="take_profit",
        )

        tracker.record_trade(
            strategy_id="win2",
            symbol="QQQ",
            entry_date=datetime.now() - timedelta(days=15),
            exit_date=datetime.now(),
            entry_premium=3.00,
            exit_premium=2.00,
            pnl=100.0,  # Winner
            exit_reason="take_profit",
        )

        tracker.record_trade(
            strategy_id="loss1",
            symbol="IWM",
            entry_date=datetime.now() - timedelta(days=5),
            exit_date=datetime.now(),
            entry_premium=1.50,
            exit_premium=2.00,
            pnl=-50.0,  # Loser
            exit_reason="stop_loss",
        )

        # Get summary
        summary = tracker.get_trade_summary()

        assert summary['total_trades'] == 3
        assert summary['winning_trades'] == 2
        assert summary['losing_trades'] == 1
        assert summary['win_rate'] == 2/3
        assert summary['avg_pnl'] == pytest.approx(50.0)  # (100 + 100 - 50) / 3
        assert summary['avg_winning_pnl'] == 100.0
        assert summary['avg_losing_pnl'] == -50.0

    def test_win_rate_calculation(self, tmp_path):
        """Test win rate is calculated correctly."""
        tracker = PaperMetricsTracker(table_path=str(tmp_path / "paper_trades"))

        # Record 10 trades: 6 winners, 4 losers (60% win rate)
        for i in range(6):
            tracker.record_trade(
                strategy_id=f"win{i}",
                symbol="SPY",
                entry_date=datetime.now() - timedelta(days=10),
                exit_date=datetime.now(),
                entry_premium=2.0,
                exit_premium=1.0,
                pnl=100.0,
                exit_reason="take_profit",
            )

        for i in range(4):
            tracker.record_trade(
                strategy_id=f"loss{i}",
                symbol="SPY",
                entry_date=datetime.now() - timedelta(days=10),
                exit_date=datetime.now(),
                entry_premium=1.0,
                exit_premium=2.0,
                pnl=-50.0,
                exit_reason="stop_loss",
            )

        summary = tracker.get_trade_summary()
        assert summary['win_rate'] == pytest.approx(0.6)

    def test_get_decision_breakdown(self, tmp_path):
        """Test exit reason distribution."""
        tracker = PaperMetricsTracker(table_path=str(tmp_path / "paper_trades"))

        # Record trades with different exit reasons
        tracker.record_trade(
            strategy_id="trade1",
            symbol="SPY",
            entry_date=datetime.now() - timedelta(days=10),
            exit_date=datetime.now(),
            entry_premium=2.0,
            exit_premium=1.0,
            pnl=100.0,
            exit_reason="take_profit",
        )

        tracker.record_trade(
            strategy_id="trade2",
            symbol="SPY",
            entry_date=datetime.now() - timedelta(days=10),
            exit_date=datetime.now(),
            entry_premium=2.0,
            exit_premium=3.0,
            pnl=-100.0,
            exit_reason="stop_loss",
        )

        tracker.record_trade(
            strategy_id="trade3",
            symbol="SPY",
            entry_date=datetime.now() - timedelta(days=45),
            exit_date=datetime.now(),
            entry_premium=2.0,
            exit_premium=0.5,
            pnl=150.0,
            exit_reason="time_exit",
        )

        # Two stop losses, one take profit, one time exit
        tracker.record_trade(
            strategy_id="trade4",
            symbol="SPY",
            entry_date=datetime.now() - timedelta(days=10),
            exit_date=datetime.now(),
            entry_premium=2.0,
            exit_premium=3.0,
            pnl=-100.0,
            exit_reason="stop_loss",
        )

        breakdown = tracker.get_decision_breakdown()

        assert breakdown['stop_loss'] == 2
        assert breakdown['take_profit'] == 1
        assert breakdown['time_exit'] == 1

    def test_get_equity_curve(self, tmp_path):
        """Test equity curve calculation."""
        tracker = PaperMetricsTracker(table_path=str(tmp_path / "paper_trades"))

        # Record 3 trades
        base_date = datetime.now()

        tracker.record_trade(
            strategy_id="trade1",
            symbol="SPY",
            entry_date=base_date - timedelta(days=30),
            exit_date=base_date - timedelta(days=20),
            entry_premium=2.0,
            exit_premium=1.0,
            pnl=100.0,
            exit_reason="take_profit",
        )

        tracker.record_trade(
            strategy_id="trade2",
            symbol="SPY",
            entry_date=base_date - timedelta(days=15),
            exit_date=base_date - timedelta(days=10),
            entry_premium=2.0,
            exit_premium=3.0,
            pnl=-50.0,
            exit_reason="stop_loss",
        )

        tracker.record_trade(
            strategy_id="trade3",
            symbol="SPY",
            entry_date=base_date - timedelta(days=5),
            exit_date=base_date,
            entry_premium=2.0,
            exit_premium=1.0,
            pnl=75.0,
            exit_reason="take_profit",
        )

        # Get equity curve
        equity_curve = tracker.get_equity_curve()

        assert equity_curve.height == 3
        assert equity_curve['equity'].to_list() == [100.0, 50.0, 125.0]

    def test_get_sharpe_ratio(self, tmp_path):
        """Test Sharpe ratio calculation."""
        tracker = PaperMetricsTracker(table_path=str(tmp_path / "paper_trades"))

        # Record some trades
        base_date = datetime.now()

        for i in range(10):
            tracker.record_trade(
                strategy_id=f"trade{i}",
                symbol="SPY",
                entry_date=base_date - timedelta(days=30 + i * 3),
                exit_date=base_date - timedelta(days=27 + i * 3),
                entry_premium=2.0,
                exit_premium=1.0,
                pnl=50.0 + i * 10,  # Increasing profits
                exit_reason="take_profit",
            )

        sharpe = tracker.get_sharpe_ratio()

        # Should be positive for profitable trades
        assert sharpe > 0

    def test_get_max_drawdown(self, tmp_path):
        """Test maximum drawdown calculation."""
        tracker = PaperMetricsTracker(table_path=str(tmp_path / "paper_trades"))

        # Create a scenario with a drawdown
        base_date = datetime.now()

        # Big win
        tracker.record_trade(
            strategy_id="trade1",
            symbol="SPY",
            entry_date=base_date - timedelta(days=30),
            exit_date=base_date - timedelta(days=25),
            entry_premium=2.0,
            exit_premium=1.0,
            pnl=200.0,
            exit_reason="take_profit",
        )

        # Series of losses (drawdown)
        tracker.record_trade(
            strategy_id="trade2",
            symbol="SPY",
            entry_date=base_date - timedelta(days=20),
            exit_date=base_date - timedelta(days=15),
            entry_premium=2.0,
            exit_premium=3.0,
            pnl=-100.0,
            exit_reason="stop_loss",
        )

        tracker.record_trade(
            strategy_id="trade3",
            symbol="SPY",
            entry_date=base_date - timedelta(days=10),
            exit_date=base_date - timedelta(days=5),
            entry_premium=2.0,
            exit_premium=3.0,
            pnl=-50.0,
            exit_reason="stop_loss",
        )

        # Recovery
        tracker.record_trade(
            strategy_id="trade4",
            symbol="SPY",
            entry_date=base_date - timedelta(days=3),
            exit_date=base_date,
            entry_premium=2.0,
            exit_premium=1.0,
            pnl=150.0,
            exit_reason="take_profit",
        )

        drawdown = tracker.get_max_drawdown()

        # Peak was $200, trough was $50, drawdown = $150 or 75%
        assert drawdown['max_drawdown_abs'] == pytest.approx(150.0, abs=1)
        assert drawdown['max_drawdown'] == pytest.approx(0.75, abs=0.05)

    def test_get_all_metrics(self, tmp_path):
        """Test getting all metrics at once."""
        tracker = PaperMetricsTracker(table_path=str(tmp_path / "paper_trades"))

        # Record a trade
        tracker.record_trade(
            strategy_id="trade1",
            symbol="SPY",
            entry_date=datetime.now() - timedelta(days=10),
            exit_date=datetime.now(),
            entry_premium=2.0,
            exit_premium=1.0,
            pnl=100.0,
            exit_reason="take_profit",
        )

        metrics = tracker.get_all_metrics()

        assert 'trade_summary' in metrics
        assert 'decision_breakdown' in metrics
        assert 'sharpe_ratio' in metrics
        assert 'max_drawdown' in metrics
        assert 'equity_curve' in metrics
