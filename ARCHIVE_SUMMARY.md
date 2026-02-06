# V6 Codebase Cleanup Summary

**Date:** 2026-02-03
**Status:** First phase complete

---

## What Was Done

### Archived Files: 80 → `/home/bigballs/project/bot/v6_archive/`

#### Root Level Scripts (31 files)
All test/demo scripts from root directory moved to `archive/root_scripts/`:
- collect_data.py, collect_data_working.py, collect_with_util.py
- final_collect.py, one_script.py, run_queue_worker.py
- simulate_45_21_strategies.py
- demo_*.py (3 files)
- test_*.py (18 files)
- simple_*.py (3 files)
- ultra_simple.py, use_existing_connection.py, verify_data_collection.py

#### Old Dashboard Versions (9 files)
- `dashboard_v2/` - Complete old dashboard (5 files)
- `src/v6/dashboard/app_v3.py`
- `src/v6/dashboard/app_v4.py`
- `src/v6/dashboard/app_v5_hybrid.py`

#### Unused Scripts (35 files)
Moved to `archive/scripts/` and `archive/scripts_audit/`:
- Utility scripts not referenced by scheduler
- Audit scripts (data_completeness, greeks_validation, trading_safety_audit)
- Test scripts (test_delta_*.py)
- Optimization scripts (optimize_*.py)
- Continuous collectors (continuous_*.py)
- Old dashboard runners (run_dashboard_v3.py, run_dashboard_v5.py)

#### Test Files in src/ (8 files)
Moved to appropriate archive subdirectories:
- `src/v6/data/test_*.py` (7 files)
- `src/v6/execution/test_engine.py`
- `src/v6/scripts/test_*.py` (2 files)
- `src/v6/workflows/test_workflows.py`

---

## Current State

### Remaining Files: 228

| Directory | Files | Status |
|-----------|-------|--------|
| `src/v6/` | 145 | Active core code |
| `tests/` | 71 | Test suite (preserved) |
| `scripts/` | 12 | Active runnable scripts |
| Root | 0 | ✓ Clean |

---

## Files Still Needing Review

### 1. Package `__init__.py` Files (35 files)
**Decision needed:** Keep all (for cleaner imports) or remove unused?

Located in every package directory:
- src/v6/*/
- tests/*/

**Recommendation:** KEEP - Required for Python package structure

### 2. Strategy Builders (7 files)
```
src/v6/strategies/builders.py  ← Active
src/v6/strategies/strategy_templates.py  ← Active
src/v6/strategies/credit_spread_builder_45_21.py  ← ???
src/v6/strategies/delta_based_iron_condor_builder.py  ← ???
src/v6/strategies/deltalake_builder.py  ← ???
src/v6/strategies/iron_condor_builder_45_21.py  ← ???
src/v6/strategies/wheel_builder_45_21.py  ← ???
src/v6/strategies/test_builders.py  ← ???
```

**Question:** Are the specific 45-21 builders active or old versions?

### 3. Orchestration (2 files)
```
src/v6/orchestration/paper_trader.py
src/v6/orchestration/production.py
```

**Question:** Active or deprecated?

### 4. Core Modules (5 files)
```
src/v6/core/futures_analyzer.py
src/v6/core/futures_fetcher.py
src/v6/core/market_data_fetcher.py
src/v6/core/models.py
src/v6/core/unified_queue_worker.py
```

**Question:** Active or deprecated?

### 5. Models (5 files)
Separate models in each module:
```
src/v6/alerts/models.py
src/v6/decisions/models.py
src/v6/execution/models.py  ← Active (KEPT)
src/v6/risk/models.py
src/v6/strategies/models.py
```

**Question:** Keep separate or consolidate?

### 6. Metrics/Paper Trading (1 file)
```
src/v6/metrics/paper_metrics.py
```

**Question:** Active?

### 7. CLI Tools (1 file)
```
src/v6/cli/scheduler_manager.py
```

**Question:** Keep CLI scheduler manager?

### 8. Indicators (1 file)
```
src/v6/indicators/iv_rank.py
```

**Question:** Active?

### 9. Other Potential Duplicates
These may have overlapping functionality:
- `src/v6/monitoring/alerts.py` vs `src/v6/alerts/manager.py`
- `src/v6/scheduler/morning_scheduler.py` vs `src/v6/scheduler/unified_scheduler.py`
- `src/v6/scheduler/scheduler.py` (current active)
- Multiple entry/exit/monitoring implementations

---

## Active Scripts (12) - Confirmed Keep

```
scripts/validate_ib_connection.py
scripts/collect_option_snapshots.py
scripts/collect_futures_snapshots.py
scripts/calculate_daily_statistics.py
scripts/health_check.py
scripts/monitor_positions.py
scripts/queue_option_contracts.py
scripts/run_dashboard.py
scripts/run_paper_trading.py
scripts/schedule_935_et.py
scripts/sync_ib_positions.py
```

---

## Archive Location

**Path:** `/home/bigballs/project/bot/v6_archive/v6_archived_20260203_072911/`

**Structure:**
```
v6_archive/v6_archived_20260203_072911/
├── ARCHIVE_INDEX.txt
├── root_scripts/          (31 files)
├── dashboard_v2/           (5 files)
├── old_dashboards/         (3 files)
├── scripts/               (29 files)
├── scripts_audit/          (3 files)
├── src_v6_data/           (7 files)
├── src_v6_execution/      (1 file)
├── src_v6_scripts/        (2 files)
└── src_v6_workflows/      (1 file)
```

**To restore a file:**
```bash
cp /home/bigballs/project/bot/v6_archive/v6_archived_20260203_072911/<category>/<filename> \
   /home/bigballs/project/bot/v6/<original_path>/
```

---

## Next Steps

1. **Review the 9 categories above** and make decisions
2. **I will then:**
   - Archive additional files based on your decisions
   - Update any imports if needed
   - Create final cleanup summary

---

## Statistics

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Total Python files | 308 | 228 | -80 (-26%) |
| Root level scripts | 31 | 0 | -31 |
| Dashboard versions | 4 | 1 | -3 |
| Test files in src/ | 11 | 0 | -11 |
| Unused scripts | 35+ | 0 | -35 |

---

## Notes

- All test files in `tests/` directory were preserved
- Active scheduler configuration preserved
- Active dashboard (`app.py`) preserved
- No import updates needed (archived files weren't imported by active code)
- Archive timestamped for easy restoration if needed
