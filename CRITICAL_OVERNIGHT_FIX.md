# 🚨 CRITICAL SYSTEM FAILURE - OVERNIGHT FIX REQUIRED

**Date:** 2026-02-04
**Status:** Market open 64+ minutes - ZERO option data collected
**Last Success:** Feb 3, 2025 at 11:37 AM
**Impact:** LOSING ALL OPTION DATA EVERY 5 MINUTES DURING TRADING HOURS

---

## 📊 What Happened Today

### Attempted Fixes (All Failed)

1. ✅ **Fixed Exchange:** Changed from CBOE to SMART - Correct fix
2. ✅ **Fixed Expiration Selection:** Changed to 20-60 DTE monthly options
3. ✅ **Fixed Price Retrieval:** Added fallback logic for current price
4. ✅ **Fixed Strike Rounding:** Round to whole numbers
5. ✅ **Created Adaptive Script:** Tries multiple strategies automatically

### Root Cause (CONFIRMED)

**IB Gateway returns "Error 200: No security definition has been found" for ALL option contracts**

This happens regardless of:
- Exchange (SMART, CBOE, CBOE2)
- Expiration (weekly, monthly, near-term, far-term)
- Strike prices (rounded, unrounded, ATM, OTM)

**Conclusion:** The option contract construction itself is wrong for this IB API version/configuration.

---

## ✅ What DOES Work

**Proven Working Script:** `scripts/collect_options_working.py`

- Successfully collected **84,874 rows** on Jan 27, 2025
- Uses `OptionDataFetcher` from `src/v6/core/market_data_fetcher.py`
- Different approach than current `collect_option_snapshots.py`

---

## 🛠️ OVERNIGHT PRIORITY FIX

### Option 1: Switch to Working Script (RECOMMENDED)

**Replace the broken script with the proven one:**

```bash
cd /home/bigballs/project/bot/v6

# Backup current broken script
mv scripts/collect_option_snapshots.py scripts/collect_option_snapshots.broken.py

# Use working version
cp scripts/collect_options_working.py scripts/collect_option_snapshots.py

# Test at 9:25 AM
/home/bigballs/miniconda3/envs/ib/bin/python scripts/collect_option_snapshots.py

# Verify data updated
ls -lth data/lake/option_snapshots/ | head -3
```

**Expected Result:** Should collect data successfully

### Option 2: Fix Scheduler Timeout

The working script takes longer (~2-3 minutes vs 30-second timeout):

**Edit scheduler config:**
```python
# In data/lake/scheduler_config table or wherever tasks are defined
{
  "task_name": "collect_option_data",
  "timeout_seconds": 300,  # Increase from 30 to 300
  ...
}
```

### Option 3: Debug IB Gateway Contract Construction

If you want to fix the current approach:

**Compare the two implementations:**

**Working:** `src/v6/core/market_data_fetcher.py` line 183+
```python
# Uses OptionDataFetcher.build_option_contract()
# Has different qualification logic
# Returns OptionContract objects with proper formatting
```

**Broken:** `src/v6/pybike/ib_wrapper.py` line 107+
```python
# Direct ib_async Option() calls
# Different parameter order
- No formatting/cleaning after qualification
```

---

## 📋 Tomorrow Morning Checklist

### At 8:00 AM - Pre-Market

```bash
cd /home/bigballs/project/bot/v6

# 1. Check IB Gateway is running
ps aux | grep ib

# 2. Verify connection
/home/bigballs/miniconda3/envs/ib/bin/python scripts/health_check.py
```

### At 9:25 AM - Test Collection (BEFORE MARKET OPEN)

```bash
# Test collection with working script
timeout 300 /home/bigballs/miniconda3/envs/ib/bin/python scripts/collect_options_working.py

# Verify data written
ls -lth data/lake/option_snapshots/ | head -3

# Should show TODAY'S date (Feb 5) and recent time
```

### At 9:30 AM - Market Open

```bash
# Monitor first automated collection
tail -f logs/scheduler_cron.log

# In another terminal, watch data table
watch -n 60 'ls -lth data/lake/option_snapshots/ | head -3'
```

### Success Criteria

✅ Data table updates within 5 minutes of market open
✅ Timestamp shows current date and time
✅ No Error 200 messages (or minimal - some are normal)
✅ Scheduler completes tasks successfully

