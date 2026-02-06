# Option Assignment Risk Analysis - ✅ FIXED

**Date:** 2026-01-28
**Severity:** 🔴 **CRITICAL** → 🟢 **MITIGATED**
**Status:** ✅ **COMPLETE** - Assignment monitoring implemented

---

## User's Question

**"And on server assignment do we close immediately the broken strategy?"**

---

## Answer: ✅ YES - Assignment Monitoring Implemented

### Implementation Complete (2026-01-28)

**Files Created:**
- ✅ `src/v6/execution/assignment_monitor.py` (660 lines)
- ✅ `tests/execution/test_assignment_monitor.py` (400+ lines, 15 tests)

**Files Modified:**
- ✅ `src/v6/execution/engine.py` - Broken strategy validation + emergency parameter
- ✅ `src/v6/workflows/exit.py` - Emergency flag support
- ✅ `src/v6/workflows/monitoring.py` - AssignmentMonitor integration
- ✅ `src/v6/execution/__init__.py` - Export AssignmentMonitor

**Result:** **AssignmentMonitor implemented with immediate detection and emergency close.**

**See:** `ASSIGNMENT_MONITORING_IMPLEMENTATION_REPORT.md` for full details

---

## What Exists: Avoidance, Not Handling

### Time Exit Rule (Prevents Assignment, Doesn't Handle It)

**File:** `src/v6/decisions/rules/roll_rules.py:193-246`

```python
class TimeExit:
    """
    Time-based exit rule (Priority 8).

    Closes positions on the last day before expiration to avoid assignment risk:
    - DTE ≤ 1 → CLOSE

    This is a safety net to prevent assignment risk on expiration day.
    """

    def __init__(self):
        self.dte_threshold = 1  # Last day before expiration
```

**Purpose:** Close positions BEFORE assignment can occur

**Limitation:** This only prevents assignment at expiration. Does NOT handle:
- Early assignments on ITM calls (dividend plays)
- Early assignments on ITM puts (interest rate plays)
- Assignments that happen before the time exit triggers
- Assignment notifications from IB

---

## 🔴 What Happens When Assignment Occurs

### Scenario: Iron Condor Short Put Assigned

**Position:**
```
Iron Condor on SPY
Leg 1: Short $440 PUT (2 contracts) ← ASSIGNED
Leg 2: Long $435 PUT (2 contracts)
Leg 3: Short $460 CALL (2 contracts)
Leg 4: Long $465 CALL (2 contracts)
```

**Assignment Event:**
- SPY drops below $440
- Short $440 PUT gets assigned
- We are assigned 200 shares of SPY @ $440 = $88,000 debit
- Leg 1 is now gone (exercised), but legs 2-4 remain open

**Resulting Position:**
```
Cash Account:  -$88,000 (assigned shares)
Leg 2: Long $435 PUT x2 (still open)
Leg 3: Short $460 CALL x2 (still open)
Leg 4: Long $465 CALL x2 (still open)
```

**Problems:**

1. **Unbalanced Strategy** - Iron condor is broken, can't work as designed
2. **Massive Delta Exposure** - Own 200 shares delta vs delta-neutral strategy
3. **Naked Short CALL** - $460 CALL now effectively naked (no protective stock position)
4. **Margin Call Risk** - Assignment debit + naked call margin
5. **No Auto-Exit** - System continues monitoring broken strategy as if nothing happened

---

## 🔴 What Happens: System Behavior

### Current Behavior (NO Assignment Monitoring)

**1. IB sends assignment notification**
   - System has no listener for assignment events
   - Notification goes unnoticed

**2. Position changes in IB account**
   - Short option disappears
   - Stock position appears (long or short)
   - Other option legs remain open

**3. Reconciliation detects discrepancy (eventually)**
   - `src/v6/data/reconciliation.py` detects: "Position in Delta Lake but missing from IB"
   - Flags as `NAKED_POSITION` discrepancy
   - **But this is reactive, not immediate**
   - May take 5-15 minutes to detect (reconciliation interval)

**4. Monitoring workflow continues as normal**
   - `PositionMonitoringWorkflow` still tries to update trailing stops
   - Decision engine evaluates on incomplete strategy
   - May make bad decisions based on broken position

**5. Exit workflow tries to close (if triggered)**
   - `close_position()` tries to close ALL legs
   - But assigned leg is already gone
   - Tries to close remaining legs (2-4)
   - Creates partial position (naked calls + long puts)

---

## 🔴 Risk Scenarios

### Scenario 1: Early Assignment on ITM Call (Dividend Play)

