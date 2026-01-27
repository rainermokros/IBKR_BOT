"""
Risk Management Models and Configuration

This module provides data models for risk limits and exceptions
used in portfolio-level risk management.

Key patterns:
- dataclass(slots=True) for performance (internal data, validated on entry)
- Type hints for all fields
- Comprehensive docstrings

Decision tree:
    Is this data internal to my process?
    ├─ Yes → Use dataclass (performance matters) ← WE ARE HERE
    └─ No → Use Pydantic (validation critical)
"""

from dataclasses import dataclass


@dataclass(slots=True)
class RiskLimitsConfig:
    """
    Portfolio-level risk limits configuration.

    Defines thresholds for portfolio risk metrics to prevent over-exposure
    and manage aggregate Greek risk across all positions.

    Attributes:
        max_portfolio_delta: Maximum net portfolio delta allowed (default: 50.0)
        max_portfolio_gamma: Maximum net portfolio gamma allowed (default: 10.0)
        max_single_position_pct: Maximum single position as percentage of
            total exposure (default: 0.02 = 2%)
        max_per_symbol_delta: Maximum delta exposure per symbol (default: 20.0)
        max_correlated_pct: Maximum correlated exposure per sector/symbol
            as percentage (default: 0.05 = 5%)
        total_exposure_cap: Optional cap on total portfolio exposure in dollars
            (default: None = no cap)

    Example:
        >>> limits = RiskLimitsConfig(
        ...     max_portfolio_delta=50.0,
        ...     max_portfolio_gamma=10.0,
        ...     max_single_position_pct=0.02
        ... )
    """

    max_portfolio_delta: float = 50.0
    max_portfolio_gamma: float = 10.0
    max_single_position_pct: float = 0.02  # 2%
    max_per_symbol_delta: float = 20.0
    max_correlated_pct: float = 0.05  # 5%
    total_exposure_cap: float | None = None

    def __repr__(self) -> str:
        """Return string representation of risk limits config."""
        return (
            f"RiskLimitsConfig("
            f"max_delta={self.max_portfolio_delta}, "
            f"max_gamma={self.max_portfolio_gamma}, "
            f"max_pos_pct={self.max_single_position_pct:.1%}, "
            f"max_symbol_delta={self.max_per_symbol_delta}, "
            f"max_correlated_pct={self.max_correlated_pct:.1%})"
        )


class PortfolioLimitExceededError(Exception):
    """
    Exception raised when portfolio limits are exceeded.

    Raised when a new position would cause portfolio-level risk metrics
    to exceed configured thresholds.

    Attributes:
        message: Human-readable error message
        limit_type: Type of limit that was exceeded (e.g., "portfolio_delta", "symbol_delta")
        current_value: Current value of the metric
        limit_value: Maximum allowed value for the metric
        symbol: Symbol associated with the limit (if applicable)

    Example:
        >>> try:
        ...     # Some operation that might exceed limits
        ...     pass
        ... except PortfolioLimitExceededError as e:
        ...     print(f"Limit exceeded: {e.limit_type}: {e.current_value} > {e.limit_value}")
    """

    def __init__(
        self,
        message: str,
        *,
        limit_type: str,
        current_value: float,
        limit_value: float,
        symbol: str | None = None,
    ):
        """
        Initialize portfolio limit exceeded exception.

        Args:
            message: Human-readable error message
            limit_type: Type of limit that was exceeded
            current_value: Current value of the metric
            limit_value: Maximum allowed value
            symbol: Symbol associated with the limit (optional)
        """
        self.message = message
        self.limit_type = limit_type
        self.current_value = current_value
        self.limit_value = limit_value
        self.symbol = symbol
        super().__init__(self.message)

    def __repr__(self) -> str:
        """Return string representation of exception."""
        if self.symbol:
            return (
                f"PortfolioLimitExceededError("
                f"{self.limit_type} for {self.symbol}: "
                f"{self.current_value:.2f} > {self.limit_value:.2f})"
            )
        return (
            f"PortfolioLimitExceededError("
            f"{self.limit_type}: {self.current_value:.2f} > {self.limit_value:.2f})"
        )

    def __str__(self) -> str:
        """Return user-friendly string representation."""
        return self.message
