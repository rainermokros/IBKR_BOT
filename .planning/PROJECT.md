# Plan: Initialize v6 Automated Trading System

## Objective

Create a new project subdirectory `v6/` and initialize it as a fresh start for an automated options trading system with advanced automation and comprehensive risk management.

## Context

Based on the V5 Functionality Gap Analysis, the user wants to build a next-generation trading system that:

**Core Differentiators:**
1. **Advanced Automation** - Fully autonomous system (enters, monitors, adjusts, exits positions automatically) + Enhanced monitoring (better alerts and dashboards)
2. **Comprehensive Risk Management** - All three aspects:
   - Better exit rules (trailing stops, volatility adjustments)
   - Portfolio controls (position limits, correlation, concentration)
   - Real-time protection (circuit breakers, auto-hedge on risk spikes)

**Success Criteria:**
- Better risk-adjusted returns than v5 (lower drawdown, better Sharpe ratio)
- Full visibility into all system operations in real-time

**User:** Personal trading account (single user)
**Constraints:** Python 3.11+, Interactive Brokers API

**Out of Scope for v1:**
- ML model integration (deferred to future)

## Tasks

### Task 1: Create v6 Directory Structure

Create the new subdirectory and basic structure:

```bash
mkdir -p v6
cd v6
mkdir -p caretaker config data scripts strategies utils
```

**Verification:** Directory `v6/` exists with subdirectories

### Task 2: Create PROJECT.md

Create `v6/.planning/PROJECT.md` documenting:

**What This Is:**
- Next-generation automated options trading system for personal account
- Fully autonomous options trading with comprehensive real-time risk management
- Success: Better risk-adjusted returns (lower drawdown, higher Sharpe) than v5

**Core Value:**
> Autonomous trading with intelligent risk management and full visibility

**Requirements - Active:**
- [ ] Fully automated strategy entry (Iron Condors, vertical spreads)
- [ ] 12 priority-based decision rules (catastrophe, trailing stop, time exit, take profit, stop loss, delta/gamma risk, IV crush, DTE roll, VIX exit, portfolio limits)
- [ ] Real-time position synchronization (IB <-> Delta Lake)
- [ ] Comprehensive risk management (exit rules + portfolio controls + real-time protection)
- [ ] Enhanced monitoring dashboard (real-time alerts, Greeks, P/L, positions)
- [ ] IB connection management (auto-reconnect, circuit breaker, heartbeat)
- [ ] Delta Lake persistence (ACID transactions, time-travel)

**Requirements - Out of Scope:**
- ML model integration -- v1 focuses on rule-based automation, ML added in future versions

**Constraints:**
- **Tech Stack:** Python 3.11+, Interactive Brokers API, Delta Lake
- **Architecture:** Clean slate - new design inspired by v5 concepts but not constrained by v5 architecture
- **Scope:** Personal trading account (single user) - no multi-tenant complexity

**Context:**
- Builds on learnings from V5_FUNCTIONALITY_GAP_ANALYSIS.md
- V5 has working implementation but complex architecture
- V6 opportunity: simpler, cleaner design while incorporating all v5 features
- V5 data/patterns as reference, but greenfield implementation

**Key Decisions:**

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python 3.11+ | User requirement, ecosystem maturity | -- Pending |
| IB API (ib_async) | Best Python IB library, battle-tested in v5 | -- Pending |
| Delta Lake | ACID transactions, time-travel for analytics | -- Pending |
| Clean slate architecture | Avoid v5 complexity, incorporate lessons learned | -- Pending |
| Rule-based v1 | Proven approach from v5, ML added later | -- Pending |

**File Structure:**
```
v6/
├── .planning/
│   ├── PROJECT.md (this file)
│   ├── config.json
│   └── codebase/ (optional, if we map v5 patterns)
├── caretaker/        # Decision engine, monitoring, position sync
├── config/           # Configuration, thresholds, rules
├── data/             # Delta Lake tables, repositories
├── execution/        # Order execution, IB operations
├── scripts/          # Utility scripts, dashboards
├── strategies/       # Strategy builders (Iron Condor, spreads)
└── utils/            # IB connection, retry, circuit breaker
```

---

**Last updated:** 2026-01-26 after initialization
