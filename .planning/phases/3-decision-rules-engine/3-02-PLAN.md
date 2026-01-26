---
phase: 3-decision-rules-engine
plan: 02
type: execute
depends_on: ["3-01"]
files_modified: [src/v6/decisions/portfolio_risk.py, src/v6/decisions/test_portfolio_risk.py]
domain: quant-options
---

<objective>
Implement portfolio-level risk calculations (delta, gamma, theta, vega, exposure).

Purpose: Calculate portfolio-level Greeks and exposure metrics to support decision rules that need portfolio context (delta risk limits, gamma exposure, concentration checks).

Output: PortfolioRisk calculator with Greek aggregation, exposure metrics, and unit tests.
</objective>

<execution_context>
~/.claude/get-shit-done/workflows/execute-plan.md
~/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/3-decision-rules-engine/3-01-SUMMARY.md (should exist after 3-01 completes)
@src/v6/decisions/models.py (Decision models from 3-01)
@src/v6/models/ib_models.py (PositionSnapshot, Greeks models)
@src/v6/data/repositories/positions.py (Position data access)
@~/.claude/skills/expertise/quant-options/SKILL.md (options domain knowledge)

**Tech stack available:**
- Python 3.11+ dataclasses with slots=True
- polars for efficient data aggregation (from Phase 2)
- Delta Lake for position data (from Phase 2)

**Established patterns:**
- dataclass(slots=True) for performance (from Phase 1)
- Polars for data operations (from Phase 2)
- Async/await pattern (from Phase 2)

**Key decisions from 3-01:**
- Protocol-based interfaces (flexible, extensible)
- Async design for consistency
- Priority-based execution
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create portfolio risk models</name>
  <files>src/v6/decisions/portfolio_risk.py</files>
  <action>
Create portfolio risk data models:

1. **PortfolioGreeks dataclass** (slots=True):
   - delta: float (net portfolio delta)
   - gamma: float (net portfolio gamma)
   - theta: float (net portfolio theta)
   - vega: float (net portfolio vega)
   - delta_per_symbol: dict[str, float] (delta by underlying)
   - gamma_per_symbol: dict[str, float] (gamma by underlying)

2. **ExposureMetrics dataclass** (slots=True):
   - total_exposure: float (total notional exposure)
   - max_single_position: float (largest position % of portfolio)
   - correlated_exposure: dict[str, float] (exposure by sector/beta)
   - buying_power_used: float (margin utilization %)
   - buying_power_available: float

3. **PortfolioRisk dataclass** (slots=True):
   - greeks: PortfolioGreeks
   - exposure: ExposureMetrics
   - position_count: int
   - symbol_count: int
   - calculated_at: datetime

Use @dataclass(slots=True). Add validation in __post_init__ (delta in [-100, 100], percentages in [0, 100]).
  </action>
  <verify>
python -c "
from src.v6.decisions.portfolio_risk import PortfolioRisk, PortfolioGreeks, ExposureMetrics
from datetime import datetime
greeks = PortfolioGreeks(delta=0.5, gamma=0.02, theta=-10.0, vega=50.0, delta_per_symbol={}, gamma_per_symbol={})
exposure = ExposureMetrics(total_exposure=100000, max_single_position=0.02, correlated_exposure={}, buying_power_used=0.3, buying_power_available=70000)
risk = PortfolioRisk(greeks=greeks, exposure=exposure, position_count=5, symbol_count=3, calculated_at=datetime.now())
print(risk)
" executes without errors
  </verify>
  <done>
All data models created, validation works, type hints complete
  </done>
</task>

<task type="auto">
  <name>Task 2: Create PortfolioRisk calculator</name>
  <files>src/v6/decisions/portfolio_risk.py</files>
  <action>
Create PortfolioRiskCalculator class:

**Class structure:**
```python
class PortfolioRiskCalculator:
    def __init__(self, position_repo: PositionRepository)
    async def calculate_portfolio_risk(self, account_id: int | None = None) -> PortfolioRisk
    async def get_greeks_by_symbol(self, symbol: str) -> PortfolioGreeks
    async def check_delta_limits(self, max_delta: float = 0.30) -> list[str]  # Returns symbols over limit
    async def check_exposure_limits(self, max_position_pct: float = 0.02, max_correlated_pct: float = 0.05) -> list[str]
```

**Implementation:**
1. **calculate_portfolio_risk()**:
   - Fetch all open positions from position_repo
   - Aggregate Greeks: sum delta, gamma, theta, vega across all positions
   - Calculate per-symbol Greeks: group by symbol, sum Greeks
   - Calculate exposure metrics:
     - total_exposure: sum of (position_quantity * strike * 100)
     - max_single_position: max(position_value / total_portfolio_value)
     - correlated_exposure: group by sector/beta (use symbol suffix or mapping)
     - buying_power_used: fetch from IB account info
   - Return PortfolioRisk with all aggregated data

