# Phase 6 Plan 3: System Health Monitoring

**Status:** Planning
**Type:** Feature
**Priority:** Medium
**Dependencies:** Phase 6 Plan 1 (Real-Time Dashboard)
**Research:** Complete (see 6-RESEARCH.md)

---

## Objective

Build a system health monitoring page to track IB connection status, data freshness, system metrics, and active strategies. The health page provides visibility into system operational status and early warning of potential issues.

**Success Criteria:**
- System health page displays connection status, data freshness, and metrics
- IB connection status monitored (connected/disconnected, last update time)
- Data freshness checks (positions, Greeks, decisions)
- System metrics displayed (CPU, memory, disk, uptime)
- Active strategies registry shows streaming slot usage
- Health indicators color-coded (green=healthy, yellow=warning, red=critical)

---

## Execution Context

### Stack
- **streamlit** 1.28+ - Dashboard framework (from Plan 1)
- **pandas** 2.0+ - Data manipulation
- **psutil** 5.9+ - System metrics (CPU, memory, disk)

### Context Files
- `.planning/phases/6-monitoring-dashboard/6-RESEARCH.md` - System health patterns, examples
- `.planning/phases/2-position-synchronization/2-03-SUMMARY.md` - Position sync, reconciliation
- `.planning/phases/6-monitoring-dashboard/6-01-PLAN.md` - Dashboard foundation

### Key Integration Points
- **IBConnectionManager** (Phase 1): Connection status checks
- **StrategyRegistry** (Phase 2.1): Active strategies consuming streaming slots
- **Delta Lake**: Data freshness checks (last update timestamps)
- **QueueWorker** (Phase 2.1): Queue backlog status

---

## Context

### Prior Phase Accomplishments

**Phase 1 (Infrastructure):** IB connection management
- IBConnectionManager: Connect, disconnect, status checks
- Auto-reconnect on disconnect
- Heartbeat monitoring
- Connection status: CONNECTED, DISCONNECTED, CONNECTING

**Phase 2.1 (Hybrid Sync):** Streaming slot conservation
- StrategyRegistry: Tracks active strategies consuming streaming slots
- PositionQueue: Delta Lake backed queue for non-active contracts
- QueueWorker: Background daemon processes queue every 5 seconds
- **Streaming slot usage:** ~10 slots for active strategies (vs 100+ for all positions)

**Plan 1 (Real-Time Dashboard):** Dashboard foundation
- Multi-page Streamlit app structure
- Position monitor page (pages/1_positions.py)
- Portfolio analytics page (pages/2_portfolio.py)
- Data loading patterns with caching
- Auto-refresh infrastructure

### System Health Data Sources

**IB Connection Status:**
```python
# From IBConnectionManager
status = {
    "connected": bool,           # True if connected to IB
    "last_update": datetime,     # Last heartbeat received
    "disconnected_at": datetime | None,  # Disconnect timestamp
    "host": str,                 # IB gateway host
    "port": int,                 # IB gateway port
    "client_id": int             # Client ID
}
```

**Data Freshness:**
```python
# Check Delta Lake table timestamps
freshness = {
    "positions_last_sync": datetime,    # Last position sync time
    "greeks_last_update": datetime,     # Last Greeks update
    "decisions_last_run": datetime,     # Last decision evaluation
    "alerts_last_created": datetime     # Last alert created
}
```

**System Metrics:**
```python
# From psutil library
metrics = {
    "cpu_percent": float,      # CPU usage percentage
    "memory_percent": float,   # Memory usage percentage
    "disk_percent": float,     # Disk usage percentage
    "uptime": str,             # System uptime (human-readable)
    "process_count": int,      # Number of running processes
}
```

**Active Strategies Registry:**
```python
# From StrategyRegistry
active_strategies = [
    {
        "conid": int,              # Contract ID
        "symbol": str,             # Underlying symbol
        "strategy_id": str,        # Strategy execution ID
        "since": datetime          # When streaming started
    },
    # ... more strategies
]
```

---

## Tasks

### Task 1: Create System Health Data Loading Functions

**Objective:** Build data layer for system health metrics

**Files to create:**
- `src/v6/dashboard/data/health.py` - System health data loading functions

**Implementation approach:**
1. Create `check_ib_connection()` function:
   - Check IBConnectionManager status (if available)
   - Return dict with connected, last_update, host, port
   - Handle missing IBConnectionManager (return disconnected status)

