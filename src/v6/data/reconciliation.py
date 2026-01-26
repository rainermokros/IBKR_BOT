"""
Position Reconciliation Module

This module provides reconciliation logic to validate consistency between IB positions
and Delta Lake state. Implements hybrid approach: real-time event-driven streaming
+ periodic full reconciliation every 5 minutes.

Key patterns:
- Dataclass with slots=True for performance (Phase 1-04 pattern)
- Full snapshot from IB using reqPositionsAsync
- Detects 3 discrepancy types: MISSING_FROM_DELTA, NAKED_POSITION, POSITION_MISMATCH
- NAKED_POSITION is critical (data exists but position missing in IB)
- Hybrid approach: real-time streaming + periodic full reconciliation
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List

import polars as pl
from deltalake import DeltaTable
from loguru import logger

from src.v6.data.position_streamer import IBPositionStreamer


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

