# Phase 6 Plan 2: Alert Management UI

**Status:** Planning
**Type:** Feature
**Priority:** High
**Dependencies:** Phase 6 Plan 1 (Real-Time Dashboard)
**Research:** Complete (see 6-RESEARCH.md)

---

## Objective

Build an alert management interface for viewing active alerts, acknowledging issues, and tracking alert history. The alert UI provides real-time visibility into system issues, decision triggers, and risk limit breaches.

**Success Criteria:**
- Alerts page displays active and historical alerts
- Alert acknowledgment workflow (acknowledge → resolve)
- Alert filtering by severity, type, status
- Alert history with timestamps and resolution tracking
- Integration with AlertManager (Phase 3)
- Real-time alert updates (via auto-refresh)

---

## Execution Context

### Stack
- **streamlit** 1.28+ - Dashboard framework (from Plan 1)
- **pandas** 2.0+ - Data manipulation
- **delta-spark** 3.0+ - Delta Lake reads

### Context Files
- `.planning/phases/6-monitoring-dashboard/6-RESEARCH.md` - Alert UI patterns, examples
- `.planning/phases/3-decision-rules-engine/3-04-SUMMARY.md` - AlertManager architecture
- `.planning/phases/6-monitoring-dashboard/6-01-PLAN.md` - Dashboard foundation

### Key Integration Points
- **AlertManager** (Phase 3): Read alerts, acknowledge, resolve
- **Delta Lake**: Alert history stored in `alerts` table (if persisted)
- **DecisionEngine** (Phase 3): Alert generation via decision rules

---

## Context

### Prior Phase Accomplishments

**Phase 3 (Decision Rules Engine)**: Alert infrastructure
- AlertManager: Create alerts, acknowledge, resolve, history tracking
- 12 decision rules: Each generates alerts on rule triggers
- Alert models: AlertType (CATASTROPHE, RISK_LIMIT, POSITION_EXIT, etc.)
- AlertSeverity: CRITICAL, WARNING, INFO
- Alert status: ACTIVE, ACKNOWLEDGED, RESOLVED

**AlertManager API:**
```python
class AlertManager:
    def create_alert(
        alert_type: AlertType,
        severity: AlertSeverity,
        message: str,
        execution_id: str | None = None,
        metadata: dict | None = None
    ) -> Alert

    def acknowledge_alert(self, alert_id: str) -> Alert
    def resolve_alert(self, alert_id: str) -> Alert
    def get_active_alerts() -> list[Alert]
    def get_alert_history(
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        severity: AlertSeverity | None = None
    ) -> list[Alert]
```

**Plan 1 (Real-Time Dashboard):** Dashboard foundation
- Multi-page Streamlit app structure
- Position monitor page (pages/1_positions.py)
- Portfolio analytics page (pages/2_portfolio.py)
- Data loading patterns with caching
- Auto-refresh infrastructure

### Alert Data Model

**Alert Schema:**
```python
@dataclass(slots=True)
class Alert:
    alert_id: str                    # Unique identifier
    alert_type: AlertType            # CATASTROPHE, RISK_LIMIT, etc.
    severity: AlertSeverity          # CRITICAL, WARNING, INFO
    message: str                     # Human-readable description
    execution_id: str | None         # Associated position (optional)
    metadata: dict | None            # Additional context
    status: AlertStatus              # ACTIVE, ACKNOWLEDGED, RESOLVED
    created_at: datetime             # Alert creation time
    acknowledged_at: datetime | None # Acknowledgment time
    resolved_at: datetime | None     # Resolution time
```

**Alert Types (from Phase 3):**
- CATASTROPHE: System failure, IB disconnect
- RISK_LIMIT: Portfolio limits exceeded (delta, gamma, concentration)
- POSITION_EXIT: Exit decision triggered (trailing stop, time exit, etc.)
- DATA_QUALITY: Missing data, stale Greeks, IV spike
- SYSTEM: Circuit breaker opened, queue backlog

---

## Tasks

### Task 1: Create Alert Data Loading Functions

**Objective:** Build data layer for loading alerts from AlertManager/Delta Lake

