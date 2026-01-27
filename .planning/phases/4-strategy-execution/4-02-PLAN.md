---
phase: 4-strategy-execution
plan: 02
type: execute
depends_on: ["4-01"]
files_modified: [src/v6/execution/__init__.py, src/v6/execution/models.py, src/v6/execution/engine.py, src/v6/execution/test_engine.py]
domain: ib-order-manager
---

<objective>
Implement IB order execution engine with order placement, OCA groups, and bracket orders.

Purpose: Create execution engine that places orders through IB API, manages order lifecycle, handles errors, and supports advanced order types (OCA groups, bracket orders) for automated trading.

Output: OrderExecutionEngine with IB API integration, order models, OCA/bracket support, and unit tests.
</objective>

<execution_context>
~/.claude/get-shit-done/workflows/execute-plan.md
~/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/4-strategy-execution/4-01-SUMMARY.md (should exist after 4-01 completes)
@../v5/caretaker/execution_engine.py (v5 reference for patterns)
@src/v6/strategies/builders.py (Strategy builders from 4-01)
@src/v6/strategies/models.py (Strategy models)
@src/v6/decisions/models.py (Decision models from Phase 3)
@~/.claude/skills/expertise/ib-order-manager/SKILL.md (IB order management domain knowledge)

**Tech stack available:**
- ib_async for IB API integration (from Phase 1)
- Delta Lake for persistence (from Phase 2)
- DecisionEngine and rules (from Phase 3)
- Strategy builders and models (from 4-01)

**Established patterns:**
- Singleton pattern for IB connection (from Phase 1)
- dataclass(slots=True) for performance (from Phase 1)
- Protocol-based interfaces (from Phase 3)
- Async/await throughout (from Phase 2)

**IB order management key principles (from skill):**
- Contract + Order = Complete order (never submit one without the other)
- Client IDs and OrderIds critical (track persistent OrderId counter)
- Order states: PendingSubmit → Submitted → Filled/Cancelled/Inactive
- transmit=False for bracket child orders, transmit parent last
- OCA groups: One-Cancels-All (alternative orders)
- Bracket orders: Parent + TP/SL children, auto-managed by IB
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create order models and enums</name>
  <files>src/v6/execution/models.py</files>
  <action>
Create order data models and enums:

**1. Enums:**
- **OrderStatus**: PENDING_SUBMIT, SUBMITTED, FILLED, CANCELLED, INACTIVE, REJECTED
- **OrderType**: MARKET, LIMIT, STOP, STOP_LIMIT, TRAIL, TRAIL_LIMIT
- **OrderAction**: BUY, SELL
- **TimeInForce**: DAY, GTC, IOC, OPG

**2. Order dataclass (slots=True):**
- order_id: str (UUID)
- conid: int | None (IB contract ID)
- action: OrderAction
- quantity: int
- order_type: OrderType
- limit_price: float | None
- stop_price: float | None
- tif: TimeInForce
- status: OrderStatus
- filled_quantity: int
- avg_fill_price: float | None
- order_ref: ib_async.Order | None (IB order object)
- parent_order_id: str | None (for bracket orders)
- oca_group: str | None (One-Cancels-All group ID)
- created_at: datetime
- filled_at: datetime | None

**3. BracketOrder dataclass (slots=True):**
- parent_order: Order (entry order)
- take_profit: Order | None (TP order)
- stop_loss: Order | None (SL order)
- oca_group: str (group linking all orders)

**4. ExecutionResult dataclass (slots=True):**
- success: bool
- action_taken: str (CLOSED, ROLLED, PARTIAL, FAILED)
- order_ids: list[str]
- error_message: str | None

Use @dataclass(slots=True). Add validation in __post_init__ (quantity > 0, limit_price >= 0 for BUY, etc.).
  </action>
  <verify>
python -c "
from src.v6.execution.models import Order, OrderStatus, OrderType
from datetime import datetime
order = Order(
    order_id='test-123',
    conid=123456,
    action='BUY',
    quantity=1,
    order_type='LIMIT',
    limit_price=100.0,
    stop_price=None,
    tif='DAY',
    status='PENDING_SUBMIT',
    filled_quantity=0,
    avg_fill_price=None,
    order_ref=None,
    parent_order_id=None,
    oca_group=None,
    created_at=datetime.now()
)
print(order)
" executes without errors
  </verify>
  <done>
All enums and models created, validation works, type hints complete
  </done>
</task>

<task type="auto">
  <name>Task 2: Create OrderExecutionEngine with IB API integration</name>
  <files>src/v6/execution/engine.py, src/v6/execution/__init__.py</files>
  <action>
Create OrderExecutionEngine class with IB API integration:

**Class structure:**
```python
class OrderExecutionEngine:
    def __init__(self, ib_conn: IBConnectionManager, dry_run: bool = False)
    async def place_order(self, contract: ib_async.Contract, order: Order) -> Order
    async def cancel_order(self, order_id: str) -> bool
    async def place_bracket_order(self, bracket: BracketOrder) -> ExecutionResult
    async def close_position(self, strategy: Strategy) -> ExecutionResult
    async def roll_position(self, strategy: Strategy, new_dte: int) -> ExecutionResult
```

