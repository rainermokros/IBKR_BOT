# V6 Trading System - Final Structure

**Date:** 2026-02-03
**Status:** Complete - Clean, Organized, Hierarchy-Based

---

## Parent-Child Hierarchy

```
Trading System
│
├─ Strategy Builder (Parent)
│  └─ Decision Engine (Trading rule evaluation & priorities)
│
├─ Risk Manager (Parent)
│  ├─ Trading Workflows (Entry, exit, monitoring)
│  └─ Performance Tracker (P&L metrics)
│
└─ System Monitor (Parent)
   ├─ Task Scheduler (NYSE-aware scheduling)
   ├─ Trading Dashboard (Streamlit UI)
   ├─ Data Lake Storage (Options, config)
   ├─ Futures Market Analyzer (Futures analysis)
   ├─ IB Gateway Connection Manager (Connection utilities)
   ├─ Alert System (Notifications)
   └─ Order Execution Engine (Order placement)
```

---

## Directory Structure

### Level 1: Parent Components

| Parent | Path | Purpose |
|--------|------|---------|
| **Strategy Builder** | `src/v6/strategy_builder/` | Builds trading strategies (Iron Condors, Spreads) |
| **Risk Manager** | `src/v6/risk_manager/` | Risk limits, circuit breakers, monitoring |
| **System Monitor** | `src/v6/system_monitor/` | Infrastructure monitoring & management |

### Level 2: Child Components

| Parent | Child | Path | Purpose |
|--------|-------|------|---------|
| Strategy Builder | Decision Engine | `src/v6/strategy_builder/decision_engine/` | Trading rules |
| Risk Manager | Trading Workflows | `src/v6/risk_manager/trading_workflows/` | Entry/exit/monitor |
| Risk Manager | Performance Tracker | `src/v6/risk_manager/performance_tracker/` | P&L metrics |
| System Monitor | Task Scheduler | `src/v6/system_monitor/scheduler/` | NYSE scheduling |
| System Monitor | Trading Dashboard | `src/v6/system_monitor/dashboard/` | Streamlit UI |
| System Monitor | Data Lake Storage | `src/v6/system_monitor/data/` | Options, config |
| System Monitor | Futures Analyzer | `src/v6/system_monitor/futures_analyzer/` | Futures analysis |
| System Monitor | Connection Manager | `src/v6/system_monitor/connection_manager/` | IB Gateway |
| System Monitor | Alert System | `src/v6/system_monitor/alert_system/` | Notifications |
| System Monitor | Execution Engine | `src/v6/system_monitor/execution_engine/` | Order placement |

---

## Runnable Scripts

Top-level scripts in `scripts/`:

| Script | Purpose |
|--------|---------|
| `collect_futures_snapshots.py` | Data Collector - Futures |
| `collect_option_snapshots.py` | Data Collector - Options |
| `health_check.py` | System Health Check |
| `validate_ib_connection.py` | Connection Validator |
| `run_dashboard.py` | Launch Dashboard |
| `run_paper_trading.py` | Run Paper Trading |

---

## Statistics

| Category | Count |
|----------|-------|
| Parent Components | 3 |
| Child Components | 10 |
| Total Components | 13 |
| Active Python Files | 83 |
| Runnable Scripts | 6 |
| Test Files | 71 |
| **Total Remaining** | **160** |
| **Archived** | **183** |

---

## Archive Location

```
/home/bigballs/project/bot/v6_archive/
├── v6_archived_20260203_072911/  (80 files - first batch)
└── v6_obsolete_20260203_075755/    (103 files - second batch)
```

---

## Key Improvements

1. **Business-Focused Naming** - All directories use business function names
2. **Logical Hierarchy** - Parent-child relationships clear
3. **Minimal & Clean** - 160 files (down from 308)
4. **Complete Trading System** - All core components restored

---

## Monitoring Components Explained

**System Monitor** - Health of the SYSTEM
- Is data fresh and complete?
- Are correlations normal?
- Any system anomalies?

**Alert System** - Notification MANAGER
- What alerts are active?
- What's the severity?
- Have they been acknowledged?

**Performance Tracker** - Trading PERFORMANCE
- How are strategies performing?
- What's our P&L?
- Win/loss ratios?
