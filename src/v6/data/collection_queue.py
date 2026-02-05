"""
Collection Queue Manager for Option Snapshots

Tracks failed collection attempts and manages backfill queue.
Provides persistence for retry logic and backfill processing.

Key features:
- SQLite-based queue for failed collection windows
- Tracks symbol, timestamp, error type, retry count
- Excludes Error 200 (expected - contract doesn't exist)
- Provides query interface for backfill worker
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from loguru import logger


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
        """Convert to dictionary for JSON storage."""
        d = asdict(self)
        d['target_time'] = self.target_time.isoformat()
        d['attempt_time'] = self.attempt_time.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> 'QueueItem':
        """Create from dictionary."""
        data['target_time'] = datetime.fromisoformat(data['target_time'])
        data['attempt_time'] = datetime.fromisoformat(data['attempt_time'])
        return cls(**data)


class CollectionQueue:
    """
    Manages queue of failed collection attempts for backfill.

    Uses SQLite for persistence and concurrent access safety.
    """

    def __init__(self, db_path: str = "data/lake/collection_queue.db"):
        """
        Initialize collection queue.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Create database schema if not exists."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS collection_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    target_time TEXT NOT NULL,
                    attempt_time TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    error_message TEXT,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 5,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Index for faster queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status_time
                ON collection_queue(status, target_time)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_symbol_status
                ON collection_queue(symbol, status)
            """)

            conn.commit()

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

        Args:
            symbol: ETF symbol (SPY, QQQ, IWM)
            target_time: When this collection was scheduled
            error_type: Type of error (timeout, connection, etc.)
            error_message: Error details
            max_retries: Maximum retry attempts

        Returns:
            Queue item ID if added, None if skipped (e.g., Error 200)
        """
        # Skip Error 200 - expected, don't retry
        if "Error 200" in error_message or error_type == "contract_not_found":
            logger.debug(f"Skipping Error 200 for {symbol} at {target_time}")
            return None

        # Check if already queued for this time window
        with sqlite3.connect(self.db_path) as conn:
            existing = conn.execute("""
                SELECT id FROM collection_queue
                WHERE symbol = ? AND target_time = ? AND status != 'completed'
            """, (symbol, target_time.isoformat())).fetchone()

            if existing:
                logger.debug(f"Already queued: {symbol} at {target_time}")
                return existing[0]

            # Add new queue item
            cursor = conn.execute("""
                INSERT INTO collection_queue
                (symbol, target_time, attempt_time, error_type, error_message, max_retries)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                symbol,
                target_time.isoformat(),
                datetime.now().isoformat(),
                error_type,
                error_message,
                max_retries
            ))
            conn.commit()

            logger.warning(f"📝 Queued retry for {symbol} at {target_time} ({error_type})")
            return cursor.lastrowid

    def get_pending_items(self, limit: int = 10) -> List[QueueItem]:
        """
        Get pending items for backfill, ordered by target time.

        Args:
            limit: Maximum items to return

        Returns:
            List of QueueItems ready for retry
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM collection_queue
                WHERE status = 'pending'
                  AND retry_count < max_retries
                  AND target_time >= datetime('now', '-7 days')
                ORDER BY target_time ASC
                LIMIT ?
            """, (limit,)).fetchall()

            items = []
            for row in rows:
                items.append(QueueItem(
                    symbol=row['symbol'],
                    target_time=datetime.fromisoformat(row['target_time']),
                    attempt_time=datetime.fromisoformat(row['attempt_time']),
                    error_type=row['error_type'],
                    error_message=row['error_message'],
                    retry_count=row['retry_count'],
                    max_retries=row['max_retries'],
                    status=row['status']
                ))

            return items

    def mark_in_progress(self, item_id: int):
        """Mark queue item as being processed."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE collection_queue
                SET status = 'in_progress', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (item_id,))
            conn.commit()

    def mark_completed(self, item_id: int):
        """Mark queue item as successfully completed."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE collection_queue
                SET status = 'completed', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (item_id,))
            conn.commit()
            logger.success(f"✓ Backfill completed for queue item {item_id}")

    def mark_failed(self, item_id: int, error_message: str):
        """
        Mark queue item as failed and increment retry count.

        Args:
            item_id: Queue item ID
            error_message: New error message
        """
        with sqlite3.connect(self.db_path) as conn:
            # Check if should be permanently failed
            item = conn.execute("""
                SELECT retry_count, max_retries FROM collection_queue WHERE id = ?
            """, (item_id,)).fetchone()

            if item and item[0] + 1 >= item[1]:
                # Max retries reached
                conn.execute("""
                    UPDATE collection_queue
                    SET status = 'failed',
                        retry_count = retry_count + 1,
                        error_message = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (error_message, item_id))
                conn.commit()
                logger.error(f"❌ Max retries reached for queue item {item_id}")
            else:
                # Increment retry count, reset to pending
                conn.execute("""
                    UPDATE collection_queue
                    SET status = 'pending',
                        retry_count = retry_count + 1,
                        error_message = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (error_message, item_id))
                conn.commit()
                logger.warning(f"⚠️  Retry {item[0] + 1}/{item[1]} for queue item {item_id}")

    def get_stats(self) -> dict:
        """Get queue statistics."""
        with sqlite3.connect(self.db_path) as conn:
            stats = {}

            for status in ['pending', 'in_progress', 'completed', 'failed']:
                count = conn.execute("""
                    SELECT COUNT(*) FROM collection_queue WHERE status = ?
                """, (status,)).fetchone()[0]
                stats[status] = count

            # Items older than 7 days (stale)
            stale = conn.execute("""
                SELECT COUNT(*) FROM collection_queue
                WHERE status IN ('pending', 'in_progress')
                  AND target_time < datetime('now', '-7 days')
            """).fetchone()[0]
            stats['stale'] = stale

            return stats

    def cleanup_old_items(self, days: int = 30):
        """
        Remove completed items older than specified days.

        Args:
            days: Days to keep completed items
        """
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute("""
                DELETE FROM collection_queue
                WHERE status = 'completed'
                  AND updated_at < datetime('now', '-' || ? || ' days')
            """, (days,))

            conn.commit()

            if result.rowcount > 0:
                logger.info(f"🧹 Cleaned up {result.rowcount} old completed items")

    def get_failed_summaries(self, limit: int = 20) -> List[dict]:
        """
        Get summary of recent failed items for diagnostics.

        Args:
            limit: Maximum items to return

        Returns:
            List of dicts with failure information
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT symbol, target_time, error_type, error_message,
                       retry_count, max_retries, status
                FROM collection_queue
                WHERE status != 'completed'
                ORDER BY target_time DESC
                LIMIT ?
            """, (limit,)).fetchall()

            return [dict(row) for row in rows]
