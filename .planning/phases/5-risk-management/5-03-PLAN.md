---
phase: 5-risk-management
plan: 03
type: execute
depends_on: []
files_modified: [src/v6/risk/trailing_stop.py, src/v6/risk/__init__.py, src/v6/workflows/monitoring.py, src/v6/workflows/exit.py]
---

<objective>
Implement position-level trailing stops with whipsaw protection for profit protection.

Purpose: Lock in profits on winning positions by dynamically adjusting stop-loss as price moves favorably. Implement whipsaw protection to avoid premature exits in choppy markets.

Output: TrailingStop and TrailingStopManager integrated with monitoring and exit workflows.
</objective>

<execution_context>
~/.claude/get-shit-done/workflows/execute-plan.md
./summary.md
</execution_context>

<context>
@v6/.planning/PROJECT.md
@v6/.planning/ROADMAP.md
@v6/.planning/phases/5-risk-management/5-RESEARCH.md
@v6/.planning/phases/4-strategy-execution/4-03-SUMMARY.md
@v6/src/v6/workflows/monitoring.py
@v6/src/v6/workflows/exit.py
@v6/src/v6/strategies/models.py

**Research findings (from 5-RESEARCH.md):**
- Must implement whipsaw protection (activation threshold, trailing distance, minimum move)
- Research-backed defaults: activation 2%, trailing 1.5%, min move 0.5%
- Anti-pattern: Using IB trailing orders directly (loses logic-side control)
- Don't hand-roll: None for trailing stops (must implement custom for options Greeks)
- Key insight: Trailing stops based on OPTIONS PREMIUM (not underlying price)

**Existing components to integrate:**
- PositionMonitoringWorkflow.monitor_position() → add trailing stop update
- ExitWorkflow.execute_exit_decision() → handle trailing stop trigger
- Strategy model with current_premium, entry_price

**Standard stack from research:**
- dataclass(slots=True): For performance
- No external library needed (custom implementation required)
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create TrailingStop models and logic</name>
  <files>src/v6/risk/trailing_stop.py, src/v6/risk/__init__.py</files>
  <action>Create new module src/v6/risk/trailing_stop.py with:

1. TrailingStopAction Enum:
   from enum import Enum, auto
   class TrailingStopAction(Enum):
       HOLD = auto()        # No change
       ACTIVATE = auto()    # Stop activated (first time)
       UPDATE = auto()      # Stop price updated
       TRIGGER = auto()     # Stop triggered (exit position)

2. TrailingStopConfig dataclass(slots=True):
   activation_pct: float = 2.0     # Move X% before activating
   trailing_pct: float = 1.5       # Trail by Y% from peak
   min_move_pct: float = 0.5       # Minimum move to update stop

3. TrailingStop dataclass(slots=True):
   entry_premium: float             # Entry price (premium received/paid)
   highest_premium: float           # Track peak premium
   stop_premium: float | None       # Current stop level (None = not activated)
   is_active: bool = False          # Whether trailing stop is activated
   config: TrailingStopConfig

   Methods:
   a) def update(self, current_premium: float) -> tuple[float | None, TrailingStopAction]:
       """Update trailing stop based on current premium.

       Returns: (new_stop_premium, action)
       """
       Implementation:
       i) Update peak: if current_premium > self.highest_premium:
              self.highest_premium = current_premium

       ii) Check activation threshold:
           if not self.is_active:
               move_pct = (self.highest_premium - self.entry_premium) / self.entry_premium * 100
               if move_pct >= self.config.activation_pct:
                   self.is_active = True
                   self.stop_premium = self.highest_premium * (1 - self.config.trailing_pct / 100)
                   return self.stop_premium, TrailingStopAction.ACTIVATE
               return None, TrailingStopAction.HOLD

       iii) Update trailing stop if price moved enough:
           new_stop = self.highest_premium * (1 - self.config.trailing_pct / 100)
           move_from_current = abs(new_stop - self.stop_premium) / self.stop_premium * 100 if self.stop_premium else 0

           if move_from_current >= self.config.min_move_pct:
               self.stop_premium = new_stop
               return self.stop_premium, TrailingStopAction.UPDATE

       iv) Check if stop triggered:
           if current_premium <= self.stop_premium:
               return self.stop_premium, TrailingStopAction.TRIGGER

       v) Default: return self.stop_premium, TrailingStopAction.HOLD

   b) def reset(self) -> None:
       """Reset trailing stop to inactive state."""
       Set is_active=False, stop_premium=None

4. Update src/v6/risk/__init__.py:
   Export TrailingStopAction, TrailingStopConfig, TrailingStop

Use @dataclass(slots=True) for performance.
Add comprehensive docstrings.
Key: Trailing based on OPTIONS PREMIUM (not underlying price) - this is critical for options trading.
</action>
  <verify>python -c "from src.v6.risk.trailing_stop import TrailingStop, TrailingStopConfig; stop = TrailingStop(entry_premium=100.0); print('Import successful')"</verify>
  <done>TrailingStop with whipsaw protection, activation/trailing/min-move thresholds, 15+ unit tests covering HOLD/ACTIVATE/UPDATE/TRIGGER actions</done>
