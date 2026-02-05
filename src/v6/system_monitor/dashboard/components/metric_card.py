"""Metric card component.

Displays a metric with optional progress bar and color coding.
"""

import streamlit as st


def metric_card(
    name: str,
    value: float | str,
    unit: str = "",
    thresholds: dict[str, float] | None = None,
) -> None:
    """Display metric with optional progress bar.

    Args:
        name: Metric name
        value: Metric value (float for percentage, str for text)
        unit: Unit string (e.g., "%", "GB")
        thresholds: Optional dict with "warning" and "critical" thresholds
    """
    # Display metric name and value
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"**{name}**")
    with col2:
        if isinstance(value, float):
            st.markdown(f"<div style='text-align: right;'>**{value:.1f}{unit}**</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div style='text-align: right;'>**{value}{unit}**</div>", unsafe_allow_html=True)

    # Add progress bar for percentage values
    if isinstance(value, (float, int)) and unit == "%":
        # Determine color based on thresholds
        if thresholds:
            if value >= thresholds.get("critical", 90):
                color = "red"
            elif value >= thresholds.get("warning", 80):
                color = "yellow"
            else:
                color = "green"
        else:
            # Default thresholds: green <50%, yellow 50-80%, red >80%
            if value >= 80:
                color = "red"
            elif value >= 50:
                color = "yellow"
            else:
                color = "green"

        # Create progress bar
        st.progress(value / 100)

        # Add color indicator
        st.markdown(
            f"<div style='height: 5px; background-color: {color}; border-radius: 3px;'></div>",
            unsafe_allow_html=True,
        )
