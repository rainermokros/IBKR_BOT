"""
Paper Trading Dashboard Page

Displays paper trading performance metrics and trade history.

Usage:
    streamlit run src/v6/dashboard/pages/5_paper_trading.py
"""

import streamlit as st
import polars as pl
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

from v6.risk_manager.performance_tracker.paper_metrics import PaperMetricsTracker


def main():
    """Main paper trading dashboard page."""
    st.set_page_config(
        page_title="Paper Trading",
        page_icon="📝",
        layout="wide"
    )

    st.title("📝 Paper Trading Performance")
    st.markdown("Track paper trading strategy performance before live trading")

    # Initialize metrics tracker
    tracker = PaperMetricsTracker()

    # Load all metrics
    try:
        metrics = tracker.get_all_metrics()
    except Exception as e:
        st.error(f"Failed to load paper trading metrics: {e}")
        st.info("No paper trading data available yet. Start paper trading to see metrics here.")
        return

    # Summary metrics
    st.markdown("---")
    st.subheader("📊 Performance Summary")

    summary = metrics['trade_summary']

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="Total Trades",
            value=f"{summary['total_trades']}",
            delta=None,
            help="Total number of completed paper trades"
        )

    with col2:
        win_rate_pct = summary['win_rate'] * 100
        st.metric(
            label="Win Rate",
            value=f"{win_rate_pct:.1f}%",
            delta=None,
            help=f"Percentage of profitable trades ({summary['winning_trades']}/{summary['total_trades']})"
        )

    with col3:
        st.metric(
            label="Avg P&L",
            value=f"${summary['avg_pnl']:.2f}",
            delta=None,
            help="Average profit/loss per trade"
        )

    with col4:
        st.metric(
            label="Avg Duration",
            value=f"{summary['avg_duration']:.1f} days",
            delta=None,
            help="Average time in position"
        )

    # Risk-adjusted metrics
    st.markdown("---")
    st.subheader("⚖️ Risk-Adjusted Returns")

    col1, col2, col3 = st.columns(3)

    with col1:
        sharpe = metrics['sharpe_ratio']
        st.metric(
            label="Sharpe Ratio",
            value=f"{sharpe:.2f}",
            delta=None,
            help="Risk-adjusted return (annualized). Target: >1.0"
        )

    with col2:
        drawdown = metrics['max_drawdown']
        drawdown_pct = drawdown['max_drawdown'] * 100
        st.metric(
            label="Max Drawdown",
            value=f"{drawdown_pct:.1f}%",
            delta=None,
            help=f"Largest peak-to-trough decline: ${drawdown['max_drawdown_abs']:.2f}"
        )

    with col3:
        # Calculate profit factor
        avg_win = summary['avg_winning_pnl'] or 0
        avg_loss = abs(summary['avg_losing_pnl'] or 0) or 1
        profit_factor = avg_win / avg_loss if avg_loss != 0 else 0
        st.metric(
            label="Profit Factor",
            value=f"{profit_factor:.2f}",
            delta=None,
            help="Ratio of avg win to avg loss. Target: >2.0"
        )

    # Equity curve
    st.markdown("---")
    st.subheader("📈 Equity Curve")

    equity_curve = metrics['equity_curve']

    if equity_curve.height > 0:
        # Convert to pandas for plotting
        equity_df = equity_curve.to_pandas()

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=equity_df['date'],
                y=equity_df['equity'],
                mode='lines+markers',
                name='Cumulative P&L',
                line=dict(color='#2E86AB', width=2),
            )
        )

        # Add zero line
        fig.add_hline(y=0, line_dash="dash", line_color="gray")

        fig.update_layout(
            title="Paper Trading Equity Curve",
            xaxis_title="Date",
            yaxis_title="Cumulative P&L ($)",
            hovermode='x unified',
            height=400,
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No equity curve data available yet")

    # Exit reason distribution
    st.markdown("---")
    st.subheader("🔍 Exit Reason Distribution")

    decision_breakdown = metrics['decision_breakdown']

    if decision_breakdown:
        # Create pie chart
        reasons = list(decision_breakdown.keys())
        counts = list(decision_breakdown.values())

        fig = go.Figure(
            go.Pie(
                labels=reasons,
                values=counts,
                hole=0.3,
                marker=dict(colors=px.colors.sequential.Blues)
            )
        )

        fig.update_layout(
            title="Exit Reasons Breakdown",
            height=400,
        )

        st.plotly_chart(fig, use_container_width=True)

        # Show table
        st.markdown("**Exit Reason Details:**")
        breakdown_df = pl.DataFrame({
            'Exit Reason': reasons,
            'Count': counts,
            'Percentage': [f"{(c / sum(counts) * 100):.1f}%" for c in counts]
        })
        st.dataframe(breakdown_df, use_container_width=True)
    else:
        st.info("No exit reason data available yet")

    # Trade history
    st.markdown("---")
    st.subheader("📜 Trade History")

    try:
        # Load all trades
        trades_df = pl.read_delta("data/lake/paper_trades").sort('exit_date', descending=True)

        if trades_df.height > 0:
            # Format for display
            display_df = trades_df.select(
                pl.col('exit_date').dt.strftime('%Y-%m-%d').alias('Exit Date'),
                pl.col('symbol').alias('Symbol'),
                pl.col('exit_reason').alias('Exit Reason'),
                pl.col('pnl').alias('P&L'),
                pl.col('duration_days').alias('Duration (days)'),
            ).with_columns(
                pl.format("${:.2f}", pl.col('P&L')).alias('P&L')
            )

            st.dataframe(display_df, use_container_width=True)
        else:
            st.info("No trades completed yet")
    except Exception as e:
        st.warning(f"Could not load trade history: {e}")

    # Performance vs expectations
    st.markdown("---")
    st.subheader("🎯 Performance vs Historical Expectations")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Historical Backtest Expectations:**")
        st.info("""
        - Win Rate: 60-70%
        - Sharpe Ratio: >1.0
        - Max Drawdown: <10%
        - Profit Factor: >2.0
        """)

    with col2:
        st.markdown("**Current Paper Trading Results:**")
        # Compare current results to expectations
        win_rate_pct = summary['win_rate'] * 100
        sharpe = metrics['sharpe_ratio']
        drawdown_pct = drawdown['max_drawdown'] * 100
        profit_factor = avg_win / avg_loss if avg_loss != 0 else 0

        # Color code based on thresholds
        win_rate_color = "✅" if win_rate_pct >= 60 else "⚠️"
        sharpe_color = "✅" if sharpe >= 1.0 else "⚠️"
        drawdown_color = "✅" if drawdown_pct < 10 else "⚠️"
        profit_factor_color = "✅" if profit_factor >= 2.0 else "⚠️"

        st.markdown(f"""
        - Win Rate: {win_rate_color} {win_rate_pct:.1f}%
        - Sharpe Ratio: {sharpe_color} {sharpe:.2f}
        - Max Drawdown: {drawdown_color} {drawdown_pct:.1f}%
        - Profit Factor: {profit_factor_color} {profit_factor:.2f}
        """)

    # Recommendations
    st.markdown("---")
    st.subheader("💡 Recommendations")

    if summary['total_trades'] < 10:
        st.warning(
            "⚠️ **Low Sample Size**: Need at least 10-20 trades before drawing conclusions. "
            "Continue paper trading to collect more data."
        )
    elif win_rate_pct < 50:
        st.error(
            "❌ **Poor Win Rate**: Win rate below 50%. Review strategy rules and "
            "market conditions before considering live trading."
        )
    elif sharpe < 0.5:
        st.warning(
            "⚠️ **Low Risk-Adjusted Returns**: Sharpe ratio below 0.5 suggests "
            "strategy may not be profitable after accounting for risk."
        )
    elif drawdown_pct > 20:
        st.error(
            "❌ **High Drawdown**: Max drawdown exceeds 20%. Review risk management "
            "and position sizing before live trading."
        )
    else:
        st.success(
            "✅ **Ready for Production**: Paper trading performance looks good! "
            "Consider transitioning to live trading with small position sizes."
        )

    # Data freshness
    st.markdown("---")
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    st.caption("Data source: Delta Lake (data/lake/paper_trades)")


if __name__ == "__main__":
    main()
