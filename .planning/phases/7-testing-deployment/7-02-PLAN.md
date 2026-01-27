# Phase 7 Plan 2: Paper Trading Validation

**Phase:** 7
**Plan:** 02
**Type:** Implementation
**Granularity:** plan
**Depends on:** None (can run in parallel with 7-01, 7-03)
**Files modified:** (tracked after execution)

## Objective

Implement a paper trading environment that simulates live trading without real capital, validates strategy performance, and collects metrics to compare against historical backtests.

## Execution Context

@~/.claude/get-shit-done/workflows/execute-plan.md
@~/.claude/get-shit-done/templates/phase-prompt.md
@~/.claude/get-shit-done/references/checkpoints.md
@~/.claude/get-shit-done/references/tdd.md

## Context

### Project State
@.planning/STATE.md
@.planning/ROADMAP.md
@.planning/PROJECT.md

### Completed Phases
@.planning/phases/4-strategy-execution/4-03-SUMMARY.md (Entry/exit workflows)
@.planning/phases/5-risk-management/5-03-SUMMARY.md (Risk controls)
@.planning/phases/6-monitoring-dashboard/6-03-SUMMARY.md (Dashboard monitoring)

### Expertise Areas
~/.claude/skills/expertise/ib-async-api/SKILL.md (IB paper trading accounts)
~/.claude/skills/expertise/ib-order-manager/SKILL.md (Order execution validation)
~/.claude/skills/expertise/position-manager/SKILL.md (Position tracking validation)

### System Components
@src/v6/execution/engine.py (OrderExecutionEngine with dry_run mode)
@src/v6/workflows/entry.py (EntryWorkflow)
@src/v6/workflows/monitoring.py (MonitoringWorkflow)
@src/v6/workflows/exit.py (ExitWorkflow)
@src/v6/dashboard/app.py (Monitoring dashboard)

## Tasks

### Task 1: Create Paper Trading Configuration
**Type:** auto

Set up configuration system for paper trading environment with separate settings from production.

**Steps:**
1. Create `src/v6/config/paper_config.py` with:
   - `PaperTradingConfig` dataclass:
     - `ib_host`, `ib_port`, `ib_client_id` (paper trading account)
     - `dry_run: bool = True` (enforce dry-run mode)
     - `max_positions: int = 5` (limit exposure)
     - `max_order_size: int = 1` (limit contract size)
     - `allowed_symbols: list[str]` (whitelist for paper trading: SPY, QQQ, IWM)
     - `paper_start_date: datetime` (track paper trading period)
     - `paper_starting_capital: float` (simulated capital)
2. Create `src/v6/config/__init__.py` to export configs
3. Create `config/paper_trading.yaml.example`:
   - IB paper trading account credentials
   - Risk limits specific to paper trading
   - Symbol whitelist
   - Position size limits
4. Create `.env.example` with:
   - `PAPER_TRADING_IB_HOST=127.0.0.1`
   - `PAPER_TRADING_IB_PORT=7497` (or different port)
   - `PAPER_TRADING_IB_CLIENT_ID=2`
   - `PAPER_TRADING_START_DATE=2026-01-27`
5. Document setup in README: `docs/PAPER_TRADING_SETUP.md`

**Acceptance Criteria:**
- Paper trading config enforces safety limits (dry_run, max positions, max order size)
- Config validates required fields (IB credentials, allowed symbols)
- Example config provided for users to copy
- .env.example clearly documents paper trading variables

### Task 2: Implement Paper Trading Orchestration
**Type:** auto

Create paper trading orchestrator that runs entry/monitoring/exit workflows with paper trading configuration.

