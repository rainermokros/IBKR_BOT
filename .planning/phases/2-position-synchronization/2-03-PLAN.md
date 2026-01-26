---
phase: 2-position-synchronization
plan: 03
type: execute
depends_on: ["02-01", "02-02"]
files_modified: [src/v6/data/reconciliation.py]
domain: position-manager
---

<objective>
Implement reconciliation logic to validate consistency between IB positions and Delta Lake state.

**Purpose:** Ensure data consistency between live IB positions and persisted Delta Lake state through hybrid reconciliation (real-time event-driven + periodic full sync).

**Output:** Working PositionReconciler that detects discrepancies, logs issues, and provides metrics for monitoring.

**Key Pattern:** Combine real-time event-driven updates (from streaming) with periodic full reconciliation (every 5 minutes) using `reqPositionsAsync()` to catch missed events or inconsistencies.
</objective>

<execution_context>
~/.claude/get-shit-done/workflows/execute-plan.md
~/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/phases/2-position-synchronization/2-01-SUMMARY.md
@.planning/phases/2-position-synchronization/2-02-SUMMARY.md
@.planning/phases/2-position-synchronization/2-RESEARCH.md
@src/v6/data/position_streamer.py
@src/v6/data/delta_persistence.py
@src/v6/utils/ib_connection.py

**Tech stack available:**
- IBPositionStreamer (real-time streaming with handler registration)
- DeltaLakePositionWriter (persists updates to Delta Lake)
- PositionUpdatesTable (Delta Lake table with position data)
- IBConnectionManager (IB connection management)
- Polars (data manipulation)

**Established patterns:**
- Singleton pattern for IB connection (100-connection limit)
- Handler registration for event streaming
- Batch writes to Delta Lake
- Last-Write-Wins conflict resolution

**Constraining decisions:**
- **Singleton IB connection** (Phase 2-01) - must use shared connection
- **Symbol partitioning** (Phase 1-02, Phase 2-02) - for query performance
- **Batch writes** (Phase 2-02) - avoid small files problem
- **Handler registration** (Phase 2-01) - receive updates via PositionUpdateHandler

</context>

<tasks>

<task type="auto">
  <name>Task 1: Create discrepancy types and result models</name>
  <files>src/v6/data/reconciliation.py</files>
  <action>
    Create discrepancy types and result models in `src/v6/data/reconciliation.py`:

    ```python
    from dataclasses import dataclass, field
    from typing import List, Literal
    from enum import Enum
    from datetime import datetime

    class DiscrepancyType(str, Enum):
        """Types of reconciliation discrepancies."""

        MISSING_FROM_DELTA = "MISSING_FROM_DELTA"  # Position in IB but not Delta Lake
        NAKED_POSITION = "NAKED_POSITION"          # Position in Delta Lake but missing from IB (CRITICAL)
        POSITION_MISMATCH = "POSITION_MISMATCH"    # Position quantity differs
        STALE_DATA = "STALE_DATA"                  # Delta Lake data too old

    @dataclass(slots=True)
    class Discrepancy:
        """A discrepancy found during reconciliation."""

        type: DiscrepancyType
        conid: int
        symbol: str
        details: str
        ib_position: float = 0.0
        delta_position: float = 0.0
        timestamp: datetime = field(default_factory=datetime.now)

    @dataclass(slots=True)
    class ReconciliationResult:
        """Result of a reconciliation run."""

        ib_count: int
        delta_count: int
        discrepancies: List[Discrepancy]
        timestamp: datetime = field(default_factory=datetime.now)
        duration_seconds: float = 0.0

        @property
        def has_critical_issues(self) -> bool:
            """Check if there are critical discrepancies (NAKED_POSITION)."""
            return any(d.type == DiscrepancyType.NAKED_POSITION for d in self.discrepancies)

        @property
        def discrepancy_count(self) -> int:
            """Total number of discrepancies."""
            return len(self.discrepancies)

        def summary(self) -> str:
            """Get human-readable summary."""
            critical_count = sum(1 for d in self.discrepancies if d.type == DiscrepancyType.NAKED_POSITION)
            return (
                f"IB: {self.ib_count}, Delta: {self.delta_count}, "
                f"Discrepancies: {self.discrepancy_count} ({critical_count} critical)"
            )
    ```

    **CRITICAL:** Use dataclass with slots=True for performance (follows Phase 1-04 pattern). Define clear discrepancy types for different failure modes.
  </action>
  <verify>
    Run `python -m py_compile src/v6/data/reconciliation.py` - should compile without errors
  </verify>
  <done>
    - DiscrepancyType enum created with 4 types
    - Discrepancy dataclass created with all relevant fields
    - ReconciliationResult dataclass created with summary methods
    - File compiles without errors
  </done>
