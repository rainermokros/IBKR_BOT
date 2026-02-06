# V6 Codebase Inventory

**Generated:** 2026-02-03
**Total Python Files:** 308

---

## Summary by Category

| Category | Count | Action |
|----------|-------|--------|
| **ACTIVE (Core)** | 91 | Keep - actively used |
| **TESTS** | 71 | Keep - test suite |
| **REVIEW NEEDED** | 71 | User decision required |
| **ARCHIVE** | 75 | Move to archive |

---

## Active Core Files (91) - KEEP

These files are actively used by the scheduler, dashboard, or core trading system.

### Scheduler (3 files)
- `src/v6/scheduler/scheduler.py` - Main unified scheduler - runs tasks via cron
- `src/v6/scheduler/nyse_calendar.py` - NYSE calendar - trading days, holidays, market hours
- `src/v6/data/scheduler_config.py` - Scheduler config Delta Lake table & default tasks

### Config (6 files)
- `src/v6/config/__init__.py` - Config package exports
- `src/v6/config/loader.py` - Config loader from YAML/environment
- `src/v6/config/production_config.py` - Production trading config
- `src/v6/config/paper_config.py` - Paper trading config
- `src/v6/config/futures_config.py` - Futures data fetcher config
- `src/v6/config/scheduler_config.py` - Scheduler config with task definitions

### Execution (5 files)
- `src/v6/execution/engine.py` - Main execution engine - handles order placement
- `src/v6/execution/strategy_executor.py` - Strategy-specific order execution
- `src/v6/execution/entry_executor.py` - Entry order execution
- `src/v6/execution/models.py` - Execution data models
- `src/v6/execution/assignment_monitor.py` - Assignment detection & handling

### Data (10 files)
- `src/v6/data/delta_persistence.py` - Delta Lake position writer
- `src/v6/data/position_streamer.py` - Real-time position streaming from IB
- `src/v6/data/position_queue.py` - Position queue for batch processing
- `src/v6/data/queue_worker.py` - Async queue worker
- `src/v6/data/reconciliation.py` - Position reconciliation IB vs Delta Lake
- `src/v6/data/strategy_registry.py` - Active strategy contract registry
- `src/v6/data/option_snapshots.py` - Option chain snapshot storage
- `src/v6/data/futures_persistence.py` - Futures data storage
- `src/v6/data/derived_statistics.py` - Derived statistics calculations
- `src/v6/data/ib_request_queue.py` - IB request queue for rate limiting

### Decisions (11 files)
- `src/v6/decisions/engine.py` - Main decision engine
- `src/v6/decisions/portfolio_risk.py` - Portfolio risk evaluation
- `src/v6/decisions/market_regime.py` - Market regime detection
- `src/v6/decisions/futures_integration.py` - Futures integration for decisions
- `src/v6/decisions/rules/__init__.py` - Rules package exports
- `src/v6/decisions/rules/catastrophe.py` - Catastrophic risk rules
- `src/v6/decisions/rules/entry_rules.py` - Entry decision rules
- `src/v6/decisions/rules/enhanced_entry_rules.py` - Enhanced entry rules
- `src/v6/decisions/rules/futures_entry_rules.py` - Futures-based entry rules
- `src/v6/decisions/rules/protection_rules.py` - Position protection rules
- `src/v6/decisions/rules/roll_rules.py` - Roll decision rules

### Strategies (5 files)
- `src/v6/strategies/builders.py` - Strategy builder classes
- `src/v6/strategies/strategy_selector.py` - Strategy selection logic
- `src/v6/strategies/smart_strike_selector.py` - Intelligent strike selection
- `src/v6/strategies/repository.py` - Strategy repository
- `src/v6/strategies/strategy_templates.py` - Strategy templates

### Risk (4 files)
- `src/v6/risk/circuit_breaker.py` - Circuit breaker - halt trading on issues
- `src/v6/risk/portfolio_limits.py` - Portfolio position/size limits
- `src/v6/risk/trailing_stop.py` - Trailing stop management
- `src/v6/risk/strategy_greeks_validator.py` - Greeks validation per strategy

### Workflows (3 files)
- `src/v6/workflows/entry.py` - Entry workflow
- `src/v6/workflows/exit.py` - Exit workflow
- `src/v6/workflows/monitoring.py` - Position monitoring workflow

### Monitoring (3 files)
- `src/v6/alerts/manager.py` - Alert manager
- `src/v6/monitoring/correlation_tracker.py` - Correlation tracking
- `src/v6/monitoring/data_quality.py` - Data quality monitoring

### Dashboard (30 files)
- `src/v6/dashboard/app.py` - Main dashboard app
- `src/v6/dashboard/config.py` - Dashboard config
- `src/v6/dashboard/components/*.py` (12 files) - UI components
- `src/v6/dashboard/data/*.py` (7 files) - Data sources
- `src/v6/dashboard/pages/*.py` (6 files) - Dashboard pages

### Scripts (11 files)
- `scripts/validate_ib_connection.py` - Validate IB Gateway connection
- `scripts/collect_option_snapshots.py` - Collect option chain data (5 min)
- `scripts/collect_futures_snapshots.py` - Collect futures data (5 min)
- `scripts/calculate_daily_statistics.py` - Calculate end-of-day statistics
- `scripts/health_check.py` - System health check
- `scripts/run_dashboard.py` - Launch Streamlit dashboard
- `scripts/run_paper_trading.py` - Run paper trading system
- `scripts/monitor_positions.py` - Monitor open positions
- `scripts/sync_ib_positions.py` - Sync positions from IB
- `scripts/queue_option_contracts.py` - Queue option contracts
- `scripts/schedule_935_et.py` - 9:35 AM ET scheduled task

