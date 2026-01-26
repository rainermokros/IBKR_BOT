---
phase: 2-position-synchronization
plan: 01
type: execute
depends_on: []
files_modified: [src/v6/data/position_streamer.py, src/v6/data/__init__.py]
domain: ib-async-api
---

<objective>
Implement real-time IB position streaming with singleton pattern to respect the 100-connection limit.

**Purpose:** Establish reliable real-time position updates from Interactive Brokers using event-driven architecture while respecting IB's connection limit constraint.

**Output:** Working IBPositionStreamer class that streams position updates in real-time with proper connection lifecycle management.

**Key Constraint:** IB has a 100-connection limit for streaming. Use singleton pattern with a single persistent connection shared by all position streaming consumers via handler registration.
</objective>

<execution_context>
~/.claude/get-shit-done/workflows/execute-plan.md
~/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/phases/1-architecture-infrastructure/1-04-SUMMARY.md
@.planning/phases/1-architecture-infrastructure/1-02-SUMMARY.md
@.planning/phases/2-position-synchronization/2-RESEARCH.md
@src/v6/models/ib_models.py
@src/v6/utils/ib_connection.py

**Tech stack available:**
- ib_async (for IB event streaming)
- Pydantic models (OptionLeg, Greeks, etc.)
- IBConnectionManager with circuit breaker and heartbeat
- Delta Lake tables (positions/, legs/, etc.)

**Established patterns:**
- Circuit breaker pattern for connection resilience
- Exponential backoff retry
- Heartbeat monitoring for connection health
- Repository pattern for data access

**Constraining decisions:**
- **Pydantic for external data validation** (Phase 1-04)
- **Dataclasses for internal state** (Phase 1-04)
- **Partition by symbol in Delta Lake** (Phase 1-02)
- **Singleton pattern required** for IB connection (100-connection limit constraint)
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create PositionUpdate dataclass and handler protocol</name>
  <files>src/v6/data/position_streamer.py</files>
  <action>
    Create PositionUpdate dataclass and PositionUpdateHandler protocol in `src/v6/data/position_streamer.py`:

    ```python
    from dataclasses import dataclass
    from datetime import datetime
    from typing import Protocol, runtime_checkable

    @dataclass(slots=True)
    class PositionUpdate:
        """Position update from IB streaming."""
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
        """Protocol for position update handlers."""

        async def on_position_update(self, update: PositionUpdate) -> None:
            """Handle position update."""
            ...
    ```

    **CRITICAL:** Use dataclass with slots=True for performance (Phase 1-04 pattern). Use runtime_checkable Protocol for handler registration to enable duck typing.
  </action>
  <verify>
    Run `python -m py_compile src/v6/data/position_streamer.py` - should compile without errors
  </verify>
  <done>
    - PositionUpdate dataclass created with all required fields
    - PositionUpdateHandler protocol defined for type checking
    - File compiles without syntax errors
  </done>
</task>

<task type="auto">
  <name>Task 2: Create IBPositionStreamer singleton class</name>
  <files>src/v6/data/position_streamer.py</files>
  <action>
    Create IBPositionStreamer class with singleton pattern in `src/v6/data/position_streamer.py`:

    ```python
    from typing import List, Optional
    from loguru import logger
    from ib_async import IB
    from v6.utils.ib_connection import IBConnectionManager

    class IBPositionStreamer:
        """
        Manages IB position streaming with single connection constraint.

        CRITICAL: Uses ONE persistent IB connection for ALL streaming.
        Singleton pattern - do not create multiple instances.

        **100-Connection Limit Constraint:**
        IB streaming has a connection limit. This class enforces singleton pattern
        to ensure only ONE connection is used for all position streaming.
        """

        _instance: Optional['IBPositionStreamer'] = None

        def __new__(cls):
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

        def __init__(self):
            # Only initialize once
            if hasattr(self, '_initialized'):
                return

            self._connection: Optional[IBConnectionManager] = None
            self._handlers: List[PositionUpdateHandler] = []
            self._is_streaming = False
            self._initialized = True

        async def start(self, host: str = "127.0.0.1", port: int = 7497, client_id: int = 1) -> None:
            """Start streaming - creates ONE persistent connection."""
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
            """Route portfolio update to all registered handlers."""
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
                import asyncio
                for handler in self._handlers:
                    asyncio.create_task(handler.on_position_update(update))

            except Exception as e:
                logger.error(f"Error in portfolio update handler: {e}")

        def register_handler(self, handler: PositionUpdateHandler) -> None:
            """Register a handler to receive position updates."""
            if handler not in self._handlers:
                self._handlers.append(handler)
                logger.info(f"Registered handler: {handler.__class__.__name__}")

        def unregister_handler(self, handler: PositionUpdateHandler) -> None:
            """Unregister a handler."""
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
            """Check if streaming is active."""
            return self._is_streaming and self._connection is not None and self._connection.is_connected
    ```

    **CRITICAL:**
    - Singleton pattern via `__new__` ensures only ONE instance exists
    - ONE persistent IB connection for ALL streaming
    - Handler registration pattern allows multiple downstream consumers without multiple connections
    - Start once, stop once - don't reconnect during normal operation
    - This respects the 100-connection limit constraint
  </action>
  <verify>
    Run `python -m py_compile src/v6/data/position_streamer.py` - should compile without errors
    Check that singleton pattern works: "Verify IBPositionStreamer() is IBPositionStreamer() returns True"
  </verify>
  <done>
    - IBPositionStreamer implements singleton pattern
    - Single persistent connection for all streaming
    - Handler registration allows multiple consumers
    - Start/stop lifecycle manages connection properly
    - Code compiles without errors
  </done>
