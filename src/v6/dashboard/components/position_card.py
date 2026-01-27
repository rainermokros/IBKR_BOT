"""
Position Card Component

Reusable component for displaying position details in an expandable card.
Shows symbol, strategy type, legs, and execution metadata.
"""

from datetime import datetime
from typing import Any

import streamlit as st
from loguru import logger


def position_card(position: dict[str, Any]) -> None:
    """
    Display position details in an expandable card.

    Args:
        position: Dictionary with position data including:
            - execution_id, symbol, strategy_type, status
            - entry_time, fill_time, close_time
            - legs_json (JSON string with leg details)

    Displays:
        - Position metadata (ID, symbol, strategy, status)
        - Execution times (entry, fill, close)
        - Leg details (action, right, strike, expiration, status, fill_price)
    """
    try:
        # Position metadata
        col1, col2, col3 = st.columns(3)

        with col1:
            st.write(f"**Execution ID:** {position.get('execution_id', 'N/A')}")

        with col2:
            st.write(f"**Status:** {position.get('status', 'N/A').upper()}")

        with col3:
            st.write(f"**Strategy ID:** {position.get('strategy_id', 'N/A')}")

        st.markdown("---")

        # Execution times
        col1, col2, col3 = st.columns(3)

        with col1:
            entry_time = position.get('entry_time')
            if isinstance(entry_time, datetime):
                st.write(f"**Entry Time:** {entry_time.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                st.write(f"**Entry Time:** {entry_time}")

        with col2:
            fill_time = position.get('fill_time')
            if isinstance(fill_time, datetime):
                st.write(f"**Fill Time:** {fill_time.strftime('%Y-%m-%d %H:%M:%S')}")
            elif fill_time and fill_time.year > 2000:  # Filter out placeholder
                st.write(f"**Fill Time:** {fill_time.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                st.write(f"**Fill Time:** Pending")

        with col3:
            close_time = position.get('close_time')
            if isinstance(close_time, datetime):
                st.write(f"**Close Time:** {close_time.strftime('%Y-%m-%d %H:%M:%S')}")
            elif close_time and close_time.year > 2000:  # Filter out placeholder
                st.write(f"**Close Time:** {close_time.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                st.write(f"**Close Time:** Open")

        st.markdown("---")

        # Legs
        st.markdown("**Leg Details:**")

        legs_json = position.get('legs_json', '[]')
        legs = parse_legs_json(legs_json)

        if not legs:
            st.caption("No legs found")
        else:
            # Display each leg
            for i, leg in enumerate(legs, 1):
                with st.container():
                    st.markdown(f"**Leg {i}:**")

                    col1, col2, col3 = st.columns(3)

                    with col1:
                        st.write(f"Action: {leg.get('action', 'N/A')}")
                        st.write(f"Right: {leg.get('right', 'N/A')}")

                    with col2:
                        st.write(f"Quantity: {leg.get('quantity', 0)}")
                        st.write(f"Strike: ${leg.get('strike', 0.0):.2f}")

                    with col3:
                        st.write(f"Expiration: {leg.get('expiration', 'N/A')}")
                        st.write(f"Status: {leg.get('status', 'N/A').upper()}")

                    fill_price = leg.get('fill_price')
                    if fill_price and fill_price > 0:
                        st.write(f"Fill Price: ${fill_price:.2f}")

                    st.markdown("---")

    except Exception as e:
        logger.error(f"Error displaying position card: {e}")
        st.error(f"Error displaying position: {e}")


def parse_legs_json(legs_json: str) -> list[dict[str, Any]]:
    """
    Parse legs JSON string into list of dictionaries.

    Args:
        legs_json: JSON string containing legs data

    Returns:
        List of leg dictionaries
    """
    import json

    try:
        legs = json.loads(legs_json)
        return legs if isinstance(legs, list) else []
    except Exception as e:
        logger.error(f"Error parsing legs JSON: {e}")
        return []
