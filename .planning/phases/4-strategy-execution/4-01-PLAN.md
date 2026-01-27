---
phase: 4-strategy-execution
plan: 01
type: execute
depends_on: ["3-01", "3-02", "3-03"]
files_modified: [src/v6/strategies/__init__.py, src/v6/strategies/builders.py, src/v6/strategies/test_builders.py]
domain: quant-options
---

<objective>
Implement strategy builders for options trading strategies.

Purpose: Create builders for common options strategies (Iron Condor, vertical spreads, custom strategies) that generate leg specifications based on market conditions and risk parameters.

Output: Strategy builders (IronCondorBuilder, VerticalSpreadBuilder, CustomStrategyBuilder), strategy models, and unit tests.
</objective>

<execution_context>
~/.claude/get-shit-done/workflows/execute-plan.md
~/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/3-decision-rules-engine/3-03-SUMMARY.md (Decision rules complete)
@../v5/strategies/strategy_builder.py (v5 reference for patterns)
@src/v6/decisions/models.py (Decision models from Phase 3)
@src/v6/models/ib_models.py (PositionSnapshot, Greeks models)
@~/.claude/skills/expertise/quant-options/SKILL.md (options domain knowledge)

**Tech stack available:**
- Python 3.11+ dataclasses with slots=True
- Delta Lake for persistence (from Phase 2)
- DecisionEngine and rules (from Phase 3)

**Established patterns:**
- dataclass(slots=True) for performance (from Phase 1)
- Protocol-based interfaces (from Phase 3)
- Delta Lake for persistence (from Phase 2)

**Common options strategies to build:**
- **Iron Condor**: Sell OTM put spread + sell OTM call spread
- **Vertical Spread**: Buy ITM option, sell OTM option (same expiration)
- **Custom**: User-defined multi-leg strategies
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create strategy models and builders</name>
  <files>src/v6/strategies/builders.py</files>
  <action>
Create strategy models and builder classes:

**1. Strategy models (dataclass slots=True):**
- **LegSpec**: right (CALL/PUT), strike, quantity (positive), action (BUY/SELL), expiration
- **Strategy**: strategy_id, symbol, strategy_type, legs: list[LegSpec], entry_time, status
- **StrategyType enum**: IRON_CONDOR, VERTICAL_SPREAD, CUSTOM, LONG_CALL, LONG_PUT, SHORT_CALL, SHORT_PUT

**2. Base builder protocol:**
```python
class StrategyBuilder(Protocol):
    priority: int
    name: str

    def build(self, symbol: str, underlying_price: float, params: dict) -> Strategy
    def validate(self, strategy: Strategy) -> bool
```

**3. IronCondorBuilder:**
- build(symbol, underlying_price, params) → Strategy
- Params: put_width, call_width, dte, delta_target (default 16)
- Returns 4-leg IC: sell OTM put spread + sell OTM call spread
- validate(): Check strikes are OTM, widths consistent

**4. VerticalSpreadBuilder:**
- build(symbol, underlying_price, params) → Strategy
- Params: direction (BULL/BEAR), width, dte, delta_target
- Returns 2-leg vertical: buy ITM, sell OTM (same expiration)
- validate(): Check one ITM, one OTM, same expiration

**5. CustomStrategyBuilder:**
- build(symbol, underlying_price, legs: list[dict]) → Strategy
- User-defined leg specifications
- validate(): Check legs have valid strikes/expirations

Use @dataclass(slots=True). Reference ../v5/strategies/strategy_builder.py for patterns, adapt to v6 async architecture.
  </action>
  <verify>
python -c "
from src.v6.strategies.builders import IronCondorBuilder, VerticalSpreadBuilder
from src.v6.strategies.models import StrategyType
ic_builder = IronCondorBuilder()
vs_builder = VerticalSpreadBuilder()
print(f'IC: {ic_builder.name}, VS: {vs_builder.name}')
" executes without errors
  </verify>
  <done>
All models and builders created, validation logic works, build methods return Strategy objects with correct legs
  </done>
</task>

<task type="auto">
  <name>Task 2: Create strategy execution models and Delta Lake persistence</name>
  <files>src/v6/strategies/models.py, src/v6/strategies/repository.py</files>
  <action>
Create strategy execution models and repository:

**1. StrategyExecution dataclass (slots=True):**
- execution_id: str (UUID)
- strategy_id: int
- symbol: str
- strategy_type: StrategyType
- status: ExecutionStatus (PENDING, FILLED, PARTIAL, FAILED, CLOSED)
- legs: list[LegExecution]
- entry_params: dict
- entry_time: datetime
- fill_time: datetime | None
- close_time: datetime | None

**2. LegExecution dataclass (slots=True):**
- leg_id: str
- conid: int | None
- right, strike, expiration, quantity, action
- status: LegStatus (PENDING, FILLED, CANCELLED)
- fill_price: float | None
- order_id: str | None

