---
phase: 4-strategy-execution
plan: 03
type: execute
depends_on: ["4-01", "4-02"]
files_modified: [src/v6/workflows/__init__.py, src/v6/workflows/entry.py, src/v6/workflows/monitoring.py, src/v6/workflows/exit.py, src/v6/workflows/test_workflows.py]
domain: quant-options
---

<objective>
Implement entry and exit workflows for automated strategy execution.

Purpose: Create end-to-end workflows that generate entry signals, execute position entries, monitor positions, and execute exits based on decision rules. This connects the decision engine, strategy builders, and order execution into a complete automated trading system.

Output: Entry workflow, position monitoring workflow, exit workflow, and integration tests.
</objective>

<execution_context>
~/.claude/get-shit-done/workflows/execute-plan.md
~/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/4-strategy-execution/4-01-SUMMARY.md (Strategy builders)
@.planning/phases/4-strategy-execution/4-02-SUMMARY.md (Order execution)
@.planning/phases/3-decision-rules-engine/3-03-SUMMARY.md (Decision rules)
@../v5/caretaker/execution_engine.py (v5 reference)
@src/v6/decisions/engine.py (DecisionEngine from Phase 3)
@src/v6/execution/engine.py (OrderExecutionEngine from 4-02)
@src/v6/strategies/builders.py (Strategy builders from 4-01)
@src/v6/strategies/repository.py (StrategyRepository from 4-01)
@~/.claude/skills/expertise/quant-options/SKILL.md (options domain knowledge)

**Tech stack available:**
- ib_async for IB API (from Phase 1)
- DecisionEngine and 12 rules (from Phase 3)
- OrderExecutionEngine (from 4-02)
- Strategy builders (from 4-01)
- Delta Lake for persistence (from Phase 2)

**Established patterns:**
- dataclass(slots=True) for performance
- Protocol-based interfaces
- Async/await throughout
- Delta Lake for all persistence

**Complete trading workflow:**
1. **Entry workflow**: Signal generation → Strategy building → Order placement → Position monitoring
2. **Monitoring workflow**: Position updates → Decision evaluation → Alert generation
3. **Exit workflow**: Decision triggered → Order execution → Position closed
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create entry workflow</name>
  <files>src/v6/workflows/entry.py</files>
  <action>
Create automated entry workflow:

**Class structure:**
```python
class EntryWorkflow:
    def __init__(self, decision_engine: DecisionEngine, execution_engine: OrderExecutionEngine, strategy_builder: StrategyBuilder, strategy_repo: StrategyRepository)
    async def evaluate_entry_signal(self, symbol: str, market_data: dict) -> bool
    async def execute_entry(self, symbol: str, strategy_type: StrategyType, params: dict) -> StrategyExecution
```

**Implementation:**
1. **evaluate_entry_signal()**:
   - Check market conditions (IV Rank, VIX, underlying trend)
   - Run decision engine with current market snapshot
   - Return True if entry conditions met (no blocking rules, positive signal)
   - Check portfolio constraints (delta limits, exposure limits from PortfolioRiskCalculator)

2. **execute_entry()**:
   - Build strategy using strategy_builder.build()
   - Validate strategy (check strikes, expirations)
   - Place entry orders via execution_engine:
     - For multi-leg strategies: place all orders
     - Use OCA group if alternative entries
     - Set bracket orders (TP/SL) if strategy_type supports it
   - Save execution to StrategyRepository with status=PENDING
   - Return StrategyExecution with order IDs
   - Handle partial fills (some legs filled, some pending)

**Entry signal criteria:**
- IV Rank >50 (sell premium) or <25 (buy premium)
- VIX not in extreme range
- Portfolio has capacity (delta limits not exceeded)
- No conflicting positions

Use DecisionEngine from Phase 3, OrderExecutionEngine from 4-02, StrategyBuilder from 4-01. Reference v5 caretaker for entry signal patterns.
  </action>
  <verify>
python -c "
from src.v6.workflows.entry import EntryWorkflow
print('EntryWorkflow imports successfully')
" executes without errors
  </verify>
  <done>
EntryWorkflow created, evaluate_entry_signal() checks market/portfolio conditions, execute_entry() builds strategy and places orders
  </done>
</task>

<task type="auto">
  <name>Task 2: Create position monitoring workflow</name>
  <files>src/v6/workflows/monitoring.py</files>
<action>
Create automated position monitoring workflow:

**Class structure:**
```python
class PositionMonitoringWorkflow:
    def __init__(self, decision_engine: DecisionEngine, alert_manager: AlertManager, strategy_repo: StrategyRepository)
    async def monitor_positions(self) -> dict[str, Decision]  # {strategy_id: decision}
    async def monitor_position(self, strategy_execution_id: str) -> Decision
```

**Implementation:**
1. **monitor_positions()**:
   - Fetch all open strategies from StrategyRepository
   - For each strategy:
     - Get latest position snapshot (Greeks, UPL, DTE)
     - Call decision_engine.evaluate(snapshot, market_data)
     - Create alert via alert_manager.create_alert() if not HOLD
     - Return dict mapping strategy_id → Decision
   - Run every 30 seconds (configurable)

2. **monitor_position()**:
   - Get position by strategy_execution_id
   - Fetch latest Greeks and market data
   - Evaluate decision rules
   - Create alert if action needed
   - Return Decision

