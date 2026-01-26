"""
IB Position Streaming Module (Hybrid: Stream + Queue)

This module provides hybrid position synchronization from Interactive Brokers:
- Active strategy contracts: STREAM (real-time updates via reqMktData)
- Non-essential contracts: QUEUE (batch processing, 0 slots consumed)

Key patterns:
- Hybrid approach: stream active, queue non-essential
- Singleton pattern to respect IB's 100-connection limit
- Handler registration for streamed position updates
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Protocol, runtime_checkable

from loguru import logger
from ib_async import IB

from v6.utils.ib_connection import IBConnectionManager
from v6.data.strategy_registry import StrategyRegistry
from v6.data.position_queue import PositionQueue


@dataclass(slots=True)
class PositionUpdate:
    """Position update from IB streaming."""
    conid: int
    symbol: str
    right: str
    strike: float
    expiry: str
    position: float
    market_price: float
    market_value: float
    average_cost: float
    unrealized_pnl: float
    timestamp: datetime


@runtime_checkable
class PositionUpdateHandler(Protocol):
    """Protocol for position update handlers."""

    async def on_position_update(self, update: PositionUpdate) -> None:
        """Handle position update."""
        ...


class IBPositionStreamer:
    """
    Manages IB position synchronization with hybrid approach.

    **Hybrid Architecture:**
    - Active contracts → STREAM (reqMktData, real-time, consume slots)
    - Non-essential contracts → QUEUE (batch processing, 0 slots)

    **Decision Logic:**
    Checks StrategyRegistry.is_active(conid) to determine stream vs queue.

    **Singleton Pattern:**
    Enforces single IB connection instance to respect 100-connection limit.
    """

    _instance: Optional['IBPositionStreamer'] = None
    _registry: Optional[StrategyRegistry] = None
    _queue: Optional[PositionQueue] = None

    def __new__(cls, registry: Optional[StrategyRegistry] = None, queue: Optional[PositionQueue] = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._registry = registry
            cls._queue = queue
        return cls._instance

    def __init__(
        self,
        registry: Optional[StrategyRegistry] = None,
        queue: Optional[PositionQueue] = None
    ):
        """
        Initialize streamer.

        Args:
            registry: StrategyRegistry for checking active contracts
            queue: PositionQueue for queuing non-essential contracts
        """
        # Only initialize once
        if hasattr(self, '_initialized'):
            return

        self._connection = None
        self._handlers: List[PositionUpdateHandler] = []
        self._registry = registry or StrategyRegistry()
        self._queue = queue or PositionQueue()
        self._is_running = False
        self._streamed_contracts: set[int] = set()  # Track actively streamed contracts
        self._initialized = True

    def register_handler(self, handler: PositionUpdateHandler) -> None:
        """
        Register a handler to receive position updates.

        Handlers are called ONLY for streamed positions (active contracts).
        Queued positions are processed by QueueWorker (no handler notification).

        Args:
            handler: Handler to register
        """
        if handler not in self._handlers:
            self._handlers.append(handler)
            logger.debug(f"Registered handler: {handler.__class__.__name__}")

    async def start(self) -> None:
        """
        Start hybrid position synchronization.

        1. Initialize registry and queue
        2. Get IB connection
        3. Fetch all positions via reqPositionsAsync()
        4. For each position: stream if active, queue if not
        5. Subscribe to updatePortfolioEvent for streamed contracts
        """
        if self._is_running:
            logger.warning("IBPositionStreamer already running")
            return

        logger.info("Starting hybrid position synchronization...")

        # Initialize registry and queue
        await self._registry.initialize()
        await self._queue.initialize()

        # Get IB connection
        from v6.utils.ib_connection import IBConnectionManager
        conn_manager = IBConnectionManager()
        await conn_manager.connect()
        self._connection = conn_manager

        if not self._connection or not self._connection.is_connected:
            raise ConnectionError("IB not connected")

        ib = self._connection.ib

        # Fetch all positions
        positions = await ib.reqPositionsAsync()
        logger.info(f"Fetched {len(positions)} positions from IB")

        # Hybrid routing: stream active, queue non-essential
        streamed_count = 0
        queued_count = 0

        for item in positions:
            # Only process option positions with non-zero quantity
            if not hasattr(item.contract, 'secType') or item.contract.secType != 'OPT':
                continue

            if item.position == 0:
                continue

            conid = item.contract.conId
            symbol = item.contract.symbol

            # Check if contract is in active strategy
            if self._registry.is_active(conid):
                # STREAM: Subscribe to market data for real-time updates
                await self._stream_contract(conid, item.contract)
                streamed_count += 1
            else:
                # QUEUE: Insert into queue for batch processing
                await self._queue.insert(conid=conid, symbol=symbol, priority=2)
                queued_count += 1

        # Subscribe to portfolio updates for streamed contracts
        ib.updatePortfolioEvent += self._on_position_update

        self._is_running = True

        logger.info(
            f"✓ Started hybrid position sync: "
            f"{streamed_count} streamed (active), "
            f"{queued_count} queued (non-essential)"
        )

    async def stop(self) -> None:
        """Stop hybrid position synchronization."""
        if not self._is_running:
            return

        self._is_running = False

        if self._connection and self._connection.is_connected:
            # Unsubscribe from portfolio updates
            ib = self._connection.ib
            ib.updatePortfolioEvent -= self._on_position_update

            # Cancel market data subscriptions
            for conid in self._streamed_contracts:
                try:
                    ib.cancelMktData(conid)
                except Exception as e:
                    logger.warning(f"Failed to cancel market data for {conid}: {e}")

            self._streamed_contracts.clear()

        logger.info("✓ Stopped hybrid position synchronization")

    async def _stream_contract(self, conid: int, contract) -> None:
        """
        Stream market data for active contract.

        Args:
            conid: IB contract ID
            contract: IB Contract object
        """
        try:
            ib = self._connection.ib

            # Subscribe to market data (snapshot=False for streaming)
            ib.reqMktData(
                contract,
                "",  # genericTickList (empty for basic data)
                "",  # snapshot (False = streaming)
                False  # snapshot
            )

            self._streamed_contracts.add(conid)
            logger.debug(f"✓ Streaming contract {conid} ({contract.symbol})")

        except Exception as e:
            logger.error(f"Failed to stream contract {conid}: {e}")

    async def _on_position_update(self, item) -> None:
        """
        Handle portfolio update event (streamed contracts only).

        Called by IB when position changes for streamed contracts.
        Creates PositionUpdate and notifies all handlers.

        Args:
            item: IB PortfolioItem object
        """
        try:
            # Only process option positions
            if not hasattr(item.contract, 'secType') or item.contract.secType != 'OPT':
                return

            if item.position == 0:
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

            # Notify all handlers asynchronously
            for handler in self._handlers:
                asyncio.create_task(handler.on_position_update(update))

        except Exception as e:
            logger.error(f"Error handling position update: {e}")

    @property
    def is_streaming(self) -> bool:
        """
        Check if hybrid sync is active.

        Returns:
            True if streaming is active and connection is healthy
        """
        return (
            self._is_running and
            self._connection is not None and
            self._connection.is_connected
        )
