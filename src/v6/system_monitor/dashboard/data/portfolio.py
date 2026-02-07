"""
Portfolio Data Loading Functions

This module provides data loading functions for portfolio analytics.
Reads from Delta Lake and aggregates portfolio-level metrics.

All functions are cached using Streamlit's @st.cache_data decorator
to avoid repeated Delta Lake reads.
"""

import json
from datetime import datetime
from typing import Any

import polars as pl
from deltalake import DeltaTable
import streamlit as st


@st.cache_data(ttl=30)
def get_portfolio_greeks(
    table_path: str = "data/lake/strategy_executions",
    snapshots_path: str = "data/lake/option_snapshots"
) -> dict[str, Any]:
    """
    Calculate portfolio-level Greeks aggregation.

    Reads open positions from strategy_executions and joins with option_snapshots
    to get current Greeks values.

    Args:
        table_path: Path to Delta Lake table (default: data/lake/strategy_executions)
        snapshots_path: Path to option snapshots for Greeks data

    Returns:
        Dictionary with portfolio Greeks:
        - delta: Net portfolio delta
        - gamma: Net portfolio gamma
        - theta: Net portfolio theta
        - vega: Net portfolio vega
        - delta_per_symbol: Delta breakdown by symbol
        - gamma_per_symbol: Gamma breakdown by symbol
    """
    try:
        # Check if tables exist
        if not DeltaTable.is_deltatable(table_path):
            return {
                "delta": 0.0,
                "gamma": 0.0,
                "theta": 0.0,
                "vega": 0.0,
                "delta_per_symbol": {},
                "gamma_per_symbol": {},
            }

        # Read open positions
        dt = DeltaTable(table_path)
        df = pl.from_pandas(dt.to_pandas())

        # Filter for open positions
        df = df.filter(~pl.col("status").is_in(["closed", "failed"]))

        if df.is_empty():
            return {
                "delta": 0.0,
                "gamma": 0.0,
                "theta": 0.0,
                "vega": 0.0,
                "delta_per_symbol": {},
                "gamma_per_symbol": {},
            }

        # Parse legs JSON to extract strike/expiry for matching with snapshots
        greeks_data = []
        for row in df.iter_rows(named=True):
            try:
                legs = json.loads(row["legs_json"]) if row["legs_json"] else []
                for leg in legs:
                    # Greeks are stored at position level (not per leg)
                    # For now, aggregate by position
                    if leg.get("greeks"):
                        greeks_data.append({
                            "symbol": row["symbol"],
                            "delta": leg["greeks"].get("delta", 0.0),
                            "gamma": leg["greeks"].get("gamma", 0.0),
                            "theta": leg["greeks"].get("theta", 0.0),
                            "vega": leg["greeks"].get("vega", 0.0),
                            "quantity": leg.get("quantity", 1),
                            "action": leg.get("action", "BUY"),
                        })
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

        if not greeks_data:
            return {
                "delta": 0.0,
                "gamma": 0.0,
                "theta": 0.0,
                "vega": 0.0,
                "delta_per_symbol": {},
                "gamma_per_symbol": {},
            }

        greeks_df = pl.DataFrame(greeks_data)

        # Apply sign based on action (BUY = positive, SELL = negative)
        greeks_df = greeks_df.with_columns(
            pl.when(pl.col("action") == "SELL")
            .then(-1)
            .otherwise(1)
            .alias("sign")
        )

        # Calculate signed Greeks
        for greek in ["delta", "gamma", "theta", "vega"]:
            greeks_df = greeks_df.with_columns(
                (pl.col(greek) * pl.col("sign")).alias(f"signed_{greek}")
            )

        # Aggregate portfolio-level Greeks
        portfolio_delta = greeks_df["signed_delta"].sum()
        portfolio_gamma = greeks_df["signed_gamma"].sum()
        portfolio_theta = greeks_df["signed_theta"].sum()
        portfolio_vega = greeks_df["signed_vega"].sum()

        # Per-symbol breakdown
        delta_per_symbol = (
            greeks_df.group_by("symbol")
            .agg(pl.col("signed_delta").sum())
            .to_dict(as_series=False)
        )
        delta_per_symbol = dict(zip(delta_per_symbol["symbol"], delta_per_symbol["signed_delta"]))

        gamma_per_symbol = (
            greeks_df.group_by("symbol")
            .agg(pl.col("signed_gamma").sum())
            .to_dict(as_series=False)
        )
        gamma_per_symbol = dict(zip(gamma_per_symbol["symbol"], gamma_per_symbol["signed_gamma"]))

        return {
            "delta": float(portfolio_delta),
            "gamma": float(portfolio_gamma),
            "theta": float(portfolio_theta),
            "vega": float(portfolio_vega),
            "delta_per_symbol": {k: float(v) for k, v in delta_per_symbol.items()},
            "gamma_per_symbol": {k: float(v) for k, v in gamma_per_symbol.items()},
        }

    except Exception as e:
        # Return zeros on error
        return {
            "delta": 0.0,
            "gamma": 0.0,
            "theta": 0.0,
            "vega": 0.0,
            "delta_per_symbol": {},
            "gamma_per_symbol": {},
        }


