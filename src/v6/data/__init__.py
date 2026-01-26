"""
V6 Data Package

This package provides data access components for the v6 trading system including:
- Real-time position streaming from IB
- Delta Lake persistence and repositories
- Position reconciliation logic
- Strategy registry for tracking active contracts
- Position queue for batch processing
- Data models and validation
"""

from v6.data.delta_persistence import (
    DeltaLakePositionWriter,
    PositionUpdatesTable,
)
from v6.data.position_streamer import (
    IBPositionStreamer,
    PositionUpdate,
    PositionUpdateHandler,
)
from v6.data.reconciliation import (
    Discrepancy,
    DiscrepancyType,
    PositionReconciler,
    ReconciliationResult,
    ReconciliationService,
)
from v6.data.strategy_registry import (
    ActiveContract,
    StrategyRegistry,
)
from v6.data.position_queue import (
    QueueStatus,
    QueuedPosition,
    PositionQueue,
)
from v6.data.queue_worker import (
    WorkerStats,
    QueueWorker,
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
    # Strategy registry
    "ActiveContract",
    "StrategyRegistry",
    # Position queue
    "QueueStatus",
    "QueuedPosition",
    "PositionQueue",
    # Queue worker
    "WorkerStats",
    "QueueWorker",
]
