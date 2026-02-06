# 🚨 CRITICAL: Option Data Collection NOT WORKING

**Status:** MARKET OPEN 30+ MINUTES - ZERO DATA COLLECTED
**Date:** 2026-02-04
**Last Successful Collection:** Feb 3, 2025 at 11:37 AM

---

## 📊 Current Situation

**❌ FAILING:**
- `option_snapshots` table NOT updating
- Scheduler running `collect_option_snapshots.py` every minute
- All attempts returning Error 200: "No security definition has been found"

**✅ WORKING:**
- IB Gateway connected
- Scheduler executing tasks
- `collect_options_working.py` script exists (successfully collected 84,874 rows on Jan 27)

---

## 🔴 Root Cause Analysis

### Issue 1: Wrong Expiration Dates (CRITICAL)

**Current Code** (`src/v6/pybike/ib_wrapper.py` line 100-102):
```python
# Use first 3 expirations from chain (nearest available)
expirations = sorted([e for e in chain.expirations if len(e) == 8])[:3]
```

**Result:** Selects `['20260204', '20260205', '20260206']` (Feb 4, 5, 6)

**Problem:**
- Today is Feb 4 - these are WEEKLY options expiring in 0-2 days
- Most weekly options don't have active contracts for every strike
- Many of these expirations may not have any contracts at all

**✅ CORRECT APPROACH:** Use monthly expirations with 20-60 DTE:
```python
# Filter for expirations 20-60 days out
from datetime import datetime, timedelta
max_date = (datetime.now() + timedelta(days=60)).strftime("%Y%m%d")
min_date = (datetime.now() + timedelta(days=20)).strftime("%Y%m%d")

expirations = sorted([e for e in chain.expirations
                     if len(e) == 8 and min_date <= e <= max_date])[:3]
```

### Issue 2: Market Price Returns NaN

**Symptom:**
```
Current price for SPY: nan
Selected 0 strikes near ATM
```

**Root Cause:** IB market data request failing or returning no data

**Fix Needed:** Add retry logic and fallback prices

### Issue 3: Exchange Configuration (PARTIALLY FIXED)

**✅ FIXED:**
- Changed from `exchange='CBOE'` to `exchange='SMART'` ✓
- Removed `tradingClass` parameter ✓

**Status:** Exchange is now correct, but contracts still fail because expiration dates are wrong

---

## 🛠️ REQUIRED FIXES

### Fix 1: Expiration Selection (CRITICAL - MUST DO)

**File:** `src/v6/pybike/ib_wrapper.py`
**Line:** 100-102

**CHANGE FROM:**
```python
# Use first 3 monthly expirations (day >= 15)
expirations = [e for e in chain.expirations if len(e) == 8 and int(e[-2:]) >= 15][:3]
logger.info(f"Using {len(expirations)} expirations: {expirations}")
```

**CHANGE TO:**
```python
# Use monthly expirations 20-60 days out (avoid weeklies that may not exist)
from datetime import datetime, timedelta
max_date = (datetime.now() + timedelta(days=60)).strftime("%Y%m%d")
min_date = (datetime.now() + timedelta(days=20)).strftime("%Y%m%d")

expirations = sorted([e for e in chain.expirations
                     if len(e) == 8 and min_date <= e <= max_date])[:3]
logger.info(f"Using {len(expirations)} 20-60 DTE expirations: {expirations}")
```

### Fix 2: Add Price Validation

**File:** `src/v6/pybike/ib_wrapper.py`
**Line:** 76-77

**CHANGE FROM:**
```python
ticker = self.ib.reqMktData(stock, "", False, False)
await asyncio.sleep(1)
current_price = ticker.marketPrice() if hasattr(ticker, 'marketPrice') else 0
logger.info(f"Current price for {symbol}: {current_price}")
```

**CHANGE TO:**
```python
ticker = self.ib.reqMktData(stock, "", False, False)
await asyncio.sleep(2)  # Increased wait time

# Get current price with validation
if hasattr(ticker, 'marketPrice') and ticker.marketPrice() and ticker.marketPrice() > 0:
    current_price = ticker.marketPrice()
else:
    # Fallback: use last price
    current_price = ticker.last if hasattr(ticker, 'last') and ticker.last else 0
    logger.warning(f"Using last price: {current_price}")

# If still no price, use chain midpoint
if current_price == 0:
    chain_strikes = sorted(chain.strikes)
    if chain_strikes:
        current_price = chain_strikes[len(chain_strikes) // 2]
        logger.warning(f"Using chain midpoint as price: {current_price}")

logger.info(f"Current price for {symbol}: {current_price}")
```

---

## ✅ Test the Fixes

After applying fixes, test:

```bash
# Quick test
cd /home/bigballs/project/bot/v6
/home/bigballs/miniconda3/envs/ib/bin/python scripts/collect_option_snapshots.py
```

**Expected Output:**
- Current price should be a valid number (not nan)
- Expirations should be like `['20260220', '20260227', '20260305']` (monthly, 20-60 DTE)
- Should see "Collected X snapshots" with X > 0
- Data should write to Delta Lake

**Verify Data:**
```bash
ls -lth data/lake/option_snapshots/ | head -3
# Should show today's date and current time
```

---

## 📋 For Tomorrow's Agent

### Immediate Actions (Before 9:30 AM)

1. **Apply Fix 1** (Expiration selection) - CRITICAL
2. **Apply Fix 2** (Price validation) - HIGH PRIORITY
3. **Test manually** at 9:25 AM
4. **Monitor first collection** at 9:30 AM

### Quick Test Command

```bash
# At 9:25 AM, run:
/home/bigballs/miniconda3/envs/ib/bin/python scripts/collect_option_snapshots.py 2>&1 | tee /tmp/morning_test.log

# Check if data was written:
ls -lth data/lake/option_snapshots/ | head -3
```

### Success Criteria

✅ Current price shows valid number (not nan)
✅ Expirations are 20-60 days out (monthly, not weeklies)
✅ "Collected X snapshots" shows X > 0
✅ Data table updates with current timestamp
✅ No partition errors

---

## 🔧 Alternative: Use Working Script

If fixes don't work, use the PROVEN working script:

```bash
/home/bigballs/miniconda3/envs/ib/bin/python scripts/collect_options_working.py
```

This script successfully collected **84,874 rows** on Jan 27, 2025.

However, this script:
- Takes longer to run (may timeout scheduler)
- Uses `OptionDataFetcher` which may have different logic
- May need timeout increased in scheduler config

---

## 📝 Summary

**Root Issue:** Selecting weekly option expirations (Feb 4-6) that don't have active contracts
**Solution:** Select monthly expirations 20-60 days out
**Priority:** CRITICAL - System is not collecting ANY data during market hours
**Time Impact:** 30+ minutes lost, losing valuable option data every 5 minutes

---

**END OF CRITICAL ALERT**
