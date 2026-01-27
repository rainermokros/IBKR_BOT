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

**Journey:** Architecture → Position Sync → Decision Engine → Strategy Execution → Risk Management → Dashboard → Testing → Futures Data

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

- [x] **Phase 1: Architecture & Infrastructure** - Delta Lake setup, IB connection layer, base models
- [x] **Phase 2: Position Synchronization** - Real-time IB streaming, Delta Lake persistence, reconciliation
- [x] **Phase 2.1: Hybrid Slot Conservation** - Fix streaming slot usage with queue-based approach
- [x] **Phase 3: Decision Rules Engine** - 12 priority-based decision rules, risk calculations, alerts
- [x] **Phase 4: Strategy Execution** - Automated strategy builders, order execution, entry/exit workflows
- [x] **Phase 5: Risk Management** - Portfolio controls, circuit breakers, trailing stops, volatility adjustments
- [x] **Phase 6: Monitoring Dashboard** - Real-time display, Greeks visualization, alert management
- [x] **Phase 7: Testing & Deployment** - Integration testing, paper trading, production deployment
- [ ] **Phase 8: Futures Data Collection** - ES/NQ/RTY futures for entry signal enhancement

## Phase Details

### Phase 1: Architecture & Infrastructure ✅
**Goal**: Set up Delta Lake, IB connection layer, base models, and configuration management
**Depends on**: Nothing (first phase)
**Research**: Complete
**Plans**: 4 plans
**Status**: Complete

### Phase 2: Position Synchronization ✅
**Goal**: Hybrid position synchronization (stream active, queue non-essential)
**Depends on**: Phase 1
**Research**: Complete
**Plans**: 3 plans + 1 urgent fix phase (2.1)
**Status**: Complete

**Phase 2.1: Hybrid Slot Conservation** ✅
**Goal**: Fix streaming slot usage with StrategyRegistry and PositionQueue
**Status**: Complete (4/4 plans)

### Phase 3: Decision Rules Engine ✅
**Goal**: Implement 12 priority-based decision rules, risk calculations, and alert generation
**Depends on**: Phase 2
**Research**: Complete
**Plans**: 4 plans
**Status**: Complete

### Phase 4: Strategy Execution ✅
**Goal**: Automated strategy builders, order execution, and entry/exit workflows
**Depends on**: Phase 3
**Research**: Complete
**Plans**: 3 plans
**Status**: Complete

### Phase 5: Risk Management ✅
**Goal**: Portfolio-level controls, circuit breakers, trailing stops, and volatility adjustments
**Depends on**: Phase 4
**Research**: Complete
**Plans**: 3 plans
**Status**: Complete

### Phase 6: Monitoring Dashboard ✅
**Goal**: Real-time position display, Greeks visualization, alert management, and system health
**Depends on**: Phase 5
**Research**: Complete
**Plans**: 3 plans
**Status**: Complete

### Phase 7: Testing & Deployment ✅
**Goal**: Integration testing, paper trading validation, and production deployment
**Depends on**: Phase 6
**Research**: Complete
**Plans**: 3 plans
**Status**: Complete

### Phase 8: Futures Data Collection 🆕
**Goal**: Add futures data collection (ES, NQ, RTY) for enhanced entry signal prediction
**Depends on**: Phase 7
**Research**: Unlikely (IB futures data is standard)
**Research topics**: IB futures contract specifications, continuous futures data, correlation analysis
**Plans**: TBD

**Purpose:**
- Collect futures data as leading indicators for market direction
- Enable analysis of futures vs spot relationships
- Provide early signals for entry decisions (futures trade 23h/day vs 6.5h for equities)
- Test predictive value after 2-4 weeks of data accumulation

**Futures to Track:**
- **ES** (E-mini S&P 500) - Leading indicator for SPY
- **NQ** (E-mini Nasdaq 100) - Leading indicator for QQQ
- **RTY** (E-mini Russell 2000) - Leading indicator for IWM

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 2.1 → 3 → 4 → 5 → 6 → 7 → 8

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Architecture & Infrastructure | 4/4 | ✅ Complete | 2026-01-26 |
| 2. Position Synchronization | 3/3 | ✅ Complete | 2026-01-26 |
| 2.1. Hybrid Slot Conservation | 4/4 | ✅ Complete | 2026-01-26 |
| 3. Decision Rules Engine | 4/4 | ✅ Complete | 2026-01-26 |
| 4. Strategy Execution | 3/3 | ✅ Complete | 2026-01-26 |
| 5. Risk Management | 3/3 | ✅ Complete | 2026-01-26 |
| 6. Monitoring Dashboard | 3/3 | ✅ Complete | 2026-01-27 |
| 7. Testing & Deployment | 3/3 | ✅ Complete | 2026-01-27 |
| 8. Futures Data Collection | 0/TBD | Not started | - |

## V5 vs V6 Key Differences

| Aspect | V5 | V6 |
|--------|----|----|
| Architecture | Proven but complex | Clean slate, simpler design |
| Automation | Semi-automated | Fully autonomous |
| Risk Management | Basic exit rules | Comprehensive (exit + portfolio + real-time) |
| Monitoring | Basic dashboard | Enhanced with real-time alerts |
| ML Integration | Included | v1 rule-based, ML added later |
| Focus | Data collection + trading | Automation + risk management + visibility |
| Futures Data | No | Yes (ES, NQ, RTY for leading indicators) |