**Files to create:**
- `src/v6/dashboard/data/alerts.py` - Alert data loading functions

**Implementation approach:**
1. Create `load_alerts()` function:
   - Fetch from AlertManager.get_active_alerts() + get_alert_history()
   - Convert to pandas DataFrame
   - Add computed columns (age, response_time)
   - Cache with `@st.cache_data(ttl=60)` (60s TTL from research)

2. Create `get_alert_summary()` function:
   - Calculate alert counts (active, acknowledged, resolved today)
   - Calculate average response time (acknowledged_at - created_at)
   - Return dict with summary metrics

3. Create `filter_alerts()` function:
   - Filter by severity (CRITICAL, WARNING, INFO)
   - Filter by status (ACTIVE, ACKNOWLEDGED, RESOLVED)
   - Filter by time range (start_time, end_time)
   - Return filtered DataFrame

**Data flow:**
```
AlertManager (in-memory alerts or Delta Lake)
    ↓
load_alerts() with caching (@st.cache_data ttl=60)
    ↓
alerts_df (pandas DataFrame)
    ↓
filter_alerts() → filtered_df
    ↓
st.dataframe() or alert cards
```

**Error handling:**
- Handle AlertManager not initialized (return empty DataFrame)
- Handle missing fields (use default values)
- Log errors for debugging

**Verification:**
- `load_alerts()` returns pandas DataFrame with all alert fields
- `get_alert_summary()` calculates correct counts and averages
- `filter_alerts()` applies filters correctly
- Caching works (subsequent calls return cached data)
- Empty alert list handled gracefully

---

### Task 2: Build Alert Display Components

**Objective:** Create reusable alert display widgets

**Files to create:**
- `src/v6/dashboard/components/alert_card.py` - Alert display widget
- `src/v6/dashboard/components/alert_list.py` - Alert list view

**Implementation approach:**
1. Create `alert_card()` component:
   - Display severity badge (color-coded: red=CRITICAL, yellow=WARNING, blue=INFO)
   - Show alert type, message, timestamp
   - Show associated position (if execution_id present)
   - Show metadata (if available)
   - Add acknowledge/resolve buttons (if status=ACTIVE or ACKNOWLEDGED)

2. Create `alert_list()` component:
   - Display alerts in table format (st.dataframe)
   - Color-code severity column
   - Add hover tooltips for full message
   - Enable sorting/filtering (built-in st.dataframe)
   - Add action buttons column (acknowledge, resolve)

**Component API:**
```python
def alert_card(alert: dict, on_acknowledge: callable, on_resolve: callable):
    """Display single alert with action buttons"""
    severity_colors = {
        "CRITICAL": "🔴",
        "WARNING": "🟡",
        "INFO": "🔵"
    }
    # Display alert details
    # Add acknowledge/resolve buttons

def alert_list(alerts_df: pd.DataFrame, on_action: callable):
    """Display alerts as interactive table"""
    # Display dataframe with action buttons
    # Handle button clicks via callback
```

**Verification:**
- `alert_card()` displays all alert fields correctly
- Severity badges are color-coded
- Action buttons trigger callbacks
- `alert_list()` displays alerts in table format
- Sorting/filtering works in table view

---

### Task 3: Build Alert Management Page

**Objective:** Create alerts page with active alerts, history, and actions

**Files to create:**
- `src/v6/dashboard/pages/3_alerts.py` - Alert management page (complete)

**Implementation approach:**
1. Page layout:
   - Summary metrics: Active alerts, resolved today, avg response time
   - Tabs: Active Alerts, Alert History, Alert Configuration

2. Active Alerts tab:
   - Filter by severity (selectbox: ALL, CRITICAL, WARNING, INFO)
   - Display active alerts using `alert_card()` or `alert_list()`
   - Add acknowledge/resolve buttons
   - Show alert count by severity

3. Alert History tab:
   - Date range selector (start_date, end_date)
   - Filter by severity, status
   - Display history as table (st.dataframe)
   - Add export to CSV button

