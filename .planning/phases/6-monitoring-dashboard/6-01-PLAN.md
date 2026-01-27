# Phase 6 Plan 1: Real-Time Monitoring Dashboard

**Status:** Planning
**Type:** Feature
**Priority:** High
**Dependencies:** Phase 5 (Risk Management)
**Research:** Complete (see 6-RESEARCH.md)

---

## Objective

Build a real-time monitoring dashboard using Streamlit to display positions, portfolio Greeks, and P&L. Dashboard provides visibility into all active strategies, risk metrics, and system performance.

**Success Criteria:**
- Streamlit multi-page dashboard running on http://localhost:8501
- Real-time position display with auto-refresh (5-30s configurable)
- Portfolio Greeks aggregation with interactive Plotly visualizations
- P&L tracking and performance metrics
- Reads from Delta Lake (positions, option_legs, option_snapshots)
- Caching strategy to avoid IB API rate limits
- Responsive layout with filtering and sorting

---

## Execution Context

### Stack
- **streamlit** 1.28+ - Dashboard framework
- **plotly** 5.18+ - Interactive charts
- **pandas** 2.0+ - Data manipulation
- **delta-spark** 3.0+ - Delta Lake reads

### Context Files
- `.planning/phases/6-monitoring-dashboard/6-RESEARCH.md` - Complete research on Streamlit patterns, pitfalls, best practices
- `.planning/phases/4-strategy-execution/4-03-SUMMARY.md` - Entry/exit workflows, strategy execution data model
- `.planning/phases/5-risk-management/5-RESEARCH.md` - Risk management architecture (PortfolioRiskCalculator, risk limits)

### Key Integration Points
- **Delta Lake**: Read positions from `option_legs`, `option_snapshots`, `strategy_executions` tables
- **PortfolioRiskCalculator**: Use existing Greek aggregation (from Phase 3/5)
- **AlertManager**: Read alerts from DecisionEngine (Phase 3)
- **IBConnectionManager**: Check connection status for system health

---

## Context

### Phase 6 Overview
Phase 6 builds the monitoring and visibility layer for the v6 trading system. The dashboard provides real-time insight into:
- Active positions (symbols, strategies, Greeks, P&L)
- Portfolio-level metrics (aggregate Greeks, exposure, concentration)
- System health (IB connection, data freshness, active strategies)
- Alert management (active alerts, history, acknowledgment)

This is Plan 1 of 3:
- **6-01**: Real-time monitoring dashboard (this plan)
- **6-02**: Alert management UI
- **6-03**: System health monitoring

### Prior Phase Accomplishments

**Phase 4 (Strategy Execution)**: Complete workflow automation
- EntryWorkflow: Signal evaluation → strategy building → order placement
- PositionMonitoringWorkflow: Monitor open positions, evaluate decisions
- ExitWorkflow: Execute exit decisions, close positions
- **Data model**: StrategyExecution, OptionLeg, Greeks, P&L

**Phase 5 (Risk Management)**: Three-layered risk controls
- PortfolioLimitsChecker: Portfolio-level Greek/exposure limits
- TradingCircuitBreaker: System-level fault tolerance
- TrailingStopManager: Position-level profit protection
- **125 tests passing**: Comprehensive risk management coverage

**Phase 3 (Decision Rules Engine)**: Decision and alert infrastructure
- DecisionEngine: 12 priority-based rules
- AlertManager: Alert generation, history, acknowledgment
- PortfolioRiskCalculator: Greek aggregation, portfolio metrics

### Current System State

**Data Available in Delta Lake:**
```python
option_legs:
  - execution_id, conid, symbol, strike, expiry, right, quantity, action
  - current_premium, greeks (delta, gamma, theta, vega)

option_snapshots:
  - timestamp, execution_id, mid_price, bid_ask_spread, iv, hv
  - greeks (delta, gamma, theta, vega, rho)
  - underlying_price, dte

strategy_executions:
  - strategy_id, symbol, strategy_type, status, entry_time, close_time
  - entry_decision_id, exit_decision_id
  - metadata (legs, decisions, trailing_stops)
```

