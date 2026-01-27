---
phase: 1-architecture-infrastructure
plan: 04
type: execute
depends_on: ["1-01"]
files_modified: [src/v6/models/__init__.py, src/v6/models/ib_models.py, src/v6/models/internal_state.py]
---

<objective>
Create Pydantic models for IB data validation and dataclasses for internal state management.

Purpose: Establish type-safe data structures with validation for external IB data (Pydantic) and fast internal state tracking (dataclasses).
Output: Working Pydantic models for IB contracts/positions and dataclasses for internal state.
</objective>

<execution_context>
~/.claude/get-shit-done/workflows/execute-plan.md
./summary.md
</execution_context>

<context>
@v6/.planning/PROJECT.md
@v6/.planning/ROADMAP.md
@v6/.planning/phases/1-architecture-infrastructure/1-RESEARCH.md
@v6/.planning/phases/1-architecture-infrastructure/1-01-SUMMARY.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create Pydantic models for IB data validation</name>
  <files>src/v6/models/__init__.py, src/v6/models/ib_models.py</files>
  <action>
Create Pydantic models for validating IB API responses:

**File: src/v6/models/ib_models.py**
```python
from pydantic import BaseModel, Field, field_validator
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Literal
from enum import Enum

class OptionRight(str, Enum):
    """Option type."""
    CALL = "C"
    PUT = "P"

class PositionStatus(str, Enum):
    """Position status."""
    OPEN = "open"
    CLOSED = "closed"
    ROLLING = "rolling"

class Greeks(BaseModel):
    """Options Greeks from IB API or calculated (Pitfall 3: use Pydantic for external data)."""
    delta: float = Field(ge=-1, le=1, description="Delta sensitivity")
    gamma: float = Field(ge=-1, le=1, description="Gamma sensitivity")
    theta: float = Field(ge=-1, le=1, description="Theta time decay")
    vega: float = Field(ge=-1, le=1, description="Vega volatility sensitivity")

    class Config:
        validate_assignment = True

class OptionLeg(BaseModel):
    """Pydantic model for option leg - validates IB data (Pattern 3 from research)."""
    leg_id: str = Field(..., min_length=1)
    strategy_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    strike: Decimal = Field(..., gt=0, description="Strike price")
    expiry: date = Field(..., description="Expiration date")
    right: OptionRight
    quantity: int = Field(..., ge=-1000, le=1000, description="Quantity (can be negative for short)")
    open_price: float = Field(..., ge=0, description="Average entry price")
    current_price: float = Field(..., ge=0, description="Current market price")
    greeks: Greeks
    status: PositionStatus

    @field_validator('strike')
    def validate_strike(cls, v):
        """Ensure strike is reasonable (Pitfall 3: validate external data)."""
        if v < 1 or v > 10000:
            raise ValueError("Strike price out of range (1-10000)")
        return v

    @field_validator('expiry')
    def validate_expiry(cls, v):
        """Ensure expiry is in future (Pitfall 3: validate external data)."""
        if v <= date.today():
            raise ValueError("Expiry must be in the future")
        return v

    class Config:
        validate_assignment = True  # Validate on every assignment
        json_encoders = {
            Decimal: float,
            date: str,
            datetime: str,
        }

class StrategyPosition(BaseModel):
    """Pydantic model for strategy position."""
    strategy_id: str = Field(..., min_length=1)
    strategy_type: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    status: PositionStatus
    entry_date: datetime
    exit_date: Optional[datetime] = None
    entry_price: float = Field(ge=0)
    exit_price: Optional[float] = None
    quantity: int
    greeks: Greeks
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0

    @field_validator('strategy_type')
    def validate_strategy_type(cls, v):
        """Validate strategy type."""
        valid_types = ["iron_condor", "vertical_spread", "calendar_spread", "butterfly", "strangle"]
        if v not in valid_types:
            raise ValueError(f"Invalid strategy type: {v}. Must be one of {valid_types}")
        return v

    class Config:
        validate_assignment = True
        json_encoders = {
            datetime: str,
        }

class GreeksSnapshot(BaseModel):
    """Pydantic model for Greeks snapshots (for time-travel analytics)."""
    strategy_id: str
    symbol: str
    greeks: Greeks
    portfolio_delta: float
    portfolio_gamma: float
    portfolio_theta: float
    portfolio_vega: float
    timestamp: datetime

class Trade(BaseModel):
    """Pydantic model for trade execution."""
    transaction_id: str = Field(..., min_length=1)
    strategy_id: str = Field(..., min_length=1)
    leg_id: str = Field(..., min_length=1)
    action: Literal["BUY", "SELL", "OPEN", "CLOSE"]
    quantity: int
    price: float
    commission: float = 0.0
    timestamp: datetime
```

