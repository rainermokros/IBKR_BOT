# Exchange Fix - Error 200 Issue

> **CRITICAL FIX:** Option contracts must use `exchange='SMART'`, not `exchange='CBOE'`
> **Last Updated:** 2026-02-04
> **Status:** KNOWN ISSUE - FIX DOCUMENTED

---

## 🚨 The Problem

**Symptom:**
```
Error 200, reqId 6: No security definition has been found for the request
Unknown contract: Option(symbol='SPY', lastTradeDateOrContractMonth='20260217',
                         strike=655.0, right='P', exchange='CBOE')
```

**Root Cause:**
The code incorrectly uses `exchange='CBOE'` when creating option contracts.

**Correct Behavior:**
- **Stocks/ETFs:** Use `exchange='SMART'` ✓
- **Options:** Use `exchange='SMART'` ✓ (NOT CBOE!)

---

## 🔧 The Fix

### File: `src/v6/pybike/ib_wrapper.py`

**Location:** Lines 85-109

**Current (WRONG) Code:**
```python
# Line 86: Gets CBOE chain
chain = max([c for c in chains if 'CBOE' in str(c.exchange)],
            key=lambda x: len(x.expirations))

# Lines 89-90: Uses CBOE exchange for options
exchange = str(chain.exchange)  # This evaluates to 'CBOE'

# Line 109: Creates option contracts with CBOE
option = Option(symbol, expiry, strike, right, exchange, 'USD')
```

**Fixed (CORRECT) Code:**
```python
# Line 86: Gets CBOE chain (still OK to query the chain)
chain = max([c for c in chains if 'CBOE' in str(c.exchange)],
            key=lambda x: len(x.expirations))

# Lines 89-90: CHANGED - Use SMART for option contracts
exchange = 'SMART'  # Always use SMART for options

# Line 109: Creates option contracts with SMART
option = Option(symbol, expiry, strike, right, exchange, 'USD')
```

---

## 📝 Step-by-Step Fix Instructions

### Option 1: Edit Manually

```bash
# 1. Open the file
nano src/v6/pybike/ib_wrapper.py

# 2. Go to line 90 (Ctrl+_ then type 90)

# 3. Change this line:
exchange = str(chain.exchange)

# To this:
exchange = 'SMART'

# 4. Save and exit (Ctrl+X, then Y, then Enter)

# 5. Test the fix
/home/bigballs/miniconda3/envs/ib/bin/python scripts/collect_option_snapshots.py
```

### Option 2: Use sed (One-line fix)

```bash
# Backup the file first
cp src/v6/pybike/ib_wrapper.py src/v6/pybike/ib_wrapper.py.backup

# Apply the fix
sed -i "s/exchange = str(chain.exchange)/exchange = 'SMART'/" src/v6/pybike/ib_wrapper.py

# Verify the change
grep "exchange = 'SMART'" src/v6/pybike/ib_wrapper.py

# Test the fix
/home/bigballs/miniconda3/envs/ib/bin/python scripts/collect_option_snapshots.py
```

---

## ✅ Verify the Fix

After applying the fix, run this test:

```bash
# Run collection script
/home/bigballs/miniconda3/envs/ib/bin/python scripts/collect_option_snapshots.py 2>&1 | tee /tmp/test_fix.log

# Check for success
echo "=== CHECK RESULTS ==="
echo "1. Script completed with exit code: $?"
echo "2. Data updated:"
ls -lth data/lake/option_snapshots/ | head -3
echo "3. Contracts collected:"
grep "Collected.*snapshots" /tmp/test_fix.log
echo "4. Still some Error 200 messages? (NORMAL if data was collected)"
grep "Error 200" /tmp/test_fix.log | wc -l
```

**Expected Results:**
- Exit code: 0 (success)
- option_snapshots table shows recent timestamp
- Log shows "Collected X snapshots for SPY/QQQ/IWM"
- May still see SOME Error 200s (normal)

---

## 📊 Why This Fix Works

### Exchange Types in IB API

| Exchange | Use For | Example |
|----------|---------|---------|
| **SMART** | **All stock AND option contracts** | SPY, QQQ, IWM stocks and options |
| CBOE | Querying option chains only | Finding available expirations/strikes |
| SPECIFIC (ISE, AMEX, etc) | Rare - only when routing to specific exchange | Advanced order routing |

### The Mistake in Original Code

The code correctly:
1. ✅ Uses `SMART` for stock contracts (line 71)
2. ✅ Queries CBOE to find available option chains (line 86)

But then incorrectly:
3. ❌ Uses CBOE exchange when creating option contracts (line 90, 109)

### Why CBOE Doesn't Work

- CBOE is **one of many exchanges** where SPY options trade
- Not every strike/expiry combination exists on CBOE specifically
- IB requires the **specific exchange** where that contract trades
- Using `SMART` tells IB to **find the contract on any exchange**

### Why SMART Works

- SMART is IB's **smart routing** system
- Aggregates all exchanges (CBOE, ISE, AMEX, PHLX, etc.)
- Always works for ETF options (SPY, QQQ, IWM)
- IB automatically finds the best exchange for each contract

---

## 🎯 After the Fix

### What's Normal

✅ **You WILL still see some Error 200 messages:**
```
Error 200, reqId 6: No security definition has been found
```

This is NORMAL because:
- Not every strike/expiry combination exists
- Far OTM/ITM strikes may not have open interest
- Some expirations may not be trading yet

**What Matters:**
- ✅ Script completes successfully (exit code 0)
- ✅ Data is written to option_snapshots table
- ✅ Log shows "Collected X snapshots"
- ✅ Table timestamps update every 5 minutes

❌ **Not Normal (if fix worked):**
- Script fails with ALL contracts getting Error 200
- No data written to table
- Table timestamps not updating

---

## 🔄 Rollback If Needed

If the fix causes problems:

```bash
# Restore from backup
cp src/v6/pybike/ib_wrapper.py.backup src/v6/pybike/ib_wrapper.py

# Or manually revert the change
nano src/v6/pybike/ib_wrapper.py
# Change line 90 back to: exchange = str(chain.exchange)
```

---

## 📚 Related Documentation

- **MARKET_OPEN_CHECKLIST.md** - Section "Issue 1: option_snapshots Not Updating"
- **PRE_TRADING_CHECKLIST.md** - Section "Issue 0: CRITICAL - Exchange Configuration Error"
- **IB API Documentation:** https://ibkrcampus.com/courses/ib-api-reference-guide/

---

## 🐛 Known Issues

### After Applying Fix

**Issue:** Still seeing Error 200 messages
**Status:** ✅ NORMAL - See "What's Normal" section above

**Issue:** Collection takes longer than 5 minutes
**Status:** ⚠️ May need to reduce number of strikes/expirations

**Issue:** Data table still not updating
**Status:** 🚨 Check:
- Scheduler is running
- IB Gateway is connected
- Script is completing successfully
- Disk space available

---

**END OF EXCHANGE FIX DOCUMENT**
