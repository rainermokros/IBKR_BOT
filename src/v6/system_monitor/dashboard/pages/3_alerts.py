"""
Alert Management Page

This page displays active alerts, alert history, and provides
alert acknowledgment and resolution workflows.
"""

from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
from loguru import logger

from v6.system_monitor.dashboard.data.alerts import (
    acknowledge_alert_dashboard,
    filter_alerts,
    get_alert_summary,
    load_alerts,
    resolve_alert_dashboard,
)

# Page config
st.set_page_config(
    page_title="Alerts",
    page_icon="🔔",
    layout="wide"
)

st.title("🔔 Alert Management")

# Initialize session state for action feedback
if "alert_action_success" not in st.session_state:
    st.session_state.alert_action_success = None
if "alert_action_message" not in st.session_state:
    st.session_state.alert_action_message = None

# Load alerts
with st.spinner("Loading alerts..."):
    alerts_df = load_alerts()

# Calculate summary
summary = get_alert_summary(alerts_df)

# Display summary metrics
st.markdown("### Summary Metrics")
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric(
        "Active Alerts",
        summary["active_count"],
        delta_color="inverse"
    )

with col2:
    st.metric(
        "Acknowledged",
        summary["acknowledged_count"]
    )

with col3:
    st.metric(
        "Resolved Today",
        summary["resolved_today"]
    )

with col4:
    st.metric(
        "Avg Response Time",
        f"{summary['avg_response_time']} min"
    )

with col5:
    critical_count = summary["critical_count"]
    st.metric(
        "Critical",
        critical_count,
        delta_color="inverse" if critical_count > 0 else "normal"
    )

# Display action feedback
if st.session_state.alert_action_success is not None:
    if st.session_state.alert_action_success:
        st.success(st.session_state.alert_action_message)
    else:
        st.error(st.session_state.alert_action_message)

    # Clear feedback after display
    st.session_state.alert_action_success = None
    st.session_state.alert_action_message = None

# Create tabs
tab1, tab2, tab3 = st.tabs(["Active Alerts", "Alert History", "Configuration"])

with tab1:
    st.markdown("### 🔴 Active Alerts")

    # Filters
    col1, col2 = st.columns(2)

    with col1:
        severity_filter = st.selectbox(
            "Severity",
            ["ALL", "IMMEDIATE", "HIGH", "NORMAL", "LOW"],
            index=0,
            key="active_severity_filter"
        )

    with col2:
        # Count by severity
        if severity_filter == "ALL":
            filtered_df = alerts_df[alerts_df["status"] == "ACTIVE"]
        else:
            filtered_df = alerts_df[
                (alerts_df["status"] == "ACTIVE") &
                (alerts_df["severity"] == severity_filter)
            ]

        st.write(f"Showing {len(filtered_df)} alert(s)")

    # Display active alerts
    if filtered_df.empty:
        st.success("✅ No active alerts")
    else:
        # Define action callbacks
        def on_acknowledge(alert_id: str):
            """Handle acknowledge button click"""
            result = st.session_state.run_sync(
                acknowledge_alert_dashboard,
                alert_id
            )

            st.session_state.alert_action_success = result
            st.session_state.alert_action_message = (
                f"Alert {alert_id[:8]}... acknowledged" if result
                else f"Failed to acknowledge alert {alert_id[:8]}..."
            )
            st.rerun()

        def on_resolve(alert_id: str):
            """Handle resolve button click"""
            result = st.session_state.run_sync(
                resolve_alert_dashboard,
                alert_id
            )

            st.session_state.alert_action_success = result
            st.session_state.alert_action_message = (
                f"Alert {alert_id[:8]}... resolved" if result
                else f"Failed to resolve alert {alert_id[:8]}..."
            )
            st.rerun()

        # Display alerts using list view component
        from v6.system_monitor.dashboard.components.alert_list import alert_list_view

        alert_list_view(
            filtered_df,
            show_actions=True,
            on_acknowledge=on_acknowledge,
            on_resolve=on_resolve
        )

