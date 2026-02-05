"""
Greeks Visualization Components

Provides reusable components for visualizing portfolio Greeks.
Includes summary cards, heatmaps, and time series charts.
"""

from typing import Any

import plotly.graph_objects as go
import polars as pl
import streamlit as st


def greeks_summary_cards(greeks: dict[str, Any]) -> None:
    """
    Display portfolio Greeks as summary metric cards.

    Args:
        greeks: Dictionary with portfolio Greeks:
            - delta, gamma, theta, vega, rho

    Displays:
        - 5 columns with delta, gamma, theta, vega, rho metrics
        - Color-coded for positive/negative values
    """
    st.markdown("### Portfolio Greeks")

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        delta = greeks.get("delta", 0.0)
        st.metric(
            label="Delta",
            value=f"{delta:.4f}",
            delta=None,
            help="Net portfolio delta (directional exposure)"
        )

    with col2:
        gamma = greeks.get("gamma", 0.0)
        st.metric(
            label="Gamma",
            value=f"{gamma:.4f}",
            delta=None,
            help="Net portfolio gamma (delta sensitivity)"
        )

    with col3:
        theta = greeks.get("theta", 0.0)
        st.metric(
            label="Theta",
            value=f"${theta:.2f}/day",
            delta=None,
            help="Net portfolio theta (time decay)"
        )

    with col4:
        vega = greeks.get("vega", 0.0)
        st.metric(
            label="Vega",
            value=f"${vega:.2f}/1% IV",
            delta=None,
            help="Net portfolio vega (volatility sensitivity)"
        )

    with col5:
        rho = greeks.get("rho", 0.0)
        st.metric(
            label="Rho",
            value=f"${rho:.2f}/1% rate",
            delta=None,
            help="Net portfolio rho (interest rate sensitivity)"
        )


def plot_greeks_heatmap(
    df: pl.DataFrame,
    greek: str = "delta"
) -> go.Figure:
    """
    Plot Greeks heatmap (strike vs DTE).

    Args:
        df: DataFrame with columns:
            - strike: Strike price
            - dte: Days to expiration
            - delta, gamma, theta, vega: Greek values
        greek: Which Greek to plot (default: "delta")

    Returns:
        Plotly Figure object with heatmap

    Note:
        Returns empty figure if DataFrame is empty (placeholder for Plan 2)
    """
    if df.is_empty():
        # Return placeholder figure
        fig = go.Figure()
        fig.update_layout(
            title=f"{greek.capitalize()} Heatmap (No Data)",
            xaxis_title="Days to Expiration",
            yaxis_title="Strike Price"
        )
        return fig

    try:
        # Pivot data for heatmap
        pivot = df.pivot_table(
            values=greek,
            index="strike",
            columns="dte"
        )

        # Create heatmap
        fig = go.Figure(data=go.Heatmap(
            z=pivot.values,
            x=pivot.columns,
            y=pivot.index,
            colorscale="RdBu",  # Red (negative) to Blue (positive)
            colorbar=dict(title=greek.capitalize()),
            hoverongaps=False
        ))

        fig.update_layout(
            title=f"{greek.capitalize()} Heatmap (Strike vs DTE)",
            xaxis_title="Days to Expiration",
            yaxis_title="Strike Price",
            height=500
        )

        return fig

    except Exception as e:
        # Return error figure
        fig = go.Figure()
        fig.update_layout(
            title=f"{greek.capitalize()} Heatmap (Error: {str(e)})"
        )
        return fig


def plot_pnl_timeseries(
    df: pl.DataFrame
) -> go.Figure:
    """
    Plot portfolio P&L time series.

    Args:
        df: DataFrame with columns:
            - timestamp: Time of P&L snapshot
            - cumulative_pnl: Cumulative P&L at that time

    Returns:
        Plotly Figure object with line chart

    Note:
        Returns placeholder figure if DataFrame is empty (Plan 2)
    """
    if df.is_empty():
        # Return placeholder figure with sample data
        import numpy as np
        from datetime import datetime, timedelta

        # Generate sample data for visualization
        timestamps = [
            datetime.now() - timedelta(days=i)
            for i in range(30, 0, -1)
        ]
        cumulative_pnl = np.cumsum(np.random.randn(30) * 100)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=timestamps,
            y=cumulative_pnl,
            mode="lines",
            name="Cumulative P&L (Sample Data)",
            line=dict(color="green")
        ))

        fig.update_layout(
            title="Portfolio P&L Over Time (Sample - No Real Data)",
            xaxis_title="Time",
            yaxis_title="Cumulative P&L ($)",
            height=400
        )

        return fig

    try:
        # Get latest P&L value for color
        latest_pnl = df["cumulative_pnl"].iloc[-1]
        line_color = "green" if latest_pnl > 0 else "red"

        # Create line chart
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["timestamp"],
            y=df["cumulative_pnl"],
            mode="lines",
            name="Cumulative P&L",
            line=dict(color=line_color)
        ))

        fig.update_layout(
            title="Portfolio P&L Over Time",
            xaxis_title="Time",
            yaxis_title="Cumulative P&L ($)",
            height=400
        )

        return fig

    except Exception as e:
        # Return error figure
        fig = go.Figure()
        fig.update_layout(
            title=f"P&L Time Series (Error: {str(e)})"
        )
        return fig


def portfolio_metrics_cards(metrics: dict[str, Any]) -> None:
    """
    Display portfolio metrics as summary cards.

    Args:
        metrics: Dictionary with portfolio metrics:
            - position_count: Number of positions
            - symbol_count: Number of symbols
            - total_exposure: Total notional exposure
            - max_single_position: Largest position %
            - correlated_exposure: Exposure by symbol

    Displays:
        - 4 columns with key portfolio metrics
        - Exposure breakdown by symbol
    """
    st.markdown("### Portfolio Metrics")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="Position Count",
            value=f"{metrics.get('position_count', 0)}",
            delta=None,
            help="Number of open positions"
        )

    with col2:
        st.metric(
            label="Symbol Count",
            value=f"{metrics.get('symbol_count', 0)}",
            delta=None,
            help="Number of unique underlying symbols"
        )

    with col3:
        exposure = metrics.get('total_exposure', 0.0)
        st.metric(
            label="Total Exposure",
            value=f"${exposure:,.0f}",
            delta=None,
            help="Total notional exposure"
        )

    with col4:
        max_pos = metrics.get('max_single_position', 0.0)
        st.metric(
            label="Max Single Position",
            value=f"{max_pos:.1%}",
            delta=None,
            help="Largest position as percentage of portfolio"
        )

    # Display correlated exposure if available
    correlated = metrics.get('correlated_exposure', {})
    if correlated:
        st.markdown("#### Exposure by Symbol")
        for symbol, exposure_pct in correlated.items():
            st.write(f"**{symbol}**: {exposure_pct:.1%}")
    else:
        st.caption("No exposure data available (requires Greeks tracking)")
