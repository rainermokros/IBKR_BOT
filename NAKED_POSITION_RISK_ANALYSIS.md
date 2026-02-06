# Naked Position Risk Analysis - Critical Finding

**Date:** 2026-01-28
**Severity:** 🔴 **CRITICAL**
**Status:** Risk confirmed in partial failure scenario

---

## Executive Summary

**User's Question:** "Does the Risk Management work on strategy level? Because if we close only one leg we can end up with naked SHORTS !!!!"

**Answer:** Risk management DOES work at strategy level, BUT there's a **critical vulnerability** in the close_position() method that can create naked/unbalanced positions when some legs fail to close.

---

## ✅ Good News: Risk Management Works at Strategy Level

### 1. Trailing Stops Work at Strategy Level

**Evidence:** `src/v6/workflows/monitoring.py:195-222`

```python
# One trailing stop per entire strategy (by execution_id)
stop = self.trailing_stops.get_stop(strategy_execution_id)

# When triggered, creates CLOSE decision for ENTIRE strategy
if action == TrailingStopAction.TRIGGER:
    return Decision(
        action=DecisionAction.CLOSE,  # Closes ALL legs
        reason=f"Trailing stop triggered at {new_stop:.2f}",
        urgency=Urgency.IMMEDIATE,
    )
```

**Key Point:** Trailing stops are attached to `strategy_execution_id`, not individual legs. One stop per entire position.

---

### 2. Close Decision Closes All Legs

**Evidence:** `src/v6/workflows/exit.py:287-300`

```python
async def _execute_close(self, execution, strategy, decision):
    """Execute close position."""
    # Close position via execution engine
    result = await self.execution_engine.close_position(strategy)
    return result
```

**Evidence:** `src/v6/execution/engine.py:356-420`

```python
for leg in strategy.legs:
    # Place opposite order to close
    close_action = (
        OrderAction.SELL if leg.action == OrderAction.BUY else OrderAction.BUY
    )
    # ... place order
```

**Key Point:** `close_position()` iterates through ALL legs and closes them.

---

### 3. Partial Close (REDUCE) Not Implemented

**Evidence:** `src/v6/workflows/exit.py:320-346`

```python
async def _execute_reduce(self, execution, strategy, close_ratio, decision):
    """Execute partial close (reduce position size)."""
    # Note: OrderExecutionEngine doesn't have a partial close method yet
    # For now, we'll log a warning and return success
    self.logger.warning(
        f"Partial close not yet implemented: close_ratio={close_ratio}. "
        "Would close portion of legs."
    )
    return ExecutionResult(success=True, action_taken="REDUCED", ...)
```

**Key Point:** DecisionAction.REDUCE exists but is not implemented. Returns early without closing anything.

---

## 🔴 CRITICAL ISSUE: Partial Leg Closure Creates Naked Positions

### The Vulnerability

**Location:** `src/v6/execution/engine.py:356-428`

**Problem:** The `close_position()` method catches exceptions on individual legs and continues, which can leave some legs open while others are closed.

**Code:**
```python
for leg in strategy.legs:
    try:
        # ... place close order
        updated_order = await self.place_order(contract, close_order)
        order_ids.append(updated_order.order_id)

    except Exception as e:
        self.logger.error(f"Failed to close leg: {e}")
        # Continue with other legs  <-- ⚠️ KEEPS CLOSING OTHER LEGS
```

**Result:**
```python
# Return result with error message if no orders succeeded
if len(order_ids) == 0:
    return ExecutionResult(success=False, ...)

return ExecutionResult(
    success=True,  # ⚠️ MARKED AS SUCCESS even if only some legs closed
    action_taken="CLOSED",
    order_ids=order_ids,
)
```

---

### Real-World Example: Iron Condor Disaster

**Scenario:** Iron Condor with 4 legs

```
Leg 1: Short $440 PUT (credit +$2.00)
Leg 2: Long $435 PUT (debit -$1.50)
Leg 3: Short $460 CALL (credit +$2.00)
Leg 4: Long $465 CALL (debit -$1.50)
```

**What happens if Leg 3 close fails:**