**Key patterns from research:**
- **Pydantic for external data**: IB API responses can be malformed - always validate (Pitfall 3)
- **Field validation**: ge/le constraints, min_length, pattern matching
- **Custom validators**: Strike range, expiry in future
- **validate_assignment=True**: Validates on every assignment, not just init
- **json_encoders**: Proper serialization for Decimal, date, datetime

**Why Pydantic over dataclasses for IB data:**
- IB API data is external (can be malformed) - validation critical
- JSON schema generation for API contracts
- Type safety with field constraints
- Better error messages for validation failures
  </action>
  <verify>
    OptionLeg model validates strike range (1-10000), expiry in future
    Greeks model validates delta/gamma/theta/vega ranges (-1 to 1)
    StrategyPosition model validates strategy_type against allowed types
    All models have validate_assignment=True
    JSON encoding works for Decimal, date, datetime
  </verify>
  <done>
    OptionLeg model for option legs with validation
    Greeks model for Greeks with range validation
    StrategyPosition model for strategy positions
    GreeksSnapshot model for time-travel snapshots
    Trade model for trade executions
    All models use Pydantic with field validation and assignment validation
  </done>
</task>

<task type="auto">
  <name>Task 2: Create dataclasses for internal state</name>
  <files>src/v6/models/internal_state.py</files>
  <action>
Create dataclasses for high-performance internal state (Pattern 5 from research):

**File: src/v6/models/internal_state.py**
```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
from enum import Enum

class CircuitState(Enum):
    """Circuit breaker state."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

@dataclass(slots=True)
class PositionState:
    """Internal position state - faster than Pydantic (Pitfall 3: use dataclasses for internal state)."""
    symbol: str
    quantity: int
    entry_price: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    last_update: datetime = field(default_factory=datetime.now)

    def update_pnl(self) -> None:
        """Update unrealized P&L based on current price."""
        self.unrealized_pnl = (self.current_price - self.entry_price) * self.quantity
        self.last_update = datetime.now()

@dataclass(slots=True)
class PortfolioState:
    """Internal portfolio state - tracks all positions and portfolio-level Greeks."""
    positions: Dict[str, PositionState] = field(default_factory=dict)
    total_delta: float = 0.0
    total_gamma: float = 0.0
    total_theta: float = 0.0
    total_vega: float = 0.0
    cash_balance: float = 0.0
    last_update: datetime = field(default_factory=datetime.now)

    def add_position(self, state: PositionState) -> None:
        """Add or update position in portfolio."""
        self.positions[state.symbol] = state
        self._recalculate()

    def remove_position(self, symbol: str) -> None:
        """Remove position from portfolio."""
        if symbol in self.positions:
            del self.positions[symbol]
            self._recalculate()

    def _recalculate(self) -> None:
        """Recalculate portfolio Greeks and totals."""
        self.total_delta = sum(p.quantity * (p.current_price / 100) for p in self.positions.values())
        self.total_gamma = sum(p.quantity * 0.01 for p in self.positions.values())  # Simplified
        # Add theta, vega calculations as needed
        self.last_update = datetime.now()

    def get_position(self, symbol: str) -> Optional[PositionState]:
        """Get position by symbol."""
        return self.positions.get(symbol)

    def get_all_positions(self) -> List[PositionState]:
        """Get all positions as list."""
        return list(self.positions.values())

@dataclass
class ConnectionMetrics:
    """Internal connection metrics for monitoring."""
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
    """Top-level system state - tracks all internal state."""
    portfolio: PortfolioState = field(default_factory=PortfolioState)
    connection: ConnectionMetrics = field(default_factory=ConnectionMetrics)
    last_update: datetime = field(default_factory=datetime.now)
```