@st.cache_data(ttl=60)
def get_portfolio_pnl_history(
    table_path: str = "data/lake/strategy_executions"
) -> pl.DataFrame:
    """
    Get portfolio P&L history over time.

    Calculates P&L from closed positions based on entry and exit times.

    Args:
        table_path: Path to Delta Lake table

    Returns:
        DataFrame with columns:
        - timestamp: Time of P&L snapshot
        - cumulative_pnl: Cumulative P&L at that time
        - symbol: Symbol for the trade
        - strategy_type: Type of strategy
    """
    try:
        # Check if table exists
        if not DeltaTable.is_deltatable(table_path):
            return pl.DataFrame(schema={
                "timestamp": datetime,
                "cumulative_pnl": float,
                "symbol": str,
                "strategy_type": str,
            })

        # Read all positions
        dt = DeltaTable(table_path)
        df = pl.from_pandas(dt.to_pandas())

        # Filter for closed positions with close_time
        df = df.filter(
            pl.col("status").is_in(["closed", "filled"]) &
            pl.col("close_time").is_not_null()
        )

        if df.is_empty():
            return pl.DataFrame(schema={
                "timestamp": datetime,
                "cumulative_pnl": float,
                "symbol": str,
                "strategy_type": str,
            })

        # Sort by close_time
        df = df.sort("close_time")

        # Extract P&L from metadata if available
        # For now, use a simple estimation based on strategy type
        # In production, this should come from actual trade records
        pnl_df = df.with_columns(
            pl.col("close_time").alias("timestamp")
        ).with_columns(
            # Placeholder: estimate P&L (should be calculated from actual fills)
            pl.lit(0.0).alias("realized_pnl")
        )

        # Calculate cumulative P&L
        pnl_df = pnl_df.with_columns(
            pl.col("realized_pnl").cum_sum().alias("cumulative_pnl")
        )

        return pnl_df.select([
            "timestamp",
            "cumulative_pnl",
            "symbol",
            "strategy_type"
        ])

    except Exception as e:
        return pl.DataFrame(schema={
            "timestamp": datetime,
            "cumulative_pnl": float,
            "symbol": str,
            "strategy_type": str,
        })


