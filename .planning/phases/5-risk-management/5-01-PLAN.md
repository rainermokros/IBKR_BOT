---
phase: 5-risk-management
plan: 01
type: execute
depends_on: []
files_modified: [src/v6/risk/models.py, src/v6/risk/portfolio_limits.py, src/v6/risk/__init__.py, src/v6/workflows/entry.py]
---

<objective>
Implement portfolio-level controls for risk management before position entry.

Purpose: Enforce portfolio-level risk limits (delta, gamma, exposure, concentration) to prevent over-exposure and manage aggregate Greek risk across all positions.

Output: PortfolioLimitsChecker integrated with EntryWorkflow, blocking entries that would exceed risk thresholds.
</objective>

<execution_context>
~/.claude/get-shit-done/workflows/execute-plan.md
./summary.md
</execution_context>

<context>
@v6/.planning/PROJECT.md
@v6/.planning/ROADMAP.md
@v6/.planning/phases/5-risk-management/5-RESEARCH.md
@v6/.planning/phases/3-decision-rules-engine/3-02-SUMMARY.md
@v6/.planning/phases/4-strategy-execution/4-03-SUMMARY.md
@v6/src/v6/decisions/portfolio_risk.py
@v6/src/v6/workflows/entry.py
@v6/src/v6/strategies/models.py

**Research findings (from 5-RESEARCH.md):**
- Use PortfolioRiskCalculator (already exists) for Greek aggregation
- Check limits AGGREGATE, not per-position (Greeks accumulate)
- PortfolioRiskCalculator.calculate_portfolio_risk() returns PortfolioRisk with greeks and exposure
- Anti-pattern: Checking limits per-position only misses portfolio accumulation

**Existing components to integrate:**
- PortfolioRiskCalculator.calculate_portfolio_risk() → PortfolioRisk (with greeks, exposure)
- EntryWorkflow.evaluate_entry_signal() → add portfolio limits check
- OrderExecutionEngine → raise PortfolioLimitExceeded if limits exceeded

**Standard stack from research:**
- polars: Already in use for portfolio Greek aggregation
- dataclass(slots=True): Already used for performance
- ib_async: For position data
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create risk models and limits configuration</name>
  <files>src/v6/risk/models.py, src/v6/risk/__init__.py</files>
  <action>Create new module src/v6/risk/models.py with:

1. RiskLimitsConfig dataclass(slots=True):
   - max_portfolio_delta: float = 50.0
   - max_portfolio_gamma: float = 10.0
   - max_single_position_pct: float = 0.02 (2% per position)
   - max_per_symbol_delta: float = 20.0
   - max_correlated_pct: float = 0.05 (5% per sector/symbol)
   - total_exposure_cap: float | None = None (optional cap)

2. PortfolioLimitExceeded exception class:
   - Inherit from Exception
   - Message: "Portfolio limit exceeded: {reason}"
   - Attributes: limit_type, current_value, limit_value, symbol

3. Update src/v6/risk/__init__.py:
   - Export RiskLimitsConfig, PortfolioLimitExceeded

Use @dataclass(slots=True) for performance (consistent with v6 patterns).
Add comprehensive docstrings.
No py_vollib needed (not doing IV-based adjustments yet - per research recommendation).
</action>
  <verify>python -c "from src.v6.risk.models import RiskLimitsConfig, PortfolioLimitExceeded; print('Import successful')"</verify>
  <done>RiskLimitsConfig with all portfolio limit fields defined, PortfolioLimitExceeded exception created, module imports work</done>
</task>

<task type="auto">
  <name>Task 2: Implement PortfolioLimitsChecker</name>
  <files>src/v6/risk/portfolio_limits.py</files>
  <action>Create new module src/v6/risk/portfolio_limits.py with PortfolioLimitsChecker class:

Class PortfolioLimitsChecker:
  __init__(self, risk_calculator: PortfolioRiskCalculator, limits: RiskLimitsConfig)

Methods:
1. async def check_entry_allowed(
       new_position_delta: float,
       symbol: str,
       position_value: float
   ) -> tuple[bool, str | None]:
   """Check if new position would exceed portfolio limits."""

   Implementation steps:
   a) Get current portfolio risk: risk = await self.risk_calc.calculate_portfolio_risk()

   b) Check portfolio delta limit:
      new_portfolio_delta = risk.greeks.delta + new_position_delta
      if abs(new_portfolio_delta) > self.limits.max_portfolio_delta:
          return False, f"Portfolio delta would exceed limit: {new_portfolio_delta:.2f}"

   c) Check per-symbol delta:
      symbol_delta = risk.greeks.delta_per_symbol.get(symbol, 0)
      new_symbol_delta = symbol_delta + new_position_delta
      if abs(new_symbol_delta) > self.limits.max_per_symbol_delta:
          return False, f"Symbol {symbol} delta would exceed limit: {new_symbol_delta:.2f}"

   d) Check concentration (position value / total exposure):
      new_total_exposure = risk.exposure.total_exposure + position_value
      if new_total_exposure > 0:
          position_concentration = position_value / new_total_exposure
          if position_concentration > self.limits.max_single_position_pct:
              return False, f"Position would exceed {self.limits.max_single_position_pct:.1%} concentration"

   e) Return (True, None) if all checks pass

2. async def check_portfolio_health(self) -> list[str]:
   """Check current portfolio against all limits, return list of warnings."""
   Returns list of warning messages for limits that are already exceeded

