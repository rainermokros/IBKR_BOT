"""
Futures Data Monitor Page

Displays real-time futures data (ES, NQ, RTY) with correlation analysis.
Shows futures vs spot comparison charts and predictive value metrics.

Purpose: Monitor futures movements and assess predictive value for entry signals.

Usage:
    streamlit run src/v6/dashboard/pages/6_futures.py
"""

import time
from datetime import datetime

import polars as pl
import streamlit as st

from src.v6.core.futures_analyzer import FuturesAnalyzer
from src.v6.dashboard.config import DashboardConfig
from src.v6.dashboard.data.futures_data import (
    format_change,
    get_available_symbols,
    get_change_color,
    get_change_metrics,
    get_historical_snapshots,
    get_latest_snapshots,
)


def main():
    """Futures monitor page main function."""
    st.set_page_config(
        page_title="Futures Data",
        page_icon="📊",
        layout="wide"
    )

    # Load configuration
    config = DashboardConfig()

    st.title("📊 Futures Data Monitor")

    # Initialize session state
    if "futures_auto_refresh" not in st.session_state:
        st.session_state.futures_auto_refresh = False
    if "futures_refresh_interval" not in st.session_state:
        st.session_state.futures_refresh_interval = config.default_refresh

    # Sidebar controls
    with st.sidebar:
        st.markdown("### Controls")

        # Auto-refresh
        auto_refresh = st.checkbox(
            "Enable Auto-Refresh",
            value=st.session_state.futures_auto_refresh
        )
        st.session_state.futures_auto_refresh = auto_refresh

        if auto_refresh:
            refresh_interval = st.selectbox(
                "Refresh Interval",
                config.auto_refresh_options,
                index=config.auto_refresh_options.index(st.session_state.futures_refresh_interval)
                if st.session_state.futures_refresh_interval in config.auto_refresh_options
                else 1
            )
            st.session_state.futures_refresh_interval = refresh_interval

            if refresh_interval == 0:
                st.caption("Auto-refresh is OFF")
            else:
                st.caption(f"Refreshes every {refresh_interval}s")

        st.markdown("---")

        # Manual refresh
        if st.button("🔄 Refresh Now"):
            st.cache_data.clear()
            st.rerun()

        st.markdown("---")
        st.caption("💡 Futures data updates every 30s from Delta Lake")

    # Load latest futures snapshots
    with st.spinner("Loading futures data..."):
        snapshots = get_latest_snapshots()
        available_symbols = get_available_symbols()

    # Check if we have data
    if not snapshots:
        st.warning("""
        ⚠️ **No futures data available**

        Futures data collection may not have started yet, or the Delta Lake table doesn't exist.

        **Expected symbols:** ES, NQ, RTY

        **Table path:** `data/lake/futures_snapshots`

        **Troubleshooting:**
        1. Check if futures fetcher is running
        2. Verify Delta Lake table exists
        3. Review logs for collection errors
        """)
        return

    # Display futures snapshot table
    st.markdown("### Real-Time Futures Snapshot")

    # Create table data
    table_data = []
    for symbol in ["ES", "NQ", "RTY"]:
        if symbol in snapshots:
            snap = snapshots[symbol]
            table_data.append({
                "Symbol": symbol,
                "Bid": f"{snap['bid']:.2f}" if snap['bid'] else "N/A",
                "Ask": f"{snap['ask']:.2f}" if snap['ask'] else "N/A",
                "Last": f"{snap['last']:.2f}" if snap['last'] else "N/A",
                "Volume": f"{snap['volume']:,}" if snap['volume'] else "N/A",
                "Change 1H": format_change(snap.get('change_1h')),
                "Change 4H": format_change(snap.get('change_4h')),
                "Change Overnight": format_change(snap.get('change_overnight')),
                "Change Daily": format_change(snap.get('change_daily')),
            })

    # Display as metrics
    if table_data:
        col1, col2, col3 = st.columns(3)

        for i, row in enumerate(table_data):
            col = [col1, col2, col3][i % 3]

            with col:
                st.markdown(f"#### {row['Symbol']}")
                st.metric(
                    label="Last Price",
                    value=row['Last'],
                    delta=row['Change 1H'],
                    delta_color="normal"
                )
                st.caption(f"Bid: {row['Bid']} | Ask: {row['Ask']}")
                st.caption(f"Volume: {row['Volume']}")
                st.caption(f"4H Change: {row['Change 4H']}")
                st.caption(f"Overnight: {row['Change Overnight']}")

    st.markdown("---")

    # Historical charts section
    st.markdown("### Futures Price History (Last 4 Hours)")

    # Get historical data for each symbol
    for symbol in ["ES", "NQ", "RTY"]:
        if symbol in available_symbols:
            with st.expander(f"{symbol} Price History", expanded=True):
                hist_df = get_historical_snapshots(symbol, hours=4)

                if not hist_df.is_empty():
                    # Convert to pandas for plotting
                    hist_pd = hist_df.to_pandas()

                    # Create line chart
                    st.line_chart(
                        hist_pd.set_index('timestamp')['last'],
                        use_container_width=True,
                        height=200
                    )

                    # Display stats
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Min", f"{hist_pd['last'].min():.2f}")
                    with col2:
                        st.metric("Max", f"{hist_pd['last'].max():.2f}")
                    with col3:
                        st.metric("Data Points", f"{len(hist_pd)}")
                else:
                    st.info(f"No historical data available for {symbol}")

    st.markdown("---")

    # Correlation analysis section
    st.markdown("### Futures-Spot Correlation Analysis")

    # Check if we have sufficient data for analysis
    # Need at least 7 days of data
    analyzer = FuturesAnalyzer()

    # Get data age check
    from datetime import timedelta
    from deltalake import DeltaTable

    data_age_warning = False
    if DeltaTable.is_deltatable("data/lake/futures_snapshots"):
        try:
            dt = DeltaTable("data/lake/futures_snapshots")
            df = pl.from_pandas(dt.to_pandas())

            if not df.is_empty():
                min_timestamp = df["timestamp"].min()
                max_timestamp = df["timestamp"].max()
                data_span = (max_timestamp - min_timestamp).total_seconds() / 86400  # days

                if data_span < 7:
                    data_age_warning = True
                    st.warning(f"""
                    ⚠️ **Insufficient data for correlation analysis**

                    Current data span: **{data_span:.1f} days**
                    Required: **7 days minimum**

                    Data collection started: {min_timestamp.strftime('%Y-%m-%d %H:%M')}
                    Latest snapshot: {max_timestamp.strftime('%Y-%m-%d %H:%M')}

                    **Status:** Collecting data... Analysis will be available after 7 days.

                    **Progress:** {data_span / 7 * 100:.1f}% complete
                    """)
        except Exception as e:
            st.error(f"Error checking data age: {e}")
    else:
        data_age_warning = True
        st.warning("Delta Lake table does not exist. Cannot perform analysis.")

    # Perform analysis if sufficient data
    if not data_age_warning:
        st.info("✅ Sufficient data available. Running correlation analysis...")

        # Correlation coefficients
        st.markdown("#### Correlation Coefficients")

        col1, col2, col3 = st.columns(3)

        correlations = {
            "ES-SPY": ("ES", "SPY"),
            "NQ-QQQ": ("NQ", "QQQ"),
            "RTY-IWM": ("RTY", "IWM"),
        }

        for col, (label, (fut, spot)) in zip([col1, col2, col3], correlations.items()):
            with col:
                with st.spinner(f"Calculating {label}..."):
                    corr = analyzer.calculate_correlation(fut, spot, days=7)

                # Color coding based on correlation strength
                if abs(corr) >= 0.8:
                    delta_color = "normal"
                    emoji = "🔗"
                elif abs(corr) >= 0.5:
                    delta_color = "normal"
                    emoji = "📈"
                else:
                    delta_color = "off"
                    emoji = "⚠️"

                st.metric(
                    label=f"{emoji} {label}",
                    value=f"{corr:.3f}",
                    delta=f"{'Strong' if abs(corr) >= 0.8 else 'Moderate' if abs(corr) >= 0.5 else 'Weak'} correlation",
                    delta_color=delta_color
                )

        st.markdown("---")

        # Lead-lag analysis
        st.markdown("#### Lead-Lag Analysis")

        st.caption("Do futures movements lead spot movements? Testing lead times: 5, 15, 30, 60 minutes")

        for label, (fut, spot) in correlations.items():
            with st.expander(f"{label} Lead-Lag Analysis", expanded=(label == "ES-SPY")):
                with st.spinner(f"Analyzing {label} lead-lag..."):
                    lead_lag = analyzer.calculate_lead_lag(fut, spot, max_lead_minutes=60, days=7)

                if lead_lag:
                    # Display lead-lag results
                    for lead_minutes, corr in sorted(lead_lag.items()):
                        st.metric(
                            label=f"{lead_minutes}m lead",
                            value=f"{corr:.3f}",
                            delta=None
                        )

                    # Find optimal lead time
                    optimal_lead = max(lead_lag.items(), key=lambda x: x[1])
                    st.info(f"🎯 Optimal lead time: **{optimal_lead[0]} minutes** (correlation: {optimal_lead[1]:.3f})")
                else:
                    st.warning("No lead-lag data available")

        st.markdown("---")

        # Predictive value assessment
        st.markdown("#### Predictive Value Assessment")

        st.caption("Comprehensive assessment of futures predictive power for spot movements")

        for label, (fut, spot) in correlations.items():
            with st.expander(f"{label} Predictive Value", expanded=(label == "ES-SPY")):
                with st.spinner(f"Assessing {label} predictive value..."):
                    metrics = analyzer.assess_predictive_value(fut, spot, days=7)

                # Display metrics
                col1, col2 = st.columns(2)

                with col1:
                    if metrics.get('directional_accuracy') is not None:
                        st.metric(
                            label="Directional Accuracy",
                            value=f"{metrics['directional_accuracy'] * 100:.1f}%",
                            delta=f"{'Good' if metrics['directional_accuracy'] > 0.55 else 'Fair' if metrics['directional_accuracy'] > 0.5 else 'Poor'}"
                        )
                        st.caption("% of times futures correctly predict spot direction")

                    if metrics.get('signal_to_noise') is not None:
                        st.metric(
                            label="Signal-to-Noise Ratio",
                            value=f"{metrics['signal_to_noise']:.2f}",
                            delta=f"{'Strong' if metrics['signal_to_noise'] > 2 else 'Moderate' if metrics['signal_to_noise'] > 1 else 'Weak'}"
                        )
                        st.caption("Higher values indicate stronger predictive signal")

                with col2:
                    if metrics.get('optimal_lead_minutes') is not None:
                        st.metric(
                            label="Optimal Lead Time",
                            value=f"{metrics['optimal_lead_minutes']}m",
                            delta=None
                        )
                        st.caption("Lead time with highest correlation")

                    if metrics.get('lead_improvement') is not None:
                        st.metric(
                            label="Lead Improvement",
                            value=f"{metrics['lead_improvement']:+.3f}",
                            delta=None
                        )
                        st.caption("Improvement from base correlation")

                # Overall assessment
                if metrics.get('peak_correlation') is not None:
                    if metrics['peak_correlation'] >= 0.85 and metrics.get('directional_accuracy', 0) > 0.55:
                        st.success("🎯 **Strong predictive value** - Consider integrating into entry signals")
                    elif metrics['peak_correlation'] >= 0.7:
                        st.info("📊 **Moderate predictive value** - Useful for confirmation signals")
                    else:
                        st.warning("⚠️ **Weak predictive value** - Limited use for trading decisions")

    st.markdown("---")

    # Data freshness info
    st.markdown("### Data Freshness")
    if snapshots:
        latest_symbol = list(snapshots.keys())[0]
        latest_time = snapshots[latest_symbol]['timestamp']
        time_ago = (datetime.now() - latest_time).total_seconds()

        if time_ago < 60:
            st.success(f"✅ Data fresh: Last update {time_ago:.0f} seconds ago")
        elif time_ago < 300:
            st.info(f"📊 Data recent: Last update {time_ago/60:.1f} minutes ago")
        else:
            st.warning(f"⚠️ Data stale: Last update {time_ago/60:.1f} minutes ago")

    st.caption(f"Data source: Delta Lake (futures_snapshots table)")
    st.caption(f"Collection interval: 1 minute | Cache TTL: 30 seconds")

    # Auto-refresh loop
    if st.session_state.futures_auto_refresh and st.session_state.futures_refresh_interval > 0:
        time.sleep(st.session_state.futures_refresh_interval)
        st.rerun()


if __name__ == "__main__":
    main()
