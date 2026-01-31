# Plan: V6 Automated Trading System

## What This Is

Next-generation automated options trading system for personal account with fully autonomous strategy execution, comprehensive risk management, and real-time monitoring.

**Current Version:** v1.0 MVP (Shipped 2026-01-31)

## Core Value

> Autonomous trading with intelligent risk management and full visibility

## Requirements

### Validated (v1.0)

- ✓ Fully automated strategy entry (Iron Condors, vertical spreads) — v1.0
- ✓ 12 priority-based decision rules (catastrophe, trailing stop, time exit, take profit, stop loss, delta/gamma risk, IV crush, DTE roll, VIX exit, portfolio limits) — v1.0
- ✓ Real-time position synchronization (IB <-> Delta Lake) — v1.0
- ✓ Comprehensive risk management (exit rules + portfolio controls + real-time protection) — v1.0
- ✓ Enhanced monitoring dashboard (real-time alerts, Greeks, P/L, positions) — v1.0
- ✓ IB connection management (auto-reconnect, circuit breaker, heartbeat) — v1.0
- ✓ Delta Lake persistence (ACID transactions, time-travel) — v1.0

### Active

- [ ] Futures data collection (ES, NQ, RTY leading indicators) — Planned for Phase 8
- [ ] ML model integration for strategy optimization — Deferred to future versions

### Out of Scope

- ML model integration — v1 focuses on rule-based automation, ML added in future versions
- Multi-tenant support — Personal trading account only
- Mobile app — Web dashboard only

## Constraints

- **Tech Stack:** Python 3.11+, Interactive Brokers API (ib_async), Delta Lake, Streamlit
- **Architecture:** Clean slate - new design inspired by v5 concepts but not constrained by v5 architecture
- **Scope:** Personal trading account (single user) - no multi-tenant complexity

## Context

**Current State (v1.0):**

V6 MVP is complete and production-ready. The system delivers:

- **Modern Architecture:** Python 3.11+ with pyproject.toml packaging, ruff linting, pytest-asyncio testing
- **Delta Lake Persistence:** ACID transactions, time-travel analytics, 46,741 lines of production code
- **Hybrid Position Sync:** Streaming active positions (StrategyRegistry), queued non-active (PositionQueue)
- **Decision Engine:** 12-priority rule system with first-wins semantics, catastrophe handling, trailing stops
- **Automated Execution:** Iron Condors, vertical spreads with transactional IB order execution and rollback
- **Risk Management:** Circuit breakers, portfolio controls, position-level trailing stops with whipsaw protection
- **Monitoring Dashboard:** Streamlit dashboard with Greeks visualization, alerts, system health
- **Production Deployment:** Systemd services, health checks, automated deployment, runbooks, backup/restore

**Tech Stack:**
- Python 3.11+ with modern packaging (pyproject.toml)
- ib_async for IB API integration
- Delta Lake for persistence (Polars backend)
- Streamlit for monitoring dashboard
- pytest-asyncio for testing (146 tests)

**Testing:**
- 146 integration and unit tests
- Integration testing framework with fixtures
- Paper trading validation environment
- Production deployment tests

**Deployment:**
- Systemd services for automated management
- Health checks every 5 minutes
- Automated backup/restore procedures
- Comprehensive runbooks and documentation

**Builds on:**
- V5 functionality gap analysis
- Proven v5 patterns (rule-based approach)
- Lessons learned from v5 complexity

**Key Differentiators vs V5:**
- Clean slate architecture (simpler design)
- Hybrid position sync (streaming + polling)
- Comprehensive risk management (3-tier: exit + portfolio + system)
- Enhanced monitoring (real-time alerts, Greeks)
- Production-ready deployment (systemd, health checks)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python 3.11+ | User requirement, ecosystem maturity | ✅ Successful - modern packaging, fast performance |
| IB API (ib_async) | Best Python IB library, battle-tested in v5 | ✅ Successful - reliable connection, good async support |
| Delta Lake | ACID transactions, time-travel for analytics | ✅ Successful - reliable persistence, easy analytics |
| Clean slate architecture | Avoid v5 complexity, incorporate lessons learned | ✅ Successful - simpler, maintainable codebase |
| Rule-based v1 | Proven approach from v5, ML added later | ✅ Successful - all 12 rules working, production-ready |
| Hybrid position sync | Stream active, queue non-active | ✅ Successful - optimal slot usage |
| StrategyRegistry | Slot management for IB streaming limits | ✅ Successful - prevents slot exhaustion |
| Priority-based decision engine | 12 rules with first-wins semantics | ✅ Successful - clear rule execution order |
| Transactional execution | Rollback on failure | ✅ Successful - reliable order execution |
| Circuit breaker | System-level fault tolerance | ✅ Successful - prevents catastrophic failures |
| Streamlit dashboard | Real-time monitoring | ✅ Successful - easy to use, responsive |
| Systemd services | Production deployment | ✅ Successful - reliable service management |

## Next Milestone Goals (v1.1)

**Phase 8: Futures Data Collection**
- Collect ES, NQ, RTY futures data (23h/day vs 6.5h equities)
- Analyze futures vs spot correlations
- Test predictive value for entry signals
- Decision: Integrate into DecisionEngine if valuable after 2-4 weeks

## File Structure

```
v6/
├── .planning/
│   ├── PROJECT.md (this file)
│   ├── ROADMAP.md
│   ├── STATE.md
│   ├── MILESTONES.md
│   └── milestones/ (archive of completed milestones)
├── caretaker/        # Decision engine, monitoring, position sync
├── config/           # Configuration, thresholds, rules
├── data/             # Delta Lake tables, repositories
├── execution/        # Order execution, IB operations
├── orchestration/    # Production orchestrator, workflows
├── scripts/          # Utility scripts, dashboards, deployment
├── src/v6/
│   ├── config/       # Configuration models, loaders
│   ├── data/         # Delta Lake persistence, repositories
│   ├── decisions/    # Decision engine, rules
│   ├── strategies/   # Strategy builders
│   ├── execution/    # IB order execution
│   ├── risk/         # Risk management, circuit breaker
│   ├── monitoring/   # Dashboard, health checks
│   └── utils/        # IB connection, retry, circuit breaker
├── systemd/          # Systemd service files
├── tests/            # Integration and unit tests
└── docs/             # Documentation, runbooks
```

---

**Last updated:** 2026-01-31 after v1.0 milestone
