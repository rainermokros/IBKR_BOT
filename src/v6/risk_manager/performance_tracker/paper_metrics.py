"""
Paper Trading Metrics Tracker

This module provides the PaperMetricsTracker class that records and calculates
performance metrics specifically for paper trading.

Key features:
- Record completed trades with entry/exit details
- Calculate win rate, average P&L, average duration
- Track exit reason distribution (stop loss, take profit, time exit)
- Calculate equity curve over time
- Calculate Sharpe ratio and maximum drawdown
- Persist to Delta Lake for analysis

Usage:
    from v6.risk_manager.performance_tracker import PaperMetricsTracker

    tracker = PaperMetricsTracker()

    # Record a completed trade
    tracker.record_trade(
        strategy_id="abc123",
        entry_price=2.50,
        exit_price=2.00,
        pnl=-50.0,
        duration_days=21,
        exit_reason="stop_loss"
    )

    # Get summary
    summary = tracker.get_trade_summary()
    print(f"Win rate: {summary['win_rate']:.2%}")

    # Get equity curve
    equity_curve = tracker.get_equity_curve()
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import polars as pl
from deltalake import DeltaTable, write_deltalake
from loguru import logger

logger = logger.bind(component="PaperMetricsTracker")


class PaperMetricsTracker:
    """
    Track paper trading performance metrics.

    Records completed trades and calculates performance metrics including
    win rate, average P&L, Sharpe ratio, and maximum drawdown.

    **Metrics Tracked:**
    - Win rate: Percentage of profitable trades
    - Average P&L: Mean profit/loss per trade
    - Average duration: Mean time in trade
    - Sharpe ratio: Risk-adjusted return (annualized)
    - Max drawdown: Largest peak-to-trough decline
    - Exit reason distribution: Breakdown of exit reasons

    **Persistence:**
    - All trades persisted to Delta Lake (data/lake/paper_trades)
    - Enables historical analysis and dashboard visualization

    Attributes:
        table_path: Path to Delta Lake table for paper trades
    """

    def __init__(self, table_path: str = "data/lake/paper_trades"):
        """
        Initialize paper metrics tracker.

        Args:
            table_path: Path to Delta Lake table for paper trades
        """
        self.table_path = Path(table_path)
        self._ensure_table_exists()

    def _ensure_table_exists(self) -> None:
        """Create Delta Lake table if it doesn't exist."""
        if DeltaTable.is_deltatable(str(self.table_path)):
            return

        # Schema for paper trades
        schema = pl.Schema({
            'strategy_id': pl.String,
            'symbol': pl.String,
            'entry_date': pl.Datetime("us"),
            'exit_date': pl.Datetime("us"),
            'entry_premium': pl.Float64,
            'exit_premium': pl.Float64,
            'pnl': pl.Float64,
            'exit_reason': pl.String,
            'duration_days': pl.Int64,
            'entry_decision_type': pl.String,
            'exit_decision_type': pl.String,
        })

        # Create empty table
        empty_df = pl.DataFrame(schema=schema)
        write_deltalake(
            str(self.table_path),
            empty_df.limit(0),
            mode="overwrite",
        )

        logger.info(f"✓ Created Delta Lake table: {self.table_path}")

    def record_trade(
        self,
        strategy_id: str,
        symbol: str,
        entry_date: datetime,
        exit_date: datetime,
        entry_premium: float,
        exit_premium: float,
        pnl: float,
        exit_reason: str,
        entry_decision_type: Optional[str] = None,
        exit_decision_type: Optional[str] = None,
    ) -> None:
        """
        Record a completed paper trade.

        Args:
            strategy_id: Strategy execution ID
            symbol: Underlying symbol
            entry_date: When position was entered
            exit_date: When position was exited
            entry_premium: Premium received/paid on entry
            exit_premium: Premium paid/received on exit
            pnl: Profit/loss in dollars
            exit_reason: Reason for exit (stop_loss, take_profit, time_exit, etc.)
            entry_decision_type: Decision type that triggered entry
            exit_decision_type: Decision type that triggered exit
        """
        # Calculate duration
        duration_days = (exit_date - entry_date).days

        # Create trade record
        trade = {
            'strategy_id': strategy_id,
            'symbol': symbol,
            'entry_date': entry_date,
            'exit_date': exit_date,
            'entry_premium': entry_premium,
            'exit_premium': exit_premium,
            'pnl': pnl,
            'exit_reason': exit_reason,
            'duration_days': duration_days,
            'entry_decision_type': entry_decision_type or 'unknown',
            'exit_decision_type': exit_decision_type or 'unknown',
        }

        # Append to Delta Lake
        df = pl.DataFrame([trade])
        write_deltalake(
            str(self.table_path),
            df,
            mode="append",
        )

        logger.info(
            f"[PAPER] Trade recorded: {symbol} P&L=${pnl:.2f}, "
            f"reason={exit_reason}, duration={duration_days}d"
        )

    def record_decision(
        self,
        strategy_id: str,
        decision_type: str,
        reason: str,
        symbol: Optional[str] = None,
    ) -> None:
        """
        Record a trading decision for analysis.

        Used to track all exit decisions (even non-trade decisions like HOLD).

        Args:
            strategy_id: Strategy execution ID
            decision_type: Type of decision (EXIT, HOLD, ADJUST)
            reason: Reason for decision
            symbol: Underlying symbol (optional)
        """
        # For now, just log the decision
        # Could be persisted to a separate decisions table in the future
        logger.debug(
            f"[PAPER] Decision recorded: {strategy_id} - "
            f"{decision_type}: {reason}"
        )

    def get_trade_summary(self) -> dict:
        """
        Calculate trade summary statistics.

        Returns:
            Dict with trade summary:
                - total_trades: Total number of completed trades
                - winning_trades: Number of profitable trades
                - losing_trades: Number of unprofitable trades
                - win_rate: Percentage of profitable trades (0-1)
                - avg_pnl: Average profit/loss per trade
                - avg_winning_pnl: Average profit of winning trades
                - avg_losing_pnl: Average loss of losing trades
                - avg_duration: Average duration in days
        """
        # Load all trades
        df = pl.read_delta(str(self.table_path))

        if df.height == 0:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'avg_pnl': 0.0,
                'avg_winning_pnl': 0.0,
                'avg_losing_pnl': 0.0,
                'avg_duration': 0.0,
            }

        # Calculate metrics
        total_trades = df.height
        winning_trades = df.filter(pl.col('pnl') > 0).height
        losing_trades = df.filter(pl.col('pnl') < 0).height
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

        avg_pnl = df['pnl'].mean()

        avg_winning_pnl = df.filter(pl.col('pnl') > 0)['pnl'].mean()
        avg_losing_pnl = df.filter(pl.col('pnl') < 0)['pnl'].mean()

        avg_duration = df['duration_days'].mean()

        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'avg_pnl': avg_pnl,
            'avg_winning_pnl': avg_winning_pnl,
            'avg_losing_pnl': avg_losing_pnl,
            'avg_duration': avg_duration,
        }

    def get_decision_breakdown(self) -> dict:
        """
        Calculate exit reason distribution.

        Returns:
            Dict mapping exit_reason to count:
                {'stop_loss': 5, 'take_profit': 10, 'time_exit': 3}
        """
        # Load all trades
        df = pl.read_delta(str(self.table_path))

        if df.height == 0:
            return {}

        # Group by exit reason and count
        breakdown = df.group_by('exit_reason').agg(
            pl.count('strategy_id').alias('count')
        ).sort('count', descending=True)

        return dict(zip(breakdown['exit_reason'].to_list(), breakdown['count'].to_list()))

    def get_equity_curve(self) -> pl.DataFrame:
        """
        Calculate equity curve over time.

        Returns:
            DataFrame with columns:
                - date: Date of trade completion
                - equity: Cumulative P&L over time
                - returns: Daily returns
        """
        # Load all trades sorted by exit date
        df = pl.read_delta(str(self.table_path)).sort('exit_date')

        if df.height == 0:
            return pl.DataFrame({
                'date': [],
                'equity': [],
                'returns': [],
            })

        # Calculate cumulative P&L
        df = df.with_columns(
            pl.col('pnl').cum_sum().alias('equity')
        )

        # Calculate daily returns
        df = df.with_columns(
            pl.col('equity').pct_change().alias('returns')
        )

        # Select relevant columns
        equity_curve = df.select(
            pl.col('exit_date').alias('date'),
            'equity',
            'returns',
        )

        return equity_curve

    def get_sharpe_ratio(self, risk_free_rate: float = 0.02) -> float:
        """
        Calculate Sharpe ratio (risk-adjusted return).

        Args:
            risk_free_rate: Annual risk-free rate (default: 2%)

        Returns:
            Sharpe ratio (annualized)
        """
        # Get equity curve
        equity_curve = self.get_equity_curve()

        if equity_curve.height == 0:
            return 0.0

        # Calculate daily returns (excluding NaN)
        returns = equity_curve['returns'].drop_nans()

        if len(returns) == 0:
            return 0.0

        # Convert annual risk-free rate to daily
        daily_rf = risk_free_rate / 252

        # Calculate Sharpe ratio
        excess_returns = returns - daily_rf
        mean_return = excess_returns.mean()
        std_return = excess_returns.std()
        sharpe = mean_return / std_return if std_return and std_return != 0 else 0.0

        # Annualize (assuming 252 trading days per year)
        sharpe_annualized = sharpe * np.sqrt(252)

        return sharpe_annualized

    def get_max_drawdown(self) -> dict:
        """
        Calculate maximum drawdown.

        Returns:
            Dict with drawdown metrics:
                - max_drawdown: Maximum drawdown (0-1)
                - max_drawdown_abs: Maximum drawdown in dollars
                - max_drawdown_date: Date of maximum drawdown
        """
        # Get equity curve
        equity_curve = self.get_equity_curve()

        if equity_curve.height == 0:
            return {
                'max_drawdown': 0.0,
                'max_drawdown_abs': 0.0,
                'max_drawdown_date': None,
            }

        # Calculate running maximum
        equity = equity_curve['equity'].to_numpy()
        running_max = np.maximum.accumulate(equity)

        # Calculate drawdown
        drawdown = (equity - running_max) / running_max
        drawdown_abs = equity - running_max

        # Find maximum drawdown
        max_dd_idx = int(np.argmin(drawdown))
        max_drawdown = abs(drawdown[max_dd_idx])
        max_drawdown_abs = abs(drawdown_abs[max_dd_idx])
        max_drawdown_date = equity_curve[max_dd_idx, 'date']
        # Handle both datetime and scalar types
        if hasattr(max_drawdown_date, 'item'):
            max_drawdown_date = max_drawdown_date.item()

        return {
            'max_drawdown': max_drawdown,
            'max_drawdown_abs': max_drawdown_abs,
            'max_drawdown_date': max_drawdown_date,
        }

    def get_all_metrics(self) -> dict:
        """
        Get all paper trading metrics.

        Returns:
            Dict with all metrics:
                - trade_summary: Trade summary statistics
                - decision_breakdown: Exit reason distribution
                - sharpe_ratio: Risk-adjusted return
                - max_drawdown: Maximum drawdown metrics
                - equity_curve: Equity curve DataFrame
        """
        return {
            'trade_summary': self.get_trade_summary(),
            'decision_breakdown': self.get_decision_breakdown(),
            'sharpe_ratio': self.get_sharpe_ratio(),
            'max_drawdown': self.get_max_drawdown(),
            'equity_curve': self.get_equity_curve(),
        }
