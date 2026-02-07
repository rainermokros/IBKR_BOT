"""
Strategy Performance Tracker Module

Provides real-time performance tracking for options strategies.
Tracks trade lifecycle, unrealized P&L, and aggregates metrics by time and regime.

Key patterns:
- StrategyPerformanceTracker: Track entry/exit with unrealized P&L
- Black-Scholes approximation: Real-time option pricing
- Performance aggregation: By time range and market regime
- Integration: Writes to performance_metrics Delta Lake table (Plan 01)
- Variance analysis: Compares predictions vs actuals for strategy weight tuning
"""

import asyncio
import json
from datetime import datetime, timedelta, date
from typing import Any, Dict, List, Optional

import polars as pl
from deltalake import DeltaTable
from loguru import logger
from scipy.stats import norm

from v6.system_monitor.data.performance_metrics_persistence import (
    Greeks,
    PerformanceMetric,
    PerformanceReader,
    PerformanceWriter,
    PerformanceMetricsTable,
)
from v6.system_monitor.data.strategy_predictions import StrategyPredictionsTable


class StrategyPerformanceTracker:
    """
    Track strategy performance with real-time unrealized P&L calculation.

    Tracks complete trade lifecycle from entry to exit, calculates unrealized P&L
    using Black-Scholes approximation, and aggregates performance metrics.

    Integrates with performance_metrics Delta Lake table from Plan 01.
    """

    def __init__(
        self,
        strategy_id: str,
        metrics_writer: PerformanceWriter,
        metrics_table: Optional[PerformanceMetricsTable] = None
    ):
        """
        Initialize performance tracker.

        Args:
            strategy_id: Strategy identifier for tracking
            metrics_writer: PerformanceWriter instance for writing metrics
            metrics_table: Optional PerformanceMetricsTable (for queries)
        """
        self.strategy_id = strategy_id
        self.writer = metrics_writer
        self.table = metrics_table or PerformanceMetricsTable()

        # Cache for unrealized P&L calculations
        # Format: {trade_id: {'entry': {...}, 'current_greeks': {...}}}
        self._active_trades: Dict[str, Dict[str, Any]] = {}

        logger.info(f"✓ Initialized performance tracker for strategy: {strategy_id}")

    async def track_trade_entry(
        self,
        trade_id: str,
        entry_data: Dict[str, Any]
    ) -> None:
        """
        Track trade entry with initial metrics.

        Args:
            trade_id: Unique trade identifier
            entry_data: {
                'timestamp': datetime,
                'entry_time': datetime,
                'entry_price': float,
                'quantity': int,
                'premium_collected': float,
                'premium_paid': float,
                'net_premium': float,
                'max_profit': float,
                'max_loss': float,
                'greeks_at_entry': Greeks (optional),
                'metadata': dict (optional)
            }
        """
        # Extract fields with defaults
        timestamp = entry_data.get('timestamp', datetime.now())
        entry_time = entry_data.get('entry_time', datetime.now())
        entry_price = entry_data.get('entry_price', 0.0)
        quantity = entry_data.get('quantity', 1)
        premium_collected = entry_data.get('premium_collected', 0.0)
        premium_paid = entry_data.get('premium_paid', 0.0)
        net_premium = entry_data.get('net_premium', premium_collected - premium_paid)
        max_profit = entry_data.get('max_profit', 0.0)
        max_loss = entry_data.get('max_loss', 0.0)
        greeks_at_entry = entry_data.get('greeks_at_entry')
        metadata = entry_data.get('metadata', {})

        # Create performance metric
        metric = PerformanceMetric(
            timestamp=timestamp,
            strategy_id=self.strategy_id,
            trade_id=trade_id,
            entry_time=entry_time,
            exit_time=None,  # No exit yet
            entry_price=entry_price,
            exit_price=None,
            quantity=quantity,
            premium_collected=premium_collected,
            premium_paid=premium_paid,
            net_premium=net_premium,
            max_profit=max_profit,
            max_loss=max_loss,
            realized_pnl=0.0,  # No realized P&L at entry
            unrealized_pnl=-net_premium * quantity * 100,  # Initial unrealized
            hold_duration_minutes=None,
            exit_reason=None,
            greeks_at_entry=greeks_at_entry,
            greeks_at_exit=None,
            metadata=metadata
        )

        # Write to performance_metrics table
        await self.writer.on_metric(metric)

        # Cache for unrealized P&L calculations
        self._active_trades[trade_id] = {
            'entry': entry_data.copy(),
            'entry_metric': metric
        }

        logger.info(
            f"✓ Tracked trade entry: {trade_id} "
            f"(net_premium: ${net_premium:.2f}, unrealized_pnl: ${metric.unrealized_pnl:.2f})"
        )

    async def track_trade_exit(
        self,
        trade_id: str,
        exit_data: Dict[str, Any]
    ) -> None:
        """
        Track trade exit with final metrics.

        Args:
            trade_id: Unique trade identifier
            exit_data: {
                'exit_time': datetime,
                'exit_price': float,
                'exit_reason': str ('expiry', 'stop_loss', 'take_profit', 'manual', 'roll'),
                'greeks_at_exit': Greeks (optional)
            }
        """
        # Check if trade exists
        if trade_id not in self._active_trades:
            raise ValueError(f"Trade {trade_id} not found in active trades")

        entry_data = self._active_trades[trade_id]['entry']
        entry_metric = self._active_trades[trade_id]['entry_metric']

        # Extract exit fields
        exit_time = exit_data.get('exit_time', datetime.now())
        exit_price = exit_data.get('exit_price', 0.0)
        exit_reason = exit_data.get('exit_reason', 'manual')
        greeks_at_exit = exit_data.get('greeks_at_exit')

        # Calculate hold duration
        hold_duration_minutes = int(
            (exit_time - entry_metric.entry_time).total_seconds() / 60
        )

        # Calculate realized P&L
        # For credit strategies: premium collected - exit price
        # For debit strategies: exit price - premium paid
        if entry_metric.net_premium > 0:  # Credit
            realized_pnl = (entry_metric.net_premium - exit_price) * entry_metric.quantity * 100
        else:  # Debit
            realized_pnl = (exit_price - abs(entry_metric.net_premium)) * entry_metric.quantity * 100

        # Create final performance metric
        metric = PerformanceMetric(
            timestamp=datetime.now(),
            strategy_id=self.strategy_id,
            trade_id=trade_id,
            entry_time=entry_metric.entry_time,
            exit_time=exit_time,
            entry_price=entry_metric.entry_price,
            exit_price=exit_price,
            quantity=entry_metric.quantity,
            premium_collected=entry_metric.premium_collected,
            premium_paid=entry_metric.premium_paid,
            net_premium=entry_metric.net_premium,
            max_profit=entry_metric.max_profit,
            max_loss=entry_metric.max_loss,
            realized_pnl=realized_pnl,
            unrealized_pnl=0.0,  # No unrealized after exit
            hold_duration_minutes=hold_duration_minutes,
            exit_reason=exit_reason,
            greeks_at_entry=entry_metric.greeks_at_entry,
            greeks_at_exit=greeks_at_exit,
            metadata=entry_metric.metadata
        )

        # Write to performance_metrics table
        await self.writer.on_metric(metric)

        # Clear from active trades cache
        del self._active_trades[trade_id]

        logger.info(
            f"✓ Tracked trade exit: {trade_id} "
            f"(realized_pnl: ${realized_pnl:.2f}, duration: {hold_duration_minutes}min, "
            f"reason: {exit_reason})"
        )

    def calculate_unrealized_pnl(
        self,
        current_prices: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Calculate unrealized P&L for all active trades.

        Uses Black-Scholes approximation for option pricing.

        Args:
            current_prices: {trade_id: current_option_price}

        Returns:
            {trade_id: unrealized_pnl}

        Note:
            unrealized_pnl = (current_option_value - entry_option_value) * quantity * 100
        """
        unrealized_pnl_dict = {}

        for trade_id, trade_data in self._active_trades.items():
            entry_metric = trade_data['entry_metric']

            # Get current price (default to entry price if not provided)
            current_price = current_prices.get(trade_id, entry_metric.entry_price)

            # Calculate unrealized P&L using Black-Scholes approximation
            # For short options: (entry_price - current_price) * quantity * 100
            # For long options: (current_price - entry_price) * quantity * 100
            if entry_metric.net_premium > 0:  # Short (credit)
                unrealized_pnl = (entry_metric.entry_price - current_price) * entry_metric.quantity * 100
            else:  # Long (debit)
                unrealized_pnl = (current_price - entry_metric.entry_price) * entry_metric.quantity * 100

            unrealized_pnl_dict[trade_id] = unrealized_pnl

        return unrealized_pnl_dict

    async def write_unrealized_pnl_to_position_updates(
        self,
        unrealized_pnl_dict: Dict[str, float],
        current_prices: Dict[str, float]
    ) -> None:
        """
        Write current unrealized P&L to position_updates Delta Lake table.

        This enables historical P&L tracking while keeping Risk Manager
        reading from in-memory cache (fast + persistent).

        Args:
            unrealized_pnl_dict: {trade_id: unrealized_pnl}
            current_prices: {trade_id: current_option_price}
        """
        try:
            from datetime import date
            import polars as pl
            from deltalake import write_deltalake
            from ib_async import IB

            # Fetch current IB positions to get contract details
            ib = IB()
            await ib.connectAsync('127.0.0.1', port=4002, clientId=9970, timeout=10)
            await asyncio.sleep(1)

            positions = list(ib.positions())
            ib.disconnect()

            # Build position records
            position_records = []
            for position in positions:
                if position.position == 0:
                    continue

                contract = position.contract
                if not hasattr(contract, 'right'):
                    continue

                # Match with our tracked trades
                symbol = contract.symbol
                matching_trade_ids = [
                    tid for tid in self._active_trades.keys()
                    if self._active_trades[tid]['entry_metric'].get('symbol') == symbol
                ]

                for trade_id in matching_trade_ids:
                    entry_metric = self._active_trades[trade_id]['entry_metric']
                    upl = unrealized_pnl_dict.get(trade_id, 0)
                    current_price = current_prices.get(trade_id, entry_metric.entry_price)

                    position_records.append({
                        'conid': contract.conId,
                        'symbol': symbol,
                        'right': contract.right,
                        'strike': contract.strike,
                        'expiry': contract.lastTradeDateOrContractMonth,
                        'position': position.position,
                        'market_price': current_price,
                        'market_value': position.marketValue() if hasattr(position, 'marketValue') else None,
                        'average_cost': position.avgCost if position.avgCost else entry_metric.entry_price,
                        'unrealized_pnl': upl,
                        'timestamp': datetime.now(),
                        'date': date.today(),
                    })

            # Write to Delta Lake
            if position_records:
                df = pl.DataFrame(position_records)
                write_deltalake(
                    'data/lake/position_updates',
                    df,
                    mode='append',  # Append for historical tracking
                )
                logger.debug(f"Wrote {len(position_records)} position updates to Delta Lake")

        except Exception as e:
            logger.warning(f"Failed to write UPL to position_updates: {e}")

    def calculate_unrealized_pnl_black_scholes(
        self,
        current_market_data: Dict[str, Dict[str, float]]
    ) -> Dict[str, float]:
        """
        Calculate unrealized P&L using Black-Scholes model.

        More accurate pricing model that accounts for underlying price, time to expiry,
        volatility, and interest rates.

        Args:
            current_market_data: {
                trade_id: {
                    'underlying_price': float,
                    'strike': float,
                    'time_to_expiry': float (years),
                    'risk_free_rate': float (optional, default 0.05),
                    'volatility': float (optional)
                }
            }

        Returns:
            {trade_id: unrealized_pnl}

        Note:
            Uses Black-Scholes formula for European options.
            For American options (most equity options), this is an approximation.
        """
        unrealized_pnl_dict = {}

        for trade_id, market_data in current_market_data.items():
            if trade_id not in self._active_trades:
                continue

            entry_metric = self._active_trades[trade_id]['entry_metric']

            # Extract market data
            S = market_data['underlying_price']  # Current underlying price
            K = market_data['strike']  # Strike price
            T = market_data['time_to_expiry']  # Time to expiry (years)
            r = market_data.get('risk_free_rate', 0.05)  # Risk-free rate (5% default)
            sigma = market_data.get('volatility', 0.20)  # Volatility (20% default)

            # Calculate Black-Scholes option price
            option_price = self._black_scholes_price(S, K, T, r, sigma, is_call=False)

            # Calculate unrealized P&L
            if entry_metric.net_premium > 0:  # Short put
                unrealized_pnl = (entry_metric.entry_price - option_price) * entry_metric.quantity * 100
            else:  # Long put
                unrealized_pnl = (option_price - entry_metric.entry_price) * entry_metric.quantity * 100

            unrealized_pnl_dict[trade_id] = unrealized_pnl

        return unrealized_pnl_dict

    def _black_scholes_price(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float,
        is_call: bool = True
    ) -> float:
        """
        Calculate Black-Scholes option price.

        Args:
            S: Current underlying price
            K: Strike price
            T: Time to expiry (years)
            r: Risk-free rate
            sigma: Volatility
            is_call: True for call, False for put

        Returns:
            Option price
        """
        # Handle edge case
        if T <= 0:
            # At expiry
            if is_call:
                return max(S - K, 0)
            else:
                return max(K - S, 0)

        # Calculate d1 and d2
        d1 = (self._log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * (T ** 0.5))
        d2 = d1 - sigma * (T ** 0.5)

        # Calculate option price
        if is_call:
            price = S * norm.cdf(d1) - K * self._exp(-r * T) * norm.cdf(d2)
        else:
            price = K * self._exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

        return price

    def get_strategy_performance(
        self,
        time_range: tuple[datetime, datetime]
    ) -> Dict[str, Any]:
        """
        Get aggregate performance metrics for strategy within time range.

        Args:
            time_range: (start_datetime, end_datetime)

        Returns:
            Dict with aggregate metrics:
                - total_trades: int
                - win_rate: float (0-1)
                - avg_realized_pnl: float
                - total_realized_pnl: float
                - avg_hold_duration: float (minutes)
                - pnl_by_exit_reason: dict
                - max_drawdown: float
        """
        start, end = time_range

        # Read metrics from performance_metrics table
        reader = PerformanceReader(self.table)
        df = reader.read_strategy_metrics(self.strategy_id, start, end)

        if len(df) == 0:
            return {
                'total_trades': 0,
                'win_rate': 0.0,
                'avg_realized_pnl': 0.0,
                'total_realized_pnl': 0.0,
                'avg_hold_duration': 0.0,
                'pnl_by_exit_reason': {},
                'max_drawdown': 0.0
            }

        # Calculate aggregate metrics
        total_trades = len(df)

        # Completed trades (have exit_time)
        completed_trades = df.filter(pl.col('exit_time').is_not_null())

        if len(completed_trades) > 0:
            # Win rate
            winning_trades = completed_trades.filter(pl.col('realized_pnl') > 0)
            win_rate = len(winning_trades) / len(completed_trades)

            # Average realized P&L
            avg_realized_pnl = completed_trades['realized_pnl'].mean()

            # Total realized P&L
            total_realized_pnl = completed_trades['realized_pnl'].sum()

            # Average hold duration
            avg_hold_duration = completed_trades['hold_duration_minutes'].mean()

            # P&L by exit reason
            pnl_by_exit = {}
            for reason in ['expiry', 'stop_loss', 'take_profit', 'manual', 'roll']:
                reason_trades = completed_trades.filter(pl.col('exit_reason') == reason)
                if len(reason_trades) > 0:
                    pnl_by_exit[reason] = {
                        'count': len(reason_trades),
                        'total_pnl': float(reason_trades['realized_pnl'].sum()),
                        'avg_pnl': float(reason_trades['realized_pnl'].mean())
                    }

            # Max drawdown (calculate from cumulative P&L)
            cumulative_pnl = completed_trades['realized_pnl'].cum_sum()
            running_max = cumulative_pnl.cum_max()
            drawdown = running_max - cumulative_pnl
            max_drawdown = float(drawdown.max())
        else:
            win_rate = 0.0
            avg_realized_pnl = 0.0
            total_realized_pnl = 0.0
            avg_hold_duration = 0.0
            pnl_by_exit = {}
            max_drawdown = 0.0

        return {
            'total_trades': total_trades,
            'win_rate': float(win_rate),
            'avg_realized_pnl': float(avg_realized_pnl),
            'total_realized_pnl': float(total_realized_pnl),
            'avg_hold_duration': float(avg_hold_duration),
            'pnl_by_exit_reason': pnl_by_exit,
            'max_drawdown': max_drawdown
        }

    def get_regime_performance(self, regime: str) -> Dict[str, Any]:
        """
        Get performance metrics filtered by market regime.

        Args:
            regime: Market regime ('bullish', 'bearish', 'neutral', 'volatile')

        Returns:
            Dict with regime-specific performance metrics (same format as get_strategy_performance)

        Note:
            This is a placeholder for future integration with market_regimes table.
            Currently returns same metrics as get_strategy_performance.
        """
        # TODO: Integrate with market_regimes table from Plan 01
        # For now, return overall performance (regime filtering not implemented yet)

        logger.warning(
            f"Regime filtering not yet implemented. Returning overall performance for regime: {regime}"
        )

        # Get all-time performance
        time_range = (datetime.min, datetime.now())
        return self.get_strategy_performance(time_range)

    def get_active_trades(self) -> List[str]:
        """
        Get list of active trade IDs.

        Returns:
            List of trade IDs with open positions
        """
        return list(self._active_trades.keys())

    def analyze_prediction_variance(
        self,
        days: int = 30,
        min_predictions: int = 10,
    ) -> Dict[str, Any]:
        """
        Analyze prediction variance by strategy type and regime.

        Calculates MAE (Mean Absolute Error), MSE (Mean Squared Error), and
        weight adjustments for each strategy type based on prediction accuracy.

        Args:
            days: Number of days to look back for predictions
            min_predictions: Minimum predictions required for analysis

        Returns:
            Dict with variance metrics and weight adjustments:
                {
                    "strategy_type": {
                        "mean_absolute_error": float,
                        "mean_squared_error": float,
                        "prediction_count": int,
                        "weight_adjustment": float,  # Multiplier for scoring
                        "by_regime": {
                            "regime_name": {"mae": float, "count": int}
                        }
                    }
                }
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # Read predictions from StrategyPredictionsTable
        predictions_table = StrategyPredictionsTable()
        df = predictions_table.read_predictions(
            start_date=start_date,
            end_date=end_date,
            min_predictions=0,  # Don't filter by min here, we'll check after grouping
        )

        if len(df) < min_predictions:
            logger.warning(
                f"Insufficient predictions for variance analysis: "
                f"{len(df)} < {min_predictions}"
            )
            return {}

        # Group by strategy type
        variance_by_type = {}
        for strategy_type in df["strategy_type"].unique().to_list():
            type_df = df.filter(pl.col("strategy_type") == strategy_type)

            # Calculate metrics
            mae = type_df["prediction_error"].abs().mean()
            mse = (type_df["prediction_error"] ** 2).mean()
            count = len(type_df)

            # Weight adjustment: reduce weight for high error
            # Error 0% -> multiplier 1.0, Error 40%+ -> multiplier 0.5
            weight_adjustment = max(0.5, 1.0 - min(abs(mae) / 0.40, 0.5))

            # By regime breakdown
            by_regime = {}
            for regime in type_df["regime_at_entry"].unique().to_list():
                regime_df = type_df.filter(pl.col("regime_at_entry") == regime)
                by_regime[regime] = {
                    "mae": float(regime_df["prediction_error"].abs().mean()),
                    "count": len(regime_df),
                }

            variance_by_type[strategy_type] = {
                "mean_absolute_error": float(mae),
                "mean_squared_error": float(mse),
                "prediction_count": count,
                "weight_adjustment": weight_adjustment,
                "by_regime": by_regime,
            }

        logger.info(
            f"Variance analysis complete: {len(variance_by_type)} strategy types analyzed"
        )

        return variance_by_type

    def get_strategy_weights(
        self,
        use_variance_adjustment: bool = True,
        base_weights: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """
        Get strategy scoring weights with optional variance adjustment.

        Returns adjusted weights based on historical prediction accuracy.
        Strategies with higher prediction error get lower weights.

        Args:
            use_variance_adjustment: Whether to apply variance adjustments
            base_weights: Optional base weights (defaults to equal weighting)

        Returns:
            Dict mapping strategy_type to weight multiplier
        """
        # Base weights (equal weighting by default)
        if base_weights is None:
            base_weights = {
                "iron_condor": 1.0,
                "bull_put_spread": 1.0,
                "bear_call_spread": 1.0,
                "iron_butterfly": 1.0,
                "vertical_spread": 1.0,
            }

        if not use_variance_adjustment:
            return base_weights

        # Apply variance adjustments
        variance = self.analyze_prediction_variance()

        if not variance:
            logger.debug("No variance data available, using base weights")
            return base_weights

        adjusted_weights = {}
        for strategy_type, base_weight in base_weights.items():
            adjustment = variance.get(strategy_type, {}).get("weight_adjustment", 1.0)
            adjusted_weights[strategy_type] = base_weight * adjustment

        logger.info(f"Adjusted strategy weights: {adjusted_weights}")
        return adjusted_weights

    def get_regime_strategy_weights(
        self,
        regime: str,
        use_variance_adjustment: bool = True,
    ) -> Dict[str, float]:
        """
        Get strategy weights for a specific market regime.

        Combines regime-specific adjustments with variance-based adjustments
        to provide optimized weights for current market conditions.

        Args:
            regime: Current market regime (normal, high_volatility, crash, etc.)
            use_variance_adjustment: Whether to apply variance adjustments

        Returns:
            Dict mapping strategy_type to weight multiplier
        """
        # Regime-specific base weights
        regime_base_weights = {
            "normal": {
                "iron_condor": 1.0,
                "bull_put_spread": 1.0,
                "bear_call_spread": 1.0,
            },
            "high_volatility": {
                "iron_condor": 0.8,
                "bull_put_spread": 1.0,
                "bear_call_spread": 1.0,
            },
            "crash": {
                "iron_condor": 0.5,
                "bull_put_spread": 0.8,
                "bear_call_spread": 1.2,
            },
            "trending": {
                "iron_condor": 0.7,
                "bull_put_spread": 1.2,
                "bear_call_spread": 0.8,
            },
        }

        # Get base weights for regime (default to normal)
        base_weights = regime_base_weights.get(regime, regime_base_weights["normal"])

        if not use_variance_adjustment:
            return base_weights

        # Apply variance adjustments
        variance = self.analyze_prediction_variance()

        if not variance:
            return base_weights

        adjusted_weights = {}
        for strategy_type, base_weight in base_weights.items():
            adjustment = variance.get(strategy_type, {}).get("weight_adjustment", 1.0)
            adjusted_weights[strategy_type] = base_weight * adjustment

        logger.info(
            f"Regime-adjusted strategy weights (regime={regime}): {adjusted_weights}"
        )
        return adjusted_weights

    def _log(self, x: float) -> float:
        """Natural log helper."""
        import math
        return math.log(x)

    def _exp(self, x: float) -> float:
        """Exponential helper."""
        import math
        return math.exp(x)
