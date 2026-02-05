"""
Unrealized P&L Calculator Component

Provides real-time unrealized P&L calculation using Black-Scholes option pricing model.
Calculates P&L at position and strategy levels with historical time-series support.

Key patterns:
- UnrealizedPnLCalculator: Black-Scholes option pricing with position aggregation
- Leg-level P&L: Calculates current option value for each leg
- Strategy aggregation: Sums P&L across all positions
- Historical time series: Realized + unrealized P&L over time
"""

import json
from datetime import datetime, timedelta
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


class UnrealizedPnLCalculator:
    """
    Calculate unrealized P&L for options strategies using Black-Scholes model.

    Supports:
    - Position-level unrealized P&L with leg breakdown
    - Strategy-level aggregation across all positions
    - Historical P&L time series (realized + unrealized)
    - Black-Scholes option pricing for European options
    """

    def __init__(
        self,
        metrics_table: Optional[PerformanceMetricsTable] = None,
        risk_free_rate: float = 0.05
    ):
        """
        Initialize P&L calculator.

        Args:
            metrics_table: Optional PerformanceMetricsTable instance
            risk_free_rate: Risk-free rate for Black-Scholes (default 5%)
        """
        self.table = metrics_table or PerformanceMetricsTable()
        self.risk_free_rate = risk_free_rate

        logger.info(f"✓ Initialized UnrealizedPnLCalculator (risk_free_rate: {risk_free_rate:.2%})")

    def calculate_position_unrealized_pnl(
        self,
        position: Dict[str, Any],
        current_prices: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Calculate unrealized P&L for a single position.

        Args:
            position: Position dict with keys:
                - strategy_id: str
                - trade_id: str
                - symbol: str
                - legs: List[dict] with keys:
                    - right: str (PUT/CALL)
                    - strike: float
                    - expiration: str (YYYY-MM-DD or YYYYMMDD)
                    - quantity: int
                    - action: str (BUY/SELL)
                    - entry_price: float
                - entry_params: dict with optional 'net_premium'
            current_prices: {symbol: current_underlying_price}

        Returns:
            Dict with:
                - trade_id: str
                - strategy_id: str
                - unrealized_pnl: float (total position P&L)
                - unrealized_pnl_pct: float (P&L as % of entry value)
                - legs: List[dict] with leg-level P&L details
        """
        trade_id = position.get('trade_id', 'unknown')
        strategy_id = position.get('strategy_id', 'unknown')
        symbol = position.get('symbol', '')
        legs = position.get('legs', [])
        entry_params = position.get('entry_params', {})

        # Get current underlying price
        S = current_prices.get(symbol, 0.0)

        # Get entry net premium (if available)
        net_premium = entry_params.get('net_credit', entry_params.get('net_premium', 0.0))

        total_unrealized_pnl = 0.0
        total_entry_value = 0.0
        leg_details = []

        for leg in legs:
            right = leg.get('right', '').upper()
            strike = leg.get('strike', 0.0)
            expiry = leg.get('expiration', '')
            quantity = leg.get('quantity', 1)
            action = leg.get('action', 'BUY').upper()
            entry_price = leg.get('fill_price', leg.get('entry_price', 0.0))

            # Calculate time to expiry (years)
            T = self._calculate_time_to_expiry(expiry)

            # Get volatility (use default 20% if not available)
            sigma = leg.get('implied_volatility', 0.20)

            # Determine option type for Black-Scholes
            is_call = (right == 'CALL')

            # Calculate current option value using Black-Scholes
            current_option_value = self.black_scholes(
                S=S,
                K=strike,
                T=T,
                r=self.risk_free_rate,
                sigma=sigma,
                option_type='call' if is_call else 'put'
            )

            # Calculate entry option value (use entry_price)
            entry_option_value = entry_price

            # Calculate leg P&L
            # For short options: (entry - current) * quantity * 100
            # For long options: (current - entry) * quantity * 100
            if action == 'SELL':
                leg_pnl = (entry_option_value - current_option_value) * quantity * 100
            else:  # BUY
                leg_pnl = (current_option_value - entry_option_value) * quantity * 100

            total_unrealized_pnl += leg_pnl
            total_entry_value += abs(entry_option_value) * quantity * 100

            leg_details.append({
                'right': right,
                'strike': strike,
                'expiration': expiry,
                'quantity': quantity,
                'action': action,
                'entry_value': entry_option_value * quantity * 100,
                'current_value': current_option_value * quantity * 100,
                'unrealized_pnl': leg_pnl
            })

        # Calculate P&L percentage
        if total_entry_value > 0:
            unrealized_pnl_pct = (total_unrealized_pnl / total_entry_value) * 100
        else:
            unrealized_pnl_pct = 0.0

        return {
            'trade_id': trade_id,
            'strategy_id': strategy_id,
            'unrealized_pnl': total_unrealized_pnl,
            'unrealized_pnl_pct': unrealized_pnl_pct,
            'legs': leg_details
        }

    def black_scholes(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float,
        option_type: str = 'call'
    ) -> float:
        """
        Calculate Black-Scholes option price.

        Args:
            S: Current underlying price
            K: Strike price
            T: Time to expiry (years)
            r: Risk-free rate (annualized)
            sigma: Volatility (annualized)
            option_type: 'call' or 'put'

        Returns:
            Option price

        Note:
            Standard Black-Scholes formula for European options.
            For American options (most equity options), this is an approximation
            but provides reasonable real-time estimates.
        """
        import math

        # Handle edge cases
        if T <= 0:
            # At expiry
            if option_type == 'call':
                return max(S - K, 0)
            else:
                return max(K - S, 0)

        if sigma <= 0:
            # No volatility - intrinsic value only
            if option_type == 'call':
                return max(S - K, 0)
            else:
                return max(K - S, 0)

        # Calculate d1 and d2
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        # Calculate option price
        if option_type == 'call':
            price = S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
        else:  # put
            price = K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

        return price

    def calculate_strategy_unrealized_pnl(
        self,
        strategy_id: str,
        positions: List[Dict[str, Any]],
        current_prices: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Calculate unrealized P&L for all positions in a strategy.

        Args:
            strategy_id: Strategy identifier
            positions: List of position dicts (see calculate_position_unrealized_pnl)
            current_prices: {symbol: current_underlying_price}

        Returns:
            Dict with:
                - strategy_id: str
                - total_unrealized_pnl: float
                - total_unrealized_pnl_pct: float
                - position_count: int
                - worst_position: dict (trade_id, pnl, pnl_pct)
                - best_position: dict (trade_id, pnl, pnl_pct)
                - positions: List[dict] with position details
        """
        total_pnl = 0.0
        total_entry_value = 0.0
        position_details = []

        worst_position = {'trade_id': None, 'pnl': 0.0, 'pnl_pct': 0.0}
        best_position = {'trade_id': None, 'pnl': 0.0, 'pnl_pct': 0.0}

        for position in positions:
            result = self.calculate_position_unrealized_pnl(position, current_prices)

            total_pnl += result['unrealized_pnl']
            total_entry_value += abs(result['unrealized_pnl'] / (result['unrealized_pnl_pct'] / 100 if result['unrealized_pnl_pct'] != 0 else 1))

            position_details.append({
                'trade_id': result['trade_id'],
                'unrealized_pnl': result['unrealized_pnl'],
                'unrealized_pnl_pct': result['unrealized_pnl_pct'],
                'leg_count': len(result['legs'])
            })

            # Track best/worst positions
            if result['unrealized_pnl'] < worst_position['pnl']:
                worst_position = {
                    'trade_id': result['trade_id'],
                    'pnl': result['unrealized_pnl'],
                    'pnl_pct': result['unrealized_pnl_pct']
                }

            if result['unrealized_pnl'] > best_position['pnl']:
                best_position = {
                    'trade_id': result['trade_id'],
                    'pnl': result['unrealized_pnl'],
                    'pnl_pct': result['unrealized_pnl_pct']
                }

        # Calculate strategy-level P&L percentage
        if total_entry_value > 0:
            total_pnl_pct = (total_pnl / total_entry_value) * 100
        else:
            total_pnl_pct = 0.0

        return {
            'strategy_id': strategy_id,
            'total_unrealized_pnl': total_pnl,
            'total_unrealized_pnl_pct': total_pnl_pct,
            'position_count': len(positions),
            'worst_position': worst_position if worst_position['trade_id'] else None,
            'best_position': best_position if best_position['trade_id'] else None,
            'positions': position_details
        }

    def get_historical_pnl(
        self,
        strategy_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get historical P&L time series for a strategy.

        Combines realized P&L from closed trades with current unrealized P&L.

        Args:
            strategy_id: Strategy identifier
            days: Number of days to look back (default 30)

        Returns:
            Dict with:
                - strategy_id: str
                - days: int
                - realized_pnl: float (from closed trades)
                - unrealized_pnl: float (current open positions)
                - total_pnl: float (realized + unrealized)
                - daily_pnl_series: List[dict] with {date, pnl}
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # Read performance metrics from Delta Lake
        reader = PerformanceReader(self.table)
        df = reader.read_strategy_metrics(strategy_id, start_date, end_date)

        if df.is_empty():
            return {
                'strategy_id': strategy_id,
                'days': days,
                'realized_pnl': 0.0,
                'unrealized_pnl': 0.0,
                'total_pnl': 0.0,
                'daily_pnl_series': []
            }

        # Calculate realized P&L from closed trades
        closed_trades = df.filter(pl.col('exit_time').is_not_null())

        if not closed_trades.is_empty():
            realized_pnl = closed_trades['realized_pnl'].sum()
        else:
            realized_pnl = 0.0

        # Get current unrealized P&L from open trades
        open_trades = df.filter(pl.col('exit_time').is_null())

        if not open_trades.is_empty():
            # Get most recent unrealized P&L for each trade
            latest_unrealized = open_trades.sort('timestamp', descending=True).unique(subset=['trade_id'])
            unrealized_pnl = latest_unrealized['unrealized_pnl'].sum()
        else:
            unrealized_pnl = 0.0

        total_pnl = realized_pnl + unrealized_pnl

        # Generate daily time series
        daily_series = []

        # Group by date and sum P&L
        df_with_date = df.with_columns(
            pl.col('timestamp').dt.truncate('1d').alias('date')
        )

        daily_pnl = df_with_date.group_by('date').agg(
            pl.col('realized_pnl').sum(),
            pl.col('unrealized_pnl').sum()
        ).sort('date')

        # Calculate cumulative P&L
        cumulative_pnl = 0.0
        for row in daily_pnl.iter_rows(named=True):
            daily_realized = row['realized_pnl'] if row['realized_pnl'] is not None else 0.0
            daily_unrealized = row['unrealized_pnl'] if row['unrealized_pnl'] is not None else 0.0

            # For closed trades, add realized P&L to cumulative
            # For open trades, use most recent unrealized P&L
            cumulative_pnl += daily_realized

            daily_series.append({
                'date': row['date'].strftime('%Y-%m-%d'),
                'realized_pnl': float(daily_realized),
                'unrealized_pnl': float(daily_unrealized),
                'cumulative_pnl': float(cumulative_pnl)
            })

        return {
            'strategy_id': strategy_id,
            'days': days,
            'realized_pnl': float(realized_pnl),
            'unrealized_pnl': float(unrealized_pnl),
            'total_pnl': float(total_pnl),
            'daily_pnl_series': daily_series
        }

    def _calculate_time_to_expiry(self, expiry: str) -> float:
        """
        Calculate time to expiry in years.

        Args:
            expiry: Expiration date string (YYYY-MM-DD or YYYYMMDD)

        Returns:
            Time to expiry in years
        """
        from datetime import datetime

        try:
            # Parse expiry date
            if '-' in expiry:
                expiry_date = datetime.strptime(expiry, '%Y-%m-%d')
            else:
                expiry_date = datetime.strptime(expiry, '%Y%m%d')

            # Calculate time to expiry
            now = datetime.now()
            time_to_expiry = (expiry_date - now).total_seconds() / (365.25 * 24 * 3600)

            return max(0.0, time_to_expiry)

        except Exception as e:
            logger.warning(f"Error parsing expiry date {expiry}: {e}")
            return 0.01  # Default to small positive value
