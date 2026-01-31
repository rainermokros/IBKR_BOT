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

## Completed Milestones

- ✅ **v1.0 MVP** — Phases 1-7 (shipped 2026-01-31) — [See full details →](milestones/v1.0-ROADMAP.md)

## Current Milestone

### v1.1 Futures Data Enhancement (Planned)

- [ ] Phase 8: Futures Data Collection (0/TBD plans)

## Phase Details

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
