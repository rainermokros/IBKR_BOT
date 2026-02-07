"""
Position Data Loading Functions

This module provides data loading functions for position monitoring.
Reads from Delta Lake (strategy_executions table) to avoid IB API rate limits.

All functions are cached using Streamlit's @st.cache_data decorator
to avoid repeated Delta Lake reads.
"""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl
from deltalake import DeltaTable
from loguru import logger
import streamlit as st


@st.cache_data(ttl=30)
def load_positions(
    symbol: str | None = None,
    strategy: str | None = None,
    status: str | None = None,
    table_path: str = "data/lake/strategy_executions"
) -> pl.DataFrame:
    """
    Load positions from Delta Lake with optional filtering.

    Args:
        symbol: Filter by symbol (e.g., "SPY"). If None, returns all symbols.
        strategy: Filter by strategy_type (e.g., "iron_condor"). If None, returns all strategies.
        status: Filter by status (e.g., "OPEN", "CLOSED"). If None, returns all statuses.
        table_path: Path to Delta Lake table (default: data/lake/strategy_executions)

    Returns:
        Polars DataFrame with position data including:
        - execution_id, strategy_id, symbol, strategy_type, status
        - entry_time, fill_time, close_time
        - legs_json (JSON string with leg details)

    Note:
        Cached for 30 seconds to avoid repeated Delta Lake reads.
        Use st.cache_data.clear() to clear cache manually.
    """
    try:
        # Check if table exists
        if not DeltaTable.is_deltatable(table_path):
            logger.warning(f"Delta Lake table does not exist: {table_path}")
            return pl.DataFrame(schema={
                "execution_id": str,
                "strategy_id": int,
                "symbol": str,
                "strategy_type": str,
                "status": str,
                "entry_time": datetime,
                "fill_time": datetime,
                "close_time": datetime,
                "legs_json": str,
            })

        # Read from Delta Lake
        dt = DeltaTable(table_path)
        df = pl.from_pandas(dt.to_pandas())

        # Apply filters
        if symbol:
            df = df.filter(pl.col("symbol") == symbol)

        if strategy:
            df = df.filter(pl.col("strategy_type") == strategy)

        if status:
            df = df.filter(pl.col("status") == status.lower())

        return df

    except Exception as e:
        logger.error(f"Error loading positions: {e}")
        # Return empty DataFrame with correct schema
        return pl.DataFrame(schema={
            "execution_id": str,
            "strategy_id": int,
            "symbol": str,
            "strategy_type": str,
            "status": str,
            "entry_time": datetime,
            "fill_time": datetime,
            "close_time": datetime,
            "legs_json": str,
        })


@st.cache_data(ttl=30)
def get_position_summary(df: pl.DataFrame) -> dict[str, Any]:
    """
    Calculate summary metrics from positions DataFrame.

    Args:
        df: Positions DataFrame from load_positions()

    Returns:
        Dictionary with summary metrics:
        - total_positions: Total number of positions
        - open_positions: Number of open positions
        - symbols: List of unique symbols
        - strategies: List of unique strategy types

    Note:
        Cached for 30 seconds.
    """
    if df.is_empty():
        return {
            "total_positions": 0,
            "open_positions": 0,
            "symbols": [],
            "strategies": [],
        }

    # Count total and open positions
    total_positions = df.shape[0]

    # Count open positions (status not 'closed' or 'failed')
    open_positions = df.filter(
        ~pl.col("status").is_in(["closed", "failed"])
    ).shape[0]

    # Get unique symbols and strategies
    symbols = df["symbol"].unique().to_list()
    strategies = df["strategy_type"].unique().to_list()

    return {
        "total_positions": total_positions,
        "open_positions": open_positions,
        "symbols": symbols,
        "strategies": strategies,
    }


def parse_legs_for_display(legs_json: str) -> list[dict[str, Any]]:
    """
    Parse legs JSON for display in dashboard.

    Args:
        legs_json: JSON string containing legs data

    Returns:
        List of leg dictionaries with readable format
    """
    try:
        legs = json.loads(legs_json)

        # Format legs for display
        formatted = []
        for leg in legs:
            formatted.append({
                "action": leg.get("action", "N/A"),
                "right": leg.get("right", "N/A"),
                "quantity": leg.get("quantity", 0),
                "strike": leg.get("strike", 0.0),
                "expiration": leg.get("expiration", "N/A"),
                "status": leg.get("status", "N/A"),
                "fill_price": leg.get("fill_price", 0.0),
            })

        return formatted

    except Exception as e:
        logger.error(f"Error parsing legs JSON: {e}")
        return []


def calculate_position_metrics(df: pl.DataFrame) -> dict[str, float]:
    """
    Calculate position-level metrics for dashboard display.

    Args:
        df: Positions DataFrame from load_positions()

    Returns:
        Dictionary with metrics:
        - portfolio_delta: Net delta (from stored Greeks in legs_json)
        - unrealized_pnl: Total unrealized P&L (from stored P&L data)
    """
    if df.is_empty():
        return {
            "portfolio_delta": 0.0,
            "unrealized_pnl": 0.0,
        }

    # Calculate delta from legs_json
    portfolio_delta = 0.0
    unrealized_pnl = 0.0

    for row in df.iter_rows(named=True):
        try:
            legs = json.loads(row["legs_json"]) if row["legs_json"] else []
            for leg in legs:
                # Get delta from Greeks if available
                if leg.get("greeks"):
                    delta = float(leg["greeks"].get("delta", 0.0))
                    quantity = int(leg.get("quantity", 1))
                    action = leg.get("action", "BUY")

                    # Apply sign: BUY = positive, SELL = negative
                    sign = -1 if action == "SELL" else 1
                    portfolio_delta += delta * quantity * sign

                # Get unrealized P&L if available
                if "unrealized_pnl" in leg:
                    unrealized_pnl += float(leg["unrealized_pnl"])

        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue

    return {
        "portfolio_delta": portfolio_delta,
        "unrealized_pnl": unrealized_pnl,
    }


def get_available_symbols(table_path: str = "data/lake/strategy_executions") -> list[str]:
    """
    Get list of available symbols in the data.

    Args:
        table_path: Path to Delta Lake table

    Returns:
        List of unique symbols (sorted)
    """
    df = load_positions(table_path=table_path)

    if df.is_empty():
        return []

    symbols = df["symbol"].unique().to_list()
    return sorted(symbols)


def get_available_strategies(table_path: str = "data/lake/strategy_executions") -> list[str]:
    """
    Get list of available strategy types in the data.

    Args:
        table_path: Path to Delta Lake table

    Returns:
        List of unique strategy types (sorted, uppercase)
    """
    df = load_positions(table_path=table_path)

    if df.is_empty():
        return []

    strategies = df["strategy_type"].unique().to_list()
    return sorted([s.upper() for s in strategies])