2. Create `check_data_freshness()` function:
   - Query Delta Lake for latest timestamps (option_legs, option_snapshots)
   - Calculate age of last update (now - last_update)
   - Return dict with freshness metrics and age (seconds)

3. Create `get_system_metrics()` function:
   - Use `psutil` library (cpu_percent, virtual_memory, disk_usage)
   - Calculate system uptime (boot_time)
   - Return dict with metrics

4. Create `get_active_strategies()` function:
   - Fetch from StrategyRegistry.get_active_strategies()
   - Add streaming slot count (len(strategies))
   - Return DataFrame with strategy details

**Error handling:**
- Handle IBConnectionManager not initialized (return disconnected)
- Handle psutil not available (skip system metrics)
- Handle Delta Lake query errors (return stale timestamps)

**Data freshness thresholds:**
- Fresh: <30 seconds old
- Warning: 30-60 seconds old
- Stale: >60 seconds old

**Verification:**
- `check_ib_connection()` returns connection status
- `check_data_freshness()` calculates age correctly
- `get_system_metrics()` returns CPU, memory, disk usage
- `get_active_strategies()` returns active strategies list
- Functions handle errors gracefully (return default values)

---

### Task 2: Build System Health Display Components

**Objective:** Create reusable health status widgets

**Files to create:**
- `src/v6/dashboard/components/status_badge.py` - Status indicator widget
- `src/v6/dashboard/components/metric_card.py` - Metric display widget

**Implementation approach:**
1. Create `status_badge()` component:
   - Display status badge (emoji + text)
   - Color-code: green=healthy, yellow=warning, red=critical
   - Support statuses: CONNECTED, DISCONNECTED, FRESH, WARNING, STALE

2. Create `metric_card()` component:
   - Display metric name, value, unit
   - Add visual indicator (progress bar for percentages)
   - Color-code based on thresholds (green<50%, yellow 50-80%, red>80%)

**Component API:**
```python
def status_badge(status: str, label: str | None = None):
    """Display status badge with emoji and color"""
    status_config = {
        "CONNECTED": ("✅", "green"),
        "DISCONNECTED": ("❌", "red"),
        "FRESH": ("✅", "green"),
        "WARNING": ("⚠️", "yellow"),
        "STALE": ("❌", "red")
    }
    # Display badge with color

def metric_card(name: str, value: float | str, unit: str = "", thresholds: dict | None = None):
    """Display metric with optional progress bar"""
    # Display metric name, value, unit
    # Add progress bar if percentage
    # Color-code based on thresholds
```

**Verification:**
- `status_badge()` displays correct emoji and color
- `metric_card()` shows metric with progress bar
- Thresholds work (green/yellow/red based on value)
- Components render correctly in Streamlit

---

### Task 3: Build System Health Page

**Objective:** Create system health monitoring page with all health indicators

**Files to create:**
- `src/v6/dashboard/pages/4_health.py` - System health page (complete)

**Implementation approach:**
1. Page layout:
   - IB Connection Status section
   - Data Freshness section
   - System Metrics section
   - Active Strategies Registry section

2. IB Connection Status:
   - Display connection status badge (CONNECTED/DISCONNECTED)
   - Show last update time, host, port, client_id
   - Add reconnect button (if disconnected)
   - Show connection duration (if connected)

3. Data Freshness:
   - Display last sync times (positions, Greeks, decisions)
   - Show age in seconds (color-coded: fresh <30s, warning 30-60s, stale >60s)
   - Add refresh button to force sync
   - Show sync status (running, idle, error)

4. System Metrics:
   - Display CPU, memory, disk usage with progress bars
   - Show system uptime
   - Add color-coding (green <50%, yellow 50-80%, red >80%)
   - Display process count

5. Active Strategies Registry:
   - Display table of active strategies (conid, symbol, strategy_id, since)
   - Show streaming slot count (total active strategies)
   - Add warning if approaching slot limit (>90 slots used)
   - Enable filtering by symbol