1. Leg 1 closes ✅ (buy back PUT)
2. Leg 2 closes ✅ (sell PUT)
3. Leg 3 FAILS ❌ (order rejected, connection lost, etc.)
4. Leg 4 closes ✅ (sell CALL)

**Resulting position:**
```
Leg 3: Short $460 CALL ← **NAKED SHORT CALL!**
```

**Risk:** Unlimited upside loss if market rallies.

---

### Test Confirms the Problem

**Evidence:** `src/v6/execution/test_engine.py:558-603`

```python
async def test_close_position_with_leg_close_failure(self, engine):
    """Test closing position when leg close fails partially."""

    # Mock IB to raise exception on second leg
    def mock_place_order(contract, order):
        if "460" in str(contract.strike):
            raise Exception("Order rejected")  # Second leg fails
        return mock_trade

    # Close position
    result = await engine.close_position(strategy)

    # Verify partial success (one leg closed)
    assert result.success is True  # ⚠️ MARKED AS SUCCESS
    assert result.action_taken == "CLOSED"
    assert len(result.order_ids) == 1  # Only first leg succeeded
```

**Problem:** Test expects partial success to return `success=True`, but doesn't validate that this creates an unbalanced position.

---

## 🔍 Other Naked Position Checks

### Reconciliation System Detects Naked Positions

**Evidence:** `src/v6/data/reconciliation.py:11-12, 33-34, 138-147`

```python
class DiscrepancyType(str, Enum):
    NAKED_POSITION = "NAKED_POSITION"  # Position in Delta Lake but missing from IB (CRITICAL)

@property
def has_critical_issues(self) -> bool:
    """Check if there are critical discrepancies (NAKED_POSITION)."""
    return any(d.type == DiscrepancyType.NAKED_POSITION for d in self.discrepancies)
```

**Good:** The reconciliation system can detect when Delta Lake thinks a position exists but IB doesn't.

**Problem:** This is reactive (detects after the fact), not preventive (validates before closing).

---

## 📋 Risk Summary

| Scenario | Risk Level | Description |
|----------|------------|-------------|
| **Normal trailing stop trigger** | ✅ SAFE | Closes all legs atomically (in theory) |
| **Partial close (REDUCE)** | ✅ SAFE | Not implemented, returns early |
| **Leg close order rejected** | 🔴 **CRITICAL** | Other legs continue closing, creates naked position |
| **Connection timeout during close** | 🔴 **CRITICAL** | Partial closure, creates naked position |
| **IB API error mid-close** | 🔴 **CRITICAL** | Partial closure, creates naked position |

---

## 🎯 Root Cause

**The close_position() method has an "all-or-nothing" design intent but "best-effort" implementation.**

**Design Intent:** Close all legs of a strategy atomically

**Actual Behavior:**
1. Tries to close each leg sequentially
2. If one leg fails, logs error and continues with remaining legs
3. Returns success=True if ANY legs closed
4. Does NOT validate that all legs closed
5. Does NOT check if remaining legs create naked positions

---

## 🛠️ Recommended Fix

### Option 1: All-or-Nothing Closure (Recommended)

**Change:** If any leg fails to close, fail the entire close operation and attempt to rollback.

```python
async def close_position(self, strategy: Strategy) -> ExecutionResult:
    """
    Close a position by placing opposite orders for all legs.

    ATOMIC: All legs must close successfully, or none do.
    If any leg fails, attempt to close any legs that were opened.
    """
    order_ids = []
    closed_legs = []  # Track which legs were closed

    try:
        for leg in strategy.legs:
            # ... place close order
            order_ids.append(updated_order.order_id)
            closed_legs.append(leg)

    except Exception as e:
        self.logger.error(f"Failed to close leg: {e}")

        # ⭐ CRITICAL: Rollback - close any legs we successfully opened
        self.logger.error("Atomic close failed, attempting rollback...")
        for closed_leg in closed_legs:
            try:
                # Re-open the leg to restore original position
                await self._reopen_leg(closed_leg)
            except Exception as rollback_error:
                self.logger.critical(
                    f"CRITICAL: Failed to rollback leg {closed_leg}: {rollback_error}. "
                    "Position may be unbalanced!"
                )

        return ExecutionResult(
            success=False,
            action_taken="FAILED",
            order_ids=[],
            error_message=f"Atomic close failed: {e}. Rolled back {len(closed_legs)} legs."
        )

    return ExecutionResult(success=True, action_taken="CLOSED", order_ids=order_ids)
```