**Existing Components to Integrate:**
- `PortfolioRiskCalculator` (Phase 3): Greek aggregation, portfolio metrics
- `AlertManager` (Phase 3): Alert history, active alerts
- `IBConnectionManager` (Phase 1): Connection status checks
- `StrategyRepository` (Phase 4): Strategy execution queries

---

## Tasks

### Task 1: Create Dashboard Project Structure

**Objective:** Set up Streamlit project structure with multi-page support

**Files to create:**
- `src/v6/dashboard/__init__.py` - Package exports
- `src/v6/dashboard/app.py` - Main Streamlit app entry point
- `src/v6/dashboard/pages/__init__.py` - Pages package
- `src/v6/dashboard/pages/1_positions.py` - Position monitor page
- `src/v6/dashboard/pages/2_portfolio.py` - Portfolio analytics page
- `src/v6/dashboard/components/__init__.py` - Components package

**Implementation approach:**
1. Use Streamlit's native multi-page support (pages/ directory)
2. Configure page layout (wide, expanded sidebar)
3. Add navigation links in sidebar
4. Set page config (title, icon, layout)

**Verification:**
- `streamlit run src/v6/dashboard/app.py` starts successfully
- Multi-page navigation works (Home, Positions, Portfolio)
- Sidebar displays navigation links
- Page layout is wide, responsive

---

### Task 2: Build Position Monitor Page

**Objective:** Display all active positions with Greeks, P&L, and filtering

**Files to create:**
- `src/v6/dashboard/data/positions.py` - Position data loading functions
- `src/v6/dashboard/components/position_card.py` - Position display widget
- `src/v6/dashboard/pages/1_positions.py` - Position monitor page (complete)

**Implementation approach:**
1. Create `load_positions()` function:
   - Read from Delta Lake (option_legs joined with strategy_executions)
   - Filter by status (OPEN/CLOSED/ALL)
   - Aggregate Greeks per execution_id
   - Return pandas DataFrame

2. Create `position_card` component:
   - Display symbol, strategy_type, strike, expiry
   - Show Greeks (delta, gamma, theta, vega)
   - Show P&L (unrealized, realized)
   - Show DTE, IV rank, entry time

3. Build page layout:
   - Filters: Symbol, Strategy, Status (selectbox widgets)
   - Summary metrics: Total positions, portfolio delta, unrealized P&L
   - Position list: Expandable cards or dataframe
   - Auto-refresh toggle (5s/30s/60s/off)

**Data flow:**
```
Delta Lake (option_legs, strategy_executions)
    ↓
load_positions() with caching (@st.cache_data ttl=30)
    ↓
positions_df (pandas DataFrame)
    ↓
st.dataframe() or position cards
```

**Verification:**
- Positions load from Delta Lake successfully
- Filters work (symbol, strategy, status)
- Auto-refresh updates display without rate limiting IB
- Summary metrics calculate correctly
- Position cards display all required fields

---

### Task 3: Build Portfolio Analytics Page

**Objective:** Visualize portfolio Greeks, P&L history, and risk metrics

**Files to create:**
- `src/v6/dashboard/data/portfolio.py` - Portfolio data loading functions
- `src/v6/dashboard/components/greeks_display.py` - Greeks visualization
- `src/v6/dashboard/pages/2_portfolio.py` - Portfolio analytics page (complete)

**Implementation approach:**
1. Create `get_portfolio_greeks()` function:
   - Use PortfolioRiskCalculator (existing from Phase 3)
   - Aggregate delta, gamma, theta, vega, rho across all positions
   - Return dict with portfolio-level Greeks

2. Create `get_portfolio_pnl_history()` function:
   - Query Delta Lake for historical P&L snapshots
   - Aggregate cumulative P&L over time
   - Return DataFrame with timestamp, cumulative_pnl

3. Create Greeks visualization components:
   - **Summary cards**: Display portfolio Greeks as metrics
   - **Heatmap**: Plot delta across strike vs DTE (Plotly heatmap)
   - **P&L chart**: Line chart of cumulative P&L over time (Plotly scatter)

4. Build page layout:
   - Greeks summary (5 columns: delta, gamma, theta, vega, rho)
   - Greeks heatmap (symbol selector, strike vs DTE)
   - P&L time series (cumulative P&L chart)
   - Portfolio metrics (exposure, concentration, position count)

