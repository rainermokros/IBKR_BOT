"""
Order Execution Models

This module provides data models for order execution through IB API.
Uses dataclasses with slots=True for performance (internal data, validated on entry).

Key patterns:
- dataclass(slots=True) for performance
- __post_init__ validation for data integrity
- Type hints for all fields
- Enum-based status and types

Decision tree:
    Is this data internal to my process?
    ├─ Yes → Use dataclass (performance matters) ← WE ARE HERE
    └─ No → Use Pydantic (validation critical)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class OrderStatus(str, Enum):
    """
    Order status enum.

    Tracks the lifecycle of an order from submission to completion.
    Maps to IB order states.
    """

    PENDING_SUBMIT = "pending_submit"
    SUBMITTED = "submitted"
    FILLED = "filled"
    CANCELLED = "cancelled"
    INACTIVE = "inactive"
    REJECTED = "rejected"


class OrderType(str, Enum):
    """
    Order type enum.

    Types of orders supported by the execution engine.
    """

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
    TRAIL = "TRAIL"
    TRAIL_LIMIT = "TRAIL_LIMIT"


class OrderAction(str, Enum):
    """
    Order action enum.

    Direction of the order.
    """

    BUY = "BUY"
    SELL = "SELL"


class TimeInForce(str, Enum):
    """
    Time in force enum.

    Duration that an order remains active.
    """

    DAY = "DAY"  # Valid for the day
    GTC = "GTC"  # Good Till Cancelled
    IOC = "IOC"  # Immediate Or Cancel
    OPG = "OPG"  # At the Opening


@dataclass(slots=True)
class Order:
    """
    Order data model.

    Represents a single order to be placed through IB API.

    Attributes:
        order_id: Unique identifier for this order (UUID)
        conid: IB contract ID (None until contract is qualified)
        action: BUY or SELL
        quantity: Number of contracts (must be positive)
        order_type: Type of order (MARKET, LIMIT, etc.)
        limit_price: Limit price (for LIMIT, STOP_LIMIT orders)
        stop_price: Stop price (for STOP, STOP_LIMIT, TRAIL orders)
        tif: Time in force (DAY, GTC, IOC, OPG)
        status: Current order status
        filled_quantity: Number of contracts filled
        avg_fill_price: Average fill price (if filled)
        order_ref: IB order object reference (None until placed)
        parent_order_id: Parent order ID (for bracket child orders)
        oca_group: One-Cancels-All group ID
        created_at: When order was created
        filled_at: When order was filled (None if pending)
    """

    order_id: str
    conid: int | None
    action: OrderAction
    quantity: int
    order_type: OrderType
    limit_price: float | None
    stop_price: float | None
    tif: TimeInForce
    status: OrderStatus
    filled_quantity: int
    avg_fill_price: float | None
    order_ref: Any | None  # ib_async.Order reference
    parent_order_id: str | None
    oca_group: str | None
    created_at: datetime
    filled_at: datetime | None

    def __post_init__(self):
        """
        Validate order after initialization.

        Ensures data integrity before order is used.
        """
        # Validate order_id is not empty
        if not self.order_id or not self.order_id.strip():
            raise ValueError("Order ID cannot be empty")

        # Validate quantity is positive
        if self.quantity <= 0:
            raise ValueError(f"Quantity must be positive, got {self.quantity}")

        # Validate filled_quantity is non-negative
        if self.filled_quantity < 0:
            raise ValueError(f"Filled quantity must be non-negative, got {self.filled_quantity}")

        # Validate filled_quantity doesn't exceed quantity
        if self.filled_quantity > self.quantity:
            raise ValueError(
                f"Filled quantity ({self.filled_quantity}) cannot exceed "
                f"quantity ({self.quantity})"
            )

        # Validate limit_price based on order type
        if self.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT):
            if self.limit_price is None:
                raise ValueError(f"{self.order_type.value} orders require limit_price")
            if self.limit_price < 0:
                raise ValueError(f"Limit price must be non-negative, got {self.limit_price}")

        # Validate stop_price based on order type
        if self.order_type in (OrderType.STOP, OrderType.STOP_LIMIT, OrderType.TRAIL):
            if self.stop_price is None:
                raise ValueError(f"{self.order_type.value} orders require stop_price")
            if self.stop_price < 0:
                raise ValueError(f"Stop price must be non-negative, got {self.stop_price}")

        # Validate status consistency
        if self.status == OrderStatus.FILLED:
            if self.filled_quantity != self.quantity:
                raise ValueError(
                    f"Filled order must have filled_quantity == quantity, "
                    f"got {self.filled_quantity} != {self.quantity}"
                )
            if self.filled_at is None:
                raise ValueError("Filled order must have filled_at")

        # Validate parent_order_id has a valid order_id format
        if self.parent_order_id is not None:
            if not self.parent_order_id.strip():
                raise ValueError("Parent order ID cannot be empty string")

    def __repr__(self) -> str:
        """Return string representation of order."""
        return (
            f"Order(id={self.order_id}, {self.action.value} {self.quantity}x "
            f"{self.order_type.value}, status={self.status.value})"
        )


@dataclass(slots=True)
class BracketOrder:
    """
    Bracket order data model.

    Represents a bracket order consisting of:
    - Parent order (entry)
    - Take profit order (optional)
    - Stop loss order (optional)

    All orders are linked via OCA group.

    Attributes:
        parent_order: Entry order
        take_profit: Take profit order (optional)
        stop_loss: Stop loss order (optional)
        oca_group: OCA group ID linking all orders
    """

    parent_order: Order
    take_profit: Order | None
    stop_loss: Order | None
    oca_group: str

    def __post_init__(self):
        """
        Validate bracket order after initialization.

        Ensures data integrity before bracket is used.
        """
        # Validate oca_group is not empty
        if not self.oca_group or not self.oca_group.strip():
            raise ValueError("OCA group cannot be empty")

        # Validate parent order exists
        if self.parent_order is None:
            raise ValueError("Parent order is required")

        # Validate at least one child order exists
        if self.take_profit is None and self.stop_loss is None:
            raise ValueError("Bracket order must have at least take profit or stop loss")

        # Validate parent_order is an Order
        if not isinstance(self.parent_order, Order):
            raise ValueError(f"Parent order must be Order instance, got {type(self.parent_order)}")

        # Validate take_profit is Order or None
        if self.take_profit is not None and not isinstance(self.take_profit, Order):
            raise ValueError(f"Take profit must be Order instance, got {type(self.take_profit)}")

        # Validate stop_loss is Order or None
        if self.stop_loss is not None and not isinstance(self.stop_loss, Order):
            raise ValueError(f"Stop loss must be Order instance, got {type(self.stop_loss)}")

    def __repr__(self) -> str:
        """Return string representation of bracket order."""
        return (
            f"BracketOrder(oca={self.oca_group}, "
            f"parent={self.parent_order.order_id}, "
            f"tp={self.take_profit.order_id if self.take_profit else None}, "
            f"sl={self.stop_loss.order_id if self.stop_loss else None})"
        )


@dataclass(slots=True)
class ExecutionResult:
    """
    Execution result data model.

    Represents the result of an execution operation (close, roll, etc.).

    Attributes:
        success: Whether the operation succeeded
        action_taken: Type of action taken (CLOSED, ROLLED, PARTIAL, FAILED, DRY_RUN)
        order_ids: List of order IDs created by the operation
        error_message: Error message if operation failed
    """

    success: bool
    action_taken: str
    order_ids: list[str]
    error_message: str | None

    def __post_init__(self):
        """
        Validate execution result after initialization.

        Ensures data integrity.
        """
        # Validate action_taken is not empty
        if not self.action_taken or not self.action_taken.strip():
            raise ValueError("Action taken cannot be empty")

        # Validate order_ids is a list
        if not isinstance(self.order_ids, list):
            raise ValueError(f"Order IDs must be a list, got {type(self.order_ids)}")

        # Validate all order_ids are strings
        for order_id in self.order_ids:
            if not isinstance(order_id, str):
                raise ValueError(f"Order ID must be string, got {type(order_id)}")

        # Validate error_message consistency
        if not self.success and not self.error_message:
            raise ValueError("Failed execution must have error_message")

    def __repr__(self) -> str:
        """Return string representation of execution result."""
        return (
            f"ExecutionResult(success={self.success}, action={self.action_taken}, "
            f"orders={len(self.order_ids)})"
        )