**Situation:**
- Iron Condor with short $460 CALL
- SPY at $465, dividend tomorrow
- Short call gets assigned early (we must deliver shares)

**What happens:**
1. We are assigned to deliver 200 shares SPY
2. We don't own shares → short 200 shares created
3. Other 3 legs remain open
4. Short 200 shares + long put + short call + long call = MESS
5. Unlimited risk if SPY rallies (short shares + naked call)

**System response:** NOTHING (no assignment monitoring)

---

### Scenario 2: Assignment on ITM Put (Interest Rate Play)

**Situation:**
- Iron Condor with short $440 PUT
- SPY at $435, rates spiked
- Short put gets assigned

**What happens:**
1. We are assigned 200 shares @ $440
2. Other 3 legs remain open
3. Now own 200 shares + long put + short call + long call
4. Massive delta exposure (own 200 shares)
5. Downside risk (shares can drop to zero)

**System response:** NOTHING

---

### Scenario 3: Assignment Before Time Exit

**Situation:**
- Iron Condor with DTE=2
- Time exit triggers at DTE ≤ 1
- Assignment happens at DTE=1.5 (after hours, before market open)

**What happens:**
1. Assignment occurs
2. Market opens with broken strategy
3. System doesn't detect until reconciliation (5-15 min)
4. During that time, position moves against us
5. Time exit triggers, tries to close remaining legs
6. Creates unbalanced position

**System response:** DELAYED detection (reconciliation only)

---

## 🔴 Current System Gaps

| Gap | Severity | Impact |
|-----|----------|--------|
| **No assignment listener** | 🔴 CRITICAL | Assignments go undetected |
| **No auto-close on assignment** | 🔴 CRITICAL | Broken strategies stay open |
| **No validation for broken strategies** | 🔴 HIGH | Exit actions create partial positions |
| **Delayed detection (reconciliation)** | 🟡 MEDIUM | 5-15 min before detection |
| **No alert on assignment** | 🔴 HIGH | No manual intervention triggered |

---

## 🛠️ What Should Exist

### Required: Assignment Monitoring System

**1. Assignment Detection (Immediate)**

```python
# src/v6/execution/assignment_monitor.py

class AssignmentMonitor:
    """
    Monitor for option assignment events.

    Detects when short options are assigned and takes immediate action.
    """

    async def monitor_assignments(self):
        """
        Poll IB for assignment notifications.

        IB sends assignment notifications through:
        - IBApi.EWrapper.openOrder() - Order status change
        - IBApi.EWrapper.position() - Position changes
        - Email notifications
        """
        while True:
            # Check for assignment notifications from IB
            assignments = await self._check_ib_assignments()

            for assignment in assignments:
                await self._handle_assignment(assignment)

            await asyncio.sleep(1)  # Check every second

    async def _handle_assignment(self, assignment: Assignment):
        """
        Handle assignment event.

        CRITICAL: Immediately CLOSE entire strategy to prevent:
        - Naked positions
        - Margin calls
        - Massive delta/gamma exposure
        """
        self.logger.critical(
            f"ASSIGNMENT DETECTED: {assignment.symbol} "
            f"{assignment.right} ${assignment.strike} "
            f"({assignment.quantity} contracts)"
        )

        # 1. Mark strategy as BROKEN
        strategy_id = assignment.strategy_id
        await self.strategy_repo.mark_broken(strategy_id, reason="ASSIGNMENT")

        # 2. Create IMMEDIATE CLOSE decision
        decision = Decision(
            action=DecisionAction.CLOSE,
            reason=f"CRITICAL: Assignment detected on {assignment.symbol}. "
                   f"Closing entire strategy immediately.",
            rule="AssignmentMonitor",
            urgency=Urgency.IMMEDIATE,
            metadata={
                "assigned_leg": assignment.leg_id,
                "assignment_type": "EARLY" if assignment.dte > 1 else "EXPIRATION",
            },
        )

        # 3. Execute close immediately
        await self.exit_workflow.execute_exit_decision(
            execution=assignment.execution,
            strategy=assignment.strategy,
            decision=decision,
        )

        # 4. Send critical alert
        await self.alert_manager.send_critical_alert(
            f"ASSIGNMENT: {assignment.symbol} {assignment.right} ${assignment.strike} - "
            f"Strategy {strategy_id} closed automatically"
        )
```

---

**2. Validate No Broken Strategies in Exit**