**Visualization examples:**
```python
# Greeks heatmap
import plotly.graph_objects as go

fig = go.Figure(data=go.Heatmap(
    z=delta_values,
    x=dte_values,
    y=strike_values,
    colorscale="RdBu"
))

# P&L time series
fig = go.Figure()
fig.add_trace(go.Scatter(
    x=timestamps,
    y=cumulative_pnl,
    mode="lines"
))
```

**Verification:**
- Portfolio Greeks aggregate correctly (matches PortfolioRiskCalculator)
- Greeks heatmap displays delta across strike/DTE
- P&L chart shows historical performance
- Visualizations are interactive (zoom, pan, hover)
- Page loads quickly with caching

---

### Task 4: Add Dashboard Configuration and Startup

**Objective:** Create configuration, startup script, and documentation

**Files to create:**
- `src/v6/dashboard/config.py` - Dashboard configuration
- `scripts/run_dashboard.py` - Dashboard startup script
- `src/v6/dashboard/README.md` - Dashboard usage documentation

**Implementation approach:**
1. Create `config.py`:
   - Streamlit config (port, theme, debug mode)
   - Data cache TTL (30s for positions, 60s for alerts)
   - Auto-refresh intervals (5s, 30s, 60s, off)
   - Delta Lake paths (relative to project root)

2. Create `run_dashboard.py`:
   - Parse command-line args (port, debug)
   - Set Streamlit config via `st.set_page_config()`
   - Launch Streamlit with `streamlit run app.py`
   - Handle keyboard interrupt gracefully

3. Create `README.md`:
   - Installation: `pip install streamlit plotly pandas delta-spark`
   - Startup: `python scripts/run_dashboard.py --port 8501`
   - Usage: Navigate to http://localhost:8501
   - Features: Positions, Portfolio, Alerts, System Health
   - Troubleshooting: Common issues (IB connection, Delta Lake paths)

**Configuration example:**
```python
# config.py
from dataclasses import dataclass

@dataclass(slots=True)
class DashboardConfig:
    streamlit_port: int = 8501
    debug_mode: bool = False
    cache_ttl_positions: int = 30  # seconds
    cache_ttl_alerts: int = 60
    auto_refresh_options: list[int] = [5, 30, 60, 0]
    default_refresh: int = 30

    delta_lake_base_path: str = "data/lake"
```

**Verification:**
- `python scripts/run_dashboard.py` launches dashboard
- Dashboard accessible at http://localhost:8501
- Configuration overrides work (port, debug)
- README provides clear setup and usage instructions
- Dashboard runs in headless mode (production-ready)

---

## Verification

### Acceptance Criteria

**Functional Requirements:**
- [ ] Dashboard starts successfully and is accessible via browser
- [ ] Position monitor page displays all active positions
- [ ] Portfolio analytics page shows aggregated Greeks and P&L
- [ ] Filtering works (symbol, strategy, status)
- [ ] Auto-refresh updates display without hitting IB API rate limits
- [ ] Caching reduces Delta Lake load (cache hits logged)
- [ ] All visualizations render correctly (heatmaps, line charts)
- [ ] Navigation between pages works smoothly
- [ ] Dashboard handles empty data gracefully (no positions, no alerts)

**Performance Requirements:**
- [ ] Page load time <3 seconds with caching
- [ ] Auto-refresh completes within 1 second
- [ ] Memory usage stable (no leaks after extended use)
- [ ] Delta Lake queries optimized (read only required columns)

**Integration Requirements:**
- [ ] Reads from Delta Lake (option_legs, strategy_executions, option_snapshots)
- [ ] Uses PortfolioRiskCalculator for Greek aggregation
- [ ] Checks IB connection status (for future system health page)
- [ ] No IB API calls during dashboard refresh (reads from Delta Lake only)

### Test Plan

**Manual Tests:**
1. Start dashboard: `python scripts/run_dashboard.py`
2. Navigate to Positions page, verify filters work
3. Navigate to Portfolio page, verify Greeks display
4. Enable auto-refresh, monitor for 5 minutes (no errors, no rate limits)
5. Check browser console for errors (none expected)

**Automated Tests:**
1. `pytest tests/dashboard/test_positions.py` - Position data loading
2. `pytest tests/dashboard/test_portfolio.py` - Portfolio aggregation
3. `pytest tests/dashboard/test_components.py` - Component rendering

