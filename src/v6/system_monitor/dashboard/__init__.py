"""
V6 Dashboard Package

This package provides a real-time monitoring dashboard for the v6 trading system.
Built with Streamlit for rapid development and interactive visualizations.

Key features:
- Multi-page dashboard (positions, portfolio, alerts, system health)
- Real-time data updates with auto-refresh
- Interactive visualizations with Plotly
- Reads from Delta Lake (no IB API rate limits)
- Cached data loading for performance

Usage:
    streamlit run src/v6/dashboard/app.py
"""

__all__ = []
