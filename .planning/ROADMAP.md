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
- ✅ **v1.1 Futures Enhancement** — Phase 8 (shipped 2026-02-07)

## Current Milestone

### v1.2 Trading Optimization — IN PROGRESS

- [ ] Phase 9: Trading Optimization & Analysis (5 plans) — **PLANNED**

## Phase Details

### Phase 9: Trading Optimization & Analysis 🆕 PLANNED

**Goal**: Enhance trading performance through dynamic profit targets, portfolio integration, configuration management, and analytics feedback loops
**Status**: PLANNED (2026-02-07)
**Plans**: 5 plans

**Focus Areas:**
- Quick Wins (Tier 1): Dynamic profit targets + Configurable infrastructure
- High Value (Tier 2): Portfolio integration + Skew-aware selection + Variance analysis

**Plans:**
- [ ] 9-01: Dynamic Profit Targets (regime-based TP adjustment)
  - DynamicTakeProfit class with regime-based thresholds (crash=40%, high_vol=50%, normal=80%, low_vol=90%)
  - Integration with EnhancedMarketRegimeDetector
  - YAML configuration for TP customization
- [ ] 9-02: Configurable Infrastructure (centralize hardcoded values)
  - TradingConfig dataclass following futures_config.py pattern
  - trading_config.yaml with ib_connection, refresh_intervals, trading_limits
  - IBConnectionManager and Scheduler updated to use config
- [ ] 9-03: Unified Portfolio Integration (connect risk calc to entry workflow)
  - EntryWorkflow integrates PortfolioRiskCalculator
  - Portfolio delta checking before entry
  - PortfolioLimitsChecker validation in execute_entry()
  - Factory method for fully-wired EntryWorkflow
- [ ] 9-04: Skew-Aware Strike Selection (IV skew in strike selection)
  - SmartStrikeSelector calculates put/call IV ratio
  - Skew-adjusted target delta (higher delta on expensive side)
  - StrategySelector uses skew for strike selection
  - Skew metadata stored in strategy for analysis
- [ ] 9-05: Historical/Live Variance Analysis (prediction vs actual feedback loop)
  - StrategyPredictionsTable for storing predictions
  - Variance analysis by strategy type and regime
  - Dynamic weight adjustment based on prediction error
  - Prediction tracking at entry, actuals at exit

### Phase 8: Futures Data Collection ✅ COMPLETE

**Goal**: Add futures data collection (ES, NQ, RTY) for enhanced entry signal prediction
**Status**: COMPLETE (2026-02-07)
**Plans**: 2/2 complete

**Purpose:**
- Collect futures data as leading indicators for market direction
- Enable analysis of futures vs spot relationships
- Provide early signals for entry decisions (futures trade 23h/day vs 6.5h for equities)
- Test predictive value after 2-4 weeks of data accumulation

**Futures to Track:**
- **ES** (E-mini S&P 500) - Leading indicator for SPY
- **NQ** (E-mini Nasdaq 100) - Leading indicator for QQQ
- **RTY** (E-mini Russell 2000) - Leading indicator for IWM

**Delivered:**
- FuturesFetcher using unified IBConnectionManager
- Delta Lake futures_snapshots table with partitioning
- Change metrics calculation (1h, 4h, overnight, daily)
- Contract rollover detection (7 days before expiry)
- Maintenance window handling (5-6pm ET)
- Dashboard integration for real-time display
- Correlation analysis tools (lead-lag, predictive value)
- 26 integration tests (all passing)

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
| 8. Futures Data Collection | 2/2 | ✅ Complete | 2026-02-07 |
| 9. Trading Optimization | 0/5 | Planned | 2026-02-07 |

**Total:** 29 plans completed across 8 phases; Phase 9 planned (5 plans)

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
