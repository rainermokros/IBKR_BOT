---
phase: 09-trading-optimization
plan: 03
title: "Unified Portfolio Integration"
completed: 2026-02-07
duration: ~30 minutes
---

# Phase 9 Plan 03: Unified Portfolio Integration Summary

Integrate portfolio risk calculation into the entry workflow to ensure current portfolio state (delta, position counts) is accurately reflected in entry decisions.

## One-Liner
Portfolio-aware entry workflow using PortfolioRiskCalculator for Greek-based risk assessment and PortfolioLimitsChecker for limit validation.

## Completed Tasks

| Task | Name | Commit | Files |
| ---- | ----- | ------ | ----- |
| 1 | Review PortfolioRiskCalculator interface | - | Understanding documented |
| 2 | Add portfolio risk integration to evaluate_entry_signal | d87be3c | src/v6/risk_manager/trading_workflows/entry.py, src/v6/strategy_builder/decision_engine/portfolio_risk.py |
| 3 | Enhance portfolio limit checking in execute_entry | e0c1d89 | src/v6/risk_manager/trading_workflows/entry.py |
| 4 | Add EntryWorkflow.from_config factory method | 7cdc8d2 | src/v6/risk_manager/trading_workflows/entry.py |

## Artifacts Created

### 1. Enhanced EntryWorkflow (`src/v6/risk_manager/trading_workflows/entry.py`)

**New parameters:**
- `portfolio_risk_calc: PortfolioRiskCalculator = None` - Portfolio risk calculator for real-time state

**Methods modified:**
- `evaluate_entry_signal()`: Now calls `calculate_portfolio_risk()` to get current portfolio delta and position counts
- `execute_entry()`: Enhanced delta calculation using Greeks from strategy.metadata, detailed rejection logging

**New methods:**
- `from_config()`: Factory method for creating fully-wired EntryWorkflow with portfolio components

### 2. Fixed PortfolioRiskCalculator (`src/v6/strategy_builder/decision_engine/portfolio_risk.py`)

**Changes:**
- Removed non-existent `PositionsRepository` dependency
- Now reads positions directly from Delta Lake table (`data/lake/positions`)
- Uses Polars LazyFrame for efficient data loading
- Constructor: `__init__(positions_path: str | None = None)`

## Deviations from Plan

### Rule 3 - Auto-fix blocking issue: Fixed PortfolioRiskCalculator import

**Found during:** Task 2
**Issue:** `PortfolioRiskCalculator` imported non-existent `PositionsRepository`
**Fix:** Modified `PortfolioRiskCalculator` to read positions directly from Delta Lake table
**Files modified:** `src/v6/strategy_builder/decision_engine/portfolio_risk.py`
**Commit:** d87be3c

The original implementation expected a repository class that doesn't exist. Fixed by implementing direct Delta Lake reads using Polars, following the pattern established in `option_snapshots.py`.

## Key Links Established

| From | To | Via | Pattern |
| ---- | --- | --- | ------ |
| `EntryWorkflow.evaluate_entry_signal()` | `PortfolioRiskCalculator.calculate_portfolio_risk()` | Calls for portfolio state | `portfolio_risk_calc` |
| `EntryWorkflow.execute_entry()` | `PortfolioLimitsChecker.check_entry_allowed()` | Validates limits before entry | `portfolio_limits` |
| `PortfolioLimitsChecker` | `PortfolioRiskCalculator` | Uses for portfolio calculations | `risk_calculator` |

## Verification Results

All verification checks passed:
1. Python syntax check: PASSED
2. Import test: PASSED
3. PortfolioRiskCalculator import: PASSED
4. PortfolioLimitsChecker import: PASSED
5. from_config() callable: True

## Self-Check: PASSED

**Created files:**
- [x] `.planning/phases/09-trading-optimization/9-03-SUMMARY.md` - This file

**Commits verified:**
- [x] d87be3c: feat(9-03): integrate PortfolioRiskCalculator into EntryWorkflow
- [x] e0c1d89: feat(9-03): enhance portfolio limit checking with Greek-based delta calculation
- [x] 7cdc8d2: feat(9-03): add EntryWorkflow.from_config factory method

**Success criteria met:**
- [x] EntryWorkflow uses PortfolioRiskCalculator for portfolio state at entry
- [x] Portfolio delta calculated and used in entry decision
- [x] PortfolioLimitsChecker validates entry against all limits
- [x] Rejection logging shows clear reason (delta, concentration, etc.)
- [x] from_config() creates fully wired EntryWorkflow
- [x] Backward compatible (works without portfolio components)
