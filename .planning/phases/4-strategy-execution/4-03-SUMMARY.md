# Phase 4 Plan 3: Entry and Exit Workflows Summary

**Implemented complete entry and exit workflows connecting all components.**

## Accomplishments

- EntryWorkflow (signal evaluation, strategy building, order placement)
- PositionMonitoringWorkflow (position monitoring, decision evaluation, alerts)
- ExitWorkflow (execute exit decisions, close all positions)
- Integration tests (11 tests, all passing)
- End-to-end workflow tested
- Fixed StrategyRepository to set close_time on status=CLOSED

## Files Created/Modified

- `src/v6/workflows/entry.py` - Entry workflow (410 lines)
- `src/v6/workflows/monitoring.py` - Monitoring workflow (280 lines)
- `src/v6/workflows/exit.py` - Exit workflow (350 lines)
- `src/v6/workflows/__init__.py` - Package exports
- `src/v6/workflows/test_workflows.py` - Integration tests (550 lines)
- `src/v6/strategies/repository.py` - Added close_time handling

## Technical Details

### EntryWorkflow

**Purpose:** Evaluate entry signals, build strategies, execute entry orders

**Key Features:**
- `evaluate_entry_signal()`: Checks market conditions
  - IV Rank >50 (sell premium) or <25 (buy premium)
  - VIX <35 (not extreme volatility)
  - Portfolio delta < max_portfolio_delta
  - Position count < max_positions_per_symbol
  - Underlying price validation

- `execute_entry()`: Builds strategy, places orders, saves execution
  - Uses StrategyBuilder.build() to create strategy
  - Validates strategy with StrategyBuilder.validate()
  - Creates IB contracts for each leg
  - Places MARKET orders by default (reliable)
  - Places LIMIT orders if limit_price provided
  - Converts Strategy.strategy_id (string) to StrategyExecution.strategy_id (int)
  - Saves execution to StrategyRepository
  - Handles partial fills (some legs filled, some pending)

**Entry Signal Criteria:**
```
IV Rank: >50 (sell) or <25 (buy)
VIX: <35 (avoid extreme volatility)
Portfolio Delta: <0.3 (configurable)
Position Count: <5 per symbol (configurable)
```

### PositionMonitoringWorkflow

**Purpose:** Monitor all open positions, evaluate decisions, generate alerts

**Key Features:**
- `monitor_positions()`: Fetches all open strategies, evaluates each
  - Returns dict mapping execution_id → Decision
  - Calls DecisionEngine.evaluate() for each position
  - Creates alerts via AlertManager (automatic in DecisionEngine)
  - Logs action counts summary

- `monitor_position()`: Evaluates single position
  - Fetches execution from StrategyRepository
  - Creates snapshot with Greeks, P&L, DTE
  - Fetches market data (VIX, IV, portfolio delta)
  - Evaluates decision rules via DecisionEngine
  - Returns Decision with action, reason, rule, urgency

- `start_monitoring_loop()`: Continuous monitoring
  - Runs every 30 seconds (configurable)
  - Runs until cancelled
  - Handles errors gracefully, continues monitoring

**Position Data Sources:**
- Greeks from Delta Lake (option_snapshots table)
- Market data from real-time updates or polling
- Strategy status from StrategyRepository

### ExitWorkflow

**Purpose:** Execute exit decisions (CLOSE, ROLL, HOLD) and close all positions

**Key Features:**
- `execute_exit_decision()`: Executes single exit decision
  - CLOSE: Calls OrderExecutionEngine.close_position()
  - ROLL: Calls OrderExecutionEngine.roll_position()
  - HOLD: Returns success=True, no action
  - Updates StrategyRepository status
  - Sets close_time automatically (handled by repository)

- `execute_close_all()`: Closes all positions for symbol
  - Fetches open strategies from StrategyRepository
  - Executes CLOSE decision for each
  - Returns dict mapping execution_id → ExecutionResult
  - Continues on individual failures
  - Logs success count

- `_execution_to_strategy()`: Converts StrategyExecution to Strategy
  - Extracts leg data for OrderExecutionEngine
  - Handles LegAction conversion

