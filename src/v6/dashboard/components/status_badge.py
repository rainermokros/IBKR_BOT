"""Status badge component.

Displays a status indicator with emoji and color coding.
"""

import streamlit as st


def status_badge(status: str, label: str | None = None) -> None:
    """Display status badge with emoji and color.

    Args:
        status: Status string ("CONNECTED", "DISCONNECTED", "FRESH", "WARNING", "STALE")
        label: Optional label to display next to status
    """
    status_config = {
        "CONNECTED": ("✅", "green"),
        "DISCONNECTED": ("❌", "red"),
        "FRESH": ("✅", "green"),
        "WARNING": ("⚠️", "yellow"),
        "STALE": ("❌", "red"),
    }

    emoji, color = status_config.get(status, ("❓", "gray"))

    # Display badge
    if label:
        st.markdown(
            f"<span style='color: {color}; font-weight: bold;'>{emoji} {status}</span> - {label}",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"<span style='color: {color}; font-weight: bold; font-size: 1.2em;'>{emoji} {status}</span>",
            unsafe_allow_html=True,
        )