</task>

<task type="auto">
  <name>Task 2: Implement PositionReconciler class</name>
  <files>src/v6/data/reconciliation.py</files>
  <action>
    Create PositionReconciler class in `src/v6/data/reconciliation.py`:

    ```python
    import asyncio
    from loguru import logger
    import polars as pl
    from deltalake import DeltaTable
    from ib_async import IB
    from v6.data.position_streamer import IBPositionStreamer

    class PositionReconciler:
        """
        Reconcile IB positions with Delta Lake state.

        Fetches full position snapshot from IB and compares with Delta Lake
        to detect discrepancies. Handles the hybrid approach: real-time
        streaming + periodic full reconciliation.
        """

        def __init__(
            self,
            streamer: IBPositionStreamer,
            delta_table_path: str = "data/lake/position_updates"
        ):
            """
            Initialize reconciler.

            Args:
                streamer: IBPositionStreamer singleton (for IB connection)
                delta_table_path: Path to Delta Lake position_updates table
            """
            self.streamer = streamer
            self.delta_table_path = delta_table_path

        async def reconcile(self) -> ReconciliationResult:
            """
            Run full reconciliation between IB and Delta Lake.

            Returns:
                ReconciliationResult with all discrepancies found
            """
            start_time = datetime.now()

            # Fetch all positions from IB (full snapshot)
            ib_positions = await self._fetch_ib_positions_full()

            # Fetch latest state from Delta Lake
            delta_positions = await self._fetch_delta_positions()

            # Build maps for comparison
            ib_map = {p['conid']: p for p in ib_positions}
            delta_map = {p['conid']: p for p in delta_positions}

            # Find discrepancies
            discrepancies = []

            # Check for MISSING_FROM_DELTA (in IB but not Delta Lake)
            for conid, ib_pos in ib_map.items():
                if conid not in delta_map:
                    discrepancies.append(Discrepancy(
                        type=DiscrepancyType.MISSING_FROM_DELTA,
                        conid=conid,
                        symbol=ib_pos['symbol'],
                        details=f"Position {ib_pos['position']} in IB but missing from Delta Lake",
                        ib_position=ib_pos['position'],
                        delta_position=0.0
                    ))

            # Check for NAKED_POSITION (in Delta Lake but not IB - CRITICAL)
            for conid, delta_pos in delta_map.items():
                if conid not in ib_map:
                    discrepancies.append(Discrepancy(
                        type=DiscrepancyType.NAKED_POSITION,
                        conid=conid,
                        symbol=delta_pos['symbol'],
                        details=f"Position {delta_pos['position']} in Delta Lake but missing from IB (CRITICAL)",
                        ib_position=0.0,
                        delta_position=delta_pos['position']
                    ))

            # Check for POSITION_MISMATCH (quantity differs)
            common_conids = set(ib_map.keys()) & set(delta_map.keys())
            for conid in common_conids:
                ib_pos = ib_map[conid]
                delta_pos = delta_map[conid]

                if abs(ib_pos['position'] - delta_pos['position']) > 0.001:  # Float tolerance
                    discrepancies.append(Discrepancy(
                        type=DiscrepancyType.POSITION_MISMATCH,
                        conid=conid,
                        symbol=ib_pos['symbol'],
                        details=f"Position differs: IB={ib_pos['position']}, Delta={delta_pos['position']}",
                        ib_position=ib_pos['position'],
                        delta_position=delta_pos['position']
                    ))

            # Calculate duration
            duration = (datetime.now() - start_time).total_seconds()

            result = ReconciliationResult(
                ib_count=len(ib_positions),
                delta_count=len(delta_positions),
                discrepancies=discrepancies,
                duration_seconds=duration
            )

            # Log results
            if result.has_critical_issues:
                logger.error(f"Reconciliation found CRITICAL issues: {result.summary()}")
            elif result.discrepancy_count > 0:
                logger.warning(f"Reconciliation found discrepancies: {result.summary()}")
            else:
                logger.info(f"Reconciliation passed: {result.summary()}")

            return result

        async def _fetch_ib_positions_full(self) -> List[dict]:
            """
            Fetch all positions from IB using reqPositionsAsync.

            Returns:
                List of position dictionaries
            """
            if not self.streamer._connection or not self.streamer._connection.is_connected:
                logger.error("IB not connected, cannot fetch positions")
                return []

            ib = self.streamer._connection.ib
            positions = await ib.reqPositionsAsync()

            result = []
            for item in positions:
                # Only include option positions with non-zero quantity
                if not hasattr(item.contract, 'secType') or item.contract.secType != 'OPT':
                    continue

                if item.position == 0:
                    continue

                result.append({
                    'conid': item.contract.conId,
                    'symbol': item.contract.symbol,
                    'right': item.contract.right,
                    'strike': item.contract.strike,
                    'expiry': item.contract.lastTradeDateOrContractMonth,
                    'position': item.position,
                })

            logger.debug(f"Fetched {len(result)} positions from IB")
            return result

        async def _fetch_delta_positions(self) -> List[dict]:
            """
            Fetch latest positions from Delta Lake.

            Returns:
                List of position dictionaries (latest per conid)
            """
            if not DeltaTable.is_deltatable(self.delta_table_path):
                logger.warning(f"Delta Lake table not found: {self.delta_table_path}")
                return []

            dt = DeltaTable(self.delta_table_path)
            df = dt.to_pandas()
            df = pl.from_pandas(df)

            # Get latest position per conid (sort by timestamp desc, take first)
            latest = df.sort('timestamp', descending=True).unique(subset=['conid'], keep='first')

            result = []
            for row in latest.to_dicts():
                result.append({
                    'conid': row['conid'],
                    'symbol': row['symbol'],
                    'right': row['right'],
                    'strike': row['strike'],
                    'expiry': row['expiry'],
                    'position': row['position'],
                })

            logger.debug(f"Fetched {len(result)} positions from Delta Lake")
            return result
    ```

    **CRITICAL:**
    - Uses IBPositionStreamer singleton's IB connection (respects 100-connection limit)
    - Fetches full snapshot from IB using `reqPositionsAsync()`
    - Gets latest per-conid from Delta Lake using timestamp ordering
    - Detects 3 discrepancy types: MISSING_FROM_DELTA, NAKED_POSITION, POSITION_MISMATCH
    - NAKED_POSITION is critical (data exists but position missing in IB)
  </action>
  <verify>
    Run `python -m py_compile src/v6/data/reconciliation.py` - should compile without errors
  </verify>
  <done>
    - PositionReconciler class created
    - Fetches full IB position snapshot via reqPositionsAsync
    - Fetches latest Delta Lake state per conid
    - Detects all 3 discrepancy types
    - Returns ReconciliationResult with summary
    - Code compiles without errors
  </done>
