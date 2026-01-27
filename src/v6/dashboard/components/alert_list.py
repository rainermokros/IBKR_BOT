"""
Alert list component for dashboard.

This module provides a list view component for displaying alerts.
"""

import pandas as pd
import streamlit as st


def alert_list_view(
    alerts_df: pd.DataFrame,
    show_actions: bool = True,
    on_acknowledge: callable | None = None,
    on_resolve: callable | None = None,
) -> None:
    """
    Display alerts in expandable list format.

    Args:
        alerts_df: DataFrame of alerts
        show_actions: Whether to show acknowledge/resolve buttons
        on_acknowledge: Callback for acknowledge button
        on_resolve: Callback for resolve button
    """
    if alerts_df.empty:
        st.info("✅ No alerts to display")
        return

    # Sort by created_at (newest first)
    alerts_df = alerts_df.sort_values("created_at", ascending=False)

    # Display each alert
    for idx, (_, alert) in enumerate(alerts_df.iterrows()):
        # Create expandable section with alert title
        severity = alert.get("severity", "NORMAL")
        status = alert.get("status", "ACTIVE")
        title = alert.get("title", "Untitled")
        message = alert.get("message", "")

        # Create header with severity, status, and message
        from v6.dashboard.components.alert_card import severity_badge, status_badge

        header = f"{severity_badge(severity)} {status_badge(status)} {title}"

        with st.expander(header, expanded=(idx == 0 and status == "ACTIVE")):
            # Display message
            st.write(message)

            # Display details in columns
            col1, col2, col3 = st.columns(3)

            with col1:
                if alert.get('rule'):
                    st.write(f"**Rule:** {alert.get('rule')}")

                if alert.get('symbol'):
                    st.write(f"**Symbol:** {alert.get('symbol')}")

            with col2:
                if pd.notna(alert.get('created_at')):
                    created_str = pd.to_datetime(alert.get('created_at')).strftime("%Y-%m-%d %H:%M:%S")
                    st.write(f"**Created:** {created_str}")

                if pd.notna(alert.get('age_minutes')):
                    st.write(f"**Age:** {alert.get('age_minutes')} min")

            with col3:
                if pd.notna(alert.get('strategy_id')) and alert.get('strategy_id'):
                    st.write(f"**Strategy:** {alert.get('strategy_id')}")

                if pd.notna(alert.get('response_time_seconds')):
                    response_min = alert.get('response_time_seconds') / 60
                    st.write(f"**Response:** {response_min:.1f} min")

            # Action buttons
            if show_actions and status in ['ACTIVE', 'ACKNOWLEDGED']:
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
                            on_resolve(alert.get('alert_id'))

            st.markdown("---")
