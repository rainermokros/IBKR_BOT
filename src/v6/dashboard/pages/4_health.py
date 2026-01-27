"""System Health monitoring page.

Displays IB connection status, data freshness, system metrics,
and active strategies registry.
"""

import time
from datetime import datetime

import pandas as pd
import streamlit as st

from v6.dashboard.components.metric_card import metric_card
from v6.dashboard.components.status_badge import status_badge
from v6.dashboard.data.health import (
    check_data_freshness,
    check_ib_connection,
    clear_queue,
    force_sync,
    generate_health_alerts,
    get_active_strategies,
    get_system_metrics,
    reconnect_ib,
)

# Page config
st.set_page_config(page_title="System Health", page_icon="🩺", layout="wide")

st.title("🩺 System Health")

# Auto-refresh toggle
auto_refresh = st.toggle("Auto-refresh (5s)", value=True, key="health_auto_refresh")

# IB Connection Status
st.markdown("### IB Connection Status")
ib_status = check_ib_connection()

col1, col2 = st.columns([2, 1])
with col1:
    status_badge(ib_status["status"], "IB Connection")
    st.caption(f"Last update: {ib_status['last_update']}")
    st.caption(f"Host: {ib_status['host']}:{ib_status['port']}")
    st.caption(f"Client ID: {ib_status['client_id']}")
with col2:
    if not ib_status["connected"]:
        if st.button("Reconnect to IB", key="reconnect_ib"):
            result = reconnect_ib()
            if result["success"]:
                st.success(result["message"])
                st.rerun()
            else:
                st.error(result["message"])

# Calculate connection duration
if ib_status["connected"] and ib_status["last_update"]:
    duration = datetime.now() - ib_status["last_update"]
    st.caption(f"Connected for: {str(duration).split('.')[0]}")

st.markdown("---")

# Data Freshness
st.markdown("### Data Freshness")
freshness = check_data_freshness()

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(
        "Last Position Sync",
        freshness["positions_last_sync"].strftime("%H:%M:%S"),
        delta=f"{freshness['positions_age']}s ago",
    )
    status_badge(freshness["positions_status"])
with col2:
    st.metric(
        "Last Greeks Update",
        freshness["greeks_last_update"].strftime("%H:%M:%S"),
        delta=f"{freshness['greeks_age']}s ago",
    )
    status_badge(freshness["greeks_status"])
with col3:
    st.metric(
        "Last Decision Run",
        freshness["decisions_last_run"].strftime("%H:%M:%S"),
        delta=f"{freshness['decisions_age']}s ago",
    )
    status_badge(freshness["decisions_status"])

# Force sync button
col1, col2, col3 = st.columns(3)
with col2:
    if st.button("Force Sync", key="force_sync"):
        result = force_sync()
        if result["success"]:
            st.success(result["message"])
            st.rerun()
        else:
            st.error(result["message"])

st.markdown("---")

# System Metrics
st.markdown("### System Metrics")
metrics = get_system_metrics()

col1, col2, col3 = st.columns(3)
with col1:
    metric_card("CPU Usage", metrics["cpu_percent"], "%", thresholds={"warning": 80, "critical": 90})
with col2:
    metric_card("Memory Usage", metrics["memory_percent"], "%", thresholds={"warning": 80, "critical": 90})
with col3:
    metric_card("Disk Usage", metrics["disk_percent"], "%", thresholds={"warning": 80, "critical": 90})

# Additional metrics
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("System Uptime", metrics["uptime"])
with col2:
    st.metric("Process Count", metrics["process_count"])

st.markdown("---")

# Active Strategies Registry
st.markdown("### Active Strategy Registry")
strategies_df = get_active_strategies()

if not strategies_df.empty:
    slot_count = len(strategies_df)
    st.markdown(f"**{slot_count}** active strategies consuming streaming slots")

    # Show warning if approaching slot limit
    if slot_count > 90:
        st.warning(f"⚠️ Streaming slots near limit ({slot_count}/100 used)")

    # Display strategies table
    symbol_filter = st.selectbox("Filter by symbol", ["ALL"] + sorted(strategies_df["symbol"].unique()))

    if symbol_filter != "ALL":
        filtered_df = strategies_df[strategies_df["symbol"] == symbol_filter]
    else:
        filtered_df = strategies_df

    st.dataframe(
        filtered_df,
        column_config={
            "conid": "Contract ID",
            "symbol": "Symbol",
            "strategy_id": "Strategy ID",
            "since": st.column_config.DatetimeColumn("Active Since", format="MMM D, YYYY, h:mm A"),
        },
        hide_index=True,
        use_container_width=True,
    )
else:
    st.info("No active strategies")

# Clear queue button
st.markdown("---")
st.markdown("### Queue Management")
col1, col2 = st.columns([1, 1])
with col1:
    if st.button("Clear Queue Backlog", key="clear_queue"):
        result = clear_queue()
        if result["success"]:
            st.success(result["message"])
            st.rerun()
        else:
            st.error(result["message"])

st.markdown("---")

# Health Alerts
st.markdown("### Health Alerts")
alerts = generate_health_alerts(ib_status, freshness, metrics, strategies_df)

if alerts:
    for alert in alerts:
        if alert["severity"] == "CRITICAL":
            st.error(f"**{alert['severity']}**: {alert['message']}")
        elif alert["severity"] == "WARNING":
            st.warning(f"**{alert['severity']}**: {alert['message']}")
        else:
            st.info(f"**{alert['severity']}**: {alert['message']}")
else:
    st.success("✅ No health alerts - All systems operational")

# Auto-refresh
if auto_refresh:
    time.sleep(5)
    st.rerun()
