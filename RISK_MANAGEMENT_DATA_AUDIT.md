# Risk Management Data Audit Report

**Date:** 2026-01-28
**Scope:** Phase 5 Risk Management - Delta Lake persistence audit
**Status:** ❌ **CRITICAL GAPS FOUND**

---

## Executive Summary

The Risk Management system (Phase 5) has **minimal Delta Lake persistence**. Most risk state changes are only logged to stdout/logfile, making post-mortem analysis impossible after process restart.

**Critical Finding:** Only 1 of 3 risk layers has adequate persistence.

---

## Risk Layers Audit

### ✅ Layer 1: Portfolio Limits (PARTIAL PERSISTENCE)

**What works:**
- Portfolio limit checks occur in `EntryWorkflow.execute_entry()`
- Limit violations raise `PortfolioLimitExceededError`
- Exceptions may be caught and logged

**What's missing:**
- ❌ No Delta Lake table for limit checks
- ❌ No record of limit evaluations (passed vs rejected)
- ❌ No audit trail of rejections with reasons
- ❌ Can't query "how many times did we hit delta limit?"
- ❌ Can't analyze "what percentage of entries were rejected?"

**Current handling:**
```python
# EntryWorkflow.execute_entry()
if not allowed:
    self.logger.warning(f"Entry REJECTED by portfolio limits: {reason}")
    raise PortfolioLimitExceededError(...)
```
→ Only logs to logger, raises exception (no persistence)

---

### ❌ Layer 2: Circuit Breaker (NO PERSISTENCE)

**What works:**
- Circuit breaker state transitions work correctly
- `record_failure()` and `record_success()` update in-memory state
- State transitions logged with `logger.warning()` / `logger.info()`

**What's missing:**
- ❌ No Delta Lake table for circuit breaker events
- ❌ No record of failure timestamps
- ❌ No record of state transitions (CLOSED → OPEN → HALF_OPEN → CLOSED)
- ❌ No audit trail for post-mortem: "why did trading halt at 10:30 AM?"
- ❌ Can't analyze "how often does circuit breaker open?"
- ❌ Can't reconstruct state after crash

**Current handling:**
```python
# TradingCircuitBreaker.record_failure()
self.failures.append(now)  # In-memory only
if len(self.failures) >= self.config.failure_threshold:
    self.state = CircuitState.OPEN
    logger.warning(f"Circuit breaker OPENED: {len(self.failures)} failures...")
```
→ Only logs to logger, updates in-memory state (lost on restart)

---

### ❌ Layer 3: Trailing Stops (NO PERSISTENCE)

**What works:**
- Trailing stop updates work correctly
- Triggers create CLOSE decisions which generate alerts
- AlertManager persists alerts to Delta Lake

**What's missing:**
- ❌ No Delta Lake table for trailing stop state
- ❌ No record of stop activations
- ❌ No record of stop updates (peak tracking)
- ❌ No audit trail for post-mortem: "why did position exit at 2 PM?"
- ❌ Can't analyze trailing stop effectiveness
- ❌ Can't backtest different parameters

**Current handling:**
```python
# TrailingStop.update()
if move_pct >= self.config.activation_pct:
    self.is_active = True
    self.stop_premium = self.highest_premium * (1 - self.config.trailing_pct / 100)
    logger.info(f"Trailing stop ACTIVATED: entry={...}, peak={...}, stop={...}")
```
→ Only logs to logger (lost on restart)

**Only TRIGGER events persisted:**
```python
# PositionMonitoringWorkflow
if action == TrailingStopAction.TRIGGER:
    return Decision(
        action=DecisionAction.CLOSE,
        reason=f"Trailing stop triggered at {new_stop:.2f}...",
        rule="TrailingStop",
    )
```
→ Trigger → CLOSE decision → Alert (persisted to alerts table)

**Problem:** You see the exit, but not the journey (how stop got there).

---

## What IS Persisted

### ✅ Alerts Table (v6/data/lake/alerts/)

**Schema:**
- `alert_id`: UUID
- `type`: INFO/WARNING/CRITICAL
- `severity`: IMMEDIATE/HIGH/NORMAL/LOW
- `status`: ACTIVE/ACKNOWLEDGED/RESOLVED/DISMISSED
- `title`: Short summary
- `message`: Detailed description
- `rule`: Which rule triggered (e.g., "TrailingStop", "StopLoss")
- `symbol`: Symbol
- `strategy_id`: Strategy execution ID
- `metadata`: JSON dict with rule-specific data
- `created_at`: Timestamp

**Coverage:**
- ✅ Trailing stop TRIGGER events (CLOSE alerts)
- ✅ Decision engine alerts (all 12 rules)
- ❌ Trailing stop ACTIVATE events
- ❌ Trailing stop UPDATE events
- ❌ Circuit breaker state transitions
- ❌ Portfolio limit checks

---

## Impact Assessment

### Post-Mortem Analysis

**Scenario:** System crashes at 2 PM, restarts at 2:05 PM. What can you reconstruct?

**Risk State Before Crash:**
| Data | Can Reconstruct? | How? |
|------|------------------|------|
| Circuit breaker state | ❌ NO | Lost - was it OPEN/CLOSED? Why? |
| Trailing stop levels | ❌ NO | Lost - what were stop prices? |
| Portfolio limit usage | ⚠️ PARTIAL | Can query current positions, but not rejections |
| Recent failures | ❌ NO | Lost - how many failures in window? |
| Alert history | ✅ YES | Query alerts table by timestamp |

