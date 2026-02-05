"""Data quality health indicator component.

Displays a real-time data quality health score with color coding.
"""

import streamlit as st


def display_health_score(health_score: int, anomaly_count: int = 0) -> None:
    """Display data quality health score with color coding.

    Args:
        health_score: Health score from 0-100
        anomaly_count: Number of anomalies detected
    """
    # Determine color based on health score
    if health_score >= 80:
        color = "#28a745"  # Green
        label = "Good"
        emoji = "✅"
    elif health_score >= 50:
        color = "#ffc107"  # Yellow
        label = "Warning"
        emoji = "⚠️"
    else:
        color = "#dc3545"  # Red
        label = "Critical"
        emoji = "🔴"

    # Display health score with styling
    st.markdown(
        f"""
        <div style="
            padding: 1rem;
            border-radius: 0.5rem;
            background-color: {color}20;
            border-left: 5px solid {color};
            margin-bottom: 1rem;
        ">
            <div style="display: flex; align-items: center; justify-content: space-between;">
                <div>
                    <span style="font-size: 1.5rem;">{emoji}</span>
                    <span style="font-weight: bold; font-size: 1.1rem; margin-left: 0.5rem;">
                        Data Quality: {label}
                    </span>
                </div>
                <div style="text-align: right;">
                    <span style="font-size: 2rem; font-weight: bold; color: {color};">
                        {health_score}%
                    </span>
                </div>
            </div>
            <div style="margin-top: 0.5rem; font-size: 0.9rem; color: #666;">
                Anomalies detected: <strong>{anomaly_count}</strong>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def display_health_score_compact(health_score: int, anomaly_count: int = 0) -> None:
    """Display compact version of health score for main dashboard.

    Args:
        health_score: Health score from 0-100
        anomaly_count: Number of anomalies detected
    """
    # Determine color
    if health_score >= 80:
        color = "#28a745"
    elif health_score >= 50:
        color = "#ffc107"
    else:
        color = "#dc3545"

    # Compact display
    st.markdown(
        f"""
        <div style="
            padding: 0.5rem;
            border-radius: 0.3rem;
            background-color: {color}20;
            border-left: 3px solid {color};
            text-align: center;
            cursor: pointer;
        " onclick="document.querySelector('a[aria-label=\"View Data Quality\"]').click()">
            <div style="font-size: 0.8rem; color: #666;">Data Quality</div>
            <div style="font-size: 1.5rem; font-weight: bold; color: {color};">
                {health_score}%
            </div>
            <div style="font-size: 0.7rem; color: #666;">
                {anomaly_count} anomalies
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