</task>

<task type="auto">
  <name>Task 2: Implement TrailingStopManager</name>
  <files>src/v6/risk/trailing_stop.py</files>
  <action>Add TrailingStopManager class to src/v6/risk/trailing_stop.py:

Class TrailingStopManager:
  Attributes:
    stops: dict[str, TrailingStop]  # execution_id -> TrailingStop
    config: TrailingStopConfig       # Default config for new stops

  Methods:
  1. def __init__(self, default_config: TrailingStopConfig)
     Initialize empty stops dict, store default config

  2. def add_trailing_stop(
       self,
       execution_id: str,
       entry_premium: float,
       config: TrailingStopConfig | None = None
   ) -> TrailingStop:
     """Add trailing stop to position."""
     Use provided config or default config
     Create TrailingStop with entry_premium
     Store in stops dict
     Return TrailingStop instance

  3. async def update_stops(
       self,
       current_premiums: dict[str, float]
   ) -> dict[str, tuple[float, TrailingStopAction]]:
     """Update all trailing stops based on current premiums.

     Args:
         current_premiums: execution_id -> current premium (mark-to-market)

     Returns:
         dict mapping execution_id -> (stop_premium, action)
     """
     Implementation:
     a) results = {}
     b) For each execution_id, stop in self.stops:
        current_premium = current_premiums.get(execution_id)
        if current_premium is None:
            continue  # Skip if no premium data

        new_stop, action = stop.update(current_premium)
        results[execution_id] = (new_stop, action)

        if action == TrailingStopAction.TRIGGER:
            logger.info(f"Trailing stop TRIGGERED for {execution_id}: {new_stop:.2f}")
        elif action == TrailingStopAction.ACTIVATE:
            logger.info(f"Trailing stop ACTIVATED for {execution_id}: {new_stop:.2f}")
        elif action == TrailingStopAction.UPDATE:
            logger.debug(f"Trailing stop UPDATED for {execution_id}: {new_stop:.2f}")

     c) Return results

  4. def get_stop(self, execution_id: str) -> TrailingStop | None:
     """Get trailing stop for position."""
     Return self.stops.get(execution_id)

  5. def remove_stop(self, execution_id: str) -> None:
     """Remove trailing stop (position closed)."""
     Delete from self.stops dict if exists

  6. def get_all_stops(self) -> dict[str, TrailingStop]:
     """Get all trailing stops."""
     Return self.stops

  7. def reset_stop(self, execution_id: str) -> None:
     """Reset trailing stop to inactive (for manual override)."""
     Call stop.reset() if exists

Handle edge cases: missing execution_id, no premium data, already removed stops.
Add comprehensive docstrings.
Use async for update_stops (consistent with v6 async patterns).
</action>
  <verify>python -m pytest tests/risk/test_trailing_stop.py -v</verify>
  <done>TrailingStopManager with add/remove/update/reset operations, 20+ unit tests covering multi-position management, premium updates, stop lifecycle</done>
</task>

<task type="auto">
  <name>Task 3: Integrate TrailingStopManager with workflows</name>
  <files>src/v6/workflows/monitoring.py, src/v6/workflows/exit.py, src/v6/risk/__init__.py</files>
  <action>Update monitoring and exit workflows to integrate trailing stops:

**Part A: Update PositionMonitoringWorkflow (src/v6/workflows/monitoring.py)**

1. Import TrailingStopManager, TrailingStopConfig, TrailingStopAction from src.v6.risk

2. Update PositionMonitoringWorkflow.__init__():
   Add parameter: trailing_stops: TrailingStopManager | None = None
   Store as self.trailing_stops

3. Update PositionMonitoringWorkflow.monitor_position() method:
   AFTER fetching position snapshot, BEFORE evaluating decision rules:

   a) Get current premium from snapshot:
      current_premium = snapshot.current_premium  (or calculate if not present)

   b) Update trailing stop (if manager exists and stop added):
      if self.trailing_stops:
          stop = self.trailing_stops.get_stop(execution_id)
          if stop:
              new_stop, action = stop.update(current_premium)

              if action == TrailingStopAction.TRIGGER:
                  # Create CLOSE decision with trailing stop reason
                  return Decision(
                      action=DecisionAction.CLOSE,
                      reason=f"Trailing stop triggered at {new_stop:.2f}",
                      rule_name="TrailingStop",
                      urgency=AlertUrgency.IMMEDIATE
                  )

              elif action == TrailingStopAction.ACTIVATE:
                  logger.info(f"Trailing stop activated for {execution_id} at {new_stop:.2f}")
                  # Optional: Create alert for activation

              elif action == TrailingStopAction.UPDATE:
                  logger.debug(f"Trailing stop updated for {execution_id} to {new_stop:.2f}")

   c) Continue with normal decision evaluation (DecisionEngine)