---

## 🔧 Quick Commands for Tomorrow

### Check System Status
```bash
# Current time and phase
TZ=America/New_York date

# Scheduler status
tail -20 logs/scheduler_cron.log

# Data freshness
ls -lth data/lake/option_snapshots/ | head -3

# IB connection
/home/bigballs/miniconda3/envs/ib/bin/python scripts/health_check.py
```

### Manual Collection
```bash
# If scheduler fails, collect manually
/home/bigballs/miniconda3/envs/ib/bin/python scripts/collect_options_working.py
```

### Monitor During Market Hours
```bash
# Watch scheduler activity
tail -f logs/scheduler_cron.log

# Watch for errors
tail -f logs/scheduler_cron.log | grep -E "ERROR|Failed"

# Check data updates
watch -n 300 'ls -lth data/lake/option_snapshots/ | head -3'
```

---

## 📁 Key Files Reference

### Scripts
- `scripts/collect_options_working.py` - PROVEN WORKING VERSION ✓
- `scripts/collect_option_snapshots.py` - BROKEN VERSION (needs swap)
- `scripts/collect_option_snapshots_adaptive.py` - New adaptive attempt (didn't work)

### Core Modules
- `src/v6/core/market_data_fetcher.py` - Working implementation
- `src/v6/pybike/ib_wrapper.py` - Broken implementation
- `src/v6/system_monitor/data/option_snapshots.py` - Table writer

### Documentation
- `CRITICAL_DATA_COLLECTION_ISSUE.md` - Full analysis
- `PRE_TRADING_CHECKLIST.md` - Pre-market guide
- `MARKET_OPEN_CHECKLIST.md` - Market open guide
- `EXCHANGE_FIX_QUICK.md` - Exchange fix reference

---

## 💡 Key Insights

### What We Learned

1. **Exchange MUST be SMART** for ETF options (SPY, QQQ, IWM)
2. **Weekly options may not exist** - use monthly 20-60 DTE
3. **Strike prices must be standard intervals** (whole numbers, not decimals)
4. **Current working script uses different approach** - stick with what works
5. **Scheduler timeout too short** - need 300 seconds for full collection

### What Doesn't Work

- Creating Option() contracts directly in ib_wrapper.py
- Using weeklies with day < 15 in month
- Using non-standard strike prices (599.78 vs 600)
- Current scheduler timeout (30 seconds too short)

---

## ⚡ EMERGENCY CONTACT STEPS

If system still fails tomorrow morning:

### Step 1: Manual Data Collection
```bash
/home/bigballs/miniconda3/envs/ib/bin/python scripts/collect_options_working.py
```

### Step 2: Verify IB Gateway
```bash
# Restart IB Gateway if needed
# Check IB Gateway configuration
# Verify port 4002 is accessible
```

### Step 3: Check Scheduler
```bash
# View scheduler configuration
# Check if tasks are enabled
# Verify scheduler is running: ps aux | grep scheduler
```

### Step 4: Escalate
If all else fails, the `collect_options_working.py` script CAN be run manually every 5 minutes during market hours as a temporary stopgap.

---

## 📊 Business Impact

**Data Loss Today:**
- Market open: 9:30 AM
- Current time: 10:34 AM
- **Lost:** 64 minutes of data = 13 missed collections (every 5 minutes)
- **Estimated missed data points:** ~1,000 option contracts × 13 = 13,000 data points

**Continued Impact:**
- Every 5 minutes during market hours: ~1,000 option contracts lost
- Per hour: ~12,000 data points lost
- Per trading day: ~96,000 data points lost

---

## 🎯 Tomorrow's Success Criteria

1. ✅ Data collection starts by 9:35 AM
2. ✅ option_snapshots table updates every 5 minutes
3. ✅ No more Error 200 for ALL contracts (some OK, not all)
4. ✅ Scheduler tasks complete successfully
5. ✅ Can verify data freshness with `ls -lth data/lake/option_snapshots/`

---

**END OF OVERNIGHT FIX DOCUMENT**

**Created:** 2026-02-04 10:34 AM
**Next Review:** Before 9:30 AM tomorrow (Feb 5)