**Page structure:**
```python
# pages/4_health.py
import streamlit as st
from v6.dashboard.data.health import (
    check_ib_connection,
    check_data_freshness,
    get_system_metrics,
    get_active_strategies
)
from v6.dashboard.components.status_badge import status_badge
from v6.dashboard.components.metric_card import metric_card

st.set_page_config(page_title="System Health", page_icon="🩺")
st.title("🩺 System Health")

# IB Connection Status
st.markdown("### IB Connection Status")
ib_status = check_ib_connection()
status_badge(ib_status["status"], "IB Connection")
st.caption(f"Last update: {ib_status['last_update']}")
st.caption(f"Host: {ib_status['host']}:{ib_status['port']}")

# Data Freshness
st.markdown("### Data Freshness")
freshness = check_data_freshness()
col1, col2, col3 = st.columns(3)
col1.metric("Last Position Sync", freshness["positions_last_sync"])
col2.metric("Last Greeks Update", freshness["greeks_last_update"])
col3.metric("Last Decision Run", freshness["decisions_last_run"])

# System Metrics
st.markdown("### System Metrics")
metrics = get_system_metrics()
metric_card("CPU Usage", metrics["cpu_percent"], "%")
metric_card("Memory Usage", metrics["memory_percent"], "%")
metric_card("Disk Usage", metrics["disk_percent"], "%")

# Active Strategies
st.markdown("### Active Strategy Registry")
strategies_df = get_active_strategies()
st.dataframe(strategies_df)
```

**Verification:**
- Page loads without errors
- IB connection status displays correctly
- Data freshness metrics show timestamps and age
- System metrics display with progress bars
- Active strategies table shows streaming slot usage
- Auto-refresh updates health indicators

---

### Task 4: Add System Health Actions and Alerts

**Objective:** Add actions for resolving health issues

**Files to modify:**
- `src/v6/dashboard/pages/4_health.py` - Add action buttons
- `src/v6/dashboard/data/health.py` - Add action functions

**Implementation approach:**
1. Create action functions:
   - `reconnect_ib()`: Call IBConnectionManager.reconnect()
   - `force_sync()`: Trigger manual position/Greeks sync
   - `clear_queue()`: Clear PositionQueue backlog (if stuck)

2. Add action buttons in page:
   - Reconnect button (if IB disconnected)
   - Force sync button (for data freshness)
   - Clear queue button (if backlog exists)

3. Add health alerts:
   - Generate alerts for unhealthy conditions
   - IB disconnected → CRITICAL alert
   - Data stale (>60s) → WARNING alert
   - System metrics critical (>90%) → WARNING alert
   - Streaming slots near limit (>90) → INFO alert

**Action handling:**
```python
def reconnect_ib():
    """Trigger IB reconnection"""
    try:
        ib_manager.reconnect()
        st.success("IB reconnection initiated")
        st.rerun()
    except Exception as e:
        st.error(f"Reconnection failed: {e}")

# In page
if not ib_status["connected"]:
    if st.button("Reconnect to IB"):
        reconnect_ib()
```

**Alert generation:**
```python
def generate_health_alerts(ib_status, freshness, metrics, strategies):
    """Generate alerts for unhealthy conditions"""
    alerts = []
    if not ib_status["connected"]:
        alerts.append({
            "severity": "CRITICAL",
            "message": f"IB disconnected since {ib_status['disconnected_at']}"
        })
    if freshness["positions_age"] > 60:
        alerts.append({
            "severity": "WARNING",
            "message": f"Positions stale ({freshness['positions_age']}s old)"
        })
    # ... more checks
    return alerts
```

**Verification:**
- Reconnect button triggers IB reconnection
- Force sync button updates data freshness
- Clear queue button reduces backlog
- Health alerts generate correctly
- Alerts display on health page and alerts page

---

## Verification

### Acceptance Criteria

**Functional Requirements:**
- [ ] System health page displays all health indicators
- [ ] IB connection status shows connected/disconnected and last update
- [ ] Data freshness shows timestamps and age (color-coded)
- [ ] System metrics display with progress bars (CPU, memory, disk)
- [ ] Active strategies table shows streaming slot usage
- [ ] Action buttons work (reconnect, force sync, clear queue)
- [ ] Health alerts generate for unhealthy conditions
- [ ] Auto-refresh updates health indicators

**Integration Requirements:**
- [ ] Reads from IBConnectionManager
- [ ] Reads from StrategyRegistry
- [ ] Reads from Delta Lake (data freshness)
- [ ] Uses psutil for system metrics
- [ ] Handles missing dependencies gracefully

**UX Requirements:**
- [ ] Status badges are color-coded and visible
- [ ] Progress bars show resource usage visually
- [ ] Action buttons are clearly labeled
- [ ] Age thresholds are intuitive (fresh <30s, stale >60s)
- [ ] Page layout is clean and scannable

### Test Plan

**Manual Tests:**
1. Navigate to System Health page
2. Verify IB connection status displays
3. Check data freshness metrics (should be <30s old)
4. Verify system metrics display with progress bars
5. Check active strategies table shows streaming slot usage
6. Test reconnect button (disconnect IB, click reconnect)
7. Test force sync button (click, verify data freshness updates)