**Steps:**
1. Create `src/v6/orchestration/__init__.py`
2. Create `src/v6/orchestration/paper_trader.py` with:
   - `PaperTrader` class:
     - `__init__(config: PaperTradingConfig)` - Load config, initialize components
     - `async start()` - Connect to IB (paper account), start position sync
     - `async run_entry_cycle()` - Run entry workflow with paper limits
     - `async run_monitoring_cycle()` - Run monitoring workflow
     - `async run_exit_cycle()` - Run exit workflow
     - `async stop()` - Clean shutdown
     - `get_paper_metrics()` - Return paper trading performance
3. Integrate with existing workflows:
   - EntryWorkflow: Check `config.allowed_symbols`, `config.max_positions`
   - MonitoringWorkflow: Log all decisions (paper trading analysis)
   - ExitWorkflow: Track paper P&L separately
4. Create `scripts/run_paper_trading.py`:
   - Parse config file and .env
   - Initialize PaperTrader
   - Run main loop (entry → monitor → exit cycles)
   - Handle graceful shutdown (SIGINT, SIGTERM)
5. Add logging specific to paper trading (mark all trades as "PAPER")

**Acceptance Criteria:**
- PaperTrader enforces all safety limits from config
- All trades marked as paper trading (logs, Delta Lake metadata)
- Graceful shutdown works (Ctrl+C cleans up connections)
- Separate logging for paper vs production (different log files)

### Task 3: Create Paper Trading Metrics Tracker
**Type:** auto

Implement performance tracking specifically for paper trading to validate strategies.

**Steps:**
1. Create `src/v6/metrics/__init__.py`
2. Create `src/v6/metrics/paper_metrics.py` with:
   - `PaperMetricsTracker` class:
     - `record_trade(strategy_id, entry_price, exit_price, P&L, duration)` - Record completed trade
     - `record_decision(strategy_id, decision_type, reason)` - Record all decisions (exit reasons)
     - `get_trade_summary()` - Return win rate, avg P&L, avg duration
     - `get_decision_breakdown()` - Return exit reason distribution (stop loss, take profit, time exit, etc.)
     - `get_equity_curve()` - Return equity over time for paper trading period
     - `get_sharpe_ratio()` - Calculate risk-adjusted return
     - `get_max_drawdown()` - Calculate maximum drawdown
3. Create Delta Lake table: `data/lake/paper_trades/` with schema:
   - `strategy_id`, `symbol`, `entry_date`, `exit_date`, `entry_premium`, `exit_premium`, `pnl`, `exit_reason`, `duration_days`
4. Create dashboard page for paper trading metrics:
   - `src/v6/dashboard/pages/5_paper_trading.py`:
     - Trade summary table (all paper trades)
     - Win rate, avg P&L, avg duration metrics
     - Equity curve chart (P&L over time)
     - Exit reason distribution (pie chart)
     - Comparison: paper trading vs historical expectations
5. Add paper trading metrics to existing portfolio page

**Acceptance Criteria:**
- All paper trades recorded to Delta Lake with full details
- Metrics calculated correctly (win rate, Sharpe, drawdown)
- Dashboard displays paper trading performance clearly
- Equity curve shows P&L trajectory over time
- Exit reason distribution shows which rules are triggering most

### Task 4: Implement Paper Trading Validation Tests
**Type:** auto

Create tests to validate paper trading behavior matches expected rules and risk limits.

**Steps:**
1. Create `tests/paper_trading/__init__.py`
2. Create `tests/paper_trading/test_paper_config.py`:
   - Test: Config validates required fields
   - Test: Config enforces dry_run=True
   - Test: Config limits max_positions and max_order_size
   - Test: Config rejects invalid symbols (not in whitelist)
3. Create `tests/paper_trading/test_paper_trader.py`:
   - Test: PaperTrader connects to IB paper account
   - Test: Entry workflow rejects trades exceeding max_positions
   - Test: Entry workflow rejects symbols not in whitelist
   - Test: Exit workflow records P&L to paper_metrics
   - Test: All trades marked as "PAPER" in logs and Delta Lake