2. **get_greeks_by_symbol(symbol)**:
   - Filter positions by symbol
   - Sum Greeks for that symbol
   - Return PortfolioGreeks with per-symbol aggregates

3. **check_delta_limits(max_delta)**:
   - Calculate portfolio Greeks
   - Return list of symbols where |delta_per_symbol[symbol]| > max_delta

4. **check_exposure_limits(max_position_pct, max_correlated_pct)**:
   - Calculate exposure metrics
   - Return list of symbols exceeding limits

Use polars for efficient aggregation if >10 positions. Reference v5 caretaker for Greek calculation patterns, but adapt to v6 async architecture.
  </action>
  <verify>
python -c "
from src.v6.decisions.portfolio_risk import PortfolioRiskCalculator
from src.v6.data.repositories.positions import PositionRepository
import asyncio
async def test():
    calc = PortfolioRiskCalculator(PositionRepository())
    # Test with empty portfolio (should return zeros)
    risk = await calc.calculate_portfolio_risk()
    print(f'Positions: {risk.position_count}, Delta: {risk.greeks.delta}')
asyncio.run(test())
" executes and shows position_count=0 for empty portfolio
  </verify>
  <done>
PortfolioRiskCalculator created, calculate_portfolio_risk() works, per-symbol aggregation works, limit checks work
  </done>
</task>

<task type="auto">
  <name>Task 3: Create unit tests for portfolio risk</name>
  <files>src/v6/decisions/test_portfolio_risk.py</files>
  <action>
Create comprehensive unit tests:

**Test cases:**
1. **test_empty_portfolio_returns_zeros**: No positions → all Greeks = 0, exposure = 0
2. **test_single_position_aggregation**: One position with Greeks=5 → portfolio Greeks = 5
3. **test_multi_position_greeks**: 3 positions with different Greeks → sum correctly
4. **test_per_symbol_aggregation**: 2 SPY positions, 1 QQQ position → delta_per_symbol['SPY'] = sum of SPY deltas
5. **test_delta_limits_check**: 3 symbols, one over delta limit → returns [over_limit_symbol]
6. **test_exposure_limits_check**: One position at 3% of portfolio (max=2%) → returns [symbol]
7. **test_buying_power_calculation**: Mock account data → correct buying_power_used/available

**Mock data:**
- Create mock PositionSnapshot objects with test Greeks
- Mock PositionRepository to return test positions
- Mock IB account data for buying power

Use pytest with async tests. Run with: `conda run -n ib pytest src/v6/decisions/test_portfolio_risk.py -v`
  </action>
  <verify>
conda run -n ib pytest src/v6/decisions/test_portfolio_risk.py -v shows all tests passing (7+ passed)
  </verify>
  <done>
All 7 tests pass, Greek aggregation correct, exposure metrics correct, limit checks work
  </done>
</task>

</tasks>

<verification>
Before declaring plan complete:
- [ ] `conda run -n ib pytest src/v6/decisions/test_portfolio_risk.py -v` - all tests pass
- [ ] `python -c "from src.v6.decisions.portfolio_risk import PortfolioRiskCalculator; print('Import success')"` - imports work
- [ ] Empty portfolio returns zeros (no division by zero errors)
- [ ] Greek aggregation verified (sum of positions = portfolio)
- [ ] Per-symbol Greek aggregation correct
- [ ] Delta limits check returns correct symbols
- [ ] Exposure limits check works
</verification>

<success_criteria>

- Portfolio risk models created (PortfolioGreeks, ExposureMetrics, PortfolioRisk)
- PortfolioRiskCalculator aggregates Greeks correctly
- Per-symbol Greek aggregation works
- Delta and exposure limit checks functional
- All unit tests passing (7+ tests)
- No linting errors
  </success_criteria>

<output>
After completion, create `.planning/phases/3-decision-rules-engine/3-02-SUMMARY.md`:

# Phase 3 Plan 2: Portfolio Risk Calculations Summary

**Implemented portfolio-level risk calculations with Greek aggregation and exposure metrics.**

## Accomplishments

- Portfolio risk models (PortfolioGreeks, ExposureMetrics, PortfolioRisk)
- PortfolioRiskCalculator with Greek aggregation
- Per-symbol Greek breakdown (delta_per_symbol, gamma_per_symbol)
- Exposure metrics (total, max position, correlated, buying power)
- Delta and exposure limit checks
- Unit tests (7 tests, all passing)

## Files Created/Modified

- `src/v6/decisions/portfolio_risk.py` - Risk models and calculator
- `src/v6/decisions/test_portfolio_risk.py` - Unit tests

## Deviations from Plan

None - plan executed as specified.

## Next Step

Ready for 3-03-PLAN.md (Implement 12 priority-based decision rules)
</output>
