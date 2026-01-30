# Phase 8: Futures Data Collection - Context

**Gathered:** 2026-01-30
**Status:** Ready for planning

## How This Should Work

This phase adds futures data collection (ES, NQ, RTY) as a leading indicator for the Options Trading System. The vision is a **two-phase approach**:

**Phase 1: Data Collection Infrastructure**
- Collect futures data 24/7 (except maintenance window 5-6pm ET) using the **existing IBKR connection** - not a separate connection
- Follow the **same queue table pattern** as existing data collectors with **wait periods after each round**
- Store futures snapshots in Delta Lake (`futures_snapshots` table) following existing storage patterns
- Keep **all IBKR stuff in one place** - unified connection management, not siloed

**Phase 2: Signal Integration**
- After 2-4 weeks of data accumulation, integrate futures-based signals into the DecisionEngine
- Two key signals (equally important):
  1. **Pre-market surge signal** - Use overnight futures movement to decide entry positions at market open
  2. **Regime early warning** - Detect futures collapsing to anticipate bearish regime before cash market opens
- **Hybrid timing**: Pre-market check (4:00-9:30am ET) for open bias, plus spot checks throughout day for regime shifts
- **Context-aware logic**: Signals consider market context (VIX levels, current regime) not just simple percentage thresholds

**Data Flow Architecture:**
```
IBKR Connection (unified) → Data Collectors (queue-based, rate-limited) → Delta Lake → Strategy Builder
```

The Strategy Builder reads futures data from Delta Lake (never directly from IBKR), keeping Delta Lake as the single source of truth.

## What Must Be Nailed

- **Unified IBKR integration** - Futures collection uses existing connection infrastructure, not a separate system
- **Queue table pattern** - Follow established rate-limiting and wait period patterns
- **Delta Lake persistence** - Reliable time-series storage that Strategy Builder can query
- **Two-phase execution** - Data collection first (solid infrastructure), then signal integration (decision rules)

## What's Out of Scope

Standard scope - no explicit exclusions. The phase includes:
- Data collection infrastructure
- Delta Lake storage
- Signal integration into DecisionEngine (pre-market + regime warning)
- Standard dashboard visualization (if needed)

## Specific Ideas

**Integration Requirements:**
- Use existing IBKR connection - don't create separate futures connection
- Follow same queue table logic as other collectors
- Include wait periods after each round (rate limiting)
- All IBKR operations consolidated in one place

**Signal Approach:**
- Pre-market surge: Check overnight futures movement before market open
- Regime warning: Detect futures collapsing to anticipate regime shifts
- Hybrid timing: Pre-market check + continuous spot checks
- Context-aware: Consider VIX, current regime (not just thresholds)

**Data Access:**
- Strategy Builder queries Delta Lake for futures data
- No direct IBKR access from Strategy Builder
- Delta Lake is single source of truth

## Additional Context

User emphasized architectural consistency:
- Futures collection should feel like part of the existing system, not a bolt-on
- Same queue table patterns, same rate limiting, same Delta Lake storage approach
- "All IBKR stuff in one place" - unified connection management is key

The two-phase approach (collection → integration) ensures infrastructure is solid before adding decision logic.

---

*Phase: 8-futures-data-collection*
*Context gathered: 2026-01-30*
