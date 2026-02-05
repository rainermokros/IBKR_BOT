"""
Strategy Data Models

This module provides data models for options strategies and their execution.
Uses dataclasses with slots=True for performance (internal data, validated on entry).

Key patterns:
- dataclass(slots=True) for performance
- __post_init__ validation for data integrity
- Type hints for all fields
- Immutable where possible

Decision tree:
    Is this data internal to my process?
    ├─ Yes → Use dataclass (performance matters) ← WE ARE HERE
    └─ No → Use Pydantic (validation critical)
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class StrategyType(str, Enum):
    """
    Strategy type enum.

    Types of options strategies supported by the system.
    """

    IRON_CONDOR = "iron_condor"
    VERTICAL_SPREAD = "vertical_spread"
    CUSTOM = "custom"
    LONG_CALL = "long_call"
    LONG_PUT = "long_put"
    SHORT_CALL = "short_call"
    SHORT_PUT = "short_put"


class OptionRight(str, Enum):
    """Option right enum (CALL or PUT)."""

    CALL = "CALL"
    PUT = "PUT"


class LegAction(str, Enum):
    """Leg action enum (BUY or SELL)."""

    BUY = "BUY"
    SELL = "SELL"


class ExecutionStatus(str, Enum):
    """
    Strategy execution status enum.

    Tracks the lifecycle of a strategy execution.
    """

    PENDING = "pending"
    FILLED = "filled"
    PARTIAL = "partial"
    FAILED = "failed"
    CLOSED = "closed"


class LegStatus(str, Enum):
    """
    Leg execution status enum.

    Tracks the lifecycle of individual legs within a strategy.
    """

    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class LegSpec:
    """
    Leg specification data model.

    Represents a single option leg within a strategy (e.g., one side of an iron condor).

    Attributes:
        right: Option type (CALL or PUT)
        strike: Strike price
        quantity: Number of contracts (positive for BUY, positive for SELL - action separates direction)
        action: BUY or SELL
        expiration: Expiration date
    """

    right: OptionRight
    strike: float
    quantity: int
    action: LegAction
    expiration: date

    def __post_init__(self):
        """
        Validate leg specification after initialization.

        Ensures data integrity before leg is used in strategy building.
        """
        # Validate strike is positive
        if self.strike <= 0:
            raise ValueError(f"Strike must be positive, got {self.strike}")

        # Validate quantity is positive (action separates direction)
        if self.quantity <= 0:
            raise ValueError(f"Quantity must be positive, got {self.quantity}")

        # Validate expiration is in future
        if self.expiration <= date.today():
            raise ValueError(f"Expiration must be in future, got {self.expiration}")

    def __repr__(self) -> str:
        """Return string representation of leg spec."""
        return (
            f"LegSpec({self.action.value} {self.quantity}x "
            f"{self.right.value} ${self.strike} {self.expiration})"
        )


@dataclass(slots=True)
class Strategy:
    """
    Strategy data model.

    Represents a complete options strategy with all legs.

    Attributes:
        strategy_id: Unique identifier for this strategy
        symbol: Underlying symbol (e.g., "SPY")
        strategy_type: Type of strategy (iron_condor, vertical_spread, etc.)
        legs: List of leg specifications
        entry_time: When strategy was created
        status: Strategy status (OPEN, CLOSED, etc.)
        metadata: Optional strategy-specific data
    """

    strategy_id: str
    symbol: str
    strategy_type: StrategyType
    legs: list[LegSpec]
    entry_time: datetime = field(default_factory=datetime.now)
    status: str = "OPEN"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """
        Validate strategy after initialization.

        Ensures data integrity before strategy is used.
        """
        # Validate symbol is not empty
        if not self.symbol or not self.symbol.strip():
            raise ValueError("Symbol cannot be empty")

        # Validate strategy has at least one leg
        if not self.legs:
            raise ValueError("Strategy must have at least one leg")

        # Validate strategy type
        if not isinstance(self.strategy_type, StrategyType):
            raise ValueError(f"Invalid strategy type: {self.strategy_type}")

    def __repr__(self) -> str:
        """Return string representation of strategy."""
        return (
            f"Strategy(id={self.strategy_id}, type={self.strategy_type.value}, "
            f"symbol={self.symbol}, legs={len(self.legs)})"
        )


@dataclass(slots=True)
class LegExecution:
    """
    Leg execution data model.

    Represents the execution status of a single leg within a strategy.

    Attributes:
        leg_id: Unique identifier for this leg execution
        conid: IB contract ID (once assigned)
        right: Option type (CALL or PUT)
        strike: Strike price
        expiration: Expiration date
        quantity: Number of contracts
        action: BUY or SELL
        status: Execution status (PENDING, FILLED, CANCELLED)
        fill_price: Fill price per share (if filled)
        order_id: IB order ID (if submitted)
        fill_time: When leg was filled (None if pending)
    """

    leg_id: str
    conid: int | None
    right: OptionRight
    strike: float
    expiration: date
    quantity: int
    action: LegAction
    status: LegStatus
    fill_price: float | None = None
    order_id: str | None = None
    fill_time: datetime | None = None

    def __post_init__(self):
        """
        Validate leg execution after initialization.

        Ensures data integrity before execution is tracked.
        """
        # Validate strike is positive
        if self.strike <= 0:
            raise ValueError(f"Strike must be positive, got {self.strike}")

        # Validate quantity is positive
        if self.quantity <= 0:
            raise ValueError(f"Quantity must be positive, got {self.quantity}")

        # If filled, must have fill_price
        if self.status == LegStatus.FILLED and self.fill_price is None:
            raise ValueError("Filled leg must have fill_price")

        # If filled, must have fill_time
        if self.status == LegStatus.FILLED and self.fill_time is None:
            raise ValueError("Filled leg must have fill_time")

    def __repr__(self) -> str:
        """Return string representation of leg execution."""
        return (
            f"LegExecution(id={self.leg_id}, {self.action.value} "
            f"{self.quantity}x {self.right.value} ${self.strike}, "
            f"status={self.status.value})"
        )


@dataclass(slots=True)
class StrategyExecution:
    """
    Strategy execution data model.

    Represents the execution lifecycle of a strategy from entry to exit.

    Attributes:
        execution_id: Unique identifier for this execution (UUID)
        strategy_id: Strategy identifier
        symbol: Underlying symbol
        strategy_type: Type of strategy
        status: Execution status (PENDING, FILLED, PARTIAL, FAILED, CLOSED)
        legs: List of leg executions
        entry_params: Parameters used to build strategy
        entry_time: When strategy was submitted for execution
        fill_time: When strategy was filled (None if pending)
        close_time: When strategy was closed (None if still open)
    """

    execution_id: str
    strategy_id: int
    symbol: str
    strategy_type: StrategyType
    status: ExecutionStatus
    legs: list[LegExecution]
    entry_params: dict[str, Any]
    entry_time: datetime
    fill_time: datetime | None = None
    close_time: datetime | None = None

    def __post_init__(self):
        """
        Validate strategy execution after initialization.

        Ensures data integrity before execution is tracked.
        """
        # Validate execution_id is not empty
        if not self.execution_id or not self.execution_id.strip():
            raise ValueError("Execution ID cannot be empty")

        # Validate symbol is not empty
        if not self.symbol or not self.symbol.strip():
            raise ValueError("Symbol cannot be empty")

        # Validate strategy has at least one leg
        if not self.legs:
            raise ValueError("Strategy execution must have at least one leg")

        # Validate status consistency
        if self.status == ExecutionStatus.FILLED and self.fill_time is None:
            raise ValueError("Filled execution must have fill_time")

        if self.status == ExecutionStatus.CLOSED and self.close_time is None:
            raise ValueError("Closed execution must have close_time")

    def __repr__(self) -> str:
        """Return string representation of strategy execution."""
        return (
            f"StrategyExecution(id={self.execution_id}, type={self.strategy_type.value}, "
            f"symbol={self.symbol}, status={self.status.value}, legs={len(self.legs)})"
        )

    @property
    def is_open(self) -> bool:
        """Check if execution is still open (not closed)."""
        return self.status not in (ExecutionStatus.CLOSED, ExecutionStatus.FAILED)

    @property
    def is_filled(self) -> bool:
        """Check if execution is filled (fully or partially)."""
        return self.status in (ExecutionStatus.FILLED, ExecutionStatus.PARTIAL, ExecutionStatus.CLOSED)