</task>

<task type="auto">
  <name>Task 3: Implement ReconciliationService for periodic reconciliation</name>
  <files>src/v6/data/reconciliation.py</files>
  <action>
    Create ReconciliationService class in `src/v6/data/reconciliation.py`:

    ```python
    class ReconciliationService:
        """
        Run periodic reconciliation between IB and Delta Lake.

        Implements the hybrid approach: real-time streaming (event-driven)
        + periodic full reconciliation (every 5 minutes by default).
        """

        def __init__(
            self,
            reconciler: PositionReconciler,
            interval: int = 300  # 5 minutes
        ):
            """
            Initialize service.

            Args:
                reconciler: PositionReconciler instance
                interval: Seconds between reconciliations (default: 300s = 5min)
            """
            self.reconciler = reconciler
            self.interval = interval
            self._task: asyncio.Task = None
            self._is_running = False

        async def start(self) -> None:
            """Start periodic reconciliation."""
            if self._is_running:
                logger.warning("Reconciliation service already running")
                return

            self._is_running = True
            self._task = asyncio.create_task(self._reconcile_loop())
            logger.info(f"✓ Started reconciliation service (interval: {self.interval}s)")

        async def stop(self) -> None:
            """Stop periodic reconciliation."""
            self._is_running = False

            if self._task and not self._task.done():
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

            logger.info("✓ Stopped reconciliation service")

        async def _reconcile_loop(self) -> None:
            """Periodic reconciliation loop."""
            while self._is_running:
                try:
                    await asyncio.sleep(self.interval)

                    if self._is_running:
                        result = await self.reconciler.reconcile()

                        # Alert on critical issues
                        if result.has_critical_issues:
                            logger.error(f"🚨 CRITICAL: {result.summary()}")
                            # TODO: Send alert notification (Phase 3)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Reconciliation error: {e}", exc_info=True)

        async def reconcile_now(self) -> ReconciliationResult:
            """Trigger immediate reconciliation (outside periodic schedule)."""
            return await self.reconciler.reconcile()
    ```

    **CRITICAL:**
    - Runs periodic reconciliation every 5 minutes (300 seconds)
    - Hybrid approach: real-time streaming + periodic full sync
    - Logs warnings for discrepancies, errors for critical issues
    - Can trigger immediate reconciliation via `reconcile_now()`
  </action>
  <verify>
    Run `python -m py_compile src/v6/data/reconciliation.py` - should compile without errors
  </verify>
  <done>
    - ReconciliationService class created
    - Runs periodic reconciliation every 5 minutes
    - Logs discrepancies and critical issues
    - Supports immediate reconciliation on-demand
    - Code compiles without errors
  </done>
