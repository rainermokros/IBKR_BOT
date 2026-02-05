"""
Risk Management Module

This module provides portfolio-level risk management functionality including:
- Risk limits configuration
- Portfolio limit checking
- Portfolio limit exceeded exceptions
- Circuit breaker for system-level fault tolerance

Example:
    >>> from v6.risk_manager import RiskLimitsConfig, PortfolioLimitExceeded
    >>> from v6.risk_manager.portfolio_limits import PortfolioLimitsChecker
    >>>
    >>> # Configure limits
    >>> limits = RiskLimitsConfig(max_portfolio_delta=50.0)
    >>>
    >>> # Create checker
    >>> checker = PortfolioLimitsChecker(risk_calculator, limits)
    >>>
    >>> # Check if entry is allowed
    >>> allowed, reason = await checker.check_entry_allowed(
    ...     new_position_delta=5.0,
    ...     symbol="SPY",
    ...     position_value=10000.0
    ... )
"""

from v6.risk_manager.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerOpenException,
    CircuitState,
    TradingCircuitBreaker,
)
from v6.risk_manager.models import PortfolioLimitExceededError, RiskLimitsConfig
from v6.risk_manager.trailing_stop import (
    TrailingStop,
    TrailingStopAction,
    TrailingStopConfig,
    TrailingStopManager,
)

# Alias for backward compatibility
PortfolioLimitExceeded = PortfolioLimitExceededError

__all__ = [
    # Models
    "RiskLimitsConfig",
    "PortfolioLimitExceededError",
    "PortfolioLimitExceeded",  # Alias
    # Circuit breaker
    "CircuitState",
    "CircuitBreakerConfig",
    "CircuitBreakerOpenException",
    "TradingCircuitBreaker",
    # Trailing stop
    "TrailingStop",
    "TrailingStopAction",
    "TrailingStopConfig",
    "TrailingStopManager",
]