**Why dataclasses for internal state (Pitfall 3 from research):**
- **Faster than Pydantic**: No validation overhead
- **Simpler**: No validation needed for trusted internal data
- **Performance**: slots=True reduces memory usage
- **Use case**: Internal state that never leaves the process

**Decision tree from research:**
```
Does this data come from outside my process?
├─ Yes → Use Pydantic (validation critical)
└─ No → Use dataclass (performance matters)
```
  </action>
  <verify>
    PositionState has slots=True for performance
    PortfolioState manages positions Dict and recalculates Greeks
    ConnectionMetrics tracks connection health
    SystemState aggregates all internal state
    All dataclasses use @dataclass(slots=True) for performance
  </verify>
  <done>
    PositionState dataclass for individual position tracking
    PortfolioState dataclass for portfolio-level state and Greeks
    ConnectionMetrics dataclass for connection monitoring
    SystemState dataclass for top-level state aggregation
    All use slots=True for performance
  </done>
</task>

</tasks>

<verification>
Before declaring plan complete:
- [ ] All Pydantic models created with field validation
- [ ] OptionLeg validates strike (1-10000) and expiry (future)
- [ ] Greeks validates ranges (-1 to 1 for all Greeks)
- [   StrategyPosition validates strategy_type against allowed types
- [ ] All models have validate_assignment=True
- [ ] JSON encoders work for Decimal, date, datetime
- [ ] Dataclasses use slots=True for performance
- [ ] PositionState.update_pnl() calculates unrealized P&L correctly
- [ ] PortfolioState manages positions Dict and recalculates portfolio Greeks
</verification>

<success_criteria>
- All tasks completed
- Pydantic models provide validation for external IB data
- Dataclasses provide fast internal state management
- Clear separation: Pydantic (external) vs dataclasses (internal)
- Type safety across all data structures
- Phase 1 complete: Architecture & Infrastructure ready
</success_criteria>

<output>
After completion, create `v6/.planning/phases/1-architecture-infrastructure/1-04-SUMMARY.md`:

# Phase 1 Plan 4: Base Models Summary

**Implemented type-safe data structures with Pydantic validation for external data and dataclasses for internal state.**

## Accomplishments

- Created Pydantic models: OptionLeg, Greeks, StrategyPosition, GreeksSnapshot, Trade
- All Pydantic models have field validation (ranges, formats, required fields)
- Created dataclasses: PositionState, PortfolioState, ConnectionMetrics, SystemState
- All dataclasses use slots=True for performance
- Clear separation: Pydantic for external (IB data), dataclasses for internal (state)

## Files Created/Modified

- `src/v6/models/__init__.py` - Models package export
- `src/v6/models/ib_models.py` - Pydantic models for IB data
- `src/v6/models/internal_state.py` - Dataclasses for internal state

## Decisions Made

- **Pydantic for external data**: IB API responses require validation (Pitfall 3)
- **Dataclasses for internal state**: Faster, no validation overhead (Pitfall 3)
- **validate_assignment=True**: Validate on every assignment, not just init
- **slots=True**: Reduced memory usage for dataclasses
- **Field constraints**: Strike range (1-10000), Greeks range (-1 to 1), expiry in future
- **Strategy types**: iron_condor, vertical_spread, calendar_spread, butterfly, strangle

## Issues Encountered

None

## Next Phase

Phase 1 complete: Architecture & Infrastructure

**Next:** Phase 2: Position Synchronization (01-01-PLAN.md)
</output>