</task>

<task type="auto">
  <name>Task 3: Create data package init file</name>
  <files>src/v6/data/__init__.py</files>
  <action>
    Create `src/v6/data/__init__.py` to export position streaming components:

    ```python
    from v6.data.position_streamer import (
        PositionUpdate,
        PositionUpdateHandler,
        IBPositionStreamer,
    )

    __all__ = [
        "PositionUpdate",
        "PositionUpdateHandler",
        "IBPositionStreamer",
    ]
    ```

    This enables clean imports: `from v6.data import IBPositionStreamer, PositionUpdate`
  </action>
  <verify>
    Run `python -c "from v6.data import IBPositionStreamer, PositionUpdate; print('✓ Imports work')"`
  </verify>
  <done>
    - __init__.py created with proper exports
    - Imports work without errors
    - All components accessible from v6.data package
  </done>
</task>

<task type="auto">
  <name>Task 4: Create integration test script</name>
  <files>src/v6/data/test_position_streamer.py</files>
  <action>
    Create integration test script `src/v6/data/test_position_streamer.py` to verify the streaming works:

    ```python
    import asyncio
    from loguru import logger
    from v6.data import IBPositionStreamer, PositionUpdate, PositionUpdateHandler

    class TestHandler(PositionUpdateHandler):
        """Test handler that logs position updates."""

        async def on_position_update(self, update: PositionUpdate) -> None:
            logger.info(f"Position update: {update.symbol} {update.right} {update.strike} - Pos: {update.position}")

    async def main():
        """Test position streaming."""
        logger.info("Starting position streaming test...")

        # Get singleton instance
        streamer = IBPositionStreamer()

        # Register test handler
        handler = TestHandler()
        streamer.register_handler(handler)

        # Start streaming (requires IB Gateway/TWS running)
        try:
            await streamer.start()

            # Stream for 30 seconds
            logger.info("Streaming for 30 seconds...")
            await asyncio.sleep(30)

            # Stop streaming
            await streamer.stop()

            logger.info("✓ Test complete - position streaming works")

        except Exception as e:
            logger.error(f"Test failed: {e}")
            logger.info("Note: This test requires IB Gateway/TWS to be running")

    if __name__ == "__main__":
        asyncio.run(main())
    ```

    **Note:** This requires IB Gateway/TWS to be running. It's an integration test, not a unit test.
  </action>
  <verify>
    Run `python -m py_compile src/v6/data/test_position_streamer.py` - should compile
    Script should exist and be runnable (but may fail if IB not running - that's OK)
  </verify>
  <done>
    - Integration test script created
    - Script compiles without errors
    - Test demonstrates singleton pattern and handler registration
    - Includes clear error message if IB not running
  </done>
</task>

</tasks>

<verification>
Before declaring plan complete:
- [ ] `python -m py_compile src/v6/data/position_streamer.py` succeeds without errors
- [ ] `python -c "from v6.data import IBPositionStreamer; s1 = IBPositionStreamer(); s2 = IBPositionStreamer(); assert s1 is s2"` - singleton verification
- [ ] All files compile without syntax errors
- [ ] ruff linter passes with no errors
- [ ] Integration test script is runnable
</verification>

<success_criteria>

- PositionUpdate dataclass created with all IB position fields
- PositionUpdateHandler protocol defined for type checking
- IBPositionStreamer implements singleton pattern correctly
- Single persistent connection shared by all handlers
- Handler registration enables multiple downstream consumers
- Integration test script demonstrates functionality
- All verification checks pass
- No errors or warnings introduced

</success_criteria>

<output>
After completion, create `.planning/phases/2-position-synchronization/2-01-SUMMARY.md`:

# Phase 2 Plan 1: IB Position Streaming Summary

**Implemented real-time IB position streaming with singleton pattern respecting 100-connection limit.**

## Accomplishments

- Created PositionUpdate dataclass for streaming position data
- Created PositionUpdateHandler protocol for type-safe handler registration
- Implemented IBPositionStreamer singleton class with single persistent connection
- Handler registration pattern enables multiple consumers without multiple connections
- Integration test script demonstrates functionality

## Files Created/Modified

- `src/v6/data/position_streamer.py` - IBPositionStreamer singleton with handler registration
- `src/v6/data/__init__.py` - Data package exports
- `src/v6/data/test_position_streamer.py` - Integration test script

## Decisions Made

- **Singleton pattern**: Enforces single IB connection instance to respect 100-connection limit
- **Handler registration**: Multiple downstream consumers share one connection via callback registration
- **Dataclass with slots**: PositionUpdate uses dataclass for performance (follows Phase 1-04 pattern)
- **Protocol for handlers**: runtime_checkable Protocol enables duck typing with type hints
- **Persistent connection**: Start once, stop once - don't reconnect during normal operation
- **Asynchronous handler routing**: All handlers called asynchronously via asyncio.create_task

## Issues Encountered

None

## Next Step

Ready for 02-02-PLAN.md (Delta Lake Persistence)

The position streaming foundation is in place with:
- Singleton pattern respecting 100-connection limit
- Handler registration for multiple consumers
- Real-time position updates from IB via updatePortfolioEvent

Ready to build Delta Lake persistence layer that receives updates via handler registration.
</output>