```python
# src/v6/execution/engine.py

async def close_position(self, strategy: Strategy) -> ExecutionResult:
    """
    Close a position by placing opposite orders for all legs.

    CRITICAL: Check if strategy is already broken (assignment occurred).
    """
    # Check if strategy has missing legs (assignment indicator)
    if await self._has_missing_legs(strategy):
        self.logger.critical(
            f"CRITICAL: Strategy {strategy.strategy_id} appears broken. "
            "Some legs may have been assigned. Manual intervention required."
        )

        return ExecutionResult(
            success=False,
            action_taken="FAILED",
            order_ids=[],
            error_message="Cannot close broken strategy. Legs may be assigned. Manual review required."
        )

    # ... continue with close logic
```

---

**3. Immediate Assignment Notification from IB**

```python
# IB API callback for assignment detection

class IBWrapper(EWrapper):
    def openOrder(self, order: Order, orderState: OrderState):
        """
        Called when order status changes.

        Assignment indicators:
        - order.status == OrderStatus.Filled
        - order.permId changes (assigned/exercised)
        """
        if self._is_assignment(order):
            # Create assignment event
            assignment = Assignment(
                conid=order.contract.conId,
                symbol=order.contract.symbol,
                right=order.contract.right,
                strike=order.contract.strike,
                quantity=order.totalQuantity,
                strategy_id=self._get_strategy_id(order),
            )

            # Trigger immediate handling
            asyncio.create_task(
                self.assignment_monitor.handle_assignment(assignment)
            )

    def position(self, account: str, contract: Contract, position: float, avgCost: float):
        """
        Called when position changes.

        Assignment indicators:
        - Option position disappears (was 2, now 0)
        - Stock position appears (was 0, now 100 or -100)
        """
        if contract.secType == "STK" and abs(position) > 0:
            # Check if this is from assignment (not normal trade)
            if self._is_from_assignment(contract, position):
                # Create assignment event
                assignment = self._identify_assignment_source(contract, position)

                # Trigger immediate handling
                asyncio.create_task(
                    self.assignment_monitor.handle_assignment(assignment)
                )
```

---

**4. Enhanced Reconciliation**

```python
# src/v6/data/reconciliation.py

async def reconcile(self) -> ReconciliationResult:
    """
    Reconcile IB positions with Delta Lake.

    ENHANCED: Immediate critical alert if broken strategy detected.
    """
    result = ReconciliationResult(...)

    # ... existing logic ...

    # Check for broken strategies (partial leg closures)
    for discrepancy in result.discrepancies:
        if discrepancy.type == DiscrepancyType.NAKED_POSITION:
            # CRITICAL: This could be assignment
            self.logger.critical(
                f"CRITICAL: Potential assignment detected. "
                f"Position {discrepancy.delta_position} in Delta Lake "
                f"but missing from IB (conid={discrepancy.conid})"
            )

            # Check if this is part of a strategy
            strategy_id = await self._get_strategy_id_for_leg(discrepancy.conid)

            if strategy_id:
                # IMMEDIATE ALERT
                await self.alert_manager.send_critical_alert(
                    f"POTENTIAL ASSIGNMENT: Leg {discrepancy.conid} missing from IB. "
                    f"Strategy {strategy_id} may be broken. "
                    f"Manual review required immediately."
                )

                # Mark strategy as broken
                await self.strategy_repo.mark_broken(
                    strategy_id,
                    reason=f"Leg {discrepancy.conid} missing - potential assignment"
                )

                # Trigger emergency close (if configured)
                if self.auto_close_on_assignment:
                    await self._emergency_close_strategy(strategy_id)

    return result
```

---

## 🎯 Answer to User's Question

**Q:** "And on server assignment do we close immediately the broken strategy?"

**A:** ❌ **NO - We do NOT detect assignments or auto-close broken strategies.**

**Current State:**
- ❌ No assignment monitoring
- ❌ No assignment detection
- ❌ No auto-close on assignment
- ❌ No validation for broken strategies
- ⚠️ Only reconciliation detects (after 5-15 min delay)
- ⚠️ Only prevention (time exit), not handling

**What Happens on Assignment:**
1. Assignment occurs
2. Strategy is now broken (missing leg, stock position created)
3. System doesn't notice
4. Monitoring continues on broken strategy
5. Reconciliation detects eventually (5-15 min later)
6. Manual intervention required

**Risk Level:** 🔴 **CRITICAL**

**Recommended Actions:**
1. Implement AssignmentMonitor class
2. Add IB API listeners for assignment events
3. Auto-close strategy on assignment detection
4. Send critical alerts immediately
5. Validate no broken strategies before close
6. Add reconciliation emergency close

---

**Severity:** CRITICAL
**Priority:** IMMEDIATE
**Risk Level:** HIGH (can create unlimited loss, margin calls, regulatory issues)
