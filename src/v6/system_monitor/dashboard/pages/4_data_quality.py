"""
Data Quality Monitoring Dashboard Page

Real-time data quality monitoring with anomaly detection, health scores,
and detailed metrics. Shows missing values, stale data, corrupted data,
and anomaly timeline.

Usage:
    streamlit run src/v6/dashboard/pages/4_data_quality.py
"""

import time
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import polars as pl
import streamlit as st

from v6.system_monitor.dashboard.components.data_quality_indicator import display_health_score
from v6.system_monitor.dashboard.config import DashboardConfig
from v6.system_monitor.data_quality import DataQualityMonitor
from v6.system_monitor.alerts import AlertManager


@st.cache_data(ttl=30)
def load_data_quality_report() -> tuple:
    """Load data quality report with 30-second cache.

    Returns:
        Tuple of (report, anomalies_df, missing_df)
    """
    monitor = DataQualityMonitor()

    # Generate report
    report = monitor.assess_data_quality()

    # Convert anomalies to DataFrame if needed
    anomalies_df = report.anomalies if len(report.anomalies) > 0 else pd.DataFrame()

    # Create missing values DataFrame
    missing_df = pd.DataFrame(
        list(report.missing_values.items()),
        columns=["Column", "Missing Count"],
    )

    return report, anomalies_df, missing_df


def display_summary_cards(report) -> None:
    """Display summary metric cards.

    Args:
        report: DataQualityReport instance
    """
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="Health Score",
            value=f"{report.health_score}%",
            delta=None,
            help="Overall data quality score (0-100 scale)",
        )

    with col2:
        color = "🔴" if report.anomaly_count > 10 else "🟡" if report.anomaly_count > 5 else "🟢"
        st.metric(
            label="Anomalies",
            value=f"{color} {report.anomaly_count}",
            delta=None,
            help="Number of anomalous data points detected",
        )

    with col3:
        missing_total = sum(report.missing_values.values()) if report.missing_values else 0
        st.metric(
            label="Missing Values",
            value=f"{missing_total:,}",
            delta=None,
            help="Total count of missing values in dataset",
        )

    with col4:
        status = "⚠️ Stale" if report.stale_data else "✅ Fresh"
        st.metric(
            label="Data Freshness",
            value=status,
            delta=None,
            help="Whether data is fresh (last 5 minutes) or stale",
        )


def display_health_score_chart(report) -> None:
    """Display health score gauge chart.

    Args:
        report: DataQualityReport instance
    """
    # Create gauge chart
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=report.health_score,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={
            'text': "Data Quality Health Score",
            'font': {'size': 20}
        },
        delta={
            'reference': 80,
            'increasing': {'color': "#28a745"},
            'decreasing': {'color': "#dc3545"}
        },
        gauge={
            'axis': {
                'range': [None, 100],
                'tickwidth': 1,
                'tickcolor': "darkgray"
            },
            'bar': {
                'color': "#28a745" if report.health_score >= 80 else "#ffc107" if report.health_score >= 50 else "#dc3545"
            },
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [0, 50], 'color': '#ffebee'},
                {'range': [50, 80], 'color': '#fff8e1'},
                {'range': [80, 100], 'color': '#e8f5e9'},
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': 50
            }
        }
    ))

    fig.update_layout(
        height=300,
        margin=dict(l=20, r=20, t=40, b=20),
    )

    st.plotly_chart(fig, use_container_width=True)


def display_anomaly_timeline(anomalies_df: pd.DataFrame) -> None:
    """Display anomaly timeline chart.

    Args:
        anomalies_df: DataFrame with anomalies
    """
    if len(anomalies_df) == 0:
        st.info("✅ No anomalies detected in the last 24 hours")
        return

    # Check if timestamp column exists
    if "timestamp" not in anomalies_df.columns:
        st.warning("⚠️ No timestamp information available for anomalies")
        return

    # Convert timestamp to datetime if needed
    anomalies_df["timestamp"] = pd.to_datetime(anomalies_df["timestamp"])

    # Group by hour for timeline
    anomalies_df["hour"] = anomalies_df["timestamp"].dt.floor("H")
    timeline = anomalies_df.groupby("hour").size().reset_index(columns=["hour", 0])
    timeline.columns = ["hour", "count"]

    # Create line chart
    fig = px.line(
        timeline,
        x="hour",
        y="count",
        title="Anomaly Timeline (Last 24 Hours)",
        labels={"hour": "Time", "count": "Anomaly Count"},
        markers=True,
    )

    fig.update_layout(
        height=300,
        xaxis_title="Time",
        yaxis_title="Anomaly Count",
    )

    st.plotly_chart(fig, use_container_width=True)


