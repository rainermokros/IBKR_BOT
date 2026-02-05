"""
Positions Monitor Page

Displays all active positions with Greeks, P&L, and filtering.
Supports auto-refresh for real-time updates.
"""

import time

import streamlit as st

from v6.system_monitor.dashboard.components.position_card import position_card
from v6.system_monitor.dashboard.config import DashboardConfig
from v6.system_monitor.dashboard.data.positions import (
    calculate_position_metrics,
    get_available_strategies,
    get_available_symbols,
    get_position_summary,
    load_positions,
    parse_legs_for_display,
)


def main():
    """Positions monitor page main function."""
    st.set_page_config(
        page_title="Positions",
        page_icon="📈",
        layout="wide"
    )

    # Load configuration
    config = DashboardConfig()

    st.title("📈 Position Monitor")

    # Initialize session state for filters
    if "pos_symbol_filter" not in st.session_state:
        st.session_state.pos_symbol_filter = "ALL"
    if "pos_strategy_filter" not in st.session_state:
        st.session_state.pos_strategy_filter = "ALL"
    if "pos_status_filter" not in st.session_state:
        st.session_state.pos_status_filter = "OPEN"
    if "pos_auto_refresh" not in st.session_state:
        st.session_state.pos_auto_refresh = False
    if "pos_refresh_interval" not in st.session_state:
        st.session_state.pos_refresh_interval = config.default_refresh

    # Filters section
    with st.sidebar:
        st.markdown("### Filters")

        # Symbol filter
        available_symbols = get_available_symbols()
        symbol_options = ["ALL"] + available_symbols
        symbol_filter = st.selectbox(
            "Symbol",
            symbol_options,
            index=symbol_options.index(st.session_state.pos_symbol_filter) if st.session_state.pos_symbol_filter in symbol_options else 0
        )
        st.session_state.pos_symbol_filter = symbol_filter

        # Strategy filter
        available_strategies = get_available_strategies()
        strategy_options = ["ALL"] + available_strategies
        strategy_filter = st.selectbox(
            "Strategy",
            strategy_options,
            index=strategy_options.index(st.session_state.pos_strategy_filter) if st.session_state.pos_strategy_filter in strategy_options else 0
        )
        st.session_state.pos_strategy_filter = strategy_filter

        # Status filter
        status_options = ["ALL", "OPEN", "CLOSED"]
        status_filter = st.selectbox(
            "Status",
            status_options,
            index=status_options.index(st.session_state.pos_status_filter) if st.session_state.pos_status_filter in status_options else 1
        )
        st.session_state.pos_status_filter = status_filter

        st.markdown("---")

        # Auto-refresh controls
        st.markdown("### Auto-Refresh")

        auto_refresh = st.checkbox(
            "Enable Auto-Refresh",
            value=st.session_state.pos_auto_refresh
        )
        st.session_state.pos_auto_refresh = auto_refresh

        if auto_refresh:
            refresh_interval = st.selectbox(
                "Refresh Interval",
                config.auto_refresh_options,
                index=config.auto_refresh_options.index(st.session_state.pos_refresh_interval) if st.session_state.pos_refresh_interval in config.auto_refresh_options else 1
            )
            st.session_state.pos_refresh_interval = refresh_interval

            if refresh_interval == 0:
                st.caption("Auto-refresh is OFF")
            else:
                st.caption(f"Refreshes every {refresh_interval}s")

        st.markdown("---")

        # Manual refresh button
        if st.button("🔄 Refresh Now"):
            st.cache_data.clear()
            st.rerun()

    # Load positions with filters
    with st.spinner("Loading positions..."):
        symbol = st.session_state.pos_symbol_filter if st.session_state.pos_symbol_filter != "ALL" else None
        strategy = st.session_state.pos_strategy_filter if st.session_state.pos_strategy_filter != "ALL" else None
        status = st.session_state.pos_status_filter if st.session_state.pos_status_filter != "ALL" else None

        positions_df = load_positions(
            symbol=symbol,
            strategy=strategy,
            status=status
        )

    # Summary metrics
    summary = get_position_summary(positions_df)
    metrics = calculate_position_metrics(positions_df)

    st.markdown("### Portfolio Summary")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="Total Positions",
            value=f"{summary['total_positions']}",
            delta=None,
            help="Total number of positions matching filters"
        )

    with col2:
        st.metric(
            label="Open Positions",
            value=f"{summary['open_positions']}",
            delta=None,
            help="Number of positions currently open"
        )

    with col3:
        st.metric(
            label="Portfolio Delta",
            value=f"{metrics['portfolio_delta']:.2f}",
            delta=None,
            help="Net portfolio delta (placeholder - requires Greeks)"
        )

    with col4:
        pnl = metrics['unrealized_pnl']
        st.metric(
            label="Unrealized P&L",
            value=f"${pnl:,.2f}",
            delta=None,
            help="Total unrealized P&L (placeholder - requires market data)"
        )

    st.markdown("---")

    # Position details
    if positions_df.is_empty():
        st.info("No positions found matching the current filters.")
    else:
        st.markdown(f"### Position Details ({positions_df.shape[0]} positions)")

        # Display positions as expandable cards
        for row in positions_df.iter_rows(named=True):
            with st.expander(
                f"{row['symbol']} - {row['strategy_type'].upper()} - "
                f"Status: {row['status'].upper()} - "
                f"Entry: {row['entry_time'].strftime('%Y-%m-%d %H:%M')}"
            ):
                position_card(row)

    # Auto-refresh loop
    if st.session_state.pos_auto_refresh and st.session_state.pos_refresh_interval > 0:
        time.sleep(st.session_state.pos_refresh_interval)
        st.rerun()


if __name__ == "__main__":
    main()
