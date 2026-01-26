"""
Position Queue for batch processing of non-essential contracts.

Implements persistent queue using Delta Lake (follows IB_CENTRAL_MANAGER_DESIGN.md pattern).
Non-essential contracts are queued and processed in batches (0 streaming slots consumed).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional

import polars as pl
from loguru import logger


class QueueStatus(str, Enum):
    """Status of queued position update."""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


@dataclass(slots=True)
class QueuedPosition:
    """A position update waiting in queue."""
    request_id: str
    conid: int
    symbol: str
    priority: int  # 1=active (streamed), 2=monitoring (queued)
    status: QueueStatus
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str] = None


class PositionQueue:
    """
    Persistent queue for position updates using Delta Lake.

    Non-essential contracts are queued here and processed in batches by QueueWorker.
    This conserves IB streaming slots (0 slots consumed for queued contracts).

    **Schema:**
    - request_id: UUID (unique identifier)
    - conid: IB contract ID
    - symbol: Underlying symbol
    - priority: 1 (active/streamed), 2 (monitoring/queued)
    - status: PENDING, PROCESSING, SUCCESS, FAILED
    - created_at: Timestamp when queued
    - updated_at: Timestamp of last status change
    - error_message: Error details if failed
    """

    def __init__(self, delta_lake_path: str = "data/lake/position_queue"):
        """
        Initialize queue.

        Args:
            delta_lake_path: Path to Delta Lake table
        """
        self.delta_lake_path = Path(delta_lake_path)
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize queue (create table if not exists)."""
        if self._initialized:
            return

        if not self.delta_lake_path.exists():
            self._create_table()
            logger.info(f"✓ Created position_queue table: {self.delta_lake_path}")

        self._initialized = True

    async def insert(
        self,
        conid: int,
        symbol: str,
        priority: int = 2
    ) -> str:
        """
        Insert position update into queue.

        Args:
            conid: IB contract ID
            symbol: Underlying symbol
            priority: Priority level (default: 2 for monitoring)

        Returns:
            request_id: UUID of queued item
        """
        # Ensure queue exists
        await self.initialize()

        # Generate request ID
        request_id = str(uuid.uuid4())
        now = datetime.now()

        # Create record
        record = {
            'request_id': request_id,
            'conid': conid,
            'symbol': symbol,
            'priority': priority,
            'status': QueueStatus.PENDING.value,
            'created_at': now.isoformat(),
            'updated_at': now.isoformat(),
            'error_message': None
        }

        # Insert into Delta Lake
        try:
            import deltalake as dl

            # Use explicit schema to avoid Null type issues
            df = pl.DataFrame({
                'request_id': [record['request_id']],
                'conid': [record['conid']],
                'symbol': [record['symbol']],
                'priority': [record['priority']],
                'status': [record['status']],
                'created_at': [record['created_at']],
                'updated_at': [record['updated_at']],
                'error_message': [None]
            }, schema={
                'request_id': pl.String,
                'conid': pl.Int64,
                'symbol': pl.String,
                'priority': pl.Int64,
                'status': pl.String,
                'created_at': pl.String,
                'updated_at': pl.String,
                'error_message': pl.String
            })

            dl.write_deltalake(
                str(self.delta_lake_path),
                df,
                mode='append'
            )

            logger.debug(f"✓ Queued position update: {symbol} (conid: {conid}, priority: {priority})")
            return request_id

        except Exception as e:
            logger.error(f"Failed to insert into queue: {e}")
            raise

    async def get_batch(
        self,
        priority: int = 2,
        limit: int = 50,
        status: QueueStatus = QueueStatus.PENDING
    ) -> List[QueuedPosition]:
        """
        Get batch of queued items for processing.

        Args:
            priority: Priority level to fetch (default: 2)
            limit: Max items to return (default: 50)
            status: Status to filter (default: PENDING)

        Returns:
            List of QueuedPosition items
        """
        try:
            import deltalake as dl

            dt = dl.DeltaTable(str(self.delta_lake_path))
            df = pl.from_pandas(dt.to_pandas())

            # Filter and sort - get unique request_ids (handle duplicates from delete+insert)
            batch_df = df.filter(
                (pl.col("priority") == priority) &
                (pl.col("status") == status.value)
            ).sort("created_at").unique(subset=["request_id"], keep="first").head(limit)

            # Update status to PROCESSING
            request_ids = batch_df["request_id"].to_list()
            if request_ids:
                await self._update_status(request_ids, QueueStatus.PROCESSING)

            # Convert to QueuedPosition objects
            result = []
            for row in batch_df.to_dicts():
                result.append(QueuedPosition(
                    request_id=row["request_id"],
                    conid=row["conid"],
                    symbol=row["symbol"],
                    priority=row["priority"],
                    status=QueueStatus(row["status"]),
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                    error_message=row.get("error_message")
                ))

            logger.debug(f"✓ Retrieved {len(result)} items from queue (priority: {priority})")
            return result

        except Exception as e:
            logger.error(f"Failed to get batch from queue: {e}")
            return []

    async def mark_success(
        self,
        request_ids: List[str]
    ) -> None:
        """
        Mark queued items as successfully processed.

        Args:
            request_ids: List of request IDs to mark successful
        """
        if request_ids:
            await self._update_status(request_ids, QueueStatus.SUCCESS)
            logger.debug(f"✓ Marked {len(request_ids)} items as SUCCESS")

    async def mark_failed(
        self,
        request_id: str,
        error_message: str
    ) -> None:
        """
        Mark queued item as failed.

        Args:
            request_id: Request ID that failed
            error_message: Human-readable error message
        """
        await self._update_status(
            [request_id],
            QueueStatus.FAILED,
            error_message=error_message
        )
        logger.warning(f"✗ Marked {request_id} as FAILED: {error_message}")

    async def _update_status(
        self,
        request_ids: List[str],
        status: QueueStatus,
        error_message: Optional[str] = None
    ) -> None:
        """
        Update status of queued items.

        Since Delta Lake Python API doesn't support MERGE, we use delete + insert pattern.

        Args:
            request_ids: List of request IDs to update
            status: New status
            error_message: Optional error message
        """
        try:
            import deltalake as dl

            dt = dl.DeltaTable(str(self.delta_lake_path))

            # Read current data
            df = pl.from_pandas(dt.to_pandas())

            # Filter records to update
            to_update = df.filter(pl.col("request_id").is_in(request_ids))

            # Delete old records
            for request_id in request_ids:
                dt.delete(predicate=f"request_id = '{request_id}'")

            # Update status and re-insert
            now = datetime.now().isoformat()
            updated = to_update.with_columns(
                status=pl.lit(status.value),
                updated_at=pl.lit(now)
            )

            if error_message:
                updated = updated.with_columns(
                    error_message=pl.lit(error_message)
                )

            # Append updated records
            if len(updated) > 0:
                dl.write_deltalake(
                    str(self.delta_lake_path),
                    updated,
                    mode='append'
                )

        except Exception as e:
            logger.error(f"Failed to update queue status: {e}")

    def _create_table(self) -> None:
        """Create position_queue Delta Lake table."""
        import deltalake as dl

        # Create empty table with proper schema
        df = pl.DataFrame({
            'request_id': pl.Series([], dtype=pl.String),
            'conid': pl.Series([], dtype=pl.Int64),
            'symbol': pl.Series([], dtype=pl.String),
            'priority': pl.Series([], dtype=pl.Int64),
            'status': pl.Series([], dtype=pl.String),
            'created_at': pl.Series([], dtype=pl.String),
            'updated_at': pl.Series([], dtype=pl.String),
            'error_message': pl.Series([], dtype=pl.String)
        })

        dl.write_deltalake(
            str(self.delta_lake_path),
            df,
            mode='overwrite'
        )

        logger.info(f"✓ Created position_queue table: {self.delta_lake_path}")
