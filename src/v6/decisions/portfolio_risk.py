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
