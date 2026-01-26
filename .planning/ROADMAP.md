# Roadmap: V6 Automated Trading System

## Overview

Build a next-generation automated options trading system with advanced automation and comprehensive risk management. V6 is a clean slate architecture inspired by v5 concepts but designed for simplicity while incorporating all proven features.

**Core Differentiators:**
1. **Advanced Automation** - Fully autonomous system (enters, monitors, adjusts, exits positions automatically) + Enhanced monitoring (better alerts and dashboards)
2. **Comprehensive Risk Management** - All three aspects:
   - Better exit rules (trailing stops, volatility adjustments)
   - Portfolio controls (position limits, correlation, concentration)
   - Real-time protection (circuit breakers, auto-hedge on risk spikes)

**Success Criteria:**
- Better risk-adjusted returns than v5 (lower drawdown, better Sharpe ratio)
- Full visibility into all system operations in real-time

**Journey:** Architecture & Infrastructure → Position Synchronization → Decision Rules Engine → Strategy Execution → Risk Management → Monitoring Dashboard → Testing & Deployment

## Domain Expertise

- ~/.claude/skills/expertise/ib-async-api/SKILL.md (IB connection library, patterns, error handling)
- ~/.claude/skills/expertise/ib-data/SKILL.md (IB data collection, historical data, market data)
- ~/.claude/skills/expertise/ib-order-manager/SKILL.md (IB order execution, bracket orders, OCA patterns)
- ~/.claude/skills/expertise/position-manager/SKILL.md (Position tracking, Greeks, P&L management)
- ~/.claude/skills/expertise/quant-options/SKILL.md (Options strategies, Greeks, risk management)
- ~/.claude/skills/expertise/delta-lake-lakehouse/SKILL.md (Delta Lake storage, lakehouse architecture, Parquet files)

## Key Architectural Decisions

- **Python 3.11+**: User requirement, ecosystem maturity
- **IB API (ib_async)**: Best Python IB library, battle-tested in v5
- **Delta Lake**: ACID transactions, time-travel for analytics
- **Clean Slate Architecture**: Avoid v5 complexity, incorporate lessons learned
- **Rule-based v1**: Proven approach from v5, ML added later

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Architecture & Infrastructure** - Delta Lake setup, IB connection layer, base models
- [ ] **Phase 2: Position Synchronization** - Real-time IB streaming, Delta Lake persistence, reconciliation
- [ ] **Phase 3: Decision Rules Engine** - 12 priority-based decision rules, risk calculations, alerts
- [ ] **Phase 4: Strategy Execution** - Automated strategy builders, order execution, entry/exit workflows
- [ ] **Phase 5: Risk Management** - Portfolio controls, circuit breakers, trailing stops, volatility adjustments
- [ ] **Phase 6: Monitoring Dashboard** - Real-time display, Greeks visualization, alert management
- [ ] **Phase 7: Testing & Deployment** - Integration testing, paper trading, production deployment

## Phase Details

### Phase 1: Architecture & Infrastructure
**Goal**: Set up Delta Lake, IB connection layer, base models, and configuration management
**Depends on**: Nothing (first phase)
**Research**: Likely (Delta Lake setup, ib_async patterns, project structure)
**Research topics**: Delta Lake Python API, ib_async best practices, project organization patterns
**Plans**: 4 plans

Plans:
- [ ] 01-01: Setup project structure and development environment (Python 3.11+, dependencies, testing framework)
- [ ] 01-02: Design and implement Delta Lake schema (positions, legs, Greeks, transactions, time-travel)
- [ ] 01-03: Implement IB connection manager (ib_async, auto-reconnect, circuit breaker, heartbeat)
- [ ] 01-04: Create base models and data structures (OptionLeg, Position, Strategy, Greeks, Portfolio)

### Phase 2: Position Synchronization
**Goal**: Hybrid position synchronization (stream active, queue non-essential)
**Depends on**: Phase 1
**Research**: Likely (real-time streaming patterns, data synchronization, reconciliation strategies)
**Research topics**: Real-time data sync patterns, IB position streaming, idempotent Delta Lake writes
**Plans**: 3 plans + 1 urgent fix phase

**✅ HYBRID APPROACH IMPLEMENTED:**
- **Active contracts:** Streamed via reqMktData() (real-time, consume slots)
- **Non-essential contracts:** Queued for batch processing (0 slots)
- **StrategyRegistry:** Tracks which contracts are active
- **PositionQueue:** Delta Lake backed queue
- **QueueWorker:** Background daemon processes queue every 5 seconds
- **Result:** Scales to thousands of contracts (~10 slots for active strategies)

Plans:
- [x] 02-01: Implement hybrid position polling (stream active, queue non-essential, 30s interval)
- [x] 02-02: Delta Lake persistence layer (idempotent writes, ACID transactions, time-travel queries)
- [x] 02-03: Reconciliation logic (IB ↔ local state, conflict resolution, data validation)

**✅ Phase 2.1: Hybrid Slot Conservation** (Urgent Fix - 4 plans)
- [x] 2.1-01: Create StrategyRegistry and PositionQueue
- [x] 2.1-02: Redesign IBPositionStreamer with hybrid logic
- [x] 2.1-03: Implement QueueWorker background daemon
- [x] 2.1-04: Integration testing and documentation