**Exit Actions:**
```python
CLOSE: Close all legs via OrderExecutionEngine
ROLL: Close old + log warning for new entry (manual)
HOLD: No action
REDUCE: Partial close (close_ratio from metadata)
```

## Integration Tests

11 integration tests covering complete workflow cycle:

**EntryWorkflow Tests (4 tests):**
1. `test_entry_workflow_signal_validation` - Valid market conditions pass
2. `test_entry_workflow_rejects_low_iv_rank` - IV Rank 25-50 rejected
3. `test_entry_workflow_rejects_high_vix` - VIX >35 rejected
4. `test_entry_workflow_full_execution` - Full entry with Iron Condor

**MonitoringWorkflow Tests (3 tests):**
5. `test_monitoring_workflow_no_positions` - Empty handling
6. `test_monitoring_workflow_with_position` - Evaluates position
7. `test_monitoring_workflow_single_position` - Single position monitoring

**ExitWorkflow Tests (3 tests):**
8. `test_exit_workflow_hold_decision` - HOLD returns NO_ACTION
9. `test_exit_workflow_close_decision` - CLOSE executes
10. `test_exit_workflow_close_all` - Closes all SPY positions

**End-to-End Test (1 test):**
11. `test_end_to_entry_monitor_exit` - Complete cycle
    - Entry: Build and execute Iron Condor
    - Monitoring: Evaluate position with DecisionEngine
    - Exit: Execute CLOSE decision
    - Verify: Execution updated with close_time

**Test Results:**
```
11 passed in 1.36s
```

## Integration Points

**EntryWorkflow:**
- DecisionEngine (optional, for future enhancements)
- StrategyBuilder → Strategy
- OrderExecutionEngine → place_order()
- StrategyRepository → save_execution()

**PositionMonitoringWorkflow:**
- DecisionEngine → evaluate()
- AlertManager → create_alert() (automatic via DecisionEngine)
- StrategyRepository → get_execution(), get_open_strategies()

**ExitWorkflow:**
- OrderExecutionEngine → close_position(), roll_position()
- DecisionEngine (optional, for validation)
- StrategyRepository → get_execution(), update_execution_status()

## Deviations from Plan

None - plan executed as specified.

## Fixes to Dependencies

**StrategyRepository Enhancement:**
- Added `close_time` handling in `update_execution_status()`
- When status=CLOSED, automatically sets close_time to now
- Prevents validation error: "Closed execution must have close_time"

## Commits

1. `c111a48` - feat(4-03): create EntryWorkflow with signal evaluation and order execution

## Integration Notes

- Uses DecisionEngine from Phase 3 (12 priority-based rules)
- Uses OrderExecutionEngine from 4-02 (IB API integration)
- Uses StrategyBuilder from 4-01 (Iron Condor, Vertical Spread, Custom)
- Uses StrategyRepository from 4-01 (Delta Lake persistence)
- Uses AlertManager from Phase 3 (alert generation)

**Data Flow:**
```
Market Data → EntryWorkflow → StrategyBuilder → Strategy
                                   ↓
                            OrderExecutionEngine → IB Orders
                                   ↓
                            StrategyRepository → Delta Lake
                                   ↓
PositionMonitoringWorkflow → DecisionEngine → AlertManager
                                   ↓
ExitWorkflow → OrderExecutionEngine → IB Orders → StrategyRepository
```

## Next Steps

**Phase 4 Complete!**

All 3 plans completed:
- ✅ 4-01: Strategy builders (Iron Condor, Vertical Spread, Custom)
- ✅ 4-02: IB order execution engine (bracket orders, OCA groups)
- ✅ 4-03: Entry and exit workflows (11 tests passing)

**Ready for Phase 5: Risk Management**

Future enhancements:
- Integrate live market data feed (VIX, IV, underlying changes)
- Add Greeks fetching from Delta Lake in monitoring workflow
- Implement new strategy entry in ROLL decision
- Add portfolio risk limits in EntryWorkflow
- Implement partial position reduction
