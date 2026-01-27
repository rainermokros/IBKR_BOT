"""
Portfolio Analytics Page

Visualizes portfolio Greeks, P&L history, and risk metrics.
Provides interactive charts with Plotly.
"""

import streamlit as st

from src.v6.dashboard.components.greeks_display import (
    greeks_summary_cards,
    plot_greeks_heatmap,
    plot_pnl_timeseries,
    portfolio_metrics_cards,
)
from src.v6.dashboard.config import DashboardConfig
from src.v6.dashboard.data.portfolio import (
    get_greeks_by_symbol,
    get_portfolio_greeks,
    get_portfolio_metrics,
    get_portfolio_pnl_history,
)


def main():
    """Portfolio analytics page main function."""
    st.set_page_config(
        page_title="Portfolio",
        page_icon="💼",
        layout="wide"
    )

    # Load configuration
    config = DashboardConfig()

    st.title("💼 Portfolio Analytics")

    # Initialize session state for symbol selector
    if "portfolio_symbol" not in st.session_state:
        st.session_state.portfolio_symbol = "ALL"

    # Symbol selector for heatmap
    with st.sidebar:
        st.markdown("### Options")
        available_symbols = get_available_symbols()
        symbol_options = ["ALL"] + available_symbols
        portfolio_symbol = st.selectbox(
            "Select Symbol for Heatmap",
            symbol_options,
            index=symbol_options.index(st.session_state.portfolio_symbol) if st.session_state.portfolio_symbol in symbol_options else 0
        )
        st.session_state.portfolio_symbol = portfolio_symbol

        st.markdown("---")

        # Manual refresh button
        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.rerun()

    # Greeks summary
    with st.spinner("Loading portfolio Greeks..."):
        greeks = get_portfolio_greeks()

    greeks_summary_cards(greeks)

    st.markdown("---")

    # Greeks heatmap
    st.markdown("### Greeks Heatmap")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Select Symbol:**")
        if portfolio_symbol != "ALL":
            st.write(f"Showing Greeks for **{portfolio_symbol}**")

            # Load Greeks data for heatmap
            greeks_df = get_greeks_by_symbol(portfolio_symbol)

            # Greek selector
            greek_options = ["delta", "gamma", "theta", "vega"]
            selected_greek = st.selectbox("Select Greek", greek_options, index=0)

            # Plot heatmap
            fig = plot_greeks_heatmap(greeks_df, selected_greek)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Select a symbol from the sidebar to view Greeks heatmap")

    with col2:
        st.markdown("**Portfolio P&L Over Time**")

        # Load P&L history
        pnl_df = get_portfolio_pnl_history()

        # Plot P&L time series
        fig_pnl = plot_pnl_timeseries(pnl_df)
        st.plotly_chart(fig_pnl, use_container_width=True)

    st.markdown("---")

    # Portfolio metrics
    with st.spinner("Loading portfolio metrics..."):
        metrics = get_portfolio_metrics()

    portfolio_metrics_cards(metrics)

    st.markdown("---")

    # Info section
    st.caption("Data source: Delta Lake (strategy_executions table)")
    st.caption("Note: Greeks and P&L are placeholders - will be implemented in Plan 2 after Greeks tracking")


def get_available_symbols() -> list[str]:
    """Get list of available symbols (reuse from positions module)."""
    from src.v6.dashboard.data.positions import get_available_symbols
    return get_available_symbols()


if __name__ == "__main__":
    main()
