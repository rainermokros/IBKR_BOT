# Phase 5 Plan 1: Portfolio-Level Controls Summary

**Implemented portfolio-level risk controls to prevent aggregate Greek exposure and concentration risk.**

## Accomplishments

### Risk Models and Configuration
- Created `RiskLimitsConfig` dataclass with configurable thresholds for:
  - `max_portfolio_delta`: Maximum net portfolio delta (default: 50.0)
  - `max_portfolio_gamma`: Maximum net portfolio gamma (default: 10.0)
  - `max_single_position_pct`: Maximum single position as percentage (default: 2%)
  - `max_per_symbol_delta`: Maximum delta per symbol (default: 20.0)
  - `max_correlated_pct`: Maximum correlated exposure (default: 5%)
  - `total_exposure_cap`: Optional total exposure cap in dollars
- Created `PortfolioLimitExceededError` exception for limit violations
- Used `@dataclass(slots=True)` for performance consistency with v6 patterns

### Portfolio Limits Checker
- Implemented `PortfolioLimitsChecker` class with comprehensive limit checks:
  - Portfolio delta limit checking (aggregate delta across all positions)
  - Portfolio gamma limit checking
  - Per-symbol delta limit checking
  - Concentration limit checking (position value / total exposure)
  - Correlated exposure limit checking (by symbol as proxy for sector)
  - Total exposure cap checking (if configured)
- Provided three key methods:
  - `check_entry_allowed()`: Validates if new position would exceed limits
  - `check_portfolio_health()`: Returns warnings for currently exceeded limits
  - `get_remaining_capacity()`: Calculates remaining capacity for new entries
- Integrated with existing `PortfolioRiskCalculator` for Greek aggregation

### EntryWorkflow Integration
- Updated `EntryWorkflow` to accept optional `portfolio_limits` parameter
- Added portfolio limits check AFTER strategy building, BEFORE order placement
- Calculated position metrics:
  - Position delta: Sum of SELL legs - BUY legs
  - Position value: Sum of strike × quantity × 100 for all legs
- Raises `PortfolioLimitExceededError` when limits exceeded
- Maintained backward compatibility (works without `portfolio_limits` parameter)

### Comprehensive Testing
- Created 21 unit and integration tests:
  - 14 tests for `PortfolioLimitsChecker` covering all limit types
  - 7 tests for `EntryWorkflow` integration
- Test coverage includes:
  - Empty portfolio handling
  - Moderate portfolio scenarios
  - Limit rejection scenarios (delta, symbol delta, concentration, exposure cap)
  - Negative delta handling (short positions)
  - Portfolio health warnings
  - Remaining capacity calculations
  - Backward compatibility
- All tests passing (21/21)

## Files Created/Modified

### Created
- `src/v6/risk/models.py` - Risk configuration and exceptions (68 lines)
- `src/v6/risk/portfolio_limits.py` - PortfolioLimitsChecker implementation (285 lines)
- `src/v6/risk/__init__.py` - Module exports with backward compatibility alias
- `tests/risk/__init__.py` - Test package
- `tests/risk/test_portfolio_limits.py` - 14 comprehensive unit tests (525 lines)
- `tests/workflows/__init__.py` - Test package
- `tests/workflows/test_entry.py` - 7 integration tests (476 lines)

### Modified
- `src/v6/workflows/entry.py` - Integrated portfolio limits check
  - Added `portfolio_limits` parameter to `__init__`
  - Added portfolio limits validation in `execute_entry` method
  - Added imports for risk models

## Decisions Made

1. **Use PortfolioRiskCalculator (existing) for Greek aggregation**
   - Leverages existing, tested code for portfolio risk calculation
   - Avoids duplication and ensures consistency

2. **Check limits AGGREGATE across all positions**
   - Portfolio-level limits, not per-position limits
   - Prevents Greek exposure accumulation across multiple positions

3. **Backward compatible design**
   - `EntryWorkflow` works without `portfolio_limits` parameter
   - Provides alias `PortfolioLimitExceeded` for `PortfolioLimitExceededError`
   - Existing code continues to work unchanged

4. **Concentration limit calculation**
   - Position value calculated as: sum(strike × quantity × 100)
   - Concentration = position_value / (current_exposure + position_value)
   - Prevents single position from dominating portfolio

5. **Naming convention**
   - Exception named `PortfolioLimitExceededError` (follows Python naming convention)
   - Provides `PortfolioLimitExceeded` alias for backward compatibility

6. **IV-based adjustments deferred**
   - Per research recommendation, static limits implemented first
   - IV-based dynamic scaling can be added in Phase 6 (Monitoring)

## Technical Implementation Details

### Position Delta Calculation
```python
position_delta = sum(
    leg.quantity if leg.action == LegAction.SELL else -leg.quantity
    for leg in strategy.legs
)
```
- SELL legs contribute positive delta
- BUY legs contribute negative delta
- Simplified approach (actual Greeks would be more accurate)

### Position Value Calculation
```python
position_value = sum(
    abs(leg.quantity) * leg.strike * 100
    for leg in strategy.legs
)
```
- Uses strike price as proxy for position value
- Multiplies by 100 (options contract multiplier)
- Rough estimate suitable for risk limiting

### Integration Point in EntryWorkflow
Portfolio limits check occurs at:
1. Build strategy ✓
2. **Validate strategy ✓**
3. **Check portfolio limits ← NEW**
4. Create StrategyExecution
5. Place orders

This ensures:
- Strategy is valid before checking limits
- No orders placed if limits exceeded
- Early rejection saves API calls and latency

## Verification

### Tests Passing
- All 21 tests passing (100%)
- 14 PortfolioLimitsChecker tests
- 7 EntryWorkflow integration tests
- Edge cases covered (empty portfolio, negative delta, concentration limits)

### Code Quality
- Ruff linting passes (all checks passed)
- Type hints on all functions
- Comprehensive docstrings
- Consistent with v6 patterns (`dataclass(slots=True)`, async/await)

### Integration Verified
- PortfolioLimitsChecker correctly uses PortfolioRiskCalculator
- EntryWorkflow integration working (limits checked before orders)
- Backward compatible (EntryWorkflow works without portfolio_limits)
- Exception handling tested (PortfolioLimitExceededError raised when limits exceeded)

## Next Step

Ready for **5-02-PLAN.md** (Circuit breakers and auto-hedge)

The portfolio-level controls foundation is now in place. Next phase will implement:
- Circuit breaker pattern for system-level fault tolerance
- Auto-hedge on risk spikes
- Real-time protection mechanisms