---

## Test Files (71) - KEEP

All files in `tests/` directory should be kept.

---

## Files Requiring Review (71)

Please review these files and decide: **KEEP** or **ARCHIVE**

### Root Level Scripts (31 files) - ARCHIVE candidates
These appear to be one-off test/demo scripts in root directory:

```
collect_data.py
collect_data_working.py
collect_with_util.py
final_collect.py
one_script.py
run_queue_worker.py
simulate_45_21_strategies.py
demo_*.py (3 files)
test_*.py (18 files)
simple_*.py (3 files)
ultra_simple.py
use_existing_connection.py
verify_data_collection.py
```

**Recommendation:** → **ARCHIVE** all (move to `archive/root_scripts/`)

### Old Dashboard Versions (4 files)
```
dashboard_v2/* (5 files)
src/v6/dashboard/app_v3.py
src/v6/dashboard/app_v4.py
src/v6/dashboard/app_v5_hybrid.py
```

**Recommendation:** → **ARCHIVE** (only `app.py` is current)

### Unused Scripts (32 files)
Utility scripts not referenced by scheduler:
```
scripts/analyze_*.py
scripts/audit/*
scripts/backfill_*.py
scripts/calculate_intraday_statistics.py
scripts/calculate_real_profit.py
scripts/collect_option_snapshots_enhanced.py
scripts/collect_options_once.py
scripts/continuous_*.py
scripts/ensure_dashboard.py
scripts/filter_*.py
scripts/optimize_*.py
scripts/repartition_by_strike.py
scripts/run_dashboard_v*.py
scripts/run_optimization_safe.py
scripts/run_strategist.py
scripts/run_strategy_selector.py
scripts/run_strategy_with_fresh_data.py
scripts/stop_continuous_*.py
scripts/test_delta_*.py
```

**Recommendation:** → **ARCHIVE** (move to `archive/scripts/`)

### Unused src/v6/scripts (8 files)
```
src/v6/scripts/data_collector.py
src/v6/scripts/derive_statistics.py
src/v6/scripts/load_*.py
src/v6/scripts/schedule_derived_statistics.py
src/v6/scripts/test_*.py
```

**Recommendation:** → **ARCHIVE** (duplicate of scripts/ directory)

### Other src/v6 files (40+ files)

#### Package __init__.py files - KEEP or REMOVE?
These are Python package init files. Need decision:
- Keep all (cleaner imports)
- Or remove unused ones

#### Strategy Builders (5 files) - NEED DECISION
```
src/v6/strategies/credit_spread_builder_45_21.py
src/v6/strategies/delta_based_iron_condor_builder.py
src/v6/strategies/deltalake_builder.py
src/v6/strategies/iron_condor_builder_45_21.py
src/v6/strategies/wheel_builder_45_21.py
```
**Are these active strategy builders or old versions?**

#### Models (multiple files) - NEED DECISION
```
src/v6/alerts/models.py
src/v6/decisions/models.py
src/v6/execution/models.py (KEPT)
src/v6/risk/models.py
src/v6/strategies/models.py
src/v6/models/ib_models.py
src/v6/models/internal_state.py
```

#### Core modules (7 files) - NEED DECISION
```
src/v6/core/futures_analyzer.py
src/v6/core/futures_fetcher.py
src/v6/core/market_data_fetcher.py
src/v6/core/models.py
src/v6/core/unified_queue_worker.py
src/v6/indicators/__init__.py
src/v6/indicators/iv_rank.py
```

#### Orchestration (3 files) - NEED DECISION
```
src/v6/orchestration/__init__.py
src/v6/orchestration/paper_trader.py
src/v6/orchestration/production.py
```

#### Other (remaining) - NEED DECISION
```
src/v6/alerts/__init__.py, models.py
src/v6/cli/scheduler_manager.py
src/v6/dashboard/__init__.py
src/v6/decisions/__init__.py, models.py
src/v6/execution/__init__.py
src/v6/metrics/__init__.py, paper_metrics.py
src/v6/models/__init__.py, ib_models.py, internal_state.py
src/v6/monitoring/__init__.py, alerts.py
src/v6/risk/__init__.py, models.py, risk_events.py
src/v6/strategies/__init__.py, models.py
src/v6/utils/__init__.py, ib_connection.py
src/v6/workflows/__init__.py, test_workflows.py
```

---

## Archive Candidates (75)

Clear archive candidates (safe to move):

1. **Root level test/demo scripts** (31 files)
2. **Old dashboard versions** (9 files)
3. **Unused utility scripts** (32 files)
4. **Test files in src/** (3 files in src/v6/data/test_*.py)

---

## Next Steps

1. **Review this document** and mark decisions
2. **For "REVIEW NEEDED" files**, specify KEEP or ARCHIVE
3. **I will then**:
   - Create archive directory structure
   - Move approved files to archive
   - Update any imports if needed
   - Provide cleanup summary

---

## Questions for User

1. **Package __init__.py files**: Keep all or remove unused?
2. **Strategy builders** (`src/v6/strategies/*_builder_*.py`): Active or old?
3. **Orchestration files** (`src/v6/orchestration/*.py`): Active or old?
4. **Core modules** (`src/v6/core/*.py`, `src/v6/indicators/*.py`): Active or old?
5. **Models files**: Keep separate models per module or consolidate?
6. **Metrics/paper_trading**: Active or deprecated?
7. **CLI tools**: Keep `src/v6/cli/scheduler_manager.py`?

Please mark your decisions and I'll proceed with cleanup.