**Automated Tests:**
1. `pytest tests/dashboard/test_health.py` - Health data loading
2. `pytest tests/dashboard/test_health_actions.py` - Action callbacks
3. `pytest tests/dashboard/test_health_components.py` - Component rendering

**Integration Tests:**
1. Disconnect IB, verify health page shows disconnected status
2. Stop position sync, wait 60s, verify data stale warning
3. Add test strategies to registry, verify table updates
4. Check health alerts generate on alerts page

---

## Success Criteria

**Must Have:**
- ✅ System health page with all health indicators
- ✅ IB connection status monitoring
- ✅ Data freshness checks (positions, Greeks, decisions)
- ✅ System metrics (CPU, memory, disk)
- ✅ Active strategies registry
- ✅ Action buttons (reconnect, force sync)
- ✅ Color-coded status badges

**Should Have:**
- ✅ Progress bars for resource usage
- ✅ Age thresholds (fresh/warning/stale)
- ✅ Health alerts for unhealthy conditions
- ✅ Auto-refresh for real-time updates
- ✅ Streaming slot usage warning

**Nice to Have:**
- Historical health metrics (CPU over time)
- Health trends chart (data freshness over time)
- Email notifications for critical health issues
- Automatic remediation (auto-reconnect on disconnect)

---

## Output

**Artifacts:**
1. System health data loading functions (data/health.py)
2. Health status components (components/status_badge.py, components/metric_card.py)
3. System health page (pages/4_health.py)
4. Health actions (reconnect, force sync, clear queue)
5. Health alerts generation
6. Documentation (update README.md with health monitoring)

**Documentation:**
- System health monitoring guide
- Health indicators and thresholds
- How to resolve health issues
- Health alert types and responses

**Tests:**
- Health data loading tests
- Health action callback tests
- Component rendering tests
- Integration tests (IBConnectionManager, StrategyRegistry)

---

## Notes

### Research-Based Decisions

**Auto-Refresh Frequency:**
- Decision: 5s auto-refresh for system health
- Rationale: System health changes rapidly (IB disconnect, sync status), need faster updates
- Tradeoff: More frequent refreshes, but system health page is lightweight (minimal data)
- Research backing: 6-RESEARCH.md Q1 ("Optimal refresh rate for positions/Greeks")

**Color-Coding Thresholds:**
- Decision: Green <50%, yellow 50-80%, red >80%
- Rationale: Standard system monitoring thresholds (from Prometheus/Grafana patterns)
- Tradeoff: Arbitrary thresholds, but provide clear visual feedback
- Future: Make thresholds configurable

**psutil vs /proc filesystem:**
- Decision: Use psutil library
- Rationale: Cross-platform, simpler than parsing /proc/meminfo, /proc/loadavg
- Tradeoff: Additional dependency, but psutil is widely used and stable
- Research backing: 6-RESEARCH.md "Don't Hand-Roll" section

### Dependencies on Plans 1 and 2

**Plan 1 (Real-Time Dashboard):**
- Plan 3 uses dashboard foundation from Plan 1
- System health page added to pages/ directory
- Uses auto-refresh infrastructure from Plan 1

**Plan 2 (Alert Management):**
- Plan 3 generates health alerts
- Plan 2 displays health alerts alongside other alerts
- Alert acknowledgment workflow shared

### Open Questions from Research

**Q1: Historical health metrics?**
- Research recommendation: Store health metrics in Delta Lake for trend analysis
- Decision: Not in Plan 3 (future enhancement)
- Rationale: Plan 3 focuses on real-time health, historical metrics add complexity

**Q2: Automatic remediation?**
- Research recommendation: Auto-reconnect on disconnect, auto-clear stuck queue
- Decision: Manual actions only in Plan 3
- Rationale: Automatic remediation can cause issues (e.g., reconnect loop), manual control safer
- Future: Add auto-remediation with safeguards (max retry count, cooldown)

**Q3: Multi-server monitoring?**
- Research recommendation: Support monitoring multiple trading instances
- Decision: Single-server monitoring in Plan 3
- Rationale: v6 is single-instance deployment, multi-server adds complexity
- Future: Add multi-server support if needed

---

**Phase:** 6-monitoring-dashboard
**Plan:** 03-system-health
**Status:** Ready for execution
**Created:** 2026-01-27
**Estimated complexity:** Low (straightforward data display, existing components)
