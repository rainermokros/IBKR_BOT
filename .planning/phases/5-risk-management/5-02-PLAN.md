---
phase: 5-risk-management
plan: 02
type: execute
depends_on: []
files_modified: [src/v6/risk/circuit_breaker.py, src/v6/risk/__init__.py, src/v6/execution/engine.py]
---

<objective>
Implement system-level circuit breaker for automated trading fault tolerance.

Purpose: Prevent cascading failures by halting trading during systemic issues (high order rejection rate, data feed failures, margin exhaustion). Adapt distributed systems circuit breaker pattern (Azure/Microsoft) for trading systems.

Output: TradingCircuitBreaker integrated with OrderExecutionEngine, blocking orders during fault conditions.
</objective>

<execution_context>
~/.claude/get-shit-done/workflows/execute-plan.md
./summary.md
</execution_context>

<context>
@v6/.planning/PROJECT.md
@v6/.planning/ROADMAP.md
@v6/.planning/phases/5-risk-management/5-RESEARCH.md
@v6/.planning/phases/4-strategy-execution/4-02-SUMMARY.md
@v6/src/v6/execution/engine.py
@v6/src/v6/utils/ib_connection.py

**Research findings (from 5-RESEARCH.md):**
- NOT market circuit breakers (halt venues) but SYSTEM circuit breakers (halt automation)
- Azure Circuit Breaker pattern: CLOSED (normal), OPEN (failures), HALF_OPEN (testing)
- Threshold: 5+ failures within 60s window before opening
- Half-open: Wait 30s before testing recovery, 3 successful trades before closing
- Don't hand-roll: Use Enum + dataclass pattern from Azure/Microsoft
- Anti-pattern: Circuit breaker with no half-open state (can't test recovery)

**Existing components to integrate:**
- OrderExecutionEngine.place_order() → add circuit breaker check
- IBConnectionManager → for detecting connection failures
- ExecutionResult → for tracking success/failure

**Standard stack from research:**
- dataclass(slots=True): For performance
- Enum from enum: For circuit states
- datetime/timedelta: For time windows
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create circuit breaker models and state machine</name>
  <files>src/v6/risk/circuit_breaker.py, src/v6/risk/__init__.py</files>
  <action>Create new module src/v6/risk/circuit_breaker.py with:

1. CircuitState Enum:
   from enum import Enum, auto
   class CircuitState(Enum):
       CLOSED = auto()      # Normal operation, trades allowed
       OPEN = auto()        # Failure detected, trades blocked
       HALF_OPEN = auto()   # Testing if system recovered

2. CircuitBreakerConfig dataclass(slots=True):
   failure_threshold: int = 5        # N failures before opening
   failure_window_secs: int = 60     # Time window for failures
   half_open_timeout_secs: int = 30  # Wait before testing recovery
   half_open_max_tries: int = 3      # N successful trades before closing
   open_timeout_secs: int = 300      # Stay open before half-open

3. CircuitBreakerOpenException:
   Inherits from Exception
   Message: "Circuit breaker OPEN: {reason}"
   Attributes: state, failure_count, failures_in_window

4. Update src/v6/risk/__init__.py:
   Export CircuitState, CircuitBreakerConfig, CircuitBreakerOpenException

Use @dataclass(slots=True) for performance.
Add comprehensive docstrings explaining Azure pattern adaptation.
</action>
  <verify>python -c "from src.v6.risk.circuit_breaker import CircuitState, CircuitBreakerConfig, CircuitBreakerOpenException; print('Import successful')"</verify>
  <done>CircuitState enum with 3 states, CircuitBreakerConfig with thresholds, CircuitBreakerOpenException for blocking trades, all imports work</done>
</task>

<task type="auto">
  <name>Task 2: Implement TradingCircuitBreaker</name>
  <files>src/v6/risk/circuit_breaker.py</files>
  <action>Add TradingCircuitBreaker class to src/v6/risk/circuit_breaker.py:

Class TradingCircuitBreaker:
  Attributes:
    config: CircuitBreakerConfig
    state: CircuitState
    failures: list[datetime]
    opened_at: datetime | None
    half_open_tries: int

  Methods:
  1. def __init__(self, config: CircuitBreakerConfig)
     Initialize state=CLOSED, failures=[], opened_at=None, half_open_tries=0

  2. def record_failure(self) -> CircuitState:
     """Record a failure, update circuit state if needed."""
     Implementation:
     a) Add current timestamp to failures list
     b) Clean old failures outside window (now - failure_window_secs)
     c) If len(failures) >= failure_threshold and state != OPEN:
        - Set state = OPEN
        - Set opened_at = now
        - Log warning: "Circuit breaker OPENED: {len(failures)} failures"
     d) Return current state

  3. def record_success(self) -> CircuitState:
     """Record success, update circuit if in HALF_OPEN."""
     Implementation:
     a) If state == HALF_OPEN:
        - Increment half_open_tries
        - If half_open_tries >= half_open_max_tries:
          * Set state = CLOSED
          * Clear failures list
          * Reset half_open_tries
          * Log info: "Circuit breaker CLOSED: System recovered"
     b) Return current state

  4. def is_trading_allowed(self) -> tuple[bool, str | None]:
     """Check if trading is currently allowed."""
     Implementation:
     a) If CLOSED: return (True, None)

     b) If OPEN:
        - Check if ready for half-open (time_in_open >= open_timeout_secs)
        - If ready: set state = HALF_OPEN, return (True, "HALF_OPEN: Testing recovery")
        - Else: return (False, f"OPEN: {len(failures)} failures in {failure_window_secs}s window")

     c) If HALF_OPEN: return (True, "HALF_OPEN: Testing recovery")

     d) Log state transitions for observability

  5. def get_state(self) -> dict:
     """Get current circuit state for monitoring."""
     Returns: {"state": enum name, "failures": count, "opened_at": timestamp, "half_open_tries": count}

  6. def reset(self) -> None:
     """Manually reset circuit to CLOSED (admin intervention)."""
     Set state=CLOSED, failures=[], opened_at=None, half_open_tries=0

