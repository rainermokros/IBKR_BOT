"""
Risk Events - Delta Lake Persistence for Post-Mortem Analysis

This module provides Delta Lake persistence for all Risk Management activities,
enabling post-mortem analysis and state recovery.

Key patterns:
- All risk events logged to Delta Lake for audit trail
- Supports circuit breaker state recovery
- Trailing stop history for effectiveness analysis
- Portfolio limit checks for rejection analysis

Events logged:
1. Circuit Breaker: State transitions, failures, successes
2. Trailing Stops: Activate, update, trigger events
3. Portfolio Limits: All checks, rejections, warnings
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import polars as pl
from deltalake import DeltaTable, write_deltalake
from loguru import logger


class RiskEventType(str, Enum):
    """Risk event types."""

    # Circuit breaker events
    CB_STATE_CHANGE = "circuit_breaker_state_change"
    CB_FAILURE = "circuit_breaker_failure"
    CB_SUCCESS = "circuit_breaker_success"
    CB_MANUAL_RESET = "circuit_breaker_manual_reset"

    # Trailing stop events
    TS_ADD = "trailing_stop_add"
    TS_ACTIVATE = "trailing_stop_activate"
    TS_UPDATE = "trailing_stop_update"
    TS_TRIGGER = "trailing_stop_trigger"
    TS_REMOVE = "trailing_stop_remove"
    TS_RESET = "trailing_stop_reset"

    # Portfolio limit events
    PL_CHECK = "portfolio_limit_check"
    PL_REJECTION = "portfolio_limit_rejection"
    PL_WARNING = "portfolio_limit_warning"


class CircuitState(str, Enum):
    """Circuit breaker states (duplicate from circuit_breaker.py to avoid import)."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class TrailingStopAction(str, Enum):
    """Trailing stop actions (duplicate from trailing_stop.py to avoid import)."""

    HOLD = "HOLD"
    ACTIVATE = "ACTIVATE"
    UPDATE = "UPDATE"
    TRIGGER = "TRIGGER"


@dataclass(slots=True)
class RiskEvent:
    """
    Risk event data model.

    Represents a single event from the risk management system.
    Uses optional fields for different event types.

    Attributes:
        event_id: Unique event identifier (UUID)
        event_type: Type of risk event
        component: Which component generated this event
        timestamp: When event occurred
        execution_id: Strategy execution ID (for trailing stops)
        # Circuit breaker fields
        old_state: Previous circuit state (for state changes)
        new_state: New circuit state (for state changes)
        failure_count: Number of failures (for failures)
        # Trailing stop fields
        entry_premium: Entry premium (for trailing stops)
        current_premium: Current premium (for trailing stops)
        highest_premium: Peak premium (for trailing stops)
        stop_premium: Stop level (for trailing stops)
        action: Trailing stop action (ACTIVATE, UPDATE, TRIGGER)
        # Portfolio limit fields
        limit_type: Type of limit checked
        current_value: Current value
        limit_value: Limit threshold
        allowed: Whether entry was allowed
        rejection_reason: Reason for rejection
        # Metadata
        metadata: Additional JSON data
    """

    event_id: str
    event_type: RiskEventType
    component: str
    timestamp: datetime
    execution_id: Optional[str] = None
    # Circuit breaker fields
    old_state: Optional[str] = None
    new_state: Optional[str] = None
    failure_count: Optional[int] = None
    # Trailing stop fields
    entry_premium: Optional[float] = None
    current_premium: Optional[float] = None
    highest_premium: Optional[float] = None
    stop_premium: Optional[float] = None
    action: Optional[str] = None
    # Portfolio limit fields
    limit_type: Optional[str] = None
    current_value: Optional[float] = None
    limit_value: Optional[float] = None
    allowed: Optional[bool] = None
    rejection_reason: Optional[str] = None
    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for Delta Lake."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "component": self.component,
            "timestamp": self.timestamp,
            "execution_id": self.execution_id,
            # Circuit breaker fields
            "old_state": self.old_state,
            "new_state": self.new_state,
            "failure_count": self.failure_count,
            # Trailing stop fields
            "entry_premium": self.entry_premium,
            "current_premium": self.current_premium,
            "highest_premium": self.highest_premium,
            "stop_premium": self.stop_premium,
            "action": self.action,
            # Portfolio limit fields
            "limit_type": self.limit_type,
            "current_value": self.current_value,
            "limit_value": self.limit_value,
            "allowed": self.allowed,
            "rejection_reason": self.rejection_reason,
            # Metadata
            "metadata": json.dumps(self.metadata) if self.metadata else None,
        }


