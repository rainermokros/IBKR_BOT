# Options Trading System (v6)

> **ACTIVE PROJECT** - All development is focused here. The Regime Classifier (`../market_regime/`) is on hold.

## Project Identity
- **Name:** Options Trading System
- **Folder:** `v6/`
- **Type:** Automated options trading execution platform
- **Status:** ACTIVE - Primary development focus

## Quick Summary
Fully autonomous options trading system for personal account using Interactive Brokers. Handles strategy entry (Iron Condors, vertical spreads), 12-priority decision rules, real-time position synchronization, and comprehensive risk management.

## Key Directories
- `caretaker/` - Decision engine, monitoring, position sync
- `config/` - Configuration, thresholds, rules
- `data/` - Delta Lake tables, repositories
- `execution/` - Order execution, IB operations
- `scripts/` - Utility scripts, dashboards
- `strategies/` - Strategy builders (Iron Condor, spreads)
- `utils/` - IB connection, retry, circuit breaker

## Context Notes
- **Tech Stack:** Python 3.11+, Interactive Brokers API (ib_async), Delta Lake
- **Scope:** Rule-based automation v1 (ML integration deferred)
- **Related Projects:** `../market_regime/` (Regime Classifier) provides regime predictions for strategy optimization
- **Planning:** See `.planning/PROJECT.md` for full requirements and roadmap

## Working in This Project
- Always operate from `v6/` directory context
- Reference sibling project as `../market_regime/` or "the Regime Classifier"
- Integration point: Regime predictions inform strategy positioning (21-45 DTE)

## CRITICAL RULES - READ BEFORE MAKING CHANGES

### Strategy Execution Rules
❌ **FORBIDDEN:** Creating custom/temporary scripts to execute strategies
✅ **REQUIRED:** Use the existing Strategy Builder infrastructure:
- `src/v6/strategy_builder/builders.py` - Strategy builders (IronCondorBuilder, VerticalSpreadBuilder)
- `src/v6/strategy_builder/strategy_selector.py` - Strategy selection and scoring
- `src/v6/risk_manager/trading_workflows/entry.py` - EntryWorkflow for execution

### Position Monitoring Rules
❌ **FORBIDDEN:** Creating manual monitoring scripts or "next steps" for position monitoring
✅ **REQUIRED:** Use the Risk Manager infrastructure:
- `src/v6/risk_manager/trading_workflows/monitoring.py` - PositionMonitoringWorkflow
- `src/v6/strategy_builder/decision_engine/engine.py` - DecisionEngine for exit rules
- Monitoring runs automatically every 30 seconds

### Allowed Script Types
✅ **PERMITTED:** Scripts for verification and debugging ONLY:
- Checking Delta Lake data status
- Viewing logs and metrics
- Running diagnostics
- Testing connections
- Manual data inspection

❌ **NOT PERMITTED:** Any script that:
- Executes trades directly (use EntryWorkflow)
- Monitors positions manually (use PositionMonitoringWorkflow)
- Builds strategies from scratch (use Strategy Builder)
- Bypasses risk management (use Risk Manager)

### Exception Process
If you need functionality that doesn't exist in the v6 architecture:
1. **STOP** - Don't create a custom script
2. **ASK** - Request user approval: "I need X functionality. Should I extend [existing module] or create new component?"
3. **WAIT** - User must explicitly approve before creating new execution/monitoring code

---
*This file provides immediate project context. See `.planning/PROJECT.md` for complete documentation.*
