"""
Collection Queue Manager for Option Snapshots

Tracks failed collection attempts and manages backfill queue.
Provides persistence for retry logic and backfill processing.

Key features:
- Delta Lake-based queue for failed collection windows
- Tracks symbol, timestamp, error type, retry count
- Excludes Error 200 (expected - contract doesn't exist)
- Provides query interface for backfill worker
"""

import polars as pl
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
from loguru import logger
from deltalake import DeltaTable, write_deltalake


@dataclass
class QueueItem:
    """Represents a failed collection window to retry."""
    symbol: str
    target_time: datetime  # When this collection should have happened
    attempt_time: datetime  # When we tried and failed
    error_type: str  # 'timeout', 'connection', 'no_chains', 'no_data', 'other'
    error_message: str
    retry_count: int = 0
    max_retries: int = 5
    status: str = 'pending'  # pending, in_progress, completed, failed

    def to_dict(self) -> dict:
        """Convert to dictionary for Delta Lake storage."""
        return {
            'symbol': self.symbol,
            'target_time': self.target_time.isoformat(),
            'attempt_time': self.attempt_time.isoformat(),
            'error_type': self.error_type,
            'error_message': self.error_message,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'status': self.status
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'QueueItem':
        """Create from dictionary."""
        # Handle both dict and object access (Polars rows)
        target_time = data.get('target_time')
        attempt_time = data.get('attempt_time')

        if isinstance(target_time, str):
            target_time = datetime.fromisoformat(target_time)
        if isinstance(attempt_time, str):
            attempt_time = datetime.fromisoformat(attempt_time)

        return cls(
            symbol=data['symbol'],
            target_time=target_time,
            attempt_time=attempt_time,
            error_type=data['error_type'],
            error_message=data['error_message'],
            retry_count=data['retry_count'],
            max_retries=data['max_retries'],
            status=data['status']
        )


class CollectionQueue:
    """
    Manages the backfill queue using Delta Lake.

    Provides persistent storage for failed collection attempts,
    tracks retry counts, and excludes Error 200 (contract not found).
    """

    def __init__(self, table_path: str = 'data/lake/collection_queue'):
        """
        Initialize the collection queue.

        Args:
            table_path: Path to Delta Lake table
        """
        self.table_path = table_path
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """Create Delta Lake table if it doesn't exist."""
        table_path = Path(self.table_path)

        if not table_path.exists():
            logger.info(f"Creating collection queue table at {self.table_path}")

            # Create empty table with schema
            empty_df = pl.DataFrame({
                'symbol': [],
                'target_time': [],
                'attempt_time': [],
                'error_type': [],
                'error_message': [],
                'retry_count': [],
                'max_retries': [],
                'status': [],
                'created_at': []
            }).cast({
                'symbol': pl.String,
                'target_time': pl.String,
                'attempt_time': pl.String,
                'error_type': pl.String,
                'error_message': pl.String,
                'retry_count': pl.Int32,
                'max_retries': pl.Int32,
                'status': pl.String,
                'created_at': pl.String
            })

            # Write empty table
            write_deltalake(
                self.table_path,
                empty_df,
                mode='overwrite'
            )

            logger.success(f"✓ Created collection queue table")

    def add_failure(
        self,
        symbol: str,
        target_time: datetime,
        error_type: str,
        error_message: str,
        max_retries: int = 5
    ) -> Optional[int]:
        """
        Add a failed collection to the queue.

        Skip Error 200 - these are expected (contract doesn't exist).

        Args:
            symbol: Underlying symbol
            target_time: When collection should have happened
            error_type: Type of error
            error_message: Error message
            max_retries: Maximum retry attempts

        Returns:
            Item ID if added, None if skipped
        """
        # Skip Error 200 - expected, don't retry
        if "Error 200" in error_message or error_type == "contract_not_found":
            logger.debug(f"Skipping Error 200 for {symbol} at {target_time}")
            return None

        attempt_time = datetime.now()

        # Create new item
        item = QueueItem(
            symbol=symbol,
            target_time=target_time,
            attempt_time=attempt_time,
            error_type=error_type,
            error_message=error_message,
            retry_count=0,
            max_retries=max_retries,
            status='pending'
        )

        # Write to Delta Lake
        new_data = pl.DataFrame({
            'symbol': [item.symbol],
            'target_time': [item.target_time.isoformat()],
            'attempt_time': [item.attempt_time.isoformat()],
            'error_type': [item.error_type],
            'error_message': [item.error_message],
            'retry_count': [item.retry_count],
            'max_retries': [item.max_retries],
            'status': [item.status],
            'created_at': [datetime.now().isoformat()]
        })

        write_deltalake(
            self.table_path,
            new_data,
            mode='append'
        )

        logger.debug(f"Added {symbol} {target_time} to queue ({error_type})")
        return 1

    def get_pending(self, limit: int = 100) -> List[QueueItem]:
        """
        Get pending items from queue.

        Args:
            limit: Maximum number of items to return

        Returns:
            List of QueueItem objects
        """
        try:
            dt = DeltaTable(self.table_path)
            df = pl.from_pandas(dt.to_pandas())

            # Filter for pending items
            pending = df.filter(
                (pl.col('status') == 'pending') &
                (pl.col('retry_count') < pl.col('max_retries'))
            ).sort('target_time').head(limit)

            return [QueueItem.from_dict(row) for row in pending.to_dicts()]
        except Exception as e:
            logger.warning(f"No pending items in queue: {e}")
            return []

    def mark_in_progress(self, symbol: str, target_time: datetime):
        """
        Mark item as in progress.

        Args:
            symbol: Underlying symbol
            target_time: Target collection time
        """
        try:
            dt = DeltaTable(self.table_path)
            df = pl.from_pandas(dt.to_pandas())

            # Filter and update status
            target_time_str = target_time.isoformat()

            updated = df.with_columns(
                pl.when(
                    (pl.col('symbol') == symbol) &
                    (pl.col('target_time') == target_time_str)
                )
                .then(pl.lit('in_progress'))
                .otherwise(pl.col('status'))
                .alias('status')
            )

            # Overwrite with updated data
            write_deltalake(
                self.table_path,
                updated,
                mode='overwrite'
            )

            logger.debug(f"Marked {symbol} {target_time} as in_progress")
        except Exception as e:
            logger.error(f"Failed to mark in progress: {e}")

    def mark_completed(self, symbol: str, target_time: datetime):
        """
        Mark item as completed successfully.

        Args:
            symbol: Underlying symbol
            target_time: Target collection time
        """
        try:
            dt = DeltaTable(self.table_path)
            df = pl.from_pandas(dt.to_pandas())

            # Filter and update status
            target_time_str = target_time.isoformat()

            updated = df.with_columns(
                pl.when(
                    (pl.col('symbol') == symbol) &
                    (pl.col('target_time') == target_time_str)
                )
                .then(pl.lit('completed'))
                .otherwise(pl.col('status'))
                .alias('status')
            )

            # Overwrite with updated data
            write_deltalake(
                self.table_path,
                updated,
                mode='overwrite'
            )

            logger.debug(f"Marked {symbol} {target_time} as completed")
        except Exception as e:
            logger.error(f"Failed to mark completed: {e}")

    def increment_retry(self, symbol: str, target_time: datetime):
        """
        Increment retry count for an item.

        Args:
            symbol: Underlying symbol
            target_time: Target collection time
        """
        try:
            dt = DeltaTable(self.table_path)
            df = pl.from_pandas(dt.to_pandas())

            # Filter and update retry count and status
            target_time_str = target_time.isoformat()

            updated = df.with_columns(
                pl.when(
                    (pl.col('symbol') == symbol) &
                    (pl.col('target_time') == target_time_str)
                )
                .then(pl.col('retry_count') + 1)
                .otherwise(pl.col('retry_count'))
                .alias('retry_count')
            ).with_columns(
                pl.when(
                    (pl.col('symbol') == symbol) &
                    (pl.col('target_time') == target_time_str) &
                    (pl.col('retry_count') >= pl.col('max_retries'))
                )
                .then(pl.lit('failed'))
                .otherwise(pl.col('status'))
                .alias('status')
            )

            # Overwrite with updated data
            write_deltalake(
                self.table_path,
                updated,
                mode='overwrite'
            )

            logger.debug(f"Incremented retry count for {symbol} {target_time}")
        except Exception as e:
            logger.error(f"Failed to increment retry: {e}")

    def get_stats(self) -> Dict:
        """
        Get queue statistics.

        Returns:
            Dictionary with queue stats
        """
        try:
            dt = DeltaTable(self.table_path)
            df = pl.from_pandas(dt.to_pandas())

            stats = {
                'total': len(df),
                'pending': len(df.filter(pl.col('status') == 'pending')),
                'in_progress': len(df.filter(pl.col('status') == 'in_progress')),
                'completed': len(df.filter(pl.col('status') == 'completed')),
                'failed': len(df.filter(pl.col('status') == 'failed')),
            }

            return stats
        except Exception as e:
            logger.warning(f"Failed to get stats: {e}")
            return {
                'total': 0,
                'pending': 0,
                'in_progress': 0,
                'completed': 0,
                'failed': 0,
            }

    def cleanup_old(self, days: int = 7):
        """
        Remove completed/failed items older than specified days.

        Args:
            days: Days to keep items
        """
        try:
            dt = DeltaTable(self.table_path)
            df = pl.from_pandas(dt.to_pandas())

            cutoff = datetime.now() - timedelta(days=days)

            # Filter out old completed/failed items
            filtered = df.filter(
                ~(
                    (pl.col('status').is_in(['completed', 'failed'])) &
                    (pl.col('created_at') < cutoff.isoformat())
                )
            )

            # Overwrite with filtered data
            write_deltalake(
                self.table_path,
                filtered,
                mode='overwrite'
            )

            logger.info(f"Cleaned up old queue items (> {days} days)")
        except Exception as e:
            logger.error(f"Failed to cleanup old items: {e}")