4. Alert Configuration tab:
   - Show alert rule configuration (read-only from DecisionEngine)
   - Display alert thresholds (e.g., delta limit, gamma limit)
   - Link to Phase 3 DecisionEngine configuration

**Page structure:**
```python
# pages/3_alerts.py
import streamlit as st
from v6.dashboard.data.alerts import load_alerts, get_alert_summary, filter_alerts
from v6.dashboard.components.alert_card import alert_card

st.set_page_config(page_title="Alerts", page_icon="🔔", layout="wide")
st.title("🔔 Alert Management")

# Load alerts
alerts_df = load_alerts()
summary = get_alert_summary(alerts_df)

# Summary metrics
col1, col2, col3 = st.columns(3)
col1.metric("Active Alerts", summary["active_count"])
col2.metric("Resolved Today", summary["resolved_today"])
col3.metric("Avg Response Time", f"{summary['avg_response_time']}s")

# Tabs
tab1, tab2, tab3 = st.tabs(["Active Alerts", "Alert History", "Configuration"])

with tab1:
    severity_filter = st.selectbox("Severity", ["ALL", "CRITICAL", "WARNING", "INFO"])
    filtered = filter_alerts(alerts_df, severity=severity_filter, status="ACTIVE")
    for _, alert in filtered.iterrows():
        with st.expander(f"{alert['severity']}: {alert['message']}"):
            alert_card(alert, on_acknowledge, on_resolve)

with tab2:
    # Alert history with date range filter
    st.dataframe(alerts_df)

with tab3:
    st.info("Alert rules configured in Phase 3 DecisionEngine")
```

**Verification:**
- Page loads without errors
- Summary metrics calculate correctly
- Active alerts tab displays unacknowledged alerts
- Acknowledge/resolve buttons work (update AlertManager)
- Alert history tab shows all alerts with filters
- Configuration tab displays rule information

---

### Task 4: Add Alert Actions Integration

**Objective:** Connect alert actions to AlertManager backend

**Files to modify:**
- `src/v6/dashboard/pages/3_alerts.py` - Add action callbacks
- `src/v6/dashboard/data/alerts.py` - Add action functions

**Implementation approach:**
1. Create action functions:
   - `acknowledge_alert(alert_id: str)`: Call AlertManager.acknowledge_alert()
   - `resolve_alert(alert_id: str)`: Call AlertManager.resolve_alert()
   - Handle errors (alert not found, already resolved)

2. Add action callbacks in page:
   - Use `st.button()` with `key=f"ack_{alert_id}"` to avoid conflicts
   - On button click, call action function
   - Call `st.rerun()` to refresh alert list
   - Show success/error toast message

3. Add confirmation dialog:
   - For resolve action, show confirmation dialog
   - Use `st.confirm()` (Streamlit 1.28+) or custom confirmation

**Action handling:**
```python
def acknowledge_alert(alert_id: str):
    """Acknowledge alert via AlertManager"""
    try:
        alert = alert_manager.acknowledge_alert(alert_id)
        st.success(f"Alert {alert_id} acknowledged")
        st.rerun()
    except Exception as e:
        st.error(f"Failed to acknowledge: {e}")

# In page
if st.button("Acknowledge", key=f"ack_{alert_id}"):
    acknowledge_alert(alert_id)
```

**Verification:**
- Acknowledge button updates alert status to ACKNOWLEDGED
- Resolve button updates alert status to RESOLVED
- Actions persist across page refreshes
- Error handling works (alert not found, already resolved)
- Confirmation dialog shows for resolve action

---

## Verification

### Acceptance Criteria

**Functional Requirements:**
- [ ] Alerts page displays active and historical alerts
- [ ] Summary metrics show correct counts and averages
- [ ] Active alerts can be acknowledged and resolved
- [ ] Alert history can be filtered by severity, status, time range
- [ ] Alert actions update AlertManager backend
- [ ] Page auto-refreshes to show new alerts
- [ ] Configuration tab displays alert rule information

**Integration Requirements:**
- [ ] Reads alerts from AlertManager
- [ ] Calls acknowledge_alert() and resolve_alert() correctly
- [ ] Alert status changes persist across page refreshes
- [ ] Error handling works (AlertManager not initialized, alert not found)