---

### Option 2: Validate No Naked Positions Created

**Change:** After close attempt, validate that remaining legs don't create naked positions.

```python
async def close_position(self, strategy: Strategy) -> ExecutionResult:
    """Close position with validation against naked position creation."""
    order_ids = []

    for leg in strategy.legs:
        try:
            # ... place close order
            order_ids.append(updated_order.order_id)
        except Exception as e:
            self.logger.error(f"Failed to close leg: {e}")

    # ⭐ CRITICAL: Validate no naked positions created
    if len(order_ids) > 0 and len(order_ids) < len(strategy.legs):
        self.logger.critical(
            f"CRITICAL: Partial close! {len(order_ids)}/{len(strategy.legs)} legs closed. "
            "Remaining legs may create naked/unbalanced position!"
        )

        # Check if remaining legs create naked position
        remaining_legs = [leg for i, leg in enumerate(strategy.legs) if i >= len(order_ids)]

        if self._creates_naked_position(remaining_legs):
            return ExecutionResult(
                success=False,
                action_taken="FAILED",
                order_ids=order_ids,
                error_message="CRITICAL: Partial close created naked position. Manual intervention required!"
            )

    return ExecutionResult(success=True, action_taken="CLOSED", order_ids=order_ids)

def _creates_naked_position(self, legs: list[LegSpec]) -> bool:
    """Check if remaining legs create a naked position."""
    # Check for unbalanced credit spreads
    # Check for uncovered short options
    # Check for mismatched quantities
    # ...
    return False  # Implement validation logic
```

---

### Option 3: OCA Groups (One-Cancels-All)

**Change:** Use IB's OCA (One-Cancels-All) groups to ensure all leg orders are linked.

```python
async def close_position(self, strategy: Strategy) -> ExecutionResult:
    """Close position using OCA group for atomic closure."""
    oca_group = f"CLOSE_{strategy.strategy_id}_{datetime.now().timestamp()}"

    for leg in strategy.legs:
        close_order = Order(
            # ...
            oca_group=oca_group,  # ⭐ Link all orders
            oca_type=2,  # Cancel all others if one fails
        )

        await self.place_order(contract, close_order)
```

**Limitation:** OCA groups work for new orders, but behavior on fills/partial fills varies.

---

## 🚨 Immediate Actions Required

1. **STOP using trailing stops in production** until this is fixed
2. **Add validation** to close_position() to detect partial closures
3. **Add circuit breaker** to halt trading if naked position detected
4. **Update reconciliation** to immediately alert on naked position detection
5. **Add tests** for naked position scenarios

---

## 📊 Current State

| Component | Status | Notes |
|-----------|--------|-------|
| Trailing stops (strategy level) | ✅ Works | One stop per strategy, not per leg |
| Close all legs intent | ✅ Correct | Tries to close all legs |
| Partial close prevention | ❌ **FAILS** | Continues on individual leg failures |
| Naked position validation | ❌ **MISSING** | No check for unbalanced positions |
| Rollback on failure | ❌ **MISSING** | No atomic rollback mechanism |
| Reconciliation detection | ✅ Works | Detects naked positions after the fact |

---

## ✅ Answer to User's Question

**Q:** "Does the Risk Management work on strategy level? Because if we close only one leg we can end up with naked SHORTS !!!!"

**A:** Risk management DOES work at strategy level (one trailing stop per strategy, closes all legs), BUT the close_position() implementation has a **critical flaw**:

**If any leg fails to close (order rejected, timeout, API error), the other legs continue closing, which can create naked/unbalanced positions.**

**Status:** 🔴 **CRITICAL VULNERABILITY CONFIRMED**

**Recommendation:** Implement Option 1 (All-or-Nothing with Rollback) or Option 2 (Naked Position Validation) before deploying trailing stops to production.

---

**Severity:** CRITICAL
**Priority:** IMMEDIATE
**Risk Level:** HIGH (can create unlimited loss positions)
