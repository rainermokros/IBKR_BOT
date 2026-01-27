"""
Positions Monitor Page

Displays all active positions with Greeks, P&L, and filtering.
Supports auto-refresh for real-time updates.
"""

import streamlit as st

from src.v6.dashboard.config import DashboardConfig


def main():
    """Positions monitor page main function."""
    st.set_page_config(
        page_title="Positions",
        page_icon="📈",
        layout="wide"
    )

    st.title("📈 Position Monitor")

    # Placeholder for Task 2 implementation
    st.info("Position monitor page - will be implemented in Task 2")
    st.caption("This page will display:")
    st.caption("- Active positions with Greeks, P&L, DTE")
    st.caption("- Filtering by symbol, strategy, status")
    st.caption("- Auto-refresh with configurable intervals")
    st.caption("- Summary metrics (total positions, portfolio delta, unrealized P&L)")


if __name__ == "__main__":
    main()
