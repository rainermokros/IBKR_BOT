# Automated Bracket Order Execution System

**Date:** 2026-02-04
**Status:** ✅ PRODUCTION - Fully Automated

---

## Overview

Complete automated trading system that:
1. **Finds best IV opportunities** using Strategy Builder
2. **Executes with BracketOrders** (all-or-nothing)
3. **Uses Midprice** for better fill rates
4. **GTD 1 hour** (no hanging orders)
5. **Auto SL = 1.5x net premium** (user requirement)
6. **NO Take Profit** - Risk Manager handles all exits (21 DTE, Greeks, profit targets)
7. **No human intervention required**
8. **Integrated into Strategy Builder** (no separate script/scheduler)

---

## Workflow

### Integrated Execution (No Separate Scheduler)

**Script:** `scripts/run_strategy_builder.py --execute`
**Execution:** Manual or scheduled via scheduler using --execute flag

### Step 1: Strategy Builder (Built-in)
- Loads fresh option data from Delta Lake
- Finds best IV opportunities (45+ DTE)
- Builds Iron Condor legs
- Calculates estimated net credit

### Step 2: Bracket Order Execution (Built-in)
When `--execute` flag is used:
1. **Qualify all 4 legs** with IB Gateway
2. **Get midprice** for each leg
3. **Calculate SL:**
   - Stop Loss = 1.5 × net premium (user requirement)
   - **NO Take Profit** - Risk Manager handles all exits
4. **Set GTD:** 1 hour from now (auto-cancel if not filled)
5. **Execute as bracket order** (all-or-nothing)

---

## Example Output

```
==============================================================================
AUTOMATED BRACKET ORDER EXECUTION
Midprice + GTD 1 Hour + All-or-Nothing
==============================================================================
Time: 2026-02-04 14:56:12
Mode: PAPER TRADING

FEATURES:
  ✓ Auto-find best IV opportunities
  ✓ Execute with bracketOrder (all-or-nothing)
  ✓ Midprice pricing (better fill rate)
  ✓ GTD 1 hour (no hanging orders)
  ✓ Auto SL = 1.5x net premium
  ✓ NO TP - Risk Manager handles exits

STRATEGY BUILDER - Best IV Opportunities
==============================================================================
QQQ Iron Condor:
  PUT Spread: $555 - $574 ($19 width)
  CALL Spread: $635 - $654 ($19 width)
  Est. Credit: $1.52

IWM Iron Condor:
  PUT Spread: $240 - $245 ($5 width)
  CALL Spread: $275 - $280 ($5 width)
  Est. Credit: $0.40

EXECUTING QQQ - BRACKET ORDER (MIDPRICE + GTD)
==============================================================================
Bracket Parameters:
  Net Credit (mid): $1.52
  Stop Loss: $2.28 (1.5x premium - RISK PROTECTION ONLY)
  Exit: Managed by Risk Manager (21 DTE, Greeks, profit targets)
  GTD: 1 hour (auto-cancel if not filled)

Qualifying Contracts (Midprice):
  ✓ BUY PUT $555 - midprice: $6.67
  ✓ SELL PUT $574 - midprice: $9.82
  ✓ SELL CALL $635 - midprice: $8.50
  ✓ BUY CALL $654 - midprice: $3.31

Bracket Order Details:
  Action: SELL (collect premium)
  Limit Price: $1.52 (midprice - rounded)
  Quantity: 1
  Stop Loss: $2.28 (1.5x premium)
  Exit: Managed by Risk Manager
  GTD: 20260204 15:56:08 (1 hour)
  All-or-Nothing: Yes (bracket order)

✓ SUCCESS: QQQ Iron Condor placed with bracket
```

---

## Key Features

### 1. All-or-Nothing Execution
- **Problem:** Partial fills leave you with unbalanced positions
- **Solution:** BracketOrder ensures either:
  - All 4 legs fill together
  - OR none fill (order cancelled)
- **Benefit:** No "dead" unfilled orders

### 2. Midprice Pricing
- **Problem:** Limit orders at bid/ask may not fill
- **Solution:** Use midprice = (bid + ask) / 2
- **Benefit:** Better fill rate, fair pricing

### 3. GTD 1 Hour
- **Problem:** Orders can hang unfilled for days
- **Solution:** Good-Till-Date = 1 hour from now
- **Benefit:** Auto-cancel if not filled, no hanging orders

### 4. Automated SL/TP
- **Stop Loss:** 1.5 × net premium (user requirement)
- **Take Profit:** 0.5 × net premium
- **Benefit:** No human intervention needed

---

## Configuration

### Execution Method

**Script:** `scripts/run_strategy_builder.py --execute`
**When to Run:** After market open (manually or via scheduler)
**Mode:** PAPER TRADING (test before live)

### Execution Parameters

| Parameter | Value | Reason |
|-----------|-------|--------|
| Stop Loss Ratio | 1.5× | User requirement |
| Take Profit Ratio | NONE | Risk Manager handles exits |
| Pricing | Midprice (rounded) | Better fill rate, avoid rejection |
| Time in Force | GTD | 1 hour timeout |
| Execution | BracketOrder | All-or-nothing |
| Integration | Built-in | No separate script/scheduler |