**✅ Phase 2 COMPLETE** - All plans finished, streaming slot issue resolved

**Phase 2 Accomplishments:**
- ✅ Hybrid position synchronization (stream active, queue non-essential)
- ✅ Streaming slot conservation (~10 slots vs 100+ slots)
- ✅ Delta Lake persistence with idempotent writes
- ✅ Reconciliation with periodic full sync
- ✅ Scales to thousands of contracts
- ✅ Persistent queue survives reboots (Delta Lake backed)

### Phase 3: Decision Rules Engine
**Goal**: Implement 12 priority-based decision rules, risk calculations, and alert generation
**Depends on**: Phase 2
**Research**: Likely (rule engine patterns, options risk calculations, decision prioritization)
**Research topics**: Options risk management best practices, rule engine design, alert patterns
**Plans**: 4 plans

Plans:
- [ ] 03-01: Implement rule evaluation framework (priority queue, rule execution, state management)
- [ ] 03-02: Portfolio-level risk calculations (delta, gamma, theta, vega, portfolio exposure)
- [ ] 03-03: Implement 12 priority-based decision rules (catastrophe, trailing stop, time exit, take profit, stop loss, delta/gamma risk, IV crush, DTE roll, VIX exit, portfolio limits)
- [ ] 03-04: Alert generation and management (alert types, severity, notifications, history)

### Phase 4: Strategy Execution
**Goal**: Automated strategy builders, order execution, and entry/exit workflows
**Depends on**: Phase 3
**Research**: Likely (IB order execution patterns, multi-leg orders, automation patterns)
**Research topics**: IB OCA/bracket orders, multi-leg order coordination, automation best practices
**Plans**: 3 plans

Plans:
- [ ] 04-01: Implement strategy builders (Iron Condor, vertical spreads, custom strategies)
- [ ] 04-02: IB order execution engine (order placement, OCA groups, bracket orders, error handling)
- [ ] 04-03: Entry and exit workflows (signal generation, position entry, monitoring, position exit)

### Phase 5: Risk Management
**Goal**: Portfolio-level controls, circuit breakers, trailing stops, and volatility adjustments
**Depends on**: Phase 4
**Research**: Likely (portfolio risk management, circuit breaker patterns, trailing stop algorithms)
**Research topics**: Options portfolio risk management, circuit breaker implementations, trailing stop strategies
**Plans**: 3 plans

Plans:
- [ ] 05-01: Portfolio-level controls (position limits, correlation checks, concentration limits)
- [ ] 05-02: Circuit breakers and auto-hedge (risk thresholds, automatic position reduction, hedging strategies)
- [ ] 05-03: Advanced exit rules (trailing stops, volatility-based adjustments, time-based exits)

### Phase 6: Monitoring Dashboard
**Goal**: Real-time position display, Greeks visualization, alert management, and system health
**Depends on**: Phase 5
**Research**: Likely (dashboard frameworks, real-time data visualization, monitoring patterns)
**Research topics**: Python dashboard frameworks (Streamlit, Dash), real-time visualization patterns, monitoring best practices
**Plans**: 3 plans

Plans:
- [ ] 06-01: Build real-time monitoring dashboard (position display, Greeks, P/L, portfolio health)
- [ ] 06-02: Alert management UI (alert history, active alerts, alert configuration)
- [ ] 06-03: System health monitoring (IB connection status, data freshness, system metrics)

### Phase 7: Testing & Deployment
**Goal**: Integration testing, paper trading validation, and production deployment
**Depends on**: Phase 6
**Research**: Likely (testing strategies for trading systems, deployment patterns, runbook creation)
**Research topics**: Trading system testing patterns, paper trading best practices, production deployment strategies
**Plans**: 3 plans

Plans:
- [ ] 07-01: Integration testing framework (IB test accounts, test scenarios, automated tests)
- [ ] 07-02: Paper trading validation (simulated trading, performance tracking, strategy validation)
- [ ] 07-03: Production deployment (deployment automation, monitoring setup, runbooks, documentation)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 2.1 → 3 → 4 → 5 → 6 → 7

Note: Phase 2.1 is urgent fix inserted after Phase 2.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Architecture & Infrastructure | 0/4 | Not started | - |
| 2. Position Synchronization | 3/3 | ✅ Complete | 2026-01-26 |
| 2.1. Hybrid Slot Conservation | 4/4 | ✅ Complete | 2026-01-26 |
| 3. Decision Rules Engine | 0/4 | Not started | - |
| 4. Strategy Execution | 0/3 | Not started | - |
| 5. Risk Management | 0/3 | Not started | - |
| 6. Monitoring Dashboard | 0/3 | Not started | - |
| 7. Testing & Deployment | 0/3 | Not started | - |

## V5 vs V6 Key Differences

| Aspect | V5 | V6 |
|--------|----|----|
| Architecture | Proven but complex | Clean slate, simpler design |
| Automation | Semi-automated | Fully autonomous |
| Risk Management | Basic exit rules | Comprehensive (exit + portfolio + real-time) |
| Monitoring | Basic dashboard | Enhanced with real-time alerts |
| ML Integration | Included | v1 rule-based, ML added later |
| Focus | Data collection + trading | Automation + risk management + visibility |
