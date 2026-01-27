"""
Integration Tests for Paper Trading

Tests end-to-end paper trading workflow.
"""

import pytest
from datetime import datetime
from pathlib import Path

from src.v6.config import PaperTradingConfig
from src.v6.metrics import PaperMetricsTracker


class TestPaperTradingIntegration:
    """Test end-to-end paper trading workflow."""

    def test_end_to_end_paper_trade(self, tmp_path):
        """Test complete paper trade from entry to exit."""
        # Setup config
        config = PaperTradingConfig(
            ib_host="127.0.0.1",
            ib_port=7497,
            ib_client_id=2,
            max_positions=5,
            max_order_size=1,
            allowed_symbols=["SPY"],
            data_dir=str(tmp_path / "lake"),
        )

        # Setup metrics tracker
        tracker = PaperMetricsTracker(table_path=str(tmp_path / "lake" / "paper_trades"))

        # Simulate entry
        entry_date = datetime.now()
        entry_premium = 2.50

        # Simulate exit
        exit_date = datetime.now()
        exit_premium = 2.00
        pnl = (entry_premium - exit_premium) * 100  # $50 loss

        # Record trade
        tracker.record_trade(
            strategy_id="test_strategy_1",
            symbol="SPY",
            entry_date=entry_date,
            exit_date=exit_date,
            entry_premium=entry_premium,
            exit_premium=exit_premium,
            pnl=pnl,
            exit_reason="stop_loss",
        )

        # Verify trade was recorded
        summary = tracker.get_trade_summary()
        assert summary['total_trades'] == 1
        assert summary['avg_pnl'] == pytest.approx(pnl)

    def test_paper_trading_data_isolation(self, tmp_path):
        """Test that paper trading data is isolated from production."""
        # Create separate tables for paper and production
        paper_table = tmp_path / "paper_trades"
        prod_table = tmp_path / "strategy_executions"

        # Initialize paper tracker
        paper_tracker = PaperMetricsTracker(table_path=str(paper_table))

        # Record a paper trade
        paper_tracker.record_trade(
            strategy_id="paper_trade_1",
            symbol="SPY",
            entry_date=datetime.now(),
            exit_date=datetime.now(),
            entry_premium=2.0,
            exit_premium=1.0,
            pnl=100.0,
            exit_reason="take_profit",
        )

        # Verify paper trade is in paper table
        paper_summary = paper_tracker.get_trade_summary()
        assert paper_summary['total_trades'] == 1

        # Verify production table is empty (different table)
        assert not Path(prod_table).exists() or \
               len(list(Path(prod_table).glob("**"))) == 0

    def test_multiple_paper_trades_metrics(self, tmp_path):
        """Test metrics across multiple paper trades."""
        tracker = PaperMetricsTracker(table_path=str(tmp_path / "paper_trades"))

        # Simulate 10 paper trades with 60% win rate
        for i in range(6):
            tracker.record_trade(
                strategy_id=f"win_{i}",
                symbol="SPY",
                entry_date=datetime.now(),
                exit_date=datetime.now(),
                entry_premium=2.0,
                exit_premium=1.0,
                pnl=100.0,
                exit_reason="take_profit",
            )

        for i in range(4):
            tracker.record_trade(
                strategy_id=f"loss_{i}",
                symbol="SPY",
                entry_date=datetime.now(),
                exit_date=datetime.now(),
                entry_premium=2.0,
                exit_premium=3.0,
                pnl=-50.0,
                exit_reason="stop_loss",
            )

        # Get all metrics
        metrics = tracker.get_all_metrics()

        # Verify trade summary
        assert metrics['trade_summary']['total_trades'] == 10
        assert metrics['trade_summary']['win_rate'] == 0.6
        assert metrics['trade_summary']['avg_pnl'] == 40.0  # (600 - 200) / 10

        # Verify exit reason breakdown
        assert metrics['decision_breakdown']['take_profit'] == 6
        assert metrics['decision_breakdown']['stop_loss'] == 4

        # Verify equity curve
        assert metrics['equity_curve'].height == 10

    def test_config_enforces_safety_limits_during_trading(self, tmp_path):
        """Test that config enforces safety limits throughout trading."""
        config = PaperTradingConfig(
            max_positions=3,
            max_order_size=2,
            allowed_symbols=["SPY", "QQQ"],
            data_dir=str(tmp_path / "lake"),
        )

        # Test position count limit
        assert config.validate_position_count(0) is True  # Can enter
        assert config.validate_position_count(2) is True  # Can enter 3rd
        assert config.validate_position_count(3) is False  # At limit

        # Test order size limit
        assert config.validate_order_size(1) is True
        assert config.validate_order_size(2) is True
        assert config.validate_order_size(3) is False

        # Test symbol whitelist
        assert config.validate_symbol("SPY") is True
        assert config.validate_symbol("QQQ") is True
        assert config.validate_symbol("IWM") is False

    def test_sharpe_ratio_calculation_across_trades(self, tmp_path):
        """Test Sharpe ratio is calculated correctly across multiple trades."""
        tracker = PaperMetricsTracker(table_path=str(tmp_path / "paper_trades"))

        # Create consistent profitable trades
        base_date = datetime.now()

        for i in range(20):
            tracker.record_trade(
                strategy_id=f"trade_{i}",
                symbol="SPY",
                entry_date=base_date - timedelta(days=30 + i * 2),
                exit_date=base_date - timedelta(days=28 + i * 2),
                entry_premium=2.0,
                exit_premium=1.5,
                pnl=50.0,  # Consistent $50 profit
                exit_reason="take_profit",
            )

        sharpe = tracker.get_sharpe_ratio()

        # Should have positive Sharpe for consistent profits
        assert sharpe > 0.5

    def test_max_drawdown_identification(self, tmp_path):
        """Test that max drawdown is correctly identified."""
        tracker = PaperMetricsTracker(table_path=str(tmp_path / "paper_trades"))

        base_date = datetime.now()

        # Create a scenario: big wins, then losses, then recovery
        tracker.record_trade(
            strategy_id="peak",
            symbol="SPY",
            entry_date=base_date - timedelta(days=30),
            exit_date=base_date - timedelta(days=25),
            entry_premium=2.0,
            exit_premium=0.5,
            pnl=300.0,  # Peak
            exit_reason="take_profit",
        )

        tracker.record_trade(
            strategy_id="loss1",
            symbol="SPY",
            entry_date=base_date - timedelta(days=20),
            exit_date=base_date - timedelta(days=15),
            entry_premium=2.0,
            exit_premium=3.0,
            pnl=-100.0,
            exit_reason="stop_loss",
        )

        tracker.record_trade(
            strategy_id="loss2",
            symbol="SPY",
            entry_date=base_date - timedelta(days=10),
            exit_date=base_date - timedelta(days=5),
            entry_premium=2.0,
            exit_premium=3.0,
            pnl=-100.0,
            exit_reason="stop_loss",
        )

        tracker.record_trade(
            strategy_id="trough",
            symbol="SPY",
            entry_date=base_date - timedelta(days=3),
            exit_date=base_date,
            entry_premium=2.0,
            exit_premium=3.0,
            pnl=-50.0,
            exit_reason="stop_loss",
        )

        drawdown = tracker.get_max_drawdown()

        # Peak: $300, Trough: $50, Drawdown: $250 (83%)
        assert drawdown['max_drawdown_abs'] == pytest.approx(250.0, abs=1)
        assert drawdown['max_drawdown'] > 0.8  # >80% drawdown


# Need to import timedelta here
from datetime import timedelta