with tab2:
    st.markdown("### Alert History")

    # Filters
    col1, col2, col3 = st.columns(3)

    with col1:
        severity_filter_hist = st.selectbox(
            "Severity",
            ["ALL", "IMMEDIATE", "HIGH", "NORMAL", "LOW"],
            index=0,
            key="hist_severity_filter"
        )

    with col2:
        status_filter_hist = st.selectbox(
            "Status",
            ["ALL", "ACTIVE", "ACKNOWLEDGED", "RESOLVED", "DISMISSED"],
            index=0,
            key="hist_status_filter"
        )

    with col3:
        time_range = st.selectbox(
            "Time Range",
            ["All Time", "Last 24 Hours", "Last 7 Days", "Last 30 Days"],
            index=0,
            key="hist_time_range"
        )

    # Calculate time range filter
    start_time = None
    end_time = None

    if time_range == "Last 24 Hours":
        start_time = datetime.now() - timedelta(hours=24)
    elif time_range == "Last 7 Days":
        start_time = datetime.now() - timedelta(days=7)
    elif time_range == "Last 30 Days":
        start_time = datetime.now() - timedelta(days=30)

    # Apply filters
    filtered_hist = filter_alerts(
        alerts_df,
        severity=severity_filter_hist if severity_filter_hist != "ALL" else None,
        status=status_filter_hist if status_filter_hist != "ALL" else None,
        start_time=start_time,
        end_time=end_time
    )

    st.write(f"Showing {len(filtered_hist)} alert(s)")

    # Display history as table
    if filtered_hist.empty:
        st.info("No alerts match the selected filters")
    else:
        # Prepare display DataFrame
        display_df = filtered_hist.copy()

        # Format columns
        display_df["created_at"] = pd.to_datetime(display_df["created_at"]).dt.strftime("%Y-%m-%d %H:%M")

        if "acknowledged_at" in display_df.columns:
            display_df["acknowledged_at"] = pd.to_datetime(
                display_df["acknowledged_at"], errors="coerce"
            ).dt.strftime("%Y-%m-%d %H:%M")

        if "resolved_at" in display_df.columns:
            display_df["resolved_at"] = pd.to_datetime(
                display_df["resolved_at"], errors="coerce"
            ).dt.strftime("%Y-%m-%d %H:%M")

        # Select columns for display
        columns = [
            "created_at", "severity", "status", "title",
            "message", "rule", "symbol", "resolved_at"
        ]
        display_df = display_df[[col for col in columns if col in display_df.columns]]

        # Rename columns
        display_df = display_df.rename(columns={
            "created_at": "Created",
            "severity": "Severity",
            "status": "Status",
            "title": "Title",
            "message": "Message",
            "rule": "Rule",
            "symbol": "Symbol",
            "resolved_at": "Resolved"
        })

        # Display table
        st.dataframe(
            display_df,
            column_config={
                "Created": st.column_config.DatetimeColumn("Created", width="medium"),
                "Severity": st.column_config.TextColumn("Severity", width="small"),
                "Status": st.column_config.TextColumn("Status", width="small"),
                "Title": st.column_config.TextColumn("Title", width="medium"),
                "Message": st.column_config.TextColumn("Message", width="large"),
                "Rule": st.column_config.TextColumn("Rule", width="medium"),
                "Symbol": st.column_config.TextColumn("Symbol", width="small"),
                "Resolved": st.column_config.TextColumn("Resolved", width="medium"),
            },
            hide_index=True,
            use_container_width=True
        )

        # Export to CSV
        csv = display_df.to_csv(index=False)
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name=f"alerts_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

with tab3:
    st.markdown("### Alert Configuration")

    st.info(
        "ℹ️ Alert rules are configured in Phase 3 DecisionEngine. "
        "See `.planning/phases/3-decision-rules-engine/` for details."
    )

    st.markdown("#### Alert Types")

    st.markdown("""
    | Type | Severity | Description |
    |------|----------|-------------|
    | CRITICAL | IMMEDIATE | Immediate action required (e.g., system failure) |
    | WARNING | HIGH | High priority (e.g., risk limit breach) |
    | WARNING | NORMAL | Normal priority (e.g., position exit triggered) |
    | INFO | NORMAL | Informational (e.g., position roll) |
    """)

    st.markdown("#### Alert Status Flow")

    st.markdown("""
    1. **ACTIVE**: Alert created, awaiting acknowledgment
    2. **ACKNOWLEDGED**: User has seen the alert
    3. **RESOLVED**: Alert has been resolved
    4. **DISMISSED**: Alert has been dismissed

    All alerts start as ACTIVE and progress through the lifecycle.
    """)

    st.markdown("#### Decision → Alert Mapping")

    st.markdown("""
    | Decision Action | Urgency | Alert Type | Alert Severity |
    |----------------|---------|------------|----------------|
    | CLOSE | IMMEDIATE | CRITICAL | IMMEDIATE |
    | CLOSE | HIGH | WARNING | HIGH |
    | CLOSE | NORMAL | WARNING | NORMAL |
    | ROLL | NORMAL | INFO | NORMAL |
    | HOLD | - | (no alert) | - |
    """)

    st.markdown("#### Related Documentation")

    st.markdown("""
    - **Phase 3 Plan 4**: Alert generation and management
    - **DecisionEngine**: 12 priority-based decision rules
    - **AlertManager**: Delta Lake persistence and querying

    See `.planning/phases/3-decision-rules-engine/3-04-SUMMARY.md` for details.
    """)

# Add helper function for running async functions in Streamlit
if "run_sync" not in st.session_state:
    import asyncio

    def run_sync(coro, *args, **kwargs):
        """Run async function synchronously in Streamlit"""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(coro(*args, **kwargs))

    st.session_state.run_sync = run_sync
