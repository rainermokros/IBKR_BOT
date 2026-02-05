"""
Futures Data Loading Functions

This module provides data loading functions for futures monitoring.
Reads from Delta Lake (futures_snapshots table) to avoid IB API rate limits.

All functions are cached using Streamlit's @st.cache_data decorator
to avoid repeated Delta Lake reads.
"""

from datetime import datetime, timedelta
from typing import Any, Optional

import polars as pl
from deltalake import DeltaTable
from loguru import logger
import streamlit as st


@st.cache_data(ttl=30)
def get_latest_snapshots(
    table_path: str = "data/lake/futures_snapshots"
) -> dict[str, Any]:
    """
    Get latest futures snapshots for all symbols (ES, NQ, RTY).

    Args:
        table_path: Path to Delta Lake table (default: data/lake/futures_snapshots)

    Returns:
        Dictionary mapping symbol -> snapshot dict with keys:
        - symbol, timestamp, bid, ask, last, volume
        - change_1h, change_4h, change_overnight, change_daily

        Returns empty dict if no data available.

    Note:
        Cached for 30 seconds to avoid repeated Delta Lake reads.
    """
    try:
        # Check if table exists
        if not DeltaTable.is_deltatable(table_path):
            logger.warning(f"Delta Lake table does not exist: {table_path}")
            return {}

        # Read from Delta Lake
        dt = DeltaTable(table_path)
        df = pl.from_pandas(dt.to_pandas())

        # Check if empty
        if df.is_empty():
            logger.warning(f"No data in futures snapshots table: {table_path}")
            return {}

        # Get latest snapshot for each symbol
        latest = df.sort("timestamp", descending=True).group_by("symbol").first()

        # Convert to dict
        result = {}
        for row in latest.iter_rows(named=True):
            symbol = row["symbol"]
            result[symbol] = {
                "symbol": symbol,
                "timestamp": row["timestamp"],
                "bid": row.get("bid"),
                "ask": row.get("ask"),
                "last": row.get("last"),
                "volume": row.get("volume", 0),
                "open_interest": row.get("open_interest"),
                "implied_vol": row.get("implied_vol"),
                "change_1h": row.get("change_1h"),
                "change_4h": row.get("change_4h"),
                "change_overnight": row.get("change_overnight"),
                "change_daily": row.get("change_daily"),
            }

        return result

    except Exception as e:
        logger.error(f"Error loading latest snapshots: {e}")
        return {}


@st.cache_data(ttl=30)
def get_historical_snapshots(
    symbol: str,
    hours: int = 4,
    table_path: str = "data/lake/futures_snapshots"
) -> pl.DataFrame:
    """
    Get historical futures snapshots for a symbol.

    Args:
        symbol: Futures symbol (ES, NQ, RTY)
        hours: Number of hours of historical data (default: 4)
        table_path: Path to Delta Lake table

    Returns:
        Polars DataFrame with historical snapshots sorted by timestamp ascending.
        Returns empty DataFrame if no data available.

    Note:
        Cached for 30 seconds.
    """
    try:
        # Check if table exists
        if not DeltaTable.is_deltatable(table_path):
            logger.warning(f"Delta Lake table does not exist: {table_path}")
            return pl.DataFrame()

        # Calculate time range
        end = datetime.now()
        start = end - timedelta(hours=hours)

        # Read from Delta Lake
        dt = DeltaTable(table_path)
        df = pl.from_pandas(dt.to_pandas())

        # Filter by symbol and time range
        df = df.filter(
            (pl.col("symbol") == symbol) &
            (pl.col("timestamp") >= start) &
            (pl.col("timestamp") <= end)
        )

        # Sort by timestamp ascending
        df = df.sort("timestamp")

        return df

    except Exception as e:
        logger.error(f"Error loading historical snapshots for {symbol}: {e}")
        return pl.DataFrame()


@st.cache_data(ttl=30)
def get_change_metrics(
    symbol: str,
    table_path: str = "data/lake/futures_snapshots"
) -> dict[str, float]:
    """
    Get change metrics for a futures symbol from latest snapshot.

    Args:
        symbol: Futures symbol (ES, NQ, RTY)
        table_path: Path to Delta Lake table

    Returns:
        Dictionary with change metrics:
        - change_1h: 1-hour change
        - change_4h: 4-hour change
        - change_overnight: Overnight change
        - change_daily: Daily change

        Returns dict with None values if no data available.

    Note:
        Cached for 30 seconds.
    """
    try:
        # Get latest snapshots
        snapshots = get_latest_snapshots(table_path=table_path)

        # Check if symbol exists
        if symbol not in snapshots:
            logger.warning(f"No snapshot available for {symbol}")
            return {
                "change_1h": None,
                "change_4h": None,
                "change_overnight": None,
                "change_daily": None,
            }

        # Extract change metrics
        snapshot = snapshots[symbol]
        return {
            "change_1h": snapshot.get("change_1h"),
            "change_4h": snapshot.get("change_4h"),
            "change_overnight": snapshot.get("change_overnight"),
            "change_daily": snapshot.get("change_daily"),
        }

    except Exception as e:
        logger.error(f"Error getting change metrics for {symbol}: {e}")
        return {
            "change_1h": None,
            "change_4h": None,
            "change_overnight": None,
            "change_daily": None,
        }


@st.cache_data(ttl=30)
def get_available_symbols(
    table_path: str = "data/lake/futures_snapshots"
) -> list[str]:
    """
    Get list of available futures symbols in the data.

    Args:
        table_path: Path to Delta Lake table

    Returns:
        List of unique symbols (sorted)
    """
    try:
        # Check if table exists
        if not DeltaTable.is_deltatable(table_path):
            return []

        # Read from Delta Lake
        dt = DeltaTable(table_path)
        df = pl.from_pandas(dt.to_pandas())

        # Check if empty
        if df.is_empty():
            return []

        # Get unique symbols
        symbols = df["symbol"].unique().to_list()
        return sorted(symbols)

    except Exception as e:
        logger.error(f"Error getting available symbols: {e}")
        return []


def format_change(value: Optional[float]) -> str:
    """
    Format change value for display with color coding indicator.

    Args:
        value: Change value (float or None)

    Returns:
        Formatted string with +/- prefix and 2 decimal places
    """
    if value is None:
        return "N/A"

    return f"{value:+.2f}"


def get_change_color(value: Optional[float]) -> str:
    """
    Get color for change value (green for positive, red for negative).

    Args:
        value: Change value (float or None)

    Returns:
        Color name: "green", "red", or "gray" for None
    """
    if value is None:
        return "gray"

    return "green" if value > 0 else "red"