class RiskEventsTable:
    """Delta Lake table for risk events."""

    def __init__(self, table_path: str = "data/lake/risk_events"):
        """
        Initialize risk events table.

        Args:
            table_path: Path to Delta Lake table
        """
        self.table_path = Path(table_path)
        self._ensure_table_exists()

    def _ensure_table_exists(self) -> None:
        """Create table if it doesn't exist."""
        if DeltaTable.is_deltatables(str(self.table_path)):
            return

        # Schema for risk events
        schema = pl.Schema({
            "event_id": pl.String,
            "event_type": pl.String,
            "component": pl.String,
            "timestamp": pl.Datetime("us"),
            "execution_id": pl.String,
            # Circuit breaker fields
            "old_state": pl.String,
            "new_state": pl.String,
            "failure_count": pl.Int32,
            # Trailing stop fields
            "entry_premium": pl.Float64,
            "current_premium": pl.Float64,
            "highest_premium": pl.Float64,
            "stop_premium": pl.Float64,
            "action": pl.String,
            # Portfolio limit fields
            "limit_type": pl.String,
            "current_value": pl.Float64,
            "limit_value": pl.Float64,
            "allowed": pl.Boolean,
            "rejection_reason": pl.String,
            # Metadata
            "metadata": pl.String,
        })

        # Create empty table
        empty_df = pl.DataFrame(schema=schema)
        write_deltalake(
            str(self.table_path),
            empty_df.limit(0),
            mode="overwrite",
        )

        logger.info(f"Created risk events table at {self.table_path}")

    def get_table(self) -> DeltaTable:
        """Get DeltaTable instance."""
        return DeltaTable(str(self.table_path))