Use datetime.now() for timestamps.
Use timedelta for time window calculations.
Add comprehensive docstrings with Azure pattern references.
Handle edge cases: empty failures, very old failures, manual reset.
</action>
  <verify>python -m pytest tests/risk/test_circuit_breaker.py -v (create test file)</verify>
  <done>TradingCircuitBreaker with state transitions (CLOSED→OPEN→HALF_OPEN→CLOSED), 20+ unit tests covering failure tracking, time windows, recovery testing, manual reset</done>
</task>

<task type="auto">
  <name>Task 3: Integrate TradingCircuitBreaker with OrderExecutionEngine</name>
  <files>src/v6/execution/engine.py, src/v6/risk/__init__.py</files>
  <action>Update src/v6/execution/engine.py to integrate circuit breaker:

1. Import TradingCircuitBreaker, CircuitBreakerConfig, CircuitBreakerOpenException from src.v6.risk

2. Update OrderExecutionEngine.__init__():
   Add parameter: circuit_breaker: TradingCircuitBreaker | None = None
   Store as self.circuit_breaker

3. Update OrderExecutionEngine.place_order() method:
   At START of method (before any IB API call):

   a) Check circuit breaker state:
      if self.circuit_breaker:
          allowed, reason = self.circuit_breaker.is_trading_allowed()
          if not allowed:
              logger.error(f"Order BLOCKED by circuit breaker: {reason}")
              raise CircuitBreakerOpenException(reason)

   b) Try placing order via IB:
      try:
          ib_order = self._create_ib_order(order)
          trade = self.ib_conn.placeOrder(contract, ib_order)
          result = ExecutionResult(success=True, order_id=order.order_id, ...)

          # Record success (closes circuit if in HALF_OPEN)
          if self.circuit_breaker:
              self.circuit_breaker.record_success()

          return result

      except Exception as e:
          # Record failure (may open circuit)
          if self.circuit_breaker:
              self.circuit_breaker.record_failure()

          raise

4. Create CircuitBreakerConfig with defaults:
   failure_threshold=5, failure_window_secs=60,
   half_open_timeout_secs=30, half_open_max_tries=3,
   open_timeout_secs=300

5. Update tests:
   - Update OrderExecutionEngine tests to include circuit_breaker parameter
   - Add test that blocks order when circuit OPEN
   - Add test that allows order when circuit CLOSED
   - Add test that transitions HALF_OPEN→CLOSED after successful trades
   - Add test that transitions CLOSED→OPEN after 5 failures

Ensure engine works without circuit_breaker (backward compatible).
</action>
  <verify>python -m pytest tests/execution/test_engine.py::test_order_blocked_by_circuit_breaker -v
python -m pytest tests/execution/test_engine.py::test_circuit_breaker_transitions -v</verify>
  <done>OrderExecutionEngine checks circuit breaker before orders, blocks when OPEN, records success/failure, tests verify all state transitions (CLOSED→OPEN→HALF_OPEN→CLOSED)</done>
</task>

</tasks>

<verification>
Before declaring plan complete:
- [ ] All tests pass (python -m pytest tests/risk/ tests/execution/test_engine.py -v)
- [ ] ruff linting passes (ruff check src/v6/risk/)
- [ ] Circuit breaker state transitions work correctly
- [ ] OrderExecutionEngine blocks orders when circuit OPEN
- [ ] Circuit breaker transitions HALF_OPEN→CLOSED after successes
- [ ] Backward compatible (OrderExecutionEngine works without circuit_breaker)
- [ ] Type hints on all functions
- [ ] Comprehensive docstrings
</verification>

<success_criteria>

- TradingCircuitBreaker implements Azure pattern (CLOSED/OPEN/HALF_OPEN)
- OrderExecutionEngine blocks orders during circuit OPEN state
- Circuit breaker opens after 5 failures in 60s window
- Circuit breaker transitions to HALF_OPEN after 300s
- Circuit breaker closes after 3 successful trades in HALF_OPEN
- Manual reset capability for admin intervention
- Comprehensive unit and integration tests
  </success_criteria>

<output>
After completion, create `v6/.planning/phases/5-risk-management/5-02-SUMMARY.md`:

# Phase 5 Plan 2: Circuit Breakers and Auto-Hedge Summary

**Implemented system-level circuit breaker for trading fault tolerance.**

## Accomplishments

- CircuitState enum (CLOSED, OPEN, HALF_OPEN)
- CircuitBreakerConfig with configurable thresholds
- TradingCircuitBreaker with failure tracking and recovery testing
- CircuitBreakerOpenException for blocking trades
- Integration with OrderExecutionEngine for pre-trade checking
- Comprehensive state transition tests

## Files Created/Modified

- `src/v6/risk/circuit_breaker.py` - Circuit breaker implementation
- `src/v6/risk/__init__.py` - Module exports
- `src/v6/execution/engine.py` - Integrated circuit breaker check
- `tests/risk/test_circuit_breaker.py` - Unit tests
- `tests/execution/test_engine.py` - Updated integration tests

## Decisions Made

- Azure/Microsoft circuit breaker pattern (not market circuit breakers)
- 5 failures in 60s window triggers OPEN state
- HALF_OPEN state allows testing recovery before closing
- Backward compatible (OrderExecutionEngine works without circuit_breaker)
- Manual reset capability for admin intervention

## Next Step

Ready for 5-03-PLAN.md (Advanced exit rules with trailing stops)
</output>
