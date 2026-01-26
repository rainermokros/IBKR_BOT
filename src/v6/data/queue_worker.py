"""
Queue Worker for processing queued position updates.

Background daemon that processes non-essential contracts from PositionQueue
in batches. Fetches position data from IB and updates Delta Lake.

Follows IB_CENTRAL_MANAGER_DESIGN.md daemon pattern.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import polars as pl
from loguru import logger

from src.v6.data.position_queue import PositionQueue, QueueStatus
from src.v6.utils.ib_connection import IBConnectionManager


@dataclass(slots=True)
class WorkerStats:
    """Statistics for queue worker."""
    total_processed: int = 0
    total_success: int = 0
    total_failed: int = 0
    last_batch_time: Optional[datetime] = None
    last_batch_size: int = 0


class QueueWorker:
    """
    Background daemon for processing queued position updates.

    **Purpose:**
    Process non-essential contracts from PositionQueue in batches.
    Fetches position data from IB using reqPositionsAsync().
    Updates Delta Lake with latest position information.

    **Pattern:**
    Follows IB_CENTRAL_MANAGER_DESIGN.md daemon pattern:
    - Periodic batch processing (every 5 seconds)
    - Error handling with retry logic
    - Status tracking (SUCCESS/FAILED)

    **Slot Conservation:**
    Uses reqPositionsAsync() (polling) instead of reqMktData() (streaming).
    Consumes 0 streaming slots.
    """

    def __init__(
        self,
        queue: PositionQueue,
        interval: int = 5,
        batch_size: int = 50,
        delta_lake_path: str = "data/lake/position_updates"
    ):
        """
        Initialize queue worker.

        Args:
            queue: PositionQueue to process
            interval: Seconds between batches (default: 5s)
            batch_size: Max items per batch (default: 50)
            delta_lake_path: Path to position_updates Delta Lake table
        """
        self.queue = queue
        self.interval = interval
        self.batch_size = batch_size
        self.delta_lake_path = Path(delta_lake_path)

        self._connection = None
        self._task: Optional[asyncio.Task] = None
        self._is_running = False

        self.stats = WorkerStats()

    async def start(self) -> None:
        """
        Start queue worker daemon.

        Begins periodic batch processing of queued items.
        """
        if self._is_running:
            logger.warning("QueueWorker already running")
            return

        logger.info(f"Starting QueueWorker (interval: {self.interval}s, batch: {self.batch_size})")

        # Get IB connection
        conn_manager = IBConnectionManager()
        await conn_manager.connect()
        self._connection = conn_manager

        if not self._connection or not self._connection.is_connected:
            raise ConnectionError("IB not connected")

        # Initialize queue
        await self.queue.initialize()

        self._is_running = True
        self._task = asyncio.create_task(self._worker_loop())

        logger.info("✓ QueueWorker started")

    async def stop(self) -> None:
        """
        Stop queue worker daemon.

        Gracefully stops batch processing.
        """
        self._is_running = False

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("✓ QueueWorker stopped")

    async def _worker_loop(self) -> None:
        """
        Periodic batch processing loop.

        Every interval seconds:
        1. Get batch from queue (priority 2, limit batch_size)
        2. Fetch positions from IB
        3. Update Delta Lake
        4. Mark items as SUCCESS/FAILED
        """
        while self._is_running:
            try:
                await asyncio.sleep(self.interval)

                if self._is_running:
                    await self._process_batch()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker loop error: {e}", exc_info=True)

    async def _process_batch(self) -> None:
        """
        Process one batch of queued items.

        Args:
            batch: List of QueuedPosition items
        """
        # Get batch from queue
        batch = await self.queue.get_batch(
            priority=2,
            limit=self.batch_size,
            status=QueueStatus.PENDING
        )

        if not batch:
            logger.debug("No queued items to process")
            return

        logger.info(f"Processing batch of {len(batch)} queued items")
        start_time = datetime.now()

        # Fetch positions from IB (all at once for efficiency)
        ib = self._connection.ib
        all_positions = await ib.reqPositionsAsync()

        # Build map for fast lookup: conid -> position
        position_map = {}
        for item in all_positions:
            if hasattr(item, 'contract') and hasattr(item.contract, 'conId'):
                position_map[item.contract.conId] = item

        # Process each queued item
        success_ids = []
        failed_items = []

        for queued_item in batch:
            try:
                # Find position data
                if queued_item.conid not in position_map:
                    logger.warning(f"Position {queued_item.conid} not found in IB")
                    failed_items.append((queued_item, "Position not found in IB"))
                    continue

                ib_position = position_map[queued_item.conid]

                # Create PositionUpdate
                from v6.data.position_streamer import PositionUpdate

                update = PositionUpdate(
                    conid=queued_item.conid,
                    symbol=queued_item.symbol,
                    right=ib_position.contract.right if hasattr(ib_position.contract, 'right') else 'CALL',
                    strike=ib_position.contract.strike if hasattr(ib_position.contract, 'strike') else 0.0,
                    expiry=ib_position.contract.lastTradeDateOrContractMonth if hasattr(ib_position.contract, 'lastTradeDateOrContractMonth') else '',
                    position=ib_position.position,
                    market_price=ib_position.marketPrice,
                    market_value=ib_position.marketValue,
                    average_cost=ib_position.averageCost,
                    unrealized_pnl=ib_position.unrealizedPNL,
                    timestamp=datetime.now()
                )

                # Write to Delta Lake (direct write, not via DeltaLakePositionWriter)
                await self._write_to_delta_lake([update])

                success_ids.append(queued_item.request_id)
                self.stats.total_success += 1

            except Exception as e:
                logger.error(f"Failed to process {queued_item.request_id}: {e}")
                failed_items.append((queued_item, str(e)))
                self.stats.total_failed += 1

        # Mark items as SUCCESS/FAILED
        if success_ids:
            await self.queue.mark_success(success_ids)
            logger.debug(f"Marked {len(success_ids)} items as SUCCESS")

        for item, error in failed_items:
            await self.queue.mark_failed(item.request_id, error)
            logger.debug(f"Marked {item.request_id} as FAILED: {error}")

        # Update stats
        self.stats.total_processed += len(batch)
        self.stats.last_batch_time = datetime.now()
        self.stats.last_batch_size = len(batch)

        duration = (datetime.now() - start_time).total_seconds()
        logger.info(
            f"✓ Processed batch: {len(success_ids)} success, "
            f"{len(failed_items)} failed ({duration:.2f}s)"
        )

    async def _write_to_delta_lake(self, updates: List) -> None:
        """
        Write position updates to Delta Lake.

        Args:
            updates: List of PositionUpdate objects
        """
        try:
            import deltalake as dl

            # Convert to list of dicts
            data = [{
                'conid': u.conid,
                'symbol': u.symbol,
                'right': u.right,
                'strike': u.strike,
                'expiry': u.expiry,
                'position': u.position,
                'market_price': u.market_price,
                'market_value': u.market_value,
                'average_cost': u.average_cost,
                'unrealized_pnl': u.unrealized_pnl,
                'timestamp': u.timestamp.isoformat(),
                'date': u.timestamp.date()
            } for u in updates]

            df = pl.DataFrame(data)

            # Append to Delta Lake
            dl.write_deltalake(
                str(self.delta_lake_path),
                df,
                mode='append'
            )

        except Exception as e:
            logger.error(f"Failed to write to Delta Lake: {e}")
            raise

    def get_stats(self) -> WorkerStats:
        """
        Get worker statistics.

        Returns:
            WorkerStats object with current statistics
        """
        return self.stats
