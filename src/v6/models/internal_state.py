"""
Dataclasses for Internal State Management

This module provides dataclasses for high-performance internal state tracking.
Dataclasses are used here (instead of Pydantic) because this data is internal to the process
and doesn't require validation overhead. Performance matters more than validation.

Key patterns:
- slots=True: Reduced memory usage and faster attribute access
- Field(default_factory=...): For mutable default values
- Methods: Update P&L, recalculate portfolio Greeks, manage positions

Decision tree (from research):
    Does this data come from outside my process?
    ├─ Yes → Use Pydantic (validation critical)
    └─ No → Use dataclass (performance matters) ← WE ARE HERE
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
from enum import Enum


class CircuitState(Enum):
    """Circuit breaker state for IB connection."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, stop requests
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass(slots=True)
class PositionState:
    """
    Internal position state - faster than Pydantic.

    Tracks the current state of a single position. Uses slots=True for performance
    (reduced memory usage, faster attribute access).

    Attributes:
        symbol: Underlying symbol
        quantity: Number of contracts/shares
        entry_price: Average entry price
        current_price: Current market price
        unrealized_pnl: Unrealized profit/loss
        last_update: When this state was last updated
    """

    symbol: str
    quantity: int
    entry_price: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    last_update: datetime = field(default_factory=datetime.now)

    def update_pnl(self) -> None:
        """
        Update unrealized P&L based on current price.

        Formula: (current_price - entry_price) * quantity
        Updates last_update timestamp automatically.
        """
        self.unrealized_pnl = (self.current_price - self.entry_price) * self.quantity
        self.last_update = datetime.now()


@dataclass(slots=True)
class PortfolioState:
    """
    Internal portfolio state - tracks all positions and portfolio-level Greeks.

    Manages a dictionary of positions and recalculates portfolio-level metrics
    when positions are added or removed. Uses slots=True for performance.

    Attributes:
        positions: Dictionary of symbol -> PositionState
        total_delta: Portfolio-level delta
        total_gamma: Portfolio-level gamma
        total_theta: Portfolio-level theta
        total_vega: Portfolio-level vega
        cash_balance: Available cash balance
        last_update: When this state was last updated

    Methods:
        add_position: Add or update a position in the portfolio
        remove_position: Remove a position from the portfolio
        get_position: Get a position by symbol
        get_all_positions: Get all positions as a list
    """

    positions: Dict[str, PositionState] = field(default_factory=dict)
    total_delta: float = 0.0
    total_gamma: float = 0.0
    total_theta: float = 0.0
    total_vega: float = 0.0
    cash_balance: float = 0.0
    last_update: datetime = field(default_factory=datetime.now)

    def add_position(self, state: PositionState) -> None:
        """
        Add or update position in portfolio.

        Args:
            state: PositionState to add/update
        """
        self.positions[state.symbol] = state
        self._recalculate()

    def remove_position(self, symbol: str) -> None:
        """
        Remove position from portfolio.

        Args:
            symbol: Symbol of position to remove
        """
        if symbol in self.positions:
            del self.positions[symbol]
            self._recalculate()

    def _recalculate(self) -> None:
        """
        Recalculate portfolio Greeks and totals.

        Simplified calculation for demonstration. In production, this would
        aggregate actual Greeks from OptionLeg models.
        """
        # Simplified delta calculation (would use actual Greeks in production)
        self.total_delta = sum(p.quantity * (p.current_price / 100) for p in self.positions.values())
        # Simplified gamma calculation (would use actual Greeks in production)
        self.total_gamma = sum(p.quantity * 0.01 for p in self.positions.values())
        # Add theta, vega calculations as needed
        self.last_update = datetime.now()

    def get_position(self, symbol: str) -> Optional[PositionState]:
        """
        Get position by symbol.

        Args:
            symbol: Symbol to look up

        Returns:
            PositionState if found, None otherwise
        """
        return self.positions.get(symbol)

    def get_all_positions(self) -> List[PositionState]:
        """
        Get all positions as list.

        Returns:
            List of all PositionState objects
        """
        return list(self.positions.values())


@dataclass
class ConnectionMetrics:
    """
    Internal connection metrics for monitoring IB connection health.

    Tracks connection state, circuit breaker status, and connection statistics.
    Doesn't use slots because it's instantiated infrequently (singleton pattern).

    Attributes:
        host: IB Gateway/TWS host
        port: IB Gateway/TWS port
        client_id: IB client ID
        is_connected: Current connection status
        circuit_breaker_state: Circuit breaker state (closed/open/half_open)
        failure_count: Number of consecutive failures
        last_heartbeat: Last successful heartbeat timestamp
        connection_attempts: Total connection attempts
        successful_connections: Total successful connections
    """

    host: str
    port: int
    client_id: int
    is_connected: bool = False
    circuit_breaker_state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_heartbeat: Optional[datetime] = None
    connection_attempts: int = 0
    successful_connections: int = 0


@dataclass(slots=True)
class SystemState:
    """
    Top-level system state - tracks all internal state.

    Aggregates portfolio state and connection metrics into a single top-level
    state object. This is the primary state object passed through the system.

    Attributes:
        portfolio: PortfolioState object
        connection: ConnectionMetrics object
        last_update: When this state was last updated
    """

    portfolio: PortfolioState = field(default_factory=PortfolioState)
    connection: ConnectionMetrics = field(
        default_factory=lambda: ConnectionMetrics(host="", port=0, client_id=0)
    )
    last_update: datetime = field(default_factory=datetime.now)