4. Add method to enable trailing stop for position:
   def enable_trailing_stop(
       self,
       execution_id: str,
       entry_premium: float,
       config: TrailingStopConfig | None = None
   ) -> None:
       """Enable trailing stop for position."""
       if self.trailing_stops:
           self.trailing_stops.add_trailing_stop(execution_id, entry_premium, config)

**Part B: Update ExitWorkflow (src/v6/workflows/exit.py)**

1. Import TrailingStopManager from src.v6.risk

2. Update ExitWorkflow.execute_exit_decision() method:
   AFTER closing position, BEFORE returning:

   a) Remove trailing stop if exists:
      if hasattr(self, 'trailing_stops') and self.trailing_stops:
          self.trailing_stops.remove_stop(execution_id)
          logger.debug(f"Removed trailing stop for {execution_id}")

**Part C: Update tests**

1. Update PositionMonitoringWorkflow tests:
   - Add test enabling trailing stop
   - Add test verifying ACTIVATE action
   - Add test verifying UPDATE action
   - Add test verifying TRIGGER action creates CLOSE decision
   - Add test with no trailing stop (backward compatible)

2. Update ExitWorkflow tests:
   - Add test that trailing stop is removed after CLOSE

Ensure workflows work without trailing_stops (backward compatible).
Default config: activation_pct=2.0, trailing_pct=1.5, min_move_pct=0.5
</action>
  <verify>python -m pytest tests/workflows/test_monitoring.py::test_trailing_stop_trigger -v
python -m pytest tests/workflows/test_monitoring.py::test_trailing_stop_activate -v
python -m pytest tests/workflows/test_exit.py::test_trailing_stop_removed_on_close -v</verify>
  <done>TrailingStopManager integrated with monitoring workflow, stops trigger CLOSE decisions, stops removed after exit, tests verify complete lifecycle (enable→activate→update→trigger→remove)</done>
</task>

</tasks>

<verification>
Before declaring plan complete:
- [ ] All tests pass (python -m pytest tests/risk/ tests/workflows/ -v)
- [ ] ruff linting passes (ruff check src/v6/risk/)
- [ ] TrailingStop whipsaw protection works correctly
- [ ] TrailingStopManager manages multiple positions
- [ ] PositionMonitoringWorkflow triggers CLOSE on TRIGGER
- [ ] ExitWorkflow removes stops after close
- [ ] Backward compatible (workflows work without trailing_stops)
- [ ] Type hints on all functions
- [ ] Comprehensive docstrings
</verification>

<success_criteria>

- TrailingStop with whipsaw protection (activation, trailing, min-move)
- TrailingStopManager for multi-position management
- Integration with PositionMonitoringWorkflow (updates and triggers)
- Integration with ExitWorkflow (cleanup on close)
- Trailing based on OPTIONS PREMIUM (not underlying price)
- Comprehensive unit and integration tests
- Backward compatibility maintained
  </success_criteria>

<output>
After completion, create `v6/.planning/phases/5-risk-management/5-03-SUMMARY.md`:

# Phase 5 Plan 3: Advanced Exit Rules Summary

**Implemented position-level trailing stops with whipsaw protection for profit management.**

## Accomplishments

- TrailingStop with activation/trailing/min-move thresholds
- TrailingStopManager for multi-position management
- TrailingStopAction enum (HOLD, ACTIVATE, UPDATE, TRIGGER)
- Integration with PositionMonitoringWorkflow for automatic updates
- Integration with ExitWorkflow for cleanup
- Comprehensive tests covering all lifecycle states

## Files Created/Modified

- `src/v6/risk/trailing_stop.py` - Trailing stop implementation
- `src/v6/risk/__init__.py` - Module exports
- `src/v6/workflows/monitoring.py` - Integrated trailing stop updates
- `src/v6/workflows/exit.py` - Integrated trailing stop cleanup
- `tests/risk/test_trailing_stop.py` - Unit tests
- `tests/workflows/test_monitoring.py` - Updated integration tests

## Decisions Made

- Trailing based on OPTIONS PREMIUM (not underlying price)
- Whipsaw protection: activation 2%, trailing 1.5%, min move 0.5%
- Backward compatible (workflows work without trailing_stops)
- Trigger creates CLOSE decision with IMMEDIATE urgency
- Custom implementation (IB trailing orders lose logic-side control)

## Phase 5 Complete!

All 3 plans completed:
- ✅ 5-01: Portfolio-level controls (delta, gamma, exposure, concentration)
- ✅ 5-02: Circuit breakers and auto-hedge (system fault tolerance)
- ✅ 5-03: Advanced exit rules (trailing stops with whipsaw protection)

## Next Steps

Ready for Phase 6 (Monitoring Dashboard) or production enhancements
</output>
