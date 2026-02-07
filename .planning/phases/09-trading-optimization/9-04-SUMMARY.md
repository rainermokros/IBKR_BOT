---
phase: 09-trading-optimization
plan: 04
subsystem: trading-optimization
tags: [iv-skew, strike-selection, options, delta-lake, polars]

# Dependency graph
requires:
  - phase: 09-02
    provides: TradingConfig, config infrastructure
  - phase: 09-03
    provides: PortfolioRiskCalculator integration
provides:
  - IV skew ratio calculation (put IV / call IV)
  - Skew-aware delta adjustment for strike selection
  - IV data retrieval from OptionSnapshotsTable
  - Strategy metadata with skew_ratio and skew_interpretation
affects: [9-05, backtesting, strategy-analysis]

# Tech tracking
tech-stack:
  added: []
  patterns: [skew-aware-strike-selection, lazy-delta-lake-queries, graceful-fallback-to-neutral-skew]

key-files:
  created: []
  modified:
    - src/v6/strategy_builder/smart_strike_selector.py
    - src/v6/data/option_snapshots.py
    - src/v6/strategy_builder/strategy_selector.py
    - src/v6/strategy_builder/builders.py

key-decisions:
  - "Skew ratio interpretation: >1.2 = high put skew, <0.8 = high call skew, ~1.0 = neutral"
  - "Delta adjustment capped at 0.30 to prevent excessive risk"
  - "Graceful fallback to neutral skew (1.0) when IV data unavailable"
  - "Lazy Delta Lake queries for efficient IV lookup"

patterns-established:
  - "Skew ratio calculation using symmetric OTM puts/calls at +/- 1 STD"
  - "Delta adjustment: 20% higher delta on expensive side when skew elevated"
  - "Strategy metadata includes skew metrics for post-trade analysis"

# Metrics
duration: 25min
completed: 2026-02-07
---

# Phase 9: Plan 4 - Skew-Aware Strike Selection Summary

**IV skew-aware strike selection that sells expensive options (high IV skew) for improved strategy credit received**

## Performance

- **Duration:** 25 min
- **Started:** 2026-02-07T21:17:00Z
- **Completed:** 2026-02-07T21:42:00Z
- **Tasks:** 4
- **Files modified:** 4

## Accomplishments

- Added `calculate_skew_ratio()` method to SmartStrikeSelector for put/call IV ratio calculation
- Added `adjust_target_delta_for_skew()` for dynamic delta adjustment based on skew direction
- Updated `find_strike_with_delta_binary_search()` to accept and use skew_ratio parameter
- Added `get_iv_for_strike()` to OptionSnapshotsTable for efficient IV lookups from Delta Lake
- Integrated skew calculation into all StrategySelector strategy builders (Iron Condor, Bull Put, Bear Call)
- Strategy metadata now includes skew_ratio and skew_interpretation for analysis

## Task Commits

Each task was committed atomically:

1. **Task 1: Add IV skew calculation to SmartStrikeSelector** - `be13bf3` (feat)
2. **Task 2: Add IV data retrieval to OptionSnapshotsTable** - `355313e` (feat)
3. **Task 3: Integrate skew into StrategySelector strategy building** - `18da832` (feat)
4. **Task 4: Update SmartStrikeSelector binary search to use skew-adjusted delta** - `be13bf3` (feat - included in Task 1)

## Files Created/Modified

- `src/v6/strategy_builder/smart_strike_selector.py` - Added skew calculation methods and skew-adjusted binary search
- `src/v6/data/option_snapshots.py` - Added get_iv_for_strike() method for IV lookups
- `src/v6/strategy_builder/strategy_selector.py` - Added skew calculation to all strategy builders
- `src/v6/strategy_builder/builders.py` - Added SmartStrikeSelector import and skew_ratio parameter support

## Decisions Made

1. **Skew interpretation thresholds**: >1.2 = high put skew (sell puts), <0.8 = high call skew (sell calls), ~1.0 = neutral
2. **Delta adjustment cap**: 20% higher delta on expensive side, capped at 0.30 absolute to prevent excessive risk
3. **Graceful fallback**: Return neutral skew (1.0) when IV data unavailable rather than failing
4. **Lazy Delta Lake queries**: Use pl.scan_delta() for efficient IV lookups without loading entire table

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all implementations worked as expected.

## Verification

All verification checks passed:
- Python syntax check: PASSED
- Import test: PASSED
- Skew calculation methods exist: PASSED
- get_iv_for_strike in option_snapshots: PASSED
- StrategySelector stores skew_ratio in metadata: PASSED

## Next Phase Readiness

**Ready for 9-05 (Historical/Live Variance Analysis):**
- Skew-aware strike selection complete
- IV data retrieval infrastructure in place
- Strategy metadata includes skew metrics for variance analysis

**No blockers or concerns.**

---
*Phase: 09-trading-optimization*
*Plan: 04*
*Completed: 2026-02-07*