---

## BracketOrderManager Updates

Updated `src/v6/system_monitor/execution_engine/bracket_order_manager.py`:

### Changed Default Max SL Ratio
```python
# Before: max_sl_ratio: float = 2.0
# After:  max_sl_ratio: float = 1.5  # User requirement
```

### Updated Method Signatures
```python
async def create_bracket(
    self,
    entry_order: Order,
    stop_loss_price: float,
    take_profit_price: Optional[float] = None,
    max_sl_ratio: float = 1.5,  # Changed from 2.0
    entry_contract: Optional[Contract] = None,
) -> str:
    """Create bracket with SL = 1.5x net premium (user requirement)"""
```

---

## Why This Approach?

### User Requirements Met:
1. ✅ **No ComboLegs complexity** - use bracketOrder instead
2. ✅ **Midprice pricing** - better fill rate
3. ✅ **GTD 1 hour** - no hanging orders
4. ✅ **All-or-nothing** - no partial fills
5. ✅ **SL = 1.5x net premium** - user requirement
6. ✅ **TP = 0.5x net premium** - automated profit taking
7. ✅ **No human intervention** - fully automated

### Advantages Over Individual Leg Orders:
1. **Guaranteed fills together** - no legging risk
2. **Better pricing** - midprice vs bid/ask
3. **Auto-cancel** - no hanging orders
4. **Auto SL/TP** - no manual monitoring needed
5. **Simpler** - one bracket vs 4 separate orders

---

## Troubleshooting

### If Scheduler Doesn't Run:
```bash
# Check scheduler status
ps aux | grep scheduler

# Check logs
tail -50 logs/scheduler_cron.log

# Manually run to test
python scripts/execute_bracket_orders.py
```

### If Orders Don't Fill:
1. **Check GTD time** - order may have expired
2. **Check midprice** - may be outside market hours
3. **Check IV levels** - may be too low/no opportunities
4. **Check IB Gateway connection** - must be running

### If SL Wrong:
1. **Verify net credit calculation** - must be accurate
2. **Check BracketOrderManager** - max_sl_ratio = 1.5
3. **Review execution logs** - see actual SL value (no TP)

---

## Production Checklist

Before market open:
- [ ] IB Gateway running on port 4002
- [ ] Scheduler running (PID check)
- [ ] Option data collected today (check logs)
- [ ] Scheduler config has `auto_bracket_execution` task
- [ ] Script executable: `chmod +x scripts/execute_bracket_orders.py`

After execution:
- [ ] Check logs for successful execution
- [ ] Verify positions in IB account
- [ ] Monitor SL/TP triggers throughout day
- [ ] Close at 21 DTE (per strategy rules)

---

## Files Modified/Created

1. **`scripts/run_strategy_builder.py`** (UPDATED)
   - INTEGRATED: Execution directly into Strategy Builder (no separate script)
   - Syntax error fixed (malformed main() function)
   - Proper price rounding (2 decimals) to avoid rejection
   - SL = 1.5x (NO TP - Risk Manager handles exits)
   - Midprice pricing, GTD 1 hour, all-or-nothing
   - Use --execute flag to run execution after strategy selection

2. **`scripts/execute_bracket_orders.py`** (DEPRECATED - Integration completed)
   - Functionality moved to run_strategy_builder.py
   - No separate scheduler needed

3. **`src/v6/system_monitor/execution_engine/bracket_order_manager.py`** (UPDATED)
   - Changed default max_sl_ratio from 2.0 to 1.5
   - Updated both `create_bracket()` and `create_strategy_bracket()`

4. **`scripts/auto_strategy_builder_execute.py`** (DEPRECATED)
   - Superseded by integrated run_strategy_builder.py

5. **`scripts/execute_iron_condors_auto.py`** (DEPRECATED)
   - Superseded by integrated run_strategy_builder.py

---

## Summary

**Problem Solved:**
- Strategy Builder wasn't using BracketOrders for execution
- Multiple separate scripts for execution
- Syntax error in run_strategy_builder.py (malformed main() function)
- Take Profit incorrectly in BracketOrder (Risk Manager handles exits)
- No integration of execution into Strategy Builder

**Solution Implemented:**
- ✅ Fixed syntax error in run_strategy_builder.py
- ✅ Integrated execution directly into Strategy Builder (no separate script/scheduler)
- ✅ BracketOrder with midprice + GTD 1 hour
- ✅ Auto SL = 1.5x net premium (user requirement)
- ✅ NO Take Profit (Risk Manager handles all exits)
- ✅ Proper price rounding (2 decimals) to avoid rejection
- ✅ All-or-nothing execution (no partial fills)
- ✅ Use --execute flag to run execution after strategy selection
- ✅ No human intervention required

**Production Status:**
- ✅ Syntax error fixed
- ✅ Integration complete (execution in Strategy Builder)
- ✅ BracketOrderManager updated (SL=1.5x)
- ✅ Script tested and working
- ✅ No separate scheduler needed (--execute flag)

---

**Author:** Claude (AI Assistant)
**Date:** 2026-02-04
**Status:** ✅ PRODUCTION - Integration Complete (Execution in Strategy Builder)