**Position data sources:**
- Greeks from Delta Lake (option_snapshots table from Phase 2)
- Market data from real-time updates or polling
- Strategy status from StrategyRepository

**Integration:**
- DecisionEngine evaluates 12 rules in priority order
- AlertManager creates alerts for non-HOLD decisions
- Alerts tracked in Delta Lake for history

Use DecisionEngine from Phase 3, AlertManager from Phase 3, StrategyRepository from 4-01.
  </action>
  <verify>
python -c "
from src.v6.workflows.monitoring import PositionMonitoringWorkflow
print('PositionMonitoringWorkflow imports successfully')
" executes without errors
  </verify>
  <done>
PositionMonitoringWorkflow created, monitor_positions() evaluates all open positions, monitor_position() evaluates single position, decisions trigger alerts
  </done>
</task>

<task type="auto">
  <name>Task 3: Create exit workflow and integration tests</name>
  <files>src/v6/workflows/exit.py, src/v6/workflows/test_workflows.py</files>
<action>
Create exit workflow and integration tests:

**Exit workflow (src/v6/workflows/exit.py):**
```python
class ExitWorkflow:
    def __init__(self, execution_engine: OrderExecutionEngine, decision_engine: DecisionEngine, strategy_repo: StrategyRepository)
    async def execute_exit_decision(self, strategy_execution_id: str, decision: Decision) -> ExecutionResult
    async def execute_close_all(self, symbol: str | None = None) -> dict[str, ExecutionResult]
```

**Implementation:**
1. **execute_exit_decision()**:
   - Parse decision.action:
     - CLOSE: Call execution_engine.close_position()
     - ROLL: Call execution_engine.roll_position()
     - HOLD: Do nothing, return success=True
   - Update strategy status in StrategyRepository
   - Return ExecutionResult

2. **execute_close_all()**:
   - Get all open strategies for symbol (or all if None)
   - For each strategy: execute_exit_decision() with CLOSE decision
   - Return dict mapping strategy_id → ExecutionResult

**Integration tests (src/v6/workflows/test_workflows.py):**
1. **test_entry_workflow_full**: Signal → build strategy → place orders → verify execution
2. **test_monitoring_workflow**: Create position → monitor → trigger TP rule → alert created
3. **test_exit_workflow_close**: Create position → TP triggered → exit workflow → orders placed
4. **test_exit_workflow_roll**: Create position → DTE roll → exit workflow → roll executed
5. **test_end_to_end**: Entry → monitoring → TP → exit → complete cycle

Use pytest with async tests. Mock IB API for testing. Run with: `conda run -n ib pytest src/v6/workflows/test_workflows.py -v`
  </action>
  <verify>
conda run -n ib pytest src/v6/workflows/test_workflows.py -v shows all tests passing (5+ passed)
  </verify>
  <done>
ExitWorkflow created, execute_exit_decision() handles CLOSE/ROLL/HOLD, execute_close_all() closes all positions, integration tests pass
  </done>
</task>

</tasks>

<verification>
Before declaring plan complete:
- [ ] `conda run -n ib pytest src/v6/workflows/test_workflows.py -v` - all integration tests pass
- [ ] `python -c "from src.v6.workflows.entry import EntryWorkflow; print('Import success')"` - imports work
- [ ] Entry workflow checks market conditions and portfolio limits
- [ ] Entry workflow builds strategy and places orders correctly
- [ ] Monitoring workflow evaluates all open positions
- [ ] Monitoring workflow triggers alerts on decisions
- [ ] Exit workflow executes CLOSE/ROLL/HOLD correctly
- [ ] execute_close_all() closes all positions for symbol
- [ ] End-to-end test works (entry → monitor → exit)
</verification>

<success_criteria>

- EntryWorkflow (evaluate_entry_signal, execute_entry)
- PositionMonitoringWorkflow (monitor_positions, monitor_position)
- ExitWorkflow (execute_exit_decision, execute_close_all)
- Integration tests passing (5+ tests)
- End-to-end workflow tested
- No linting errors
  </success_criteria>

<output>
After completion, create `.planning/phases/4-strategy-execution/4-03-SUMMARY.md`:

# Phase 4 Plan 3: Entry and Exit Workflows Summary

**Implemented complete entry and exit workflows connecting all components.**

## Accomplishments

- EntryWorkflow (signal evaluation, strategy building, order placement)
- PositionMonitoringWorkflow (position monitoring, decision evaluation, alerts)
- ExitWorkflow (execute exit decisions, close all positions)
- Integration tests (5 tests, all passing)
- End-to-end workflow tested

## Files Created/Modified

- `src/v6/workflows/entry.py` - Entry workflow
- `src/v6/workflows/monitoring.py` - Monitoring workflow
- `src/v6/workflows/exit.py` - Exit workflow
- `src/v6/workflows/__init__.py` - Package exports
- `src/v6/workflows/test_workflows.py` - Integration tests

## Phase 4 Complete

All 3 plans completed:
- ✅ 4-01: Strategy builders
- ✅ 4-02: IB order execution engine
- ✅ 4-03: Entry and exit workflows

**Phase 4: Strategy Execution COMPLETE**

Ready for Phase 5 (Risk Management).
</output>