**Key features:**
1. **place_order()**:
   - Set order.orderRef.transmit = True
   - Call ib.placeOrder(contract, order.orderRef)
   - Track order_id (save to local tracking)
   - Return updated Order with IB orderId
   - Handle errors (reject, connection failure)

2. **cancel_order()**:
   - Call ib.cancelOrder(orderId)
   - Update order status to CANCELLED
   - Return True if success

3. **place_bracket_order()**:
   - Create parent order (entry) + TP order + SL order
   - Set transmit=False for TP/SL (child orders)
   - Set oca_group on all orders (same group ID)
   - Link TP/SL to parent via parent_order_id
   - Transmit parent last (triggers TP/SL transmission)
   - Return ExecutionResult with all order IDs

4. **close_position()**:
   - Fetch strategy legs from StrategyRepository
   - Place opposite orders for each open leg
   - Use Market orders for immediate close
   - Update leg status in repository
   - Return ExecutionResult

5. **roll_position()**:
   - Close existing position (call close_position())
   - Build new strategy with same parameters, new DTE
   - Enter new position (place orders for new legs)
   - Return ExecutionResult with "ROLLED" action

**Error handling:**
- Catch ib_async errors
- Map to ExecutionResult with success=False
- Include error_message in result
- Log all errors for debugging

**dry_run mode:**
- If dry_run=True, simulate order placement without IB API calls
- Return mock order IDs (format: "DRY_{leg_id}_{timestamp}")
- Return ExecutionResult with success=True, action_taken=DRY_RUN

Reference ../v5/caretaker/execution_engine.py for patterns, adapt to v6 async architecture. Use IBConnectionManager from Phase 1.
  </action>
  <verify>
python -c "
from src.v6.execution.engine import OrderExecutionEngine
from src.v6.utils.ib_connection import IBConnectionManager
print('OrderExecutionEngine imports successfully')
" executes without errors
  </verify>
  <done>
OrderExecutionEngine created, place_order() works with IB API, cancel_order() works, bracket orders work with OCA groups, error handling implemented
  </done>
</task>

<task type="auto">
  <name>Task 3: Create unit tests for OrderExecutionEngine</name>
  <files>src/v6/execution/test_engine.py</files>
<action>
Create comprehensive unit tests:

**Test cases:**
1. **test_place_market_order**: Place market order → verify order placed, status updated
2. **test_place_limit_order**: Place limit order → verify order details, limit price set
3. **test_cancel_order**: Place order → cancel → verify status CANCELLED
4. **test_bracket_order_placement**: Place bracket order → verify OCA group, TP/SL linked to parent
5. **test_close_position**: Create strategy with legs → close_position() → opposite orders placed
6. **test_roll_position**: Create strategy → roll_position() → old closed, new opened
7. **test_error_handling**: Invalid order (negative quantity) → ExecutionResult with success=False
8. **test_dry_run_mode**: dry_run=True → no IB API calls, mock order IDs returned

**Mock IB connection:**
- Mock IBConnectionManager
- Mock ib.placeOrder to return mock trade with orderId
- Mock ib.cancelOrder to return True

Use pytest with async tests. Mock IB API responses. Run with: `conda run -n ib pytest src/v6/execution/test_engine.py -v`
  </action>
  <verify>
conda run -n ib pytest src/v6/execution/test_engine.py -v shows all tests passing (8+ passed)
  </verify>
  <done>
All 8 tests pass, order placement works, cancellation works, bracket orders created correctly, error handling returns ExecutionResult with details
  </done>
</task>

</tasks>

<verification>
Before declaring plan complete:
- [ ] `conda run -n ib pytest src/v6/execution/test_engine.py -v` - all tests pass
- [ ] `python -c "from src.v6.execution import OrderExecutionEngine; print('Import success')"` - imports work
- [ ] place_order() integrates with IB API
- [ ] cancel_order() updates order status
- [ ] Bracket orders create OCA group correctly
- [ ] close_position() places opposite orders for all legs
- [ ] roll_position() closes old and opens new
- [ ] Error handling returns ExecutionResult with error details
- [ ] dry_run mode simulates without IB API calls
</verification>

<success_criteria>

- Order models created (Order, BracketOrder, ExecutionResult)
- OrderExecutionEngine with IB API integration
- Bracket order support (OCA groups, TP/SL)
- Position close and roll functionality
- Error handling with ExecutionResult
- Unit tests passing (8+ tests)
- No linting errors
  </success_criteria>

<output>
After completion, create `.planning/phases/4-strategy-execution/4-02-SUMMARY.md`:

# Phase 4 Plan 2: IB Order Execution Engine Summary

**Implemented IB order execution engine with OCA groups and bracket orders.**

## Accomplishments

- Order models (Order, BracketOrder, ExecutionResult)
- OrderExecutionEngine with IB API integration
- Bracket order support (OCA groups, take profit, stop loss)
- Position close and roll functionality
- Error handling with detailed ExecutionResult
- Dry run mode for testing
- Unit tests (8 tests, all passing)

## Files Created/Modified

- `src/v6/execution/models.py` - Order data models
- `src/v6/execution/engine.py` - OrderExecutionEngine
- `src/v6/execution/__init__.py` - Package exports
- `src/v6/execution/test_engine.py` - Unit tests

## Deviations from Plan

None - plan executed as specified.

## Next Step

Ready for 4-03-PLAN.md (Entry and exit workflows)
</output>