</task>

<task type="auto">
  <name>Task 4: Create integration test script</name>
  <files>src/v6/data/test_reconciliation.py</files>
  <action>
    Create integration test script `src/v6/data/test_reconciliation.py` to verify reconciliation works:

    ```python
    import asyncio
    from loguru import logger
    from v6.data.reconciliation import PositionReconciler, ReconciliationService
    from v6.data.position_streamer import IBPositionStreamer

    async def main():
        """Test reconciliation."""
        logger.info("Starting reconciliation test...")

        # Get singleton streamer
        streamer = IBPositionStreamer()

        # Create reconciler
        reconciler = PositionReconciler(streamer)

        # Start IB connection (required for reconciliation)
        try:
            await streamer.start()
            logger.info("✓ IB connection established")

            # Run reconciliation
            result = await reconciler.reconcile()

            # Log results
            logger.info(f"Reconciliation complete:")
            logger.info(f"  IB positions: {result.ib_count}")
            logger.info(f"  Delta positions: {result.delta_count}")
            logger.info(f"  Discrepancies: {result.discrepancy_count}")
            logger.info(f"  Critical issues: {1 if result.has_critical_issues else 0}")
            logger.info(f"  Duration: {result.duration_seconds:.2f}s")

            # Log individual discrepancies
            for d in result.discrepancies:
                logger.warning(f"  [{d.type.value}] {d.symbol} ({d.conid}): {d.details}")

            # Test periodic service
            service = ReconciliationService(reconciler, interval=10)
            await service.start()
            logger.info("✓ Started periodic reconciliation (10s interval)")

            # Wait for one cycle
            await asyncio.sleep(12)

            # Stop service
            await service.stop()
            logger.info("✓ Stopped periodic reconciliation")

            # Stop streamer
            await streamer.stop()

            logger.info("✓ Test complete")

        except Exception as e:
            logger.error(f"Test failed: {e}")
            logger.info("Note: This test requires IB Gateway/TWS to be running")

    if __name__ == "__main__":
        asyncio.run(main())
    ```

    **Note:** This requires IB Gateway/TWS to be running.
  </action>
  <verify>
    Run `python -m py_compile src/v6/data/test_reconciliation.py` - should compile
    Script should exist and be runnable (but may fail if IB not running)
  </verify>
  <done>
    - Integration test script created
    - Tests PositionReconciler with real IB connection
    - Tests ReconciliationService periodic reconciliation
    - Logs all discrepancies found
    - Includes clear error message if IB not running
  </done>
</task>

<task type="auto">
  <name>Task 5: Create data package exports</name>
  <files>src/v6/data/__init__.py</files>
  <action>
    Update `src/v6/data/__init__.py` to export reconciliation components:

    ```python
    from v6.data.position_streamer import (
        PositionUpdate,
        PositionUpdateHandler,
        IBPositionStreamer,
    )
    from v6.data.delta_persistence import (
        PositionUpdatesTable,
        DeltaLakePositionWriter,
    )
    from v6.data.reconciliation import (
        DiscrepancyType,
        Discrepancy,
        ReconciliationResult,
        PositionReconciler,
        ReconciliationService,
    )

    __all__ = [
        # Position streaming
        "PositionUpdate",
        "PositionUpdateHandler",
        "IBPositionStreamer",
        # Delta Lake persistence
        "PositionUpdatesTable",
        "DeltaLakePositionWriter",
        # Reconciliation
        "DiscrepancyType",
        "Discrepancy",
        "ReconciliationResult",
        "PositionReconciler",
        "ReconciliationService",
    ]
    ```

    This enables clean imports: `from v6.data import IBPositionStreamer, PositionReconciler, ReconciliationService`
  </action>
  <verify>
    Run `python -c "from v6.data import PositionReconciler, ReconciliationService; print('✓ Imports work')"`
  </verify>
  <done>
    - __init__.py updated with reconciliation exports
    - All components accessible from v6.data package
    - Imports work without errors
  </done>