**Integration Tests:**
1. Insert test positions into Delta Lake
2. Run dashboard, verify positions display correctly
3. Modify positions in Delta Lake, verify auto-refresh picks up changes

---

## Success Criteria

**Must Have:**
- ✅ Streamlit multi-page dashboard running locally
- ✅ Real-time position display with auto-refresh
- ✅ Portfolio Greeks visualization with Plotly
- ✅ Reads from Delta Lake, no IB API calls
- ✅ Caching strategy implemented
- ✅ README with setup/usage instructions

**Should Have:**
- ✅ Filtering and sorting on position list
- ✅ Greeks heatmap (strike vs DTE)
- ✅ P&L time series chart
- ✅ Configurable auto-refresh intervals
- ✅ Responsive layout (desktop, tablet)

**Nice to Have:**
- Position cards with expandable details
- Export position data to CSV
- Dark/light theme toggle
- Performance metrics dashboard

---

## Output

**Artifacts:**
1. Dashboard project structure (src/v6/dashboard/)
2. Position monitor page (pages/1_positions.py)
3. Portfolio analytics page (pages/2_portfolio.py)
4. Data loading functions (data/positions.py, data/portfolio.py)
5. Reusable components (components/position_card.py, components/greeks_display.py)
6. Configuration (config.py)
7. Startup script (scripts/run_dashboard.py)
8. Documentation (README.md)

**Documentation:**
- Dashboard architecture (multi-page, data flow, caching)
- Setup instructions (install, configure, run)
- Usage guide (navigation, filtering, auto-refresh)
- Troubleshooting (common issues, solutions)

**Tests:**
- Position data loading tests
- Portfolio aggregation tests
- Component rendering tests
- Integration tests (Delta Lake → dashboard)

---

## Notes

### Research-Based Decisions

**Streamlit vs Dash:**
- Decision: Streamlit
- Rationale: Faster development, simpler architecture, better fit for v6 "clean slate" philosophy
- Tradeoff: Less customization than Dash, but 80% of functionality out-of-box

**Auto-Refresh vs WebSocket:**
- Decision: Auto-refresh with caching (Plan 1), WebSocket for real-time (Plan 3)
- Rationale: Auto-refresh sufficient for positions/Greeks (30s updates), WebSocket overkill for Plan 1
- Tradeoff: 5-30s latency vs sub-second, but simpler implementation
- Future: Add WebSocket for critical alerts in Plan 3

**Delta Lake vs Direct IB API:**
- Decision: Read from Delta Lake only
- Rationale: Avoid IB API rate limits, PositionSync already keeps Delta Lake updated
- Tradeoff: 5-30s latency vs real-time, but prevents rate limit errors
- Research backing: 6-RESEARCH.md Pitfall 5 ("Real-Time Updates Causing IB API Rate Limits")

### Open Questions from Research

**Q1: Optimal refresh rate for positions/Greeks?**
- Research recommendation: Start with 30s auto-refresh, user-configurable
- Decision: Implement 5s/30s/60s/off options, default 30s

**Q2: Cache TTL vs data freshness tradeoff?**
- Research recommendation: 30s TTL for positions, 60s for alerts
- Decision: 30s TTL for positions/Greeks, 60s for alert history

**Q3: Multi-user state management?**
- Research recommendation: Use `st.session_state` for per-user preferences
- Decision: Single-user dashboard (trader), no auth needed, `st.session_state` for filters

### Dependencies on Future Plans

**Plan 2 (Alert Management UI):**
- Plan 1 creates alert data loading functions
- Plan 2 builds alert history, active alerts, acknowledgment UI
- Plan 1 will have placeholder Alerts page linking to Plan 2

**Plan 3 (System Health):**
- Plan 1 checks IB connection status (basic)
- Plan 3 expands to full system health (data freshness, metrics, active strategies)
- Plan 1 will have placeholder System Health page linking to Plan 3

---

**Phase:** 6-monitoring-dashboard
**Plan:** 01-real-time-dashboard
**Status:** Ready for execution
**Created:** 2026-01-27
**Estimated complexity:** Medium (Streamlit patterns well-documented, Delta Lake integration existing)
