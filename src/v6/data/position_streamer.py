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

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Protocol, runtime_checkable

from loguru import logger

from v6.utils.ib_connection import IBConnectionManager


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


class IBPositionStreamer:
    """
    Manages IB position streaming with single connection constraint.

    CRITICAL: Uses ONE persistent IB connection for ALL streaming.
    Singleton pattern - do not create multiple instances.

    **100-Connection Limit Constraint:**
    IB streaming has a connection limit. This class enforces singleton pattern
    to ensure only ONE connection is used for all position streaming.

    Example:
        ```python
        # Get singleton instance
        streamer = IBPositionStreamer()

        # Register handler
        handler = MyHandler()
        streamer.register_handler(handler)

        # Start streaming
        await streamer.start()
        ```
    """

    _instance: Optional['IBPositionStreamer'] = None

    def __new__(cls):
        """Enforce singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize singleton instance (only once)."""
        # Only initialize once
        if hasattr(self, '_initialized'):
            return

        self._connection: Optional[IBConnectionManager] = None
        self._handlers: List[PositionUpdateHandler] = []
        self._is_streaming = False
        self._initialized = True

    async def start(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 1
    ) -> None:
        """
        Start streaming - creates ONE persistent connection.

        Args:
            host: IB gateway/TWS host
            port: IB gateway/TWS port (7497 for paper trading, 7496 for production)
            client_id: Unique client ID for this connection
        """
        if self._is_streaming:
            logger.warning("Already streaming, ignoring start request")
            return

        # Create single connection
        self._connection = IBConnectionManager(
            host=host,
            port=port,
            client_id=client_id
        )

        await self._connection.connect()
        await self._connection.start_heartbeat()

        # Register single event handler that routes to all listeners
        @self._connection.ib.updatePortfolioEvent
        def _on_portfolio_update(item):
            self._handle_portfolio_update(item)

        self._is_streaming = True
        logger.info("✓ IB Position Streaming started (singleton)")

    def _handle_portfolio_update(self, item) -> None:
        """
        Route portfolio update to all registered handlers.

        Args:
            item: Portfolio update item from IB
        """
        try:
            # Only process option positions
            if not hasattr(item.contract, 'secType') or item.contract.secType != 'OPT':
                return

            # Create PositionUpdate
            update = PositionUpdate(
                conid=item.contract.conId,
                symbol=item.contract.symbol,
                right=item.contract.right,
                strike=item.contract.strike,
                expiry=item.contract.lastTradeDateOrContractMonth,
                position=item.position,
                market_price=item.marketPrice,
                market_value=item.marketValue,
                average_cost=item.averageCost,
                unrealized_pnl=item.unrealizedPNL,
                timestamp=datetime.now()
            )

            # Route to ALL registered handlers (asynchronous)
            for handler in self._handlers:
                asyncio.create_task(handler.on_position_update(update))

        except Exception as e:
            logger.error(f"Error in portfolio update handler: {e}")

    def register_handler(self, handler: PositionUpdateHandler) -> None:
        """
        Register a handler to receive position updates.

        Args:
            handler: Handler instance implementing PositionUpdateHandler protocol
        """
        if handler not in self._handlers:
            self._handlers.append(handler)
            logger.info(f"Registered handler: {handler.__class__.__name__}")

    def unregister_handler(self, handler: PositionUpdateHandler) -> None:
        """
        Unregister a handler.

        Args:
            handler: Handler instance to remove
        """
        if handler in self._handlers:
            self._handlers.remove(handler)
            logger.info(f"Unregistered handler: {handler.__class__.__name__}")

    async def stop(self) -> None:
        """Stop streaming - stops the single persistent connection."""
        if not self._is_streaming:
            return

        self._is_streaming = False

        if self._connection:
            await self._connection.stop_heartbeat()
            await self._connection.disconnect()

        logger.info("✓ IB Position Streaming stopped")

    @property
    def is_streaming(self) -> bool:
        """
        Check if streaming is active.

        Returns:
            True if streaming is active and connection is healthy
        """
        return (
            self._is_streaming and
            self._connection is not None and
            self._connection.is_connected
        )