**After Restart:**
- Circuit breaker: **Reset to CLOSED** (loss of state, may trade prematurely)
- Trailing stops: **Lost** (if not stored in StrategyExecution metadata)
- Portfolio limits: **Unknown if limit was hit before crash**

### Historical Analysis

**Questions you CAN'T answer:**
1. "How often did trailing stops trigger vs take profit?"
2. "What percentage of trades hit circuit breaker?"
3. "How effective is 2% activation threshold?"
4. "Did portfolio limits prevent any disasters?"
5. "What was our circuit breaker uptime?"

**Questions you CAN answer (via alerts):**
1. "How many CLOSE alerts were generated?"
2. "Which rules triggered most often?"
3. "Alert resolution times"

---

## Recommendations

### Priority 1: Create Risk Events Table

**New table:** `v6/data/lake/risk_events/`

**Schema:**
```python
{
    "event_id": pl.String,           # UUID
    "event_type": pl.String,         # "circuit_breaker_state_change",
                                     # "trailing_stop_activate",
                                     # "trailing_stop_update",
                                     # "portfolio_limit_check"
    "component": pl.String,          # "circuit_breaker", "trailing_stop",
                                     # "portfolio_limits"
    "timestamp": pl.Datetime("us"),
    "execution_id": pl.String,       # For trailing stops
    # Circuit breaker fields
    "old_state": pl.String,          # Optional: CLOSED, OPEN, HALF_OPEN
    "new_state": pl.String,          # Optional: CLOSED, OPEN, HALF_OPEN
    "failure_count": pl.Int32,       # Optional: number of failures
    # Trailing stop fields
    "entry_premium": pl.Float64,     # Optional
    "current_premium": pl.Float64,   # Optional
    "highest_premium": pl.Float64,   # Optional
    "stop_premium": pl.Float64,      # Optional
    "action": pl.String,             # Optional: ACTIVATE, UPDATE, TRIGGER, HOLD
    # Portfolio limit fields
    "limit_type": pl.String,         # Optional: "portfolio_delta", "symbol_delta", etc.
    "current_value": pl.Float64,     # Optional
    "limit_value": pl.Float64,       # Optional
    "allowed": pl.Boolean,           # Optional: was entry allowed?
    "rejection_reason": pl.String,   # Optional
    # Metadata
    "metadata": pl.String,           # JSON string for additional data
}
```

**Events to log:**
1. **Circuit Breaker:**
   - Every state transition (CLOSED → OPEN, OPEN → HALF_OPEN, etc.)
   - Every `record_failure()` call
   - Every `record_success()` call (when in HALF_OPEN)

2. **Trailing Stops:**
   - ACTIVATE events (when stop first activates)
   - UPDATE events (when stop level changes)
   - TRIGGER events (already logged via alerts, but also log here)
   - ADD events (when trailing stop enabled for position)

3. **Portfolio Limits:**
   - Every `check_entry_allowed()` call
   - Rejections with reason
   - Warnings from `check_portfolio_health()`

---

### Priority 2: Circuit Breaker State Recovery

**Add to TradingCircuitBreaker:**
- `save_state()` method - persist current state to Delta Lake
- `load_state()` method - restore state on startup
- Call `save_state()` after every state transition

**Benefits:**
- Survives process restarts
- Post-mortem analysis possible
- Can detect "why was circuit open when I restarted?"

---

### Priority 3: Trailing Stop State Storage

**Option A:** Store in StrategyExecution.metadata
- Add `trailing_stop_state` to metadata JSON
- Persists with strategy execution record
- Simple, leverages existing table

**Option B:** Separate trailing_stops table
- Queryable history
- Can analyze performance across all positions
- More storage, more complex

**Recommended:** Option A (store in metadata)

---

## Implementation Plan

### Phase 1: Create Risk Events Table (1-2 hours)
1. Create `risk_events.py` with schema
2. Create Delta Lake table
3. Create `RiskEventLogger` class

### Phase 2: Circuit Breaker Logging (1 hour)
1. Add `RiskEventLogger` to `TradingCircuitBreaker`
2. Log state transitions
3. Add state persistence (save/load)

### Phase 3: Trailing Stop Logging (1 hour)
1. Add `RiskEventLogger` to `TrailingStop`
2. Log ACTIVATE, UPDATE, TRIGGER events
3. Store state in StrategyExecution.metadata

### Phase 4: Portfolio Limits Logging (1 hour)
1. Add `RiskEventLogger` to `PortfolioLimitsChecker`
2. Log all check_entry_allowed() calls
3. Log rejections with full context

### Phase 5: Dashboard Queries (1 hour)
1. Add risk events query to dashboard
2. Circuit breaker state chart
3. Trailing stop history chart
4. Portfolio limit usage chart

**Total estimated time:** 5-6 hours

---

## Conclusion

**Current state:** Risk Management system has **minimal persistence**, making post-mortem analysis impossible after restart.

**Risk level:** HIGH - Can't reconstruct what happened, can't analyze effectiveness, state lost on crash.

**Recommendation:** Implement Priority 1 (Risk Events Table) immediately for audit trail. Add state recovery (Priority 2-3) for resilience.

**Next step:** Implement risk events table and logging for all 3 layers.
