"""
V6 Trading System Dashboard - Main Application

This is the main entry point for the Streamlit dashboard.
Provides navigation to all pages and displays home page summary.

Usage:
    streamlit run src/v6/dashboard/app.py
    streamlit run src/v6/dashboard/app.py --server.port 8501
"""

import streamlit as st

from v6.system_monitor.dashboard.config import DashboardConfig


def main():
    """
    Main dashboard application.

    Sets up page configuration, sidebar navigation, and home page.
    """
    # Load configuration
    config = DashboardConfig()

    # Set page config
    st.set_page_config(
        page_title="V6 Trading Monitor",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Sidebar navigation
    st.sidebar.title("📊 V6 Trading System")
    st.sidebar.markdown("---")

    # Navigation links (auto-generated from pages/ directory)
    st.sidebar.page_link("app.py", label="Home", icon="🏠")
    st.sidebar.page_link("pages/1_positions.py", label="Positions", icon="📈")
    st.sidebar.page_link("pages/2_portfolio.py", label="Portfolio", icon="💼")
    st.sidebar.page_link("pages/3_alerts.py", label="Alerts", icon="🔔", disabled=True)
    st.sidebar.page_link("pages/4_health.py", label="System Health", icon="🩺")
    st.sidebar.page_link("pages/5_paper_trading.py", label="Paper Trading", icon="📝")
    st.sidebar.page_link("pages/6_futures.py", label="Futures", icon="📊")

    # Sidebar info
    st.sidebar.markdown("---")
    st.sidebar.caption("V6 Trading System Dashboard")
    st.sidebar.caption(f"Port: {config.streamlit_port}")

    # Main page
    st.title("📊 V6 Trading System Dashboard")
    st.markdown("Welcome to the V6 automated trading system monitor")

    # Summary metrics (placeholder - will be populated in Plan 2)
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            label="Total Positions",
            value="0",
            delta=None,
            help="Total number of open positions"
        )

    with col2:
        st.metric(
            label="Portfolio Delta",
            value="0.00",
            delta=None,
            help="Net portfolio delta exposure"
        )

    with col3:
        st.metric(
            label="Unrealized P&L",
            value="$0.00",
            delta=None,
            help="Total unrealized profit and loss"
        )

    # Info section
    st.markdown("---")
    st.markdown("### 📋 Dashboard Pages")

    st.markdown("""
    - **📈 Positions**: View all active positions with Greeks, P&L, and filtering
    - **💼 Portfolio**: Portfolio analytics with Greeks visualization and P&L history
    - **🔔 Alerts**: Alert management (coming in Plan 2)
    - **🩺 System Health**: System status, metrics, and data freshness monitoring
    - **📝 Paper Trading**: Track paper trading performance and validate strategies
    - **📊 Futures**: Monitor futures data (ES, NQ, RTY) with correlation analysis
    """)

    # Data freshness indicator
    st.markdown("---")
    st.caption("Data source: Delta Lake (updates every 30s)")
    st.caption("Note: Dashboard reads from Delta Lake to avoid IB API rate limits")


if __name__ == "__main__":
    main()
