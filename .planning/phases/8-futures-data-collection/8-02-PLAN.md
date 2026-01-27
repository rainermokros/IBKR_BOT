---
phase: 8-futures-data-collection
plan: 02
type: execute
depends_on: ['8-01']
files_modified: [src/v6/dashboard/data/futures_data.py, src/v6/core/futures_analyzer.py, src/v6/dashboard/pages/6_futures.py, src/v6/dashboard/app.py]
---

<objective>
Integrate futures data into dashboard and create analysis tools to assess predictive value after 2-4 weeks of data accumulation.

Purpose: Make futures data visible in real-time dashboard and create analysis tools to determine if futures improve entry signal prediction.

Output: Working futures dashboard with real-time display and correlation analysis tools.
</objective>

<execution_context>
@~/.claude/get-shit-done/workflows/execute-plan.md
@.planning/STATE.md
@.planning/phases/8-futures-data-collection/8-02-PLAN.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@src/v6/dashboard/app.py
@src/v6/dashboard/data/position_data.py
@src/v6/data/delta_persistence.py
@.planning/phases/8-futures-data-collection/8-01-PLAN.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create futures data loader for dashboard</name>
  <files>src/v6/dashboard/data/futures_data.py</files>
  <action>
    Create futures data loader module:
    - Load latest futures snapshots from Delta Lake futures_snapshots table
    - Cache with TTL=30s (reduce database queries)
    - Methods:
      - get_latest_snapshots() -> Dict[str, FuturesSnapshot] (ES, NQ, RTY)
      - get_historical_snapshots(symbol: str, hours: int) -> DataFrame
      - get_change_metrics(symbol: str) -> Dict[str, float] (1h, 4h, overnight, daily)
    - Error handling: return empty dict if no data available
    - Use existing delta_writer.py patterns for Delta Lake queries
  </action>
  <verify>Can load latest ES snapshot from Delta Lake, cache works (30s TTL), empty dict returned when no data</verify>
  <done>Futures data loader created with caching and Delta Lake integration</done>
</task>

<task type="auto">
  <name>Task 2: Implement futures correlation analyzer</name>
  <files>src/v6/core/futures_analyzer.py</files>
  <action>
    Create futures analysis module for correlation analysis:
    - Calculate rolling correlations between futures and spot:
      - ES vs SPY, NQ vs QQQ, RTY vs IWM
    - Lead-lag analysis:
      - Test if futures move X minutes before spot (5, 15, 30, 60 min leads)
      - Calculate correlation at different lead times
    - Predictive value assessment:
      - Measure futures directional accuracy vs subsequent spot moves
      - Calculate signal-to-noise ratio
    - Methods:
      - calculate_correlation(futures_symbol: str, spot_symbol: str, days: int) -> float
      - calculate_lead_lag(futures_symbol: str, spot_symbol: str, max_lead_minutes: int) -> Dict[int, float]
      - assess_predictive_value(futures_symbol: str, spot_symbol: str, days: int) -> Dict[str, float]
    - Return empty dict with warning if insufficient data (< 7 days)
  </action>
  <verify>Can calculate ES vs SPY correlation, lead-lag analysis works with test data, insufficient data warning appears</verify>
  <done>Futures correlation analyzer implemented with lead-lag and predictive value analysis</done>
</task>

<task type="auto">
  <name>Task 3: Create futures dashboard page</name>
  <files>src/v6/dashboard/pages/6_futures.py</files>
  <action>
    Create Streamlit dashboard page for futures monitoring:
    - Page title: "Futures Data"
    - Real-time futures display table:
      - Columns: Symbol, Bid, Ask, Last, Volume, Change 1H, Change 4H, Change Overnight, Change Daily
      - Color coding: green for positive changes, red for negative
      - Auto-refresh every 30s (st.cache_data with TTL)
    - Futures vs spot comparison charts:
      - Line chart: ES vs SPY (last 4 hours)
      - Line chart: NQ vs QQQ (last 4 hours)
      - Line chart: RTY vs IWM (last 4 hours)
      - Dual y-axis (futures price, spot price)
    - Correlation analysis section:
      - Display correlation coefficients (ES-SPY, NQ-QQQ, RTY-IWM)
      - Lead-lag analysis results (if sufficient data)
      - Predictive value assessment (if sufficient data)
      - Warning message if < 7 days of data: "Data collection in progress. Analysis available after 7 days."
    - Use existing dashboard patterns (pages/1_overview.py, pages/2_positions.py)
  </action>
  <verify>Dashboard page loads without errors, futures table displays with color coding, charts render with historical data, warning appears with insufficient data</verify>
  <done>Futures dashboard page created with real-time display and correlation analysis</done>
</task>

<task type="auto">
  <name>Task 4: Update dashboard app navigation</name>
  <files>src/v6/dashboard/app.py</files>
  <action>
    Update main dashboard app to include futures page:
    - Add Page 6: "Futures" to navigation (after Page 5: System Health)
    - Import futures page: from pages.6_futures import show_futures_page
    - Add to page routing: PAGES.append({"name": "Futures", "func": show_futures_page})
    - Ensure page order: Overview, Positions, Decisions, Risk, Alerts, Futures, System Health
  </action>
  <verify>Dashboard app loads without errors, Futures page appears in navigation, clicking navigates to futures page</verify>
  <done>Dashboard app updated with futures page in navigation</done>
</task>

</tasks>

<verification>
Before declaring plan complete:
- [ ] Futures data loader loads snapshots from Delta Lake with 30s cache
- [ ] Correlation analyzer calculates ES vs SPY correlation with test data
- [ ] Dashboard page displays futures table with color coding
- [ ] Charts render with historical data (4-hour view)
- [ ] Navigation includes Futures page
- [ ] Warning message appears with insufficient data (< 7 days)
</verification>

<success_criteria>

- Futures data visible in dashboard with real-time updates
- Correlation analysis tools functional (ready for 2-4 week assessment)
- Dashboard displays futures vs spot comparison charts
- Lead-lag analysis working (detect if futures lead spot)
- Ready to collect data for 2-4 weeks before assessing predictive value

</success_criteria>

<output>
After completion, create `.planning/phases/8-futures-data-collection/8-02-SUMMARY.md`:

# Phase 8 Plan 2: Dashboard Integration & Analysis Summary

**Futures dashboard integration with real-time display and correlation analysis tools**

## Accomplishments

- Futures data loader with Delta Lake integration and 30s caching
- Correlation analyzer for ES-SPY, NQ-QQQ, RTY-IWM with lead-lag analysis
- Streamlit futures dashboard page with real-time display and charts
- Dashboard navigation updated to include futures monitoring

## Files Created/Modified

- `src/v6/dashboard/data/futures_data.py` - Futures data loader with caching
- `src/v6/core/futures_analyzer.py` - Correlation and lead-lag analysis
- `src/v6/dashboard/pages/6_futures.py` - Futures monitoring dashboard page
- `src/v6/dashboard/app.py` - Updated navigation to include futures page

## Deviations from Plan

None expected - standard dashboard integration.

## Issues Encountered

None expected.

## Next Step

Phase 8 complete. System now collecting futures data (ES, NQ, RTY) with dashboard visibility. Ready for 2-4 week data accumulation period before analyzing predictive value.

**Future Work** (after 2-4 weeks):
- Run correlation analysis to assess predictive value
- If valuable: Integrate futures signals into DecisionEngine (priority rule 0: pre-market futures surge)
- If not valuable: Continue collection for research, add to documentation

