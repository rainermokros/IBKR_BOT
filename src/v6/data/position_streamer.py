"""
IB Position Streaming Module

This module provides real-time position streaming from Interactive Brokers using
event-driven architecture with ib_async.

Key patterns:
- Dataclass with slots=True for performance (Phase 1-04 pattern)
- Singleton pattern to respect IB's 100-connection limit constraint
- Handler registration for multiple downstream consumers
- Asynchronous handler routing via asyncio.create_task
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(slots=True)
class PositionUpdate:
    """
    Position update from IB streaming.

    This dataclass holds real-time position updates from IB's updatePortfolioEvent.
    Uses slots=True for performance (Phase 1-04 pattern).

    Attributes:
        conid: IB contract ID
        symbol: Underlying symbol (e.g., "SPY")
        right: Option type (CALL or PUT)
        strike: Strike price
        expiry: Expiration date (IB format: YYYYMMDD)
        position: Position size (positive for long, negative for short)
        market_price: Current market price per share
        market_value: Total market value (position * market_price * 100)
        average_cost: Average cost per share
        unrealized_pnl: Unrealized profit/loss
        timestamp: When this update was received
    """
    conid: int
    symbol: str
    right: str  # CALL or PUT
    strike: float
    expiry: str
    position: float  # Positive for long, negative for short
    market_price: float
    market_value: float
    average_cost: float
    unrealized_pnl: float
    timestamp: datetime


@runtime_checkable
class PositionUpdateHandler(Protocol):
    """
    Protocol for position update handlers.

    This protocol enables duck typing with type hints for handler registration.
    Any class with an async on_position_update method can be used as a handler.

    Example:
        ```python
        class MyHandler(PositionUpdateHandler):
            async def on_position_update(self, update: PositionUpdate) -> None:
                print(f"Position update: {update.symbol}")
        ```
    """

    async def on_position_update(self, update: PositionUpdate) -> None:
        """
        Handle position update.

        Args:
            update: Position update from IB streaming
        """
        ...
