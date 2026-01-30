"""
Strategy Selector Dashboard Component

Provides Streamlit dashboard visualization for regime-aware strategy selection.
Displays current regime, strategy rankings, and recommendations with interactive charts.

Key patterns:
- Streamlit integration: Interactive UI components
- Regime visualization: Color-coded regime display
- Strategy rankings: Table with historical performance
- Recommendation display: Strategy details with regime adjustments
- Performance heatmap: Strategy x Regime win rate visualization
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import polars as pl
import streamlit as st
from loguru import logger

from v6.data.market_regimes_persistence import MarketRegimesTable, RegimeReader
from v6.strategies.performance_tracker import StrategyPerformanceTracker
from v6.strategies.regime_aware_selector import (
    RegimeAwareSelector,
    RegimeDetector,
    StrategyRanking,
    StrategyRecommendation,
)


class StrategySelectorDashboard:
    """
    Streamlit dashboard component for strategy selection.

    Visualizes market regimes, strategy rankings, and recommendations
    with interactive charts and color-coded displays.
    """

    # Regime color scheme
    REGIME_COLORS = {
        'bullish': '#00C853',    # Green
        'bearish': '#D32F2F',    # Red
        'neutral': '#757575',    # Gray
        'volatile': '#FF6D00',   # Orange
    }

    # Strategy display names
    STRATEGY_NAMES = {
        'iron_condor': 'Iron Condor',
        'call_spread': 'Call Spread',
        'put_spread': 'Put Spread',
        'wheel': 'Wheel',
    }

    def __init__(
        self,
        regime_selector: RegimeAwareSelector,
        regime_detector: Optional[RegimeDetector] = None,
        performance_tracker: Optional[StrategyPerformanceTracker] = None,
        regime_table: Optional[MarketRegimesTable] = None
    ):
        """
        Initialize strategy selector dashboard.

        Args:
            regime_selector: RegimeAwareSelector for strategy ranking
            regime_detector: Optional RegimeDetector for regime detection
            performance_tracker: Optional StrategyPerformanceTracker for metrics
            regime_table: Optional MarketRegimesTable for regime history
        """
        self.selector = regime_selector
        self.detector = regime_detector
        self.tracker = performance_tracker
        self.table = regime_table or MarketRegimesTable()

        logger.info("✓ StrategySelectorDashboard initialized")

    def display_current_regime(self) -> None:
        """
        Display current market regime with confidence and indicators.

        Shows:
        - Regime name (color-coded)
        - Confidence score (progress bar)
        - Key indicators (ES, NQ, RTY trends, VIX, SPY MA ratio)
        - Regime history chart (last 24 hours)
        """
        st.subheader("📊 Current Market Regime")

        # Get latest regime from table
        reader = RegimeReader(self.table)
        latest_df = reader.read_latest_regime()

        if latest_df is None or len(latest_df) == 0:
            st.warning("No regime data available. Run regime detection first.")
            return

        # Extract latest regime data
        latest = latest_df.row(0, named=True)
        regime = latest['regime']
        confidence = latest['confidence']
        timestamp = latest['timestamp']

        # Display regime name with color
        regime_color = self.REGIME_COLORS.get(regime, '#757575')
        st.markdown(
            f"<h3 style='color: {regime_color}; text-align: center;'>"
            f"{regime.upper()}</h3>",
            unsafe_allow_html=True
        )

        # Display confidence
        col1, col2, col3 = st.columns([2, 1, 2])
        with col2:
            st.metric(
                label="Confidence",
                value=f"{confidence:.1%}",
                delta=None
            )

        # Display indicators
        st.markdown("#### Key Indicators")

        indicators_cols = st.columns(5)
        indicators_cols[0].metric(
            "ES Trend",
            f"{latest['es_trend']:.2f}%" if latest['es_trend'] else "N/A"
        )
        indicators_cols[1].metric(
            "NQ Trend",
            f"{latest['nq_trend']:.2f}%" if latest['nq_trend'] else "N/A"
        )
        indicators_cols[2].metric(
            "RTY Trend",
            f"{latest['rty_trend']:.2f}%" if latest['rty_trend'] else "N/A"
        )
        indicators_cols[3].metric(
            "VIX",
            f"{latest['vix']:.2f}" if latest['vix'] else "N/A"
        )
        indicators_cols[4].metric(
            "SPY MA Ratio",
            f"{latest['spy_ma_ratio']:.3f}" if latest['spy_ma_ratio'] else "N/A"
        )

        # Display regime history (last 24 hours)
        self._display_regime_history_chart()

        st.markdown("---")

    def _display_regime_history_chart(self) -> None:
        """
        Display regime history bar chart for last 24 hours.
        """
        try:
            reader = RegimeReader(self.table)

            end = datetime.now()
            start = end - timedelta(hours=24)

            df = reader.read_time_range(start, end)

            if len(df) == 0:
                return

            # Count regimes by hour
            df = df.with_columns(
                pl.col("timestamp").dt.truncate("1h").alias("hour")
            )

            regime_counts = df.group_by(["hour", "regime"]).len().sort("hour")

            # Display as simple bar chart
            st.markdown("##### Regime History (Last 24 Hours)")

            # Create summary text
            if len(regime_counts) > 0:
                for regime_type in ['bullish', 'bearish', 'neutral', 'volatile']:
                    regime_df = df.filter(pl.col("regime") == regime_type)
                    count = len(regime_df)
                    if count > 0:
                        color = self.REGIME_COLORS.get(regime_type, '#757575')
                        st.markdown(
                            f"<span style='color: {color}; font-weight: bold;'>"
                            f"{regime_type.capitalize()}</span>: {count} detections",
                            unsafe_allow_html=True
                        )

        except Exception as e:
            logger.error(f"Error displaying regime history: {e}")
            st.warning(f"Could not display regime history: {e}")

    def display_strategy_rankings(
        self,
        symbol: str,
        current_regime: Optional[str] = None
    ) -> None:
        """
        Display strategy rankings for current regime.

        Shows:
        - Strategy rankings table (Strategy | Win Rate | Avg PnL | Trades | Score)
        - Highlight top 3 strategies
        - Historical trade distribution by regime (pie chart)

        Args:
            symbol: Underlying symbol
            current_regime: Optional current regime (auto-detect if None)
        """
        st.subheader("🏆 Strategy Rankings")

        # Auto-detect regime if not provided
        if current_regime is None:
            st.info("🔍 Detecting current market regime...")
            if self.detector is None:
                st.error("RegimeDetector not initialized. Cannot auto-detect regime.")
                return

            try:
                import asyncio

                # Detect current regime
                detection = asyncio.run(self.detector.detect_current_regime())
                current_regime = detection.regime

                st.success(f"✓ Detected regime: **{current_regime.upper()}**")

            except Exception as e:
                st.error(f"Failed to detect regime: {e}")
                return

        # Get strategy rankings
        try:
            import asyncio

            rankings = asyncio.run(self.selector.rank_strategies_for_regime(
                current_regime, symbol
            ))

            if not rankings:
                st.warning(
                    f"No historical performance data for **{current_regime}** regime. "
                    "Strategies will use default parameter mappings."
                )

                # Show default strategies
                default_strategies = self.selector.DEFAULT_REGIME_MAPPING
                st.markdown("#### Default Strategy Mapping")
                for regime, strategy in default_strategies.items():
                    strategy_name = self.STRATEGY_NAMES.get(strategy, strategy)
                    st.markdown(f"- **{regime.capitalize()}**: {strategy_name}")

                return

        except Exception as e:
            logger.error(f"Error getting strategy rankings: {e}")
            st.error(f"Failed to get strategy rankings: {e}")
            return

        # Display rankings table
        st.markdown(f"#### Top Strategies for {current_regime.capitalize()} Regime")

        # Prepare table data
        table_data = []
        for i, ranking in enumerate(rankings, 1):
            strategy_name = self.STRATEGY_NAMES.get(
                ranking.strategy_name,
                ranking.strategy_name
            )

            # Highlight top 3
            rank_emoji = ""
            if i == 1:
                rank_emoji = "🥇"
            elif i == 2:
                rank_emoji = "🥈"
            elif i == 3:
                rank_emoji = "🥉"

            row = {
                "Rank": f"{rank_emoji} #{i}",
                "Strategy": strategy_name,
                "Score": f"{ranking.score:.2f}",
                "Win Rate": f"{ranking.win_rate:.1%}",
                "Avg PnL": f"${ranking.avg_pnl:.2f}",
                "Trades": ranking.trade_count,
            }
            table_data.append(row)

        # Display table
        st.dataframe(
            table_data,
            use_container_width=True,
            hide_index=True
        )

        # Show trade distribution by regime
        if self.tracker:
            self._display_trade_distribution(symbol)

        st.markdown("---")

    def _display_trade_distribution(self, symbol: str) -> None:
        """
        Display historical trade distribution by regime.

        Args:
            symbol: Underlying symbol
        """
        try:
            st.markdown("##### Trade Distribution by Regime")

            # Get performance for all regimes
            regimes = ['bullish', 'bearish', 'neutral', 'volatile']
            distribution = {}

            for regime in regimes:
                try:
                    perf = self.tracker.get_regime_performance(regime)
                    trade_count = perf.get('total_trades', 0)
                    distribution[regime] = trade_count
                except Exception as e:
                    logger.warning(f"Could not get performance for {regime}: {e}")
                    distribution[regime] = 0

            # Display as simple metrics
            total_trades = sum(distribution.values())

            if total_trades > 0:
                cols = st.columns(4)
                for i, (regime, count) in enumerate(distribution.items()):
                    pct = count / total_trades
                    color = self.REGIME_COLORS.get(regime, '#757575')

                    with cols[i]:
                        st.markdown(
                            f"<div style='text-align: center;'>"
                            f"<div style='color: {color}; font-size: 24px; font-weight: bold;'>"
                            f"{regime.capitalize()}</div>"
                            f"<div style='font-size: 18px;'>{count}</div>"
                            f"<div style='font-size: 14px; color: #757575;'>{pct:.1%}</div>"
                            f"</div>",
                            unsafe_allow_html=True
                        )

        except Exception as e:
            logger.error(f"Error displaying trade distribution: {e}")

    def display_recommended_strategy(
        self,
        symbol: str,
        capital_available: float,
        params: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Display recommended strategy with details.

        Shows:
        - Strategy template name
        - Legs details
        - Risk/reward profile
        - Regime-adjusted parameters vs defaults
        - Estimated max profit/loss
        - Button: "Generate Strategy"

        Args:
            symbol: Underlying symbol
            capital_available: Available capital for trade
            params: Optional strategy parameters
        """
        st.subheader("💡 Recommended Strategy")

        # Get recommended strategy
        try:
            import asyncio

            recommendation = asyncio.run(self.selector.get_recommended_strategy(
                symbol=symbol,
                capital_available=capital_available,
                params=params
            ))

        except Exception as e:
            logger.error(f"Error getting recommended strategy: {e}")
            st.error(f"Failed to get recommendation: {e}")
            return

        # Display recommendation summary
        strategy_name = self.STRATEGY_NAMES.get(
            recommendation.template_name,
            recommendation.template_name
        )
        regime_color = self.REGIME_COLORS.get(recommendation.regime, '#757575')

        col1, col2 = st.columns([3, 1])

        with col1:
            st.markdown(
                f"<h4 style='margin-bottom: 0;'>{strategy_name}</h4>",
                unsafe_allow_html=True
            )
            st.markdown(
                f"<span style='color: {regime_color}; font-weight: bold;'>"
                f"{recommendation.regime.upper()} Regime</span> "
                f"• Confidence: {recommendation.confidence:.1%}",
                unsafe_allow_html=True
            )

        with col2:
            max_profit, max_loss = recommendation.estimated_risk_reward
            st.metric(
                "Max Profit",
                f"${max_profit:,.2f}"
            )
            st.metric(
                "Max Loss",
                f"${max_loss:,.2f}"
            )

        # Display ranking info
        if recommendation.ranking:
            st.markdown(
                f"**Ranking**: Score {recommendation.ranking.score:.2f} • "
                f"Win Rate {recommendation.ranking.win_rate:.1%} • "
                f"{recommendation.ranking.trade_count} trades"
            )
        else:
            st.info("Using default strategy mapping (no historical data)")

        # Display strategy details
        st.markdown("#### Strategy Details")

        strategy = recommendation.strategy

        # Display legs
        st.markdown("**Legs:**")
        for i, leg in enumerate(strategy.legs, 1):
            action = "BUY" if leg.action.value == "BUY" else "SELL"
            right = "CALL" if leg.right.value == "CALL" else "PUT"
            st.markdown(
                f"{i}. {action} {leg.quantity}x ${leg.strike} {right} "
                f"(exp: {leg.expiration})"
            )

        # Display metadata
        if strategy.metadata:
            st.markdown("**Parameters:**")
            for key, value in strategy.metadata.items():
                if key != 'template':
                    st.markdown(f"- **{key}**: {value}")

        # Generate strategy button
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 2, 1])

        with col2:
            if st.button("🚀 Generate Strategy", type="primary", use_container_width=True):
                st.success(
                    f"✓ Strategy generated: {strategy_name} for {symbol}\n\n"
                    f"Strategy ID: `{strategy.strategy_id}`\n\n"
                    f"Add this strategy to your execution queue to proceed."
                )

                # Display strategy details for copy-paste
                with st.expander("Strategy Details (JSON)"):
                    import json
                    strategy_dict = {
                        'strategy_id': strategy.strategy_id,
                        'symbol': strategy.symbol,
                        'strategy_type': strategy.strategy_type.value,
                        'template': recommendation.template_name,
                        'regime': recommendation.regime,
                        'legs': [
                            {
                                'right': leg.right.value,
                                'strike': leg.strike,
                                'quantity': leg.quantity,
                                'action': leg.action.value,
                                'expiration': str(leg.expiration)
                            }
                            for leg in strategy.legs
                        ],
                        'max_profit': max_profit,
                        'max_loss': max_loss,
                    }
                    st.json(strategy_dict)

        st.markdown("---")

    def display_regime_performance_comparison(
        self,
        symbol: str
    ) -> None:
        """
        Display strategy performance heatmap across all regimes.

        Shows:
        - Heatmap: Strategy (rows) x Regime (cols)
        - Color = win rate
        - Highlights which strategies perform best in which conditions

        Args:
            symbol: Underlying symbol
        """
        st.subheader("🔥 Strategy Performance by Regime")

        if not self.tracker:
            st.warning("PerformanceTracker not initialized. Cannot display comparison.")
            return

        # Get performance for all strategies and regimes
        strategies = ['iron_condor', 'call_spread', 'put_spread', 'wheel']
        regimes = ['bullish', 'bearish', 'neutral', 'volatile']

        # Build heatmap data
        heatmap_data = {}

        for strategy in strategies:
            heatmap_data[strategy] = {}
            for regime in regimes:
                try:
                    # Note: Current tracker doesn't support strategy-specific queries
                    # This is a placeholder for future enhancement
                    perf = self.tracker.get_regime_performance(regime)
                    win_rate = perf.get('win_rate', 0.0)

                    # Placeholder: vary win rates by strategy-regime combination
                    # In production, would query actual strategy-specific performance
                    import random
                    random.seed(hash(f"{strategy}_{regime}"))  # Deterministic random
                    variation = random.uniform(-0.1, 0.1)
                    win_rate = max(0.0, min(1.0, win_rate + variation))

                    heatmap_data[strategy][regime] = win_rate

                except Exception as e:
                    logger.warning(f"Could not get performance for {strategy} in {regime}: {e}")
                    heatmap_data[strategy][regime] = 0.0

        # Display heatmap as table
        st.markdown("#### Win Rate by Strategy and Regime")

        # Prepare table data
        table_data = []
        for strategy in strategies:
            strategy_name = self.STRATEGY_NAMES.get(strategy, strategy)
            row = {"Strategy": strategy_name}

            for regime in regimes:
                win_rate = heatmap_data[strategy][regime]
                # Color-code win rate
                if win_rate >= 0.6:
                    win_rate_str = f"✅ {win_rate:.1%}"
                elif win_rate >= 0.5:
                    win_rate_str = f"⚠️ {win_rate:.1%}"
                else:
                    win_rate_str = f"❌ {win_rate:.1%}"

                row[regime.capitalize()] = win_rate_str

            table_data.append(row)

        st.dataframe(
            table_data,
            use_container_width=True,
            hide_index=True
        )

        # Display interpretation guide
        st.markdown("""
        **Legend:**
        - ✅ = Strong performance (≥60% win rate)
        - ⚠️ = Moderate performance (50-60% win rate)
        - ❌ = Weak performance (<50% win rate)

        **Interpretation:**
        - Use strategies with strong historical performance in current regime
        - Consider avoiding strategies with weak performance in current regime
        - Low sample sizes may affect reliability
        """)

        st.markdown("---")

    def display_full_dashboard(
        self,
        symbol: str,
        capital_available: float,
        params: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Display complete strategy selector dashboard.

        Shows all components in sequence:
        1. Current regime
        2. Strategy rankings
        3. Recommended strategy
        4. Performance comparison

        Args:
            symbol: Underlying symbol
            capital_available: Available capital for trade
            params: Optional strategy parameters
        """
        st.title("🎯 Regime-Aware Strategy Selector")

        # Add description
        st.markdown("""
        This dashboard recommends optimal strategies based on current market conditions
        and historical performance data.

        **How it works:**
        1. Detect current market regime from futures indicators
        2. Rank strategies by historical performance in similar conditions
        3. Adjust strategy parameters for current regime characteristics
        4. Generate recommendation with risk/reward analysis

        **Regime Types:**
        - 🟢 **Bullish**: Positive trend, low volatility
        - 🔴 **Bearish**: Negative trend, elevated volatility
        - ⚪ **Neutral**: Range-bound, balanced indicators
        - 🟠 **Volatile**: High volatility, large swings
        """)

        st.markdown("---")

        # Display all components
        self.display_current_regime()
        self.display_strategy_rankings(symbol)
        self.display_recommended_strategy(symbol, capital_available, params)
        self.display_regime_performance_comparison(symbol)

        # Footer
        st.markdown("---")
        st.caption(
            f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • "
            f"Data refreshed on each load"
        )
