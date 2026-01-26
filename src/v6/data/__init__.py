"""
V6 Data Package

This package provides data access components for the v6 trading system including:
- Real-time position streaming from IB
- Delta Lake persistence and repositories
- Position reconciliation logic
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