</task>

</tasks>

<verification>
Before declaring plan complete:
- [ ] `python -m py_compile src/v6/data/reconciliation.py` succeeds without errors
- [ ] `python -c "from v6.data import PositionReconciler, ReconciliationService; print('✓ OK')"` works
- [ ] All 3 discrepancy types implemented (MISSING_FROM_DELTA, NAKED_POSITION, POSITION_MISMATCH)
- [ ] ReconciliationService runs periodic reconciliation (default: 5 minutes)
- [ ] ruff linter passes with no errors
- [ ] Integration test script is runnable
</verification>

<success_criteria>

- DiscrepancyType enum with 4 types defined
- Discrepancy and ReconciliationResult dataclasses created
- PositionReconciler fetches IB snapshot via reqPositionsAsync
- PositionReconciler fetches Delta Lake state (latest per conid)
- Detects all 3 discrepancy types with details
- ReconciliationService runs periodic reconciliation every 5 minutes
- Integration test demonstrates functionality
- All verification checks pass
- No errors or warnings introduced

</success_criteria>

<output>
After completion, create `.planning/phases/2-position-synchronization/2-03-SUMMARY.md`:

# Phase 2 Plan 3: Reconciliation Logic Summary

**Implemented reconciliation logic to validate consistency between IB positions and Delta Lake state.**

## Accomplishments

- Created DiscrepancyType enum with 4 types (MISSING_FROM_DELTA, NAKED_POSITION, POSITION_MISMATCH, STALE_DATA)
- Implemented PositionReconciler with full IB snapshot and Delta Lake comparison
- Created ReconciliationService for periodic reconciliation every 5 minutes
- Hybrid approach: real-time streaming + periodic full reconciliation
- Integration test demonstrates discrepancy detection

## Files Created/Modified

- `src/v6/data/reconciliation.py` - Discrepancy models, PositionReconciler, ReconciliationService
- `src/v6/data/test_reconciliation.py` - Integration test script
- `src/v6/data/__init__.py` - Updated with reconciliation exports

## Decisions Made

- **Hybrid reconciliation**: Real-time streaming (event-driven) + periodic full sync (every 5 min)
- **Three discrepancy types**: MISSING_FROM_DELTA, NAKED_POSITION (critical), POSITION_MISMATCH
- **Full snapshot approach**: Use reqPositionsAsync for complete IB state
- **Latest per conid**: Delta Lake query gets most recent position per conid
- **Periodic interval**: 5 minutes (300 seconds) balances freshness vs overhead
- **Singleton connection**: Uses IBPositionStreamer's IB connection (respects 100-connection limit)

## Issues Encountered

None

## Phase 2 Complete

All 3 plans in Phase 2 (Position Synchronization) have been successfully completed:
- 02-01: IB Position Streaming (singleton pattern, handler registration)
- 02-02: Delta Lake Persistence (idempotent writes, batch processing)
- 02-03: Reconciliation Logic (hybrid real-time + periodic, discrepancy detection)

**Phase 2 Accomplishments:**
- Real-time IB position streaming with 100-connection limit respected
- Delta Lake persistence with idempotent writes and Last-Write-Wins conflict resolution
- Hybrid reconciliation with periodic full sync every 5 minutes
- Discrepancy detection for data consistency validation

**Next:** Phase 3: Decision Rules Engine (01-01-PLAN.md)

The position synchronization foundation is in place with:
- Real-time streaming from IB via updatePortfolioEvent
- Reliable persistence to Delta Lake with ACID guarantees
- Periodic reconciliation catching inconsistencies
- Handler registration pattern for clean separation of concerns

Ready to build decision rules engine on top of this solid synchronization foundation.
</output>
