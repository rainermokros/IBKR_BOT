"""
V6 Data Models Package

This package provides type-safe data structures for the v6 trading system:
- Pydantic models: For validating external IB API data
- Dataclasses: For high-performance internal state management

Usage:
    from v6.models import OptionLeg, Greeks, StrategyPosition, GreeksSnapshot, Trade
    from v6.models import PositionState, PortfolioState, ConnectionMetrics, SystemState
"""

# Pydantic models for external IB data validation
from v6.models.ib_models import (
    OptionRight,
    PositionStatus,
    Greeks,
    OptionLeg,
    StrategyPosition,
    GreeksSnapshot,
    Trade,
)

# Dataclasses for internal state management
# from v6.models.internal_state import (
#     CircuitState,
#     PositionState,
#     PortfolioState,
#     ConnectionMetrics,
#     SystemState,
# )

__all__ = [
    # Pydantic models
    "OptionRight",
    "PositionStatus",
    "Greeks",
    "OptionLeg",
    "StrategyPosition",
    "GreeksSnapshot",
    "Trade",
    # Dataclasses (uncommented after Task 2)
    # "CircuitState",
    # "PositionState",
    # "PortfolioState",
    # "ConnectionMetrics",
    # "SystemState",
]