**UX Requirements:**
- [ ] Severity badges are color-coded and visible
- [ ] Alert cards show all relevant information
- [ ] Action buttons are clearly visible
- [ ] Filters work (severity, status, time range)
- [ ] Table view supports sorting and pagination

### Test Plan

**Manual Tests:**
1. Navigate to Alerts page
2. Verify active alerts display
3. Click acknowledge on active alert, verify status changes
4. Click resolve on acknowledged alert, verify status changes
5. Test filters (severity, time range)
6. Verify auto-refresh picks up new alerts

**Automated Tests:**
1. `pytest tests/dashboard/test_alerts.py` - Alert data loading
2. `pytest tests/dashboard/test_alert_actions.py` - Action callbacks
3. `pytest tests/dashboard/test_alert_components.py` - Component rendering

**Integration Tests:**
1. Create test alerts via AlertManager
2. Run dashboard, verify alerts display
3. Acknowledge/resolve alerts, verify status persists
4. Check alert history, verify all alerts shown

---

## Success Criteria

**Must Have:**
- ✅ Alerts page with active alerts and history
- ✅ Acknowledge/resolve actions working
- ✅ Filtering by severity, status, time range
- ✅ Integration with AlertManager
- ✅ Auto-refresh for real-time updates

**Should Have:**
- ✅ Summary metrics (active, resolved, response time)
- ✅ Color-coded severity badges
- ✅ Alert cards with expandable details
- ✅ Export to CSV for alert history
- ✅ Configuration tab showing rule thresholds

**Nice to Have:**
- Alert notifications (browser push notifications)
- Alert trends chart (alerts over time)
- Bulk acknowledge/resolve actions
- Alert annotation (add notes to alerts)

---

## Output

**Artifacts:**
1. Alert data loading functions (data/alerts.py)
2. Alert display components (components/alert_card.py, components/alert_list.py)
3. Alert management page (pages/3_alerts.py)
4. Action integration (acknowledge, resolve)
5. Documentation (update README.md with alert usage)

**Documentation:**
- Alert management workflow
- Alert types and severity levels
- How to acknowledge/resolve alerts
- Alert filtering and export

**Tests:**
- Alert data loading tests
- Alert action callback tests
- Component rendering tests
- Integration tests (AlertManager ↔ dashboard)

---

## Notes

### Research-Based Decisions

**Auto-Refresh vs WebSocket:**
- Decision: Auto-refresh (from Plan 1)
- Rationale: Alerts update infrequently (seconds to minutes), auto-refresh sufficient
- Tradeoff: 30s latency vs sub-second, but simpler implementation
- Future: Consider WebSocket for critical alerts (CATASTROPHE severity)

**Table View vs Cards:**
- Decision: Both (user-selectable)
- Rationale: Table view for scanning many alerts, cards for detailed inspection
- Tradeoff: More code, but better UX for different use cases

**Confirmation Dialog:**
- Decision: Show confirmation for resolve action only
- Rationale: Acknowledge is reversible (can unacknowledge), resolve is final
- Tradeoff: Extra click, but prevents accidental resolution

### Alert Persistence Consideration

**Current State (Phase 3):**
- AlertManager stores alerts in memory
- Alerts lost on restart (no persistence)

**Future Enhancement:**
- Persist alerts to Delta Lake (alerts table)
- Query alerts from Delta Lake in dashboard
- Enable alert history across restarts

**Plan 2 Assumption:**
- AlertManager persists alerts in memory only
- Alert history is limited to current session
- Dashboard handles empty alert list gracefully

### Dependencies on Plan 3

**Plan 3 (System Health):**
- Plan 2 creates alert data loading and display patterns
- Plan 3 adds system health alerts (IB disconnect, data freshness, circuit breaker)
- Plan 2 will display system health alerts alongside other alerts

---

**Phase:** 6-monitoring-dashboard
**Plan:** 02-alert-management
**Status:** Ready for execution
**Created:** 2026-01-27
**Estimated complexity:** Low (AlertManager API existing, straightforward UI)