class RiskEventLogger:
    """
    Logger for risk management events to Delta Lake.

    Provides async logging for all risk events with batching.
    Events are buffered and written in batches to avoid small files problem.

    Usage:
        >>> logger = RiskEventLogger()
        >>> await logger.initialize()
        >>>
        >>> # Log circuit breaker state change
        >>> await logger.log_circuit_breaker_state_change(
        ...     old_state="CLOSED",
        ...     new_state="OPEN",
        ...     failure_count=5
        ... )
        >>>
        >>> # Log trailing stop activation
        >>> await logger.log_trailing_stop_activate(
        ...     execution_id="abc123",
        ...     entry_premium=100.0,
        ...     current_premium=103.0,
        ...     stop_premium=101.45
        ... )
    """

    def __init__(
        self,
        table: RiskEventsTable | None = None,
        batch_size: int = 100,
        batch_interval_secs: int = 5,
    ):
        """
        Initialize risk event logger.

        Args:
            table: RiskEventsTable instance (creates default if None)
            batch_size: Number of events to batch before writing
            batch_interval_secs: Seconds between batch writes
        """
        self.table = table or RiskEventsTable()
        self.batch_size = batch_size
        self.batch_interval_secs = batch_interval_secs
        self._buffer: list[RiskEvent] = []

    async def initialize(self) -> None:
        """Initialize logger (called once at startup)."""
        logger.info("RiskEventLogger initialized")

    async def _write_batch(self) -> None:
        """Write buffered events to Delta Lake."""
        if not self._buffer:
            return

        try:
            # Convert events to dictionaries
            records = [event.to_dict() for event in self._buffer]

            # Write to Delta Lake
            df = pl.DataFrame(records)
            write_deltalake(
                str(self.table.table_path),
                df,
                mode="append",
            )

            logger.debug(f"Wrote {len(self._buffer)} risk events to Delta Lake")
            self._buffer.clear()

        except Exception as e:
            logger.error(f"Failed to write risk events: {e}")
            # Keep buffer on error (will retry next time)

    async def _maybe_write_batch(self) -> None:
        """Write batch if buffer is full."""
        if len(self._buffer) >= self.batch_size:
            await self._write_batch()

    async def _add_event(self, event: RiskEvent) -> None:
        """Add event to buffer and write if batch full."""
        self._buffer.append(event)
        await self._maybe_write_batch()

    async def flush(self) -> None:
        """Flush all buffered events to Delta Lake."""
        await self._write_batch()

    # Circuit breaker logging

    async def log_circuit_breaker_state_change(
        self,
        old_state: str,
        new_state: str,
        failure_count: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log circuit breaker state transition."""
        event = RiskEvent(
            event_id=str(uuid.uuid4()),
            event_type=RiskEventType.CB_STATE_CHANGE,
            component="circuit_breaker",
            timestamp=datetime.now(),
            old_state=old_state,
            new_state=new_state,
            failure_count=failure_count,
            metadata=metadata or {},
        )
        await self._add_event(event)

    async def log_circuit_breaker_failure(
        self,
        failure_count: int,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log circuit breaker failure."""
        event = RiskEvent(
            event_id=str(uuid.uuid4()),
            event_type=RiskEventType.CB_FAILURE,
            component="circuit_breaker",
            timestamp=datetime.now(),
            failure_count=failure_count,
            metadata=metadata or {},
        )
        await self._add_event(event)

    async def log_circuit_breaker_success(
        self,
        state: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log circuit breaker success (in HALF_OPEN)."""
        event = RiskEvent(
            event_id=str(uuid.uuid4()),
            event_type=RiskEventType.CB_SUCCESS,
            component="circuit_breaker",
            timestamp=datetime.now(),
            new_state=state,
            metadata=metadata or {},
        )
        await self._add_event(event)

    async def log_circuit_breaker_manual_reset(
        self,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log manual circuit breaker reset."""
        event = RiskEvent(
            event_id=str(uuid.uuid4()),
            event_type=RiskEventType.CB_MANUAL_RESET,
            component="circuit_breaker",
            timestamp=datetime.now(),
            metadata=metadata or {},
        )
        await self._add_event(event)

    # Trailing stop logging

    async def log_trailing_stop_add(
        self,
        execution_id: str,
        entry_premium: float,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Log trailing stop added to position."""
        event = RiskEvent(
            event_id=str(uuid.uuid4()),
            event_type=RiskEventType.TS_ADD,
            component="trailing_stop",
            timestamp=datetime.now(),
            execution_id=execution_id,
            entry_premium=entry_premium,
            metadata=config or {},
        )
        await self._add_event(event)

    async def log_trailing_stop_activate(
        self,
        execution_id: str,
        entry_premium: float,
        current_premium: float,
        highest_premium: float,
        stop_premium: float,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log trailing stop activation."""
        event = RiskEvent(
            event_id=str(uuid.uuid4()),
            event_type=RiskEventType.TS_ACTIVATE,
            component="trailing_stop",
            timestamp=datetime.now(),
            execution_id=execution_id,
            entry_premium=entry_premium,
            current_premium=current_premium,
            highest_premium=highest_premium,
            stop_premium=stop_premium,
            action="ACTIVATE",
            metadata=metadata or {},
        )
        await self._add_event(event)

    async def log_trailing_stop_update(
        self,
        execution_id: str,
        current_premium: float,
        highest_premium: float,
        stop_premium: float,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log trailing stop update."""
        event = RiskEvent(
            event_id=str(uuid.uuid4()),
            event_type=RiskEventType.TS_UPDATE,
            component="trailing_stop",
            timestamp=datetime.now(),
            execution_id=execution_id,
            current_premium=current_premium,
            highest_premium=highest_premium,
            stop_premium=stop_premium,
            action="UPDATE",
            metadata=metadata or {},
        )
        await self._add_event(event)

    async def log_trailing_stop_trigger(
        self,
        execution_id: str,
        current_premium: float,
        stop_premium: float,
        highest_premium: float,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log trailing stop trigger."""
        event = RiskEvent(
            event_id=str(uuid.uuid4()),
            event_type=RiskEventType.TS_TRIGGER,
            component="trailing_stop",
            timestamp=datetime.now(),
            execution_id=execution_id,
            current_premium=current_premium,
            stop_premium=stop_premium,
            highest_premium=highest_premium,
            action="TRIGGER",
            metadata=metadata or {},
        )
        await self._add_event(event)

    async def log_trailing_stop_remove(
        self,
        execution_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log trailing stop removed."""
        event = RiskEvent(
            event_id=str(uuid.uuid4()),
            event_type=RiskEventType.TS_REMOVE,
            component="trailing_stop",
            timestamp=datetime.now(),
            execution_id=execution_id,
            metadata=metadata or {},
        )
        await self._add_event(event)

    # Portfolio limit logging

    async def log_portfolio_limit_check(
        self,
        allowed: bool,
        limit_type: str | None = None,
        current_value: float | None = None,
        limit_value: float | None = None,
        execution_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log portfolio limit check."""
        event = RiskEvent(
            event_id=str(uuid.uuid4()),
            event_type=RiskEventType.PL_CHECK,
            component="portfolio_limits",
            timestamp=datetime.now(),
            execution_id=execution_id,
            limit_type=limit_type,
            current_value=current_value,
            limit_value=limit_value,
            allowed=allowed,
            metadata=metadata or {},
        )
        await self._add_event(event)

    async def log_portfolio_limit_rejection(
        self,
        limit_type: str,
        current_value: float,
        limit_value: float,
        rejection_reason: str,
        execution_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log portfolio limit rejection."""
        event = RiskEvent(
            event_id=str(uuid.uuid4()),
            event_type=RiskEventType.PL_REJECTION,
            component="portfolio_limits",
            timestamp=datetime.now(),
            execution_id=execution_id,
            limit_type=limit_type,
            current_value=current_value,
            limit_value=limit_value,
            allowed=False,
            rejection_reason=rejection_reason,
            metadata=metadata or {},
        )
        await self._add_event(event)

    async def log_portfolio_limit_warning(
        self,
        limit_type: str,
        current_value: float,
        limit_value: float,
        warning_message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log portfolio limit warning."""
        event = RiskEvent(
            event_id=str(uuid.uuid4()),
            event_type=RiskEventType.PL_WARNING,
            component="portfolio_limits",
            timestamp=datetime.now(),
            limit_type=limit_type,
            current_value=current_value,
            limit_value=limit_value,
            metadata={"warning": warning_message, **(metadata or {})},
        )
        await self._add_event(event)
