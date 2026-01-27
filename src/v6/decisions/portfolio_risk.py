"""
Portfolio Risk Models and Calculator

This module provides portfolio-level risk calculations with Greek aggregation
and exposure metrics to support decision rules that need portfolio context.

Key patterns:
- dataclass(slots=True) for performance (internal data, validated on entry)
- __post_init__ validation for data integrity
- Type hints for all fields
- Polars for efficient aggregation when >10 positions

Decision tree:
    Is this data internal to my process?
    ├─ Yes → Use dataclass (performance matters) ← WE ARE HERE
    └─ No → Use Pydantic (validation critical)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import polars as pl
from loguru import logger

from src.v6.data.repositories.positions import PositionsRepository


@dataclass(slots=True)
class PortfolioGreeks:
    """
    Portfolio-level options Greeks.

    Represents aggregate Greeks across all positions in the portfolio.
    Used for portfolio-level risk assessment and limit checking.

    Attributes:
        delta: Net portfolio delta (sum of all position deltas)
        gamma: Net portfolio gamma (sum of all position gammas)
        theta: Net portfolio theta (sum of all position thetas)
        vega: Net portfolio vega (sum of all position vegas)
        delta_per_symbol: Delta breakdown by underlying symbol
        gamma_per_symbol: Gamma breakdown by underlying symbol

    Raises:
        ValueError: If delta values are outside valid range
    """

    delta: float
    gamma: float
    theta: float
    vega: float
    delta_per_symbol: dict[str, float] = field(default_factory=dict)
    gamma_per_symbol: dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        """
        Validate Greek values after initialization.

        Ensures data integrity before portfolio Greeks are used.
        Delta should be bounded (short strangles can have high delta, but
        absolute values >100 are usually data errors).
        """
        # Validate delta is within reasonable bounds
        # Note: Portfolio delta can exceed [-1, 1] due to multi-leg strategies
        # but absolute values >100 typically indicate data errors
        if abs(self.delta) > 100:
            raise ValueError(f"Portfolio delta {self.delta} exceeds reasonable bounds [-100, 100]")

        # Validate gamma is within reasonable bounds
        if abs(self.gamma) > 100:
            raise ValueError(f"Portfolio gamma {self.gamma} exceeds reasonable bounds [-100, 100]")

        # Validate theta is within reasonable bounds (negative for long options, positive for short)
        if abs(self.theta) > 10000:
            raise ValueError(f"Portfolio theta {self.theta} exceeds reasonable bounds [-10000, 10000]")

        # Validate vega is within reasonable bounds
        if abs(self.vega) > 10000:
            raise ValueError(f"Portfolio vega {self.vega} exceeds reasonable bounds [-10000, 10000]")

        # Ensure per-symbol dictionaries are valid
        if not isinstance(self.delta_per_symbol, dict):
            raise ValueError("delta_per_symbol must be a dictionary")

        if not isinstance(self.gamma_per_symbol, dict):
            raise ValueError("gamma_per_symbol must be a dictionary")

        # Validate per-symbol deltas are within bounds
        for symbol, delta in self.delta_per_symbol.items():
            if abs(delta) > 100:
                raise ValueError(f"Symbol {symbol} delta {delta} exceeds bounds [-100, 100]")

        # Validate per-symbol gammas are within bounds
        for symbol, gamma in self.gamma_per_symbol.items():
            if abs(gamma) > 100:
                raise ValueError(f"Symbol {symbol} gamma {gamma} exceeds bounds [-100, 100]")

    def __repr__(self) -> str:
        """Return string representation of portfolio Greeks."""
        return (
            f"PortfolioGreeks(delta={self.delta:.4f}, gamma={self.gamma:.4f}, "
            f"theta={self.theta:.2f}, vega={self.vega:.2f}, "
            f"symbols={len(self.delta_per_symbol)})"
        )


@dataclass(slots=True)
class ExposureMetrics:
    """
    Portfolio exposure metrics for risk management.

    Tracks portfolio exposure across multiple dimensions: total exposure,
    concentration risk, and margin utilization.

    Attributes:
        total_exposure: Total notional exposure (sum of position values)
        max_single_position: Largest position as percentage of portfolio (0-1)
        correlated_exposure: Exposure by sector/beta grouping
        buying_power_used: Margin utilization as percentage (0-1)
        buying_power_available: Available buying power in dollars

    Raises:
        ValueError: If percentage values are outside [0, 1]
    """

    total_exposure: float
    max_single_position: float
    correlated_exposure: dict[str, float]
    buying_power_used: float
    buying_power_available: float

    def __post_init__(self):
        """
        Validate exposure metrics after initialization.

        Ensures percentage values are in valid ranges.
        """
        # Validate max_single_position is percentage [0, 1]
        if not 0 <= self.max_single_position <= 1:
            raise ValueError(
                f"max_single_position {self.max_single_position} must be in [0, 1], "
                f"got {self.max_single_position}"
            )

        # Validate buying_power_used is percentage [0, 1]
        if not 0 <= self.buying_power_used <= 1:
            raise ValueError(
                f"buying_power_used {self.buying_power_used} must be in [0, 1], "
                f"got {self.buying_power_used}"
            )

        # Validate buying_power_available is non-negative
        if self.buying_power_available < 0:
            raise ValueError(
                f"buying_power_available {self.buying_power_available} must be >= 0"
            )

        # Validate total_exposure is non-negative
        if self.total_exposure < 0:
            raise ValueError(f"total_exposure {self.total_exposure} must be >= 0")

        # Ensure correlated_exposure is a dict
        if not isinstance(self.correlated_exposure, dict):
            raise ValueError("correlated_exposure must be a dictionary")

        # Validate correlated exposure percentages are in [0, 1]
        for sector, exposure_pct in self.correlated_exposure.items():
            if not 0 <= exposure_pct <= 1:
                raise ValueError(
                    f"Sector {sector} exposure {exposure_pct} must be in [0, 1]"
                )

    def __repr__(self) -> str:
        """Return string representation of exposure metrics."""
        return (
            f"ExposureMetrics(total=${self.total_exposure:,.0f}, "
            f"max_pos={self.max_single_position:.1%}, "
            f"margin_used={self.buying_power_used:.1%}, "
            f"sectors={len(self.correlated_exposure)})"
        )


@dataclass(slots=True)
class PortfolioRisk:
    """
    Complete portfolio risk assessment.

    Aggregates all portfolio risk metrics: Greeks, exposure, and position counts.
    This is the primary data structure for portfolio-level risk assessment.

    Attributes:
        greeks: Portfolio-level Greeks (delta, gamma, theta, vega)
        exposure: Exposure metrics (total, concentration, margin)
        position_count: Number of open positions
        symbol_count: Number of unique underlying symbols
        calculated_at: When this risk assessment was calculated

    Raises:
        ValueError: If counts are negative or calculated_at is invalid
    """

    greeks: PortfolioGreeks
    exposure: ExposureMetrics
    position_count: int
    symbol_count: int
    calculated_at: datetime

    def __post_init__(self):
        """
        Validate portfolio risk after initialization.

        Ensures counts are non-negative and timestamp is valid.
        """
        # Validate position_count is non-negative
        if self.position_count < 0:
            raise ValueError(
                f"position_count {self.position_count} must be >= 0"
            )

        # Validate symbol_count is non-negative
        if self.symbol_count < 0:
            raise ValueError(
                f"symbol_count {self.symbol_count} must be >= 0"
            )

        # Validate calculated_at is datetime
        if not isinstance(self.calculated_at, datetime):
            raise ValueError(
                f"calculated_at must be datetime, got {type(self.calculated_at)}"
            )

        # Sanity check: symbol_count should not exceed position_count
        # (unless there are 0 positions, in which case both should be 0)
        if self.position_count > 0 and self.symbol_count > self.position_count:
            raise ValueError(
                f"symbol_count {self.symbol_count} cannot exceed position_count {self.position_count}"
            )

    def __repr__(self) -> str:
        """Return string representation of portfolio risk."""
        return (
            f"PortfolioRisk(positions={self.position_count}, symbols={self.symbol_count}, "
            f"delta={self.greeks.delta:.4f}, exposure=${self.exposure.total_exposure:,.0f}, "
            f"margin_used={self.exposure.buying_power_used:.1%})"
        )


class PortfolioRiskCalculator:
    """
    Calculator for portfolio-level risk metrics.

    Aggregates Greeks and exposure metrics across all positions to support
    decision rules that need portfolio context (delta risk limits, gamma exposure,
    concentration checks).

    Attributes:
        position_repo: Repository for accessing position data

    Example:
        >>> calc = PortfolioRiskCalculator(PositionRepository())
        >>> risk = await calc.calculate_portfolio_risk()
        >>> print(risk.greeks.delta)
        0.5
    """

    def __init__(self, position_repo: PositionsRepository):
        """
        Initialize the portfolio risk calculator.

        Args:
            position_repo: Repository for accessing position data
        """
        self.position_repo = position_repo

    async def calculate_portfolio_risk(self, account_id: Optional[int] = None) -> PortfolioRisk:
        """
        Calculate comprehensive portfolio risk metrics.

        Aggregates Greeks across all positions, calculates exposure metrics,
        and returns complete portfolio risk assessment.

        Args:
            account_id: Optional account ID filter (for multi-account support)

        Returns:
            PortfolioRisk with aggregated Greeks, exposure, and counts

        Note:
            Uses Polars for efficient aggregation when >10 positions.
            Falls back to simple aggregation for small portfolios.
        """
        # Fetch all open positions
        df = self.position_repo.get_open_positions()

        # Handle empty portfolio
        if df.is_empty():
            return PortfolioRisk(
                greeks=PortfolioGreeks(
                    delta=0.0,
                    gamma=0.0,
                    theta=0.0,
                    vega=0.0,
                    delta_per_symbol={},
                    gamma_per_symbol={},
                ),
                exposure=ExposureMetrics(
                    total_exposure=0.0,
                    max_single_position=0.0,
                    correlated_exposure={},
                    buying_power_used=0.0,
                    buying_power_available=0.0,
                ),
                position_count=0,
                symbol_count=0,
                calculated_at=datetime.now(),
            )

        # Use Polars for aggregation
        position_count = df.shape[0]

        # Aggregate Greeks across all positions
        # Note: df should have delta, gamma, theta, vega columns
        total_delta = df["delta"].sum()
        total_gamma = df["gamma"].sum()
        total_theta = df["theta"].sum()
        total_vega = df["vega"].sum()

        # Per-symbol Greek aggregation
        try:
            symbol_greeks = df.group_by("symbol").agg(
                [
                    pl.col("delta").sum().alias("delta"),
                    pl.col("gamma").sum().alias("gamma"),
                ]
            )

            delta_per_symbol = dict(zip(
                symbol_greeks["symbol"].to_list(),
                symbol_greeks["delta"].to_list(),
                strict=True
            ))
            gamma_per_symbol = dict(zip(
                symbol_greeks["symbol"].to_list(),
                symbol_greeks["gamma"].to_list(),
                strict=True
            ))
        except (AttributeError, KeyError) as e:
            logger.warning(f"Could not aggregate by symbol: {e}")
            delta_per_symbol = {}
            gamma_per_symbol = {}

        # Calculate exposure metrics
        try:
            # Position value: quantity * strike * 100 (multiplier)
            if "strike" in df.columns and "quantity" in df.columns:
                df_with_value = df.with_columns(
                    (pl.col("quantity") * pl.col("strike") * 100).alias("position_value")
                )
                total_exposure = df_with_value["position_value"].sum()

                # Max single position as percentage
                if total_exposure > 0:
                    max_position_value = df_with_value["position_value"].max()
                    max_single_position = max_position_value / total_exposure
                else:
                    max_single_position = 0.0
            else:
                # Fallback: use entry_price * quantity
                if "entry_price" in df.columns and "quantity" in df.columns:
                    df_with_value = df.with_columns(
                        (pl.col("entry_price") * pl.col("quantity").abs() * 100).alias("position_value")
                    )
                    total_exposure = df_with_value["position_value"].sum()

                    if total_exposure > 0:
                        max_position_value = df_with_value["position_value"].max()
                        max_single_position = max_position_value / total_exposure
                    else:
                        max_single_position = 0.0
                else:
                    total_exposure = 0.0
                    max_single_position = 0.0
        except Exception as e:
            logger.warning(f"Could not calculate exposure metrics: {e}")
            total_exposure = 0.0
            max_single_position = 0.0

        # Correlated exposure (by symbol as proxy for sector)
        # TODO: Add sector mapping when available
        try:
            if "strike" in df.columns and "quantity" in df.columns:
                df_with_value = df.with_columns(
                    (pl.col("quantity") * pl.col("strike") * 100).alias("position_value")
                )
                symbol_exposure = df_with_value.group_by("symbol").agg(
                    pl.col("position_value").sum().alias("exposure")
                )
                if total_exposure > 0:
                    correlated_exposure = {
                        symbol: (exp / total_exposure)
                        for symbol, exp in zip(
                            symbol_exposure["symbol"].to_list(),
                            symbol_exposure["exposure"].to_list(),
                            strict=True
                        )
                    }
                else:
                    correlated_exposure = {}
            else:
                correlated_exposure = {}
        except Exception as e:
            logger.warning(f"Could not calculate correlated exposure: {e}")
            correlated_exposure = {}

        # Buying power (TODO: Integrate with IB account data)
        # For now, set defaults
        buying_power_used = 0.0
        buying_power_available = 0.0

        # Symbol count
        try:
            symbol_count = df["symbol"].n_unique()
        except (AttributeError, KeyError):
            symbol_count = 0

        return PortfolioRisk(
            greeks=PortfolioGreeks(
                delta=total_delta,
                gamma=total_gamma,
                theta=total_theta,
                vega=total_vega,
                delta_per_symbol=delta_per_symbol,
                gamma_per_symbol=gamma_per_symbol,
            ),
            exposure=ExposureMetrics(
                total_exposure=total_exposure,
                max_single_position=max_single_position,
                correlated_exposure=correlated_exposure,
                buying_power_used=buying_power_used,
                buying_power_available=buying_power_available,
            ),
            position_count=position_count,
            symbol_count=symbol_count,
            calculated_at=datetime.now(),
        )

    async def get_greeks_by_symbol(self, symbol: str) -> PortfolioGreeks:
        """
        Calculate Greeks for a specific symbol.

        Filters positions by symbol and aggregates Greeks.

        Args:
            symbol: Underlying symbol (e.g., "SPY")

        Returns:
            PortfolioGreeks with per-symbol aggregates
        """
        # Fetch positions for symbol
        df = self.position_repo.get_by_symbol(symbol)

        # Filter for open positions
        if "status" in df.columns:
            df = df.filter(pl.col("status") == "open")

        # Handle no positions
        if df.is_empty():
            return PortfolioGreeks(
                delta=0.0,
                gamma=0.0,
                theta=0.0,
                vega=0.0,
                delta_per_symbol={},
                gamma_per_symbol={},
            )

        # Aggregate Greeks
        delta = df["delta"].sum()
        gamma = df["gamma"].sum()
        theta = df["theta"].sum()
        vega = df["vega"].sum()

        return PortfolioGreeks(
            delta=delta,
            gamma=gamma,
            theta=theta,
            vega=vega,
            delta_per_symbol={symbol: delta},
            gamma_per_symbol={symbol: gamma},
        )

    async def check_delta_limits(self, max_delta: float = 0.30) -> list[str]:
        """
        Check which symbols exceed delta limits.

        Calculates portfolio Greeks and returns list of symbols where
        |delta_per_symbol[symbol]| > max_delta.

        Args:
            max_delta: Maximum allowed delta per symbol (default: 0.30)

        Returns:
            List of symbols exceeding delta limit
        """
        # Calculate portfolio risk
        risk = await self.calculate_portfolio_risk()

        # Check per-symbol deltas
        over_limit = []
        for symbol, delta in risk.greeks.delta_per_symbol.items():
            if abs(delta) > max_delta:
                over_limit.append(symbol)

        return over_limit

    async def check_exposure_limits(
        self,
        max_position_pct: float = 0.02,
        max_correlated_pct: float = 0.05,
    ) -> list[str]:
        """
        Check which symbols/sectors exceed exposure limits.

        Calculates exposure metrics and returns list of symbols exceeding limits.

        Args:
            max_position_pct: Maximum single position as percentage (default: 2%)
            max_correlated_pct: Maximum correlated exposure as percentage (default: 5%)

        Returns:
            List of symbols/sectors exceeding exposure limits
        """
        # Calculate portfolio risk
        risk = await self.calculate_portfolio_risk()

        over_limit = []

        # Check max single position
        # We need to identify which position is the max
        # This requires recalculating with symbol tracking
        df = self.position_repo.get_open_positions()
        if not df.is_empty():
            try:
                if "strike" in df.columns and "quantity" in df.columns:
                    df_with_value = df.with_columns(
                        (pl.col("quantity") * pl.col("strike") * 100).alias("position_value")
                    )
                    total_exposure = df_with_value["position_value"].sum()
                    if total_exposure > 0:
                        max_pos = df_with_value.group_by("symbol").agg(
                            pl.col("position_value").sum().alias("exposure")
                        )
                        for symbol, exposure in zip(
                            max_pos["symbol"].to_list(),
                            max_pos["exposure"].to_list(),
                            strict=True
                        ):
                            if (exposure / total_exposure) > max_position_pct:
                                over_limit.append(symbol)
            except Exception as e:
                logger.warning(f"Could not check position limits: {e}")

        # Check correlated exposure
        for sector, exposure_pct in risk.exposure.correlated_exposure.items():
            if exposure_pct > max_correlated_pct:
                over_limit.append(f"sector:{sector}")

        return over_limit