def display_anomaly_details(anomalies_df: pd.DataFrame) -> None:
    """Display detailed anomaly records.

    Args:
        anomalies_df: DataFrame with anomalies
    """
    if len(anomalies_df) == 0:
        st.info("✅ No anomalies detected")
        return

    st.subheader("🔍 Anomaly Details")

    # Show summary stats
    st.write(f"**Total anomalies:** {len(anomalies_df)}")

    # Display anomaly table
    # Select relevant columns for display
    display_cols = []
    possible_cols = ["timestamp", "symbol", "close", "volume", "anomaly_score"]

    for col in possible_cols:
        if col in anomalies_df.columns:
            display_cols.append(col)

    if display_cols:
        # Sort by anomaly score (most anomalous first)
        if "anomaly_score" in anomalies_df.columns:
            display_df = anomalies_df[display_cols].sort_values("anomaly_score", ascending=True)
        else:
            display_df = anomalies_df[display_cols]

        st.dataframe(
            display_df.head(100),
            use_container_width=True,
            hide_index=True,
        )


def display_missing_values(missing_df: pd.DataFrame) -> None:
    """Display missing values table.

    Args:
        missing_df: DataFrame with missing values by column
    """
    if len(missing_df) == 0:
        st.info("✅ No missing values detected")
        return

    st.subheader("📋 Missing Values by Column")

    # Create bar chart
    fig = px.bar(
        missing_df,
        x="Column",
        y="Missing Count",
        title="Missing Values by Column",
        color="Missing Count",
        color_continuous_scale="Reds",
    )

    fig.update_layout(
        height=300,
        xaxis_title="Column",
        yaxis_title="Missing Count",
    )

    st.plotly_chart(fig, use_container_width=True)

    # Display table
    st.dataframe(
        missing_df,
        use_container_width=True,
        hide_index=True,
    )


def display_quality_checks(report) -> None:
    """Display data quality check results.

    Args:
        report: DataQualityReport instance
    """
    st.subheader("🔒 Data Quality Checks")

    # Create checklist
    checks = {
        "Stale Data": report.stale_data,
        "Corrupted Data": report.corrupted_data,
        "Out-of-Range Values": report.out_of_range,
    }

    for check_name, is_issue in checks.items():
        if is_issue:
            st.error(f"❌ {check_name}: Issue detected")
        else:
            st.success(f"✅ {check_name}: OK")


def main():
    """Data quality monitoring dashboard main function."""
    st.set_page_config(
        page_title="Data Quality",
        page_icon="🔍",
        layout="wide"
    )

    # Load configuration
    config = DashboardConfig()

    # Page header
    st.markdown("<h2 style='font-size: 1.5rem;'>🔍 Data Quality Monitoring</h2>", unsafe_allow_html=True)

    # Auto-refresh setup
    if "dq_auto_refresh" not in st.session_state:
        st.session_state.dq_auto_refresh = False

    # Sidebar for controls
    with st.sidebar:
        st.markdown("### Controls")

        # Auto-refresh
        auto_refresh = st.checkbox("Auto-Refresh (30s)", value=False)
        st.session_state.dq_auto_refresh = auto_refresh

        if st.button("🔄 Refresh Now"):
            st.cache_data.clear()
            st.rerun()

        st.markdown("---")
        st.caption("Last refresh: {}".format(datetime.now().strftime("%H:%M:%S")))

        # Alert settings
        st.markdown("### Alerts")
        enable_alerts = st.checkbox("Enable Alerts", value=False)

        if enable_alerts:
            st.info("💡 Configure Slack webhook in .env to receive alerts")

    # Load data quality report
    with st.spinner("Analyzing data quality..."):
        report, anomalies_df, missing_df = load_data_quality_report()

    # Display health score indicator
    display_health_score(report.health_score, report.anomaly_count)

    st.markdown("---")

    # Display summary cards
    display_summary_cards(report)

    st.markdown("---")

    # Display health score gauge
    col1, col2 = st.columns(2)

    with col1:
        display_health_score_chart(report)

    with col2:
        display_quality_checks(report)

    st.markdown("---")

    # Display anomaly timeline
    st.subheader("📈 Anomaly Timeline")
    display_anomaly_timeline(anomalies_df)

    st.markdown("---")

    # Display tabs for detailed views
    tab1, tab2, tab3 = st.tabs(["Anomalies", "Missing Values", "Details"])

    with tab1:
        display_anomaly_details(anomalies_df)

    with tab2:
        display_missing_values(missing_df)

    with tab3:
        st.subheader("📊 Detailed Information")
        st.write(f"**Report generated at:** {report.timestamp.isoformat()}")
        st.write(f"**Anomaly count:** {report.anomaly_count}")
        st.write(f"**Health score:** {report.health_score}/100")

        if len(report.missing_values) > 0:
            st.write("**Missing values by column:**")
            for col, count in report.missing_values.items():
                st.write(f"- {col}: {count:,}")

    # Auto-refresh logic
    if auto_refresh:
        time.sleep(30)
        st.rerun()


if __name__ == "__main__":
    main()