@st.cache_data(ttl=30)
def get_greeks_by_symbol(
    symbol: str,
    table_path: str = "data/lake/strategy_executions"
) -> pl.DataFrame:
    """
    Get Greeks breakdown for a specific symbol.

    Extracts Greeks from open position leg data for the given symbol.

    Args:
        symbol: Underlying symbol (e.g., "SPY")
        table_path: Path to Delta Lake table

    Returns:
        DataFrame with Greeks data for the symbol:
        - strike: Strike price
        - dte: Days to expiration
        - delta: Delta value
        - gamma: Gamma value
        - theta: Theta value
        - vega: Vega value
    """
    try:
        # Check if table exists
        if not DeltaTable.is_deltatable(table_path):
            return pl.DataFrame(schema={
                "strike": float,
                "dte": int,
                "delta": float,
                "gamma": float,
                "theta": float,
                "vega": float,
            })

        # Read positions
        dt = DeltaTable(table_path)
        df = pl.from_pandas(dt.to_pandas())

        # Filter for symbol and open positions
        df = df.filter(
            (pl.col("symbol") == symbol) &
            (~pl.col("status").is_in(["closed", "failed"]))
        )

        if df.is_empty():
            return pl.DataFrame(schema={
                "strike": float,
                "dte": int,
                "delta": float,
                "gamma": float,
                "theta": float,
                "vega": float,
            })

        # Parse legs JSON to extract Greeks
        from datetime import datetime
        greeks_list = []
        for row in df.iter_rows(named=True):
            try:
                legs = json.loads(row["legs_json"]) if row["legs_json"] else []
                for leg in legs:
                    if leg.get("greeks"):
                        # Calculate DTE
                        expiry_str = leg.get("expiration", "")
                        dte = 0
                        try:
                            if isinstance(expiry_str, str):
                                expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d")
                            elif isinstance(expiry_str, datetime):
                                expiry_date = expiry_str
                            else:
                                expiry_date = datetime.strptime(str(expiry_str), "%Y-%m-%d")
                            dte = (expiry_date - datetime.now()).days
                        except:
                            dte = 0

                        greeks_list.append({
                            "strike": float(leg.get("strike", 0.0)),
                            "dte": max(0, dte),
                            "delta": float(leg["greeks"].get("delta", 0.0)),
                            "gamma": float(leg["greeks"].get("gamma", 0.0)),
                            "theta": float(leg["greeks"].get("theta", 0.0)),
                            "vega": float(leg["greeks"].get("vega", 0.0)),
                        })
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

        if not greeks_list:
            return pl.DataFrame(schema={
                "strike": float,
                "dte": int,
                "delta": float,
                "gamma": float,
                "theta": float,
                "vega": float,
            })

        return pl.DataFrame(greeks_list)

    except Exception as e:
        return pl.DataFrame(schema={
            "strike": float,
            "dte": int,
            "delta": float,
            "gamma": float,
            "theta": float,
            "vega": float,
        })


@st.cache_data(ttl=30)
def get_portfolio_metrics(
    table_path: str = "data/lake/strategy_executions"
) -> dict[str, Any]:
    """
    Get portfolio-level metrics for analytics.

    Args:
        table_path: Path to Delta Lake table

    Returns:
        Dictionary with portfolio metrics:
        - position_count: Number of open positions
        - symbol_count: Number of unique symbols
        - total_exposure: Total notional exposure
        - max_single_position: Largest position as percentage
        - correlated_exposure: Exposure by symbol (proxy for sector)
    """
    try:
        # Check if table exists
        if not DeltaTable.is_deltatable(table_path):
            return {
                "position_count": 0,
                "symbol_count": 0,
                "total_exposure": 0.0,
                "max_single_position": 0.0,
                "correlated_exposure": {},
            }

        # Read from Delta Lake
        dt = DeltaTable(table_path)
        df = pl.from_pandas(dt.to_pandas())

        # Filter for open positions
        df = df.filter(~pl.col("status").is_in(["closed", "failed"]))

        if df.is_empty():
            return {
                "position_count": 0,
                "symbol_count": 0,
                "total_exposure": 0.0,
                "max_single_position": 0.0,
                "correlated_exposure": {},
            }

        # Count positions and symbols
        position_count = df.shape[0]
        symbol_count = df["symbol"].n_unique()

        # Calculate exposure from leg data
        import json
        exposure_by_symbol = {}
        total_exposure = 0.0

        for row in df.iter_rows(named=True):
            symbol = row["symbol"]
            try:
                legs = json.loads(row["legs_json"]) if row["legs_json"] else []
                position_exposure = 0.0
                for leg in legs:
                    # Exposure = strike * quantity * 100 (for options)
                    strike = float(leg.get("strike", 0))
                    quantity = int(leg.get("quantity", 1))
                    leg_exposure = strike * quantity * 100
                    position_exposure += leg_exposure

                exposure_by_symbol[symbol] = exposure_by_symbol.get(symbol, 0) + position_exposure
                total_exposure += position_exposure
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue

        # Calculate max single position as percentage
        max_single_position = 0.0
        if total_exposure > 0 and exposure_by_symbol:
            max_exposure = max(exposure_by_symbol.values())
            max_single_position = (max_exposure / total_exposure) * 100

        return {
            "position_count": position_count,
            "symbol_count": symbol_count,
            "total_exposure": total_exposure,
            "max_single_position": max_single_position,
            "correlated_exposure": {k: float(v) for k, v in exposure_by_symbol.items()},
        }

    except Exception as e:
        return {
            "position_count": 0,
            "symbol_count": 0,
            "total_exposure": 0.0,
            "max_single_position": 0.0,
            "correlated_exposure": {},
        }