3. async def get_remaining_capacity(
       symbol: str
   ) -> dict[str, float]:
   """Calculate remaining capacity for new entries by symbol."""
   Returns: {"delta": X, "exposure": Y, "position_count": Z}

Use PortfolioRiskCalculator from src.v6.decisions.portfolio_risk.
Use async/await throughout (consistent with v6 architecture).
Handle empty portfolio gracefully (PortfolioRiskCalculator already does).
Add comprehensive docstrings and type hints.
</action>
  <verify>python -m pytest tests/risk/test_portfolio_limits.py -v (create test file)</verify>
  <done>PortfolioLimitsChecker with all limit checks implemented, 15+ unit tests covering delta/exposure/concentration limits, empty portfolio handling, per-symbol checks</done>
</task>

<task type="auto">
  <name>Task 3: Integrate PortfolioLimitsChecker with EntryWorkflow</name>
  <files>src/v6/workflows/entry.py, src/v6/risk/__init__.py</files>
  <action>Update src/v6/workflows/entry.py to integrate portfolio limits:

1. Import PortfolioLimitsChecker, RiskLimitsConfig, PortfolioLimitExceeded from src.v6.risk

2. Update EntryWorkflow.__init__():
   Add parameter: portfolio_limits: PortfolioLimitsChecker | None = None
   Store as self.portfolio_limits

3. Update EntryWorkflow.execute_entry() method:
   AFTER building strategy, BEFORE placing orders:

   a) Calculate position metrics:
      - position_delta = sum(leg.quantity for leg in strategy.legs if leg.action == "SELL")
      - position_value = sum(abs(leg.quantity) * strategy.underlying_price * 100 for leg in strategy.legs)

   b) Check portfolio limits (if checker provided):
      if self.portfolio_limits:
          allowed, reason = await self.portfolio_limits.check_entry_allowed(
              new_position_delta=position_delta,
              symbol=strategy.symbol,
              position_value=position_value
          )
          if not allowed:
              logger.warning(f"Entry REJECTED by portfolio limits: {reason}")
              raise PortfolioLimitExceeded(reason)

   c) Log: "Entry allowed by portfolio limits" if passed

4. Create RiskLimitsConfig with default values:
   max_portfolio_delta=50, max_portfolio_gamma=10,
   max_single_position_pct=0.02, max_per_symbol_delta=20

5. Update tests:
   - Update EntryWorkflow tests to include portfolio_limits parameter
   - Add test that rejects entry when limits exceeded
   - Add test that allows entry when limits not exceeded

Ensure entry workflow continues to work without portfolio_limits (backward compatible).
</action>
  <verify>python -m pytest tests/workflows/test_entry.py::test_entry_rejected_by_portfolio_limits -v
python -m pytest tests/workflows/test_entry.py::test_entry_allowed_by_portfolio_limits -v</verify>
  <done>EntryWorkflow checks portfolio limits before placing orders, rejects entries that would exceed limits, tests verify both rejection and acceptance scenarios</done>
</task>

</tasks>

<verification>
Before declaring plan complete:
- [ ] All tests pass (python -m pytest tests/risk/ tests/workflows/test_entry.py -v)
- [ ] ruff linting passes (ruff check src/v6/risk/)
- [ ] PortfolioLimitsChecker correctly uses PortfolioRiskCalculator
- [ ] EntryWorkflow integration working (limits checked before orders)
- [ ] Backward compatible (EntryWorkflow works without portfolio_limits)
- [ ] Type hints on all functions
- [ ] Comprehensive docstrings
</verification>

<success_criteria>

- PortfolioLimitsChecker implemented with delta, gamma, exposure, concentration checks
- Integration with PortfolioRiskCalculator verified
- EntryWorkflow blocks entries exceeding portfolio limits
- Unit tests covering all limit types and edge cases
- Integration tests verifying end-to-end blocking
- Backward compatibility maintained
  </success_criteria>

<output>
After completion, create `v6/.planning/phases/5-risk-management/5-01-SUMMARY.md`:

# Phase 5 Plan 1: Portfolio-Level Controls Summary

**Implemented portfolio-level risk controls to prevent aggregate Greek exposure and concentration risk.**

## Accomplishments

- RiskLimitsConfig dataclass with configurable thresholds
- PortfolioLimitExceeded exception for limit violations
- PortfolioLimitsChecker with delta, gamma, exposure, concentration checks
- Integration with EntryWorkflow for pre-trade risk gating
- Comprehensive unit and integration tests

## Files Created/Modified

- `src/v6/risk/models.py` - Risk configuration and exceptions
- `src/v6/risk/portfolio_limits.py` - PortfolioLimitsChecker
- `src/v6/risk/__init__.py` - Module exports
- `src/v6/workflows/entry.py` - Integrated portfolio limits check
- `tests/risk/test_portfolio_limits.py` - Unit tests
- `tests/workflows/test_entry.py` - Updated integration tests

## Decisions Made

- Use PortfolioRiskCalculator (existing) for Greek aggregation
- Check limits AGGREGATE across all positions (not per-position)
- Backward compatible (EntryWorkflow works without portfolio_limits)
- Optional: IV-based adjustments deferred (per research recommendation)

## Next Step

Ready for 5-02-PLAN.md (Circuit breakers and auto-hedge)
</output>