4. Create `tests/paper_trading/test_paper_metrics.py`:
   - Test: Metrics tracker records trades correctly
   - Test: Win rate calculated correctly
   - Test: Sharpe ratio calculated correctly
   - Test: Max drawdown calculated correctly
   - Test: Equity curve returns data in correct format
5. Create `tests/paper_trading/test_paper_integration.py`:
   - Test: End-to-end paper trade (entry → monitor → exit)
   - Test: Paper trading cycle runs without errors
   - Test: Dashboard reads paper trading data correctly
   - Test: Paper trading doesn't affect production data

**Acceptance Criteria:**
- All paper trading configuration validated
- Safety limits enforced (max positions, symbol whitelist, dry run)
- Metrics calculations tested for accuracy
- Integration test validates complete paper trading workflow
- Tests confirm paper trading data isolated from production

## Verification

### Manual Testing
1. Set up IB paper trading account (or use mock if unavailable)
2. Configure paper trading in `config/paper_trading.yaml`
3. Run paper trader: `python scripts/run_paper_trading.py`
4. Monitor dashboard at http://localhost:8501/pages/5_paper_trading
5. Verify trades executed with paper trading limits
6. Verify metrics tracked correctly (win rate, P&L, equity curve)

### Automated Checks
```bash
# Run paper trading tests
pytest tests/paper_trading/ -v

# Run paper trader (with mock IB if unavailable)
python scripts/run_paper_trading.py --dry-run --mock-ib

# Check Delta Lake has paper trades
python -c "import polars as pl; df = pl.read_delta('data/lake/paper_trades'); print(df)"

# Verify dashboard loads paper data
streamlit run src/v6/dashboard/app.py
```

## Success Criteria

- [ ] Paper trading configuration enforces safety limits
- [ ] Paper trader runs complete cycles (entry → monitor → exit)
- [ ] All trades marked as "PAPER" and isolated from production
- [ ] Paper trading metrics tracked (win rate, Sharpe, drawdown)
- [ ] Dashboard displays paper trading performance
- [ ] Tests validate safety limits and metrics calculations
- [ ] Documentation for setting up paper trading account
- [ ] Paper trading runs for at least 1 week without errors
- [ ] Performance metrics collected and comparable to backtests

## Output

**Created Files:**
- `src/v6/config/__init__.py`
- `src/v6/config/paper_config.py` (PaperTradingConfig dataclass)
- `config/paper_trading.yaml.example` (example configuration)
- `.env.example` (updated with paper trading variables)
- `src/v6/orchestration/__init__.py`
- `src/v6/orchestration/paper_trader.py` (PaperTrader orchestrator)
- `scripts/run_paper_trading.py` (main script)
- `src/v6/metrics/__init__.py`
- `src/v6/metrics/paper_metrics.py` (PaperMetricsTracker)
- `src/v6/dashboard/pages/5_paper_trading.py` (paper trading dashboard page)
- `tests/paper_trading/__init__.py`
- `tests/paper_trading/test_paper_config.py` (config validation)
- `tests/paper_trading/test_paper_trader.py` (orchestrator tests)
- `tests/paper_trading/test_paper_metrics.py` (metrics calculation tests)
- `tests/paper_trading/test_paper_integration.py` (end-to-end tests)
- `docs/PAPER_TRADING_SETUP.md` (setup guide)

**Delta Lake Tables:**
- `data/lake/paper_trades/` (paper trading trade history)

**Modified Files:**
- `src/v6/dashboard/app.py` (add paper trading page to navigation)
- `.gitignore` (add config/paper_trading.yaml)

**Documentation:**
- PAPER_TRADING_SETUP.md with:
  - IB paper trading account setup
  - Configuration instructions
  - Running paper trader
  - Monitoring dashboard
  - Transitioning to production

**Tests Created:**
- 10+ paper trading tests (config, orchestrator, metrics, integration)
- All tests passing
- Paper trading validated for safety and accuracy
