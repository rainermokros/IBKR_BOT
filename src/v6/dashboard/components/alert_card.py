"""
Alert display components for dashboard.

This module provides reusable components for displaying alerts,
including severity badges, alert cards, and action buttons.
"""

from datetime import datetime

import pandas as pd
import streamlit as st


def alert_card(
    alert: pd.Series | dict,
    on_acknowledge: callable | None = None,
    on_resolve: callable | None = None,
) -> None:
    """
    Display single alert with action buttons.

    Args:
        alert: Alert data (pandas Series or dict)
        on_acknowledge: Callback for acknowledge button
        on_resolve: Callback for resolve button
    """
    # Convert dict to Series if needed
    if isinstance(alert, dict):
        alert = pd.Series(alert)

    # Severity colors
    severity_colors = {
        "IMMEDIATE": "🔴",
        "HIGH": "🟠",
        "NORMAL": "🟡",
        "LOW": "🔵"
    }
    severity_icon = severity_colors.get(alert.get("severity", "NORMAL"), "⚪")

    # Status colors
    status_colors = {
        "ACTIVE": "🔴",
        "ACKNOWLEDGED": "🟡",
        "RESOLVED": "🟢",
        "DISMISSED": "⚫"
    }
    status_icon = status_colors.get(alert.get("status", "ACTIVE"), "⚪")

    # Display alert header
    col1, col2, col3 = st.columns([3, 1, 1])

    with col1:
        st.markdown(f"**{severity_icon} {alert.get('title', 'Untitled')}**")
        st.caption(alert.get("message", "No description"))

    with col2:
        st.metric("Status", f"{status_icon} {alert.get('status', 'UNKNOWN')}")

    with col3:
        if alert.get('severity'):
            st.metric("Severity", alert.get('severity'))

    # Display alert details
    with st.expander("Details", expanded=False):
        col1, col2 = st.columns(2)

        with col1:
            st.write(f"**Rule:** {alert.get('rule', 'N/A')}")

            if alert.get('symbol'):
                st.write(f"**Symbol:** {alert.get('symbol')}")

            if pd.notna(alert.get('strategy_id')) and alert.get('strategy_id'):
                st.write(f"**Strategy ID:** {alert.get('strategy_id')}")

        with col2:
            if pd.notna(alert.get('created_at')):
                created_str = pd.to_datetime(alert.get('created_at')).strftime("%Y-%m-%d %H:%M:%S")
                st.write(f"**Created:** {created_str}")

            if pd.notna(alert.get('acknowledged_at')):
                ack_str = pd.to_datetime(alert.get('acknowledged_at')).strftime("%Y-%m-%d %H:%M:%S")
                st.write(f"**Acknowledged:** {ack_str}")

            if pd.notna(alert.get('resolved_at')):
                resolved_str = pd.to_datetime(alert.get('resolved_at')).strftime("%Y-%m-%d %H:%M:%S")
                st.write(f"**Resolved:** {resolved_str}")

            if pd.notna(alert.get('age_minutes')):
                st.write(f"**Age:** {alert.get('age_minutes')} min")

        # Display metadata if available
        metadata = alert.get('metadata')
        if metadata and isinstance(metadata, str):
            st.json(metadata)

    # Action buttons (only for active/acknowledged alerts)
    status = alert.get('status', 'ACTIVE')
    if status in ['ACTIVE', 'ACKNOWLEDGED']:
        col1, col2 = st.columns(2)

        with col1:
            if status == 'ACTIVE' and on_acknowledge:
                if st.button(
                    "Acknowledge",
                    key=f"ack_{alert.get('alert_id')}",
                    use_container_width=True
                ):
                    on_acknowledge(alert.get('alert_id'))

        with col2:
            if on_resolve:
                if st.button(
                    "Resolve",
                    key=f"resolve_{alert.get('alert_id')}",
                    use_container_width=True
                ):
                    # Show confirmation dialog
                    if st.session_state.get(f"confirm_resolve_{alert.get('alert_id')}", False):
                        on_resolve(alert.get('alert_id'))
                        st.session_state[f"confirm_resolve_{alert.get('alert_id')}"] = False
                    else:
                        st.session_state[f"confirm_resolve_{alert.get('alert_id')}"] = True
                        st.warning("Click Resolve again to confirm")

    st.markdown("---")


def alert_list(
    alerts_df: pd.DataFrame,
    on_action: callable | None = None,
) -> None:
    """
    Display alerts as interactive table.

    Args:
        alerts_df: DataFrame of alerts
        on_action: Callback for action buttons
    """
    if alerts_df.empty:
        st.info("No alerts to display")
        return

    # Prepare display DataFrame
    display_df = alerts_df.copy()

    # Add severity icons
    severity_icons = {
        "IMMEDIATE": "🔴",
        "HIGH": "🟠",
        "NORMAL": "🟡",
        "LOW": "🔵"
    }
    display_df["severity_icon"] = display_df["severity"].map(severity_icons).fillna("⚪")

    # Add status icons
    status_icons = {
        "ACTIVE": "🔴",
        "ACKNOWLEDGED": "🟡",
        "RESOLVED": "🟢",
        "DISMISSED": "⚫"
    }
    display_df["status_icon"] = display_df["status"].map(status_icons).fillna("⚪")

    # Format timestamps
    display_df["created_at"] = pd.to_datetime(display_df["created_at"]).dt.strftime("%Y-%m-%d %H:%M")

    # Select and reorder columns for display
    columns = [
        "severity_icon", "status_icon", "title", "message",
        "rule", "symbol", "created_at"
    ]
    display_df = display_df[[col for col in columns if col in display_df.columns]]

    # Rename columns
    display_df = display_df.rename(columns={
        "severity_icon": "Severity",
        "status_icon": "Status",
        "title": "Title",
        "message": "Message",
        "rule": "Rule",
        "symbol": "Symbol",
        "created_at": "Created"
    })

    # Display with action buttons
    st.dataframe(
        display_df,
        column_config={
            "Severity": st.column_config.TextColumn("Severity", width="small"),
            "Status": st.column_config.TextColumn("Status", width="small"),
            "Title": st.column_config.TextColumn("Title", width="medium"),
            "Message": st.column_config.TextColumn("Message", width="large"),
            "Rule": st.column_config.TextColumn("Rule", width="medium"),
            "Symbol": st.column_config.TextColumn("Symbol", width="small"),
            "Created": st.column_config.DatetimeColumn("Created", width="medium"),
        },
        hide_index=True,
        use_container_width=True
    )


def severity_badge(severity: str) -> str:
    """
    Get severity badge icon.

    Args:
        severity: Severity string (IMMEDIATE, HIGH, NORMAL, LOW)

    Returns:
        Icon string
    """
    severity_icons = {
        "IMMEDIATE": "🔴",
        "HIGH": "🟠",
        "NORMAL": "🟡",
        "LOW": "🔵"
    }
    return severity_icons.get(severity, "⚪")


def status_badge(status: str) -> str:
    """
    Get status badge icon.

    Args:
        status: Status string (ACTIVE, ACKNOWLEDGED, RESOLVED, DISMISSED)

    Returns:
        Icon string
    """
    status_icons = {
        "ACTIVE": "🔴",
        "ACKNOWLEDGED": "🟡",
        "RESOLVED": "🟢",
        "DISMISSED": "⚫"
    }
    return status_icons.get(status, "⚪")