**3. StrategyRepository (Delta Lake):**
```python
class StrategyRepository:
    async def initialize(self) -> None
    async def save_execution(self, execution: StrategyExecution) -> None
    async def get_execution(self, execution_id: str) -> StrategyExecution | None
    async def get_open_strategies(self, symbol: str | None = None) -> list[StrategyExecution]
    async def update_execution_status(self, execution_id: str, status: ExecutionStatus) -> None
    async def update_leg_status(self, leg_id: str, status: LegStatus, fill_price: float) -> None
```

Delta Lake schema:
```
strategy_executions/
  - execution_id: string
  - strategy_id: int
  - symbol: string
  - strategy_type: string
  - status: string
  - entry_params: string (JSON)
  - entry_time: timestamp
  - fill_time: timestamp
  - close_time: timestamp
```

Use Delta Lake patterns from src/v6/data/delta_persistence.py.
  </action>
  <verify>
python -c "
from src.v6.strategies.repository import StrategyRepository
import asyncio
async def test():
    repo = StrategyRepository()
    await repo.initialize()
    print('Repository initialized')
asyncio.run(test())
" executes and initializes Delta Lake tables
  </verify>
  <done>
Models created, StrategyRepository with Delta Lake persistence works, initialize() creates tables
  </done>
</task>

<task type="auto">
  <name>Task 3: Create unit tests for strategy builders</name>
  <files>src/v6/strategies/test_builders.py</files>
  <action>
Create comprehensive unit tests:

**Test cases:**
1. **test_iron_condor_builder**: Build IC with params → 4 legs, correct strikes, widths correct
2. **test_iron_condor_validation**: Invalid params (negative width) → validate() returns False
3. **test_vertical_spread_bull**: Build bull vertical spread → buy CALL ITM, sell CALL OTM
4. **test_vertical_spread_bear**: Build bear vertical spread → buy PUT ITM, sell PUT OTM
5. **test_custom_strategy_builder**: Build custom 3-leg strategy → legs match input
6. **test_strategy_repository_save**: Create execution → save to Delta Lake → retrieve matches
7. **test_strategy_repository_get_open**: Create executions (OPEN, CLOSED) → get_open returns only OPEN
8. **test_leg_status_update**: Create execution → update leg status → Delta Lake reflects change

Mock IB contracts if needed. Use pytest with async tests. Run with: `conda run -n ib pytest src/v6/strategies/test_builders.py -v`
  </action>
  <verify>
conda run -n ib pytest src/v6/strategies/test_builders.py -v shows all tests passing (8+ passed)
  </verify>
  <done>
All 8 tests pass, builders create valid strategies, validation works, repository persistence works
  </done>
</task>

</tasks>

<verification>
Before declaring plan complete:
- [ ] `conda run -n ib pytest src/v6/strategies/test_builders.py -v` - all tests pass
- [ ] `python -c "from src.v6.strategies import StrategyRepository; print('Import success')"` - imports work
- [ ] IronCondorBuilder creates 4-leg IC with correct widths
- [ ] VerticalSpreadBuilder creates 2-leg spreads (ITM/OTM)
- [ ] CustomStrategyBuilder handles user-defined legs
- [ ] StrategyRepository Delta Lake persistence works
- [ ] No linting errors (ruff check passes)
</verification>

<success_criteria>

- Strategy models created (LegSpec, Strategy, StrategyExecution, LegExecution)
- 3 strategy builders (IronCondor, VerticalSpread, Custom)
- StrategyRepository with Delta Lake persistence
- All validation logic working
- Unit tests passing (8+ tests)
- No linting errors
  </success_criteria>

<output>
After completion, create `.planning/phases/4-strategy-execution/4-01-SUMMARY.md`:

# Phase 4 Plan 1: Strategy Builders Summary

**Implemented strategy builders for common options trading strategies.**

## Accomplishments

- Strategy models (LegSpec, Strategy, StrategyExecution, LegExecution)
- IronCondorBuilder (4-leg IC with configurable widths)
- VerticalSpreadBuilder (2-leg spreads, bullish/bearish)
- CustomStrategyBuilder (user-defined multi-leg)
- StrategyRepository with Delta Lake persistence
- Unit tests (8 tests, all passing)

## Files Created/Modified

- `src/v6/strategies/models.py` - Strategy data models
- `src/v6/strategies/builders.py` - Strategy builders
- `src/v6/strategies/repository.py` - StrategyRepository
- `src/v6/strategies/__init__.py` - Package exports
- `src/v6/strategies/test_builders.py` - Unit tests

## Deviations from Plan

None - plan executed as specified.

## Next Step

Ready for 4-02-PLAN.md (IB order execution engine)
</output>
