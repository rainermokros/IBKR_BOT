# Market Open Checklist - V6 Options Trading Bot

> **Purpose:** Post-market-open verification and monitoring guide
> **Use When:** Market has just opened (9:30 AM ET) or during trading hours
> **Last Updated:** 2026-02-04

---

## ⚡ IMMEDIATE CHECKS (Within 5 minutes of 9:30 AM)

### Check 1: Scheduler Phase Transition (CRITICAL)

**When:** Immediately at 9:30 AM
**What:** Verify scheduler switched from `pre_market` to `market_open`

```bash
# Check current phase in scheduler log
tail -20 logs/scheduler_cron.log | grep "Phase:"

# Expected output should show:
# "Time: 09:30:03 (Phase: market_open)"
```

**If FAILING (still shows pre_market):**
- Check system time: `TZ=America/New_York date`
- Restart scheduler: Kill process and let cron restart it
- Verify NYSE calendar: Market should be open today

---

### Check 2: Data Collection Started (CRITICAL)

**When:** Within 1 minute of 9:30 AM
**What:** Verify `collect_option_snapshots.py` is running

```bash
# Check if task is executing
tail -30 logs/scheduler_cron.log | grep "Running task: collect_option_data"

# Should show:
# "Running task: collect_option_data"
# "Script: scripts/collect_option_snapshots.py"
```

**If FAILING (task not running):**
- Check scheduler config: `data/lake/scheduler_config/` table
- Verify task is enabled and frequency is "5min"
- Manually trigger: `/home/bigballs/miniconda3/envs/ib/bin/python scripts/collect_option_snapshots.py`

---

### Check 3: option_snapshots Table Updating (CRITICAL)

**When:** Within 5 minutes of 9:30 AM
**What:** Verify new data is being written

```bash
# Check last update timestamp
ls -lth data/lake/option_snapshots/ | head -5

# Should show TODAY'S date with current time
# Example: "Feb  4 09:35" would indicate data from 9:35 AM

# Check Delta Lake transaction log
ls -lth data/lake/option_snapshots/_delta_log/ | head -3

# Should show recent .json files with today's timestamp
```

**If FAILING (no new data):**
- **IMMEDIATE ACTION REQUIRED** - See "CRITICAL ISSUES" section below
- Check if collection script is completing
- Look for errors in scheduler log
- Verify IB connection is working

---

### Check 4: IB Connection Active (CRITICAL)

**When:** Immediately at 9:30 AM
**What:** Verify IB Gateway connection

```bash
# Run health check
/home/bigballs/miniconda3/envs/ib/bin/python scripts/health_check.py

# Should show:
# "✓ IB Connection: IB connection OK"
```

**If FAILING:**
- Check if IB Gateway is running
- Verify connection settings in `.env`
- Restart IB Gateway

---

## 📊 ROUTINE MONITORING (Every 15 minutes during market hours)

### Monitor 1: Data Freshness

**When:** Every 15 minutes (9:45, 10:00, 10:15, etc.)
**What:** Verify option_snapshots updated within last 10 minutes

```bash
# Quick one-liner
python3 -c "
from datetime import datetime
import subprocess
result = subprocess.run(['ls', '-lth', 'data/lake/option_snapshots/'], capture_output=True, text=True)
lines = result.stdout.strip().split('\n')
if len(lines) > 1:
    print(f'Last update: {lines[1]}')
"

# Or simpler:
ls -lth data/lake/option_snapshots/ | head -2
```

**Expected:**
- Last update should be within last 10 minutes
- Timestamp should increment every 5 minutes

**If FAILING:**
- Check scheduler is running: `ps aux | grep scheduler`
- Check for errors in logs
- May need manual intervention

---

### Monitor 2: Scheduler Health

**When:** Every 15 minutes
**What:** Verify scheduler is checking in every minute

```bash
# Check latest check time
tail -5 logs/scheduler_cron.log | grep "SCHEDULER CHECK"

# Should show entries every minute
# Example: "SCHEDULER CHECK - 2026-02-04 09:45:03"
```

**Expected:**
- Log entries every minute
- Phase shows "market_open"
- No ERROR entries

**If FAILING:**
- Check if cron is running: `service cron status`
- Check crontab: `crontab -l | grep v6`
- Restart if needed

---

### Monitor 3: Error Detection

**When:** Every 15 minutes
**What:** Scan for critical errors in logs

```bash
# Check for errors in last 100 lines
tail -100 logs/scheduler_cron.log | grep -E "ERROR|CRITICAL|Failed"

# Check collection script for contract errors
# (Some errors are expected - see "Expected Errors" section)
```

**Expected:**
- May see some "Error 200" messages (expected - see below)
- Should NOT see "Failed (exit code: 1)" consistently
- Should NOT see timeout errors

---

## 🕐 SPECIFIC TIME CHECKS

### 9:35 AM Check - Contract Selection

**What:** Verify today's option contracts are queued

```bash
# Check ib_request_queue updated
ls -lth data/lake/ib_request_queue/ | head -3

# Check 9:35 task log
tail -50 /tmp/v6_935_et.log 2>/dev/null || echo "Log not created yet"
```

**Expected:**
- `ib_request_queue` should show update at 9:35 AM or later
- Log should show successful contract selection

**If FAILING:**
- Manually run: `/home/bigballs/miniconda3/envs/ib/bin/python scripts/schedule_935_et.py`
- Check why selection failed (may need strategy selector)

---

### 10:00 AM Check - System Stability

**What:** Verify system has been stable for first 30 minutes

```bash
# Comprehensive check
echo "=== 10:00 AM STABILITY CHECK ==="
echo "Time: $(TZ=America/New_York date)"
echo ""
echo "Data updates:"
ls -lth data/lake/option_snapshots/ | head -2
echo ""
echo "Scheduler health:"
tail -3 logs/scheduler_cron.log | grep "Phase:"
echo ""
echo "Recent errors:"
tail -100 logs/scheduler_cron.log | grep -i "error\|failed" | tail -5
```

**Expected:**
- Multiple data updates (every 5 minutes since 9:30)
- Phase consistently showing "market_open"
- No critical errors

---

### 12:00 PM Check - Mid-Day Review

**What:** Comprehensive mid-day system health check

```bash
# Full diagnostic
/home/bigballs/miniconda3/envs/ib/bin/python scripts/health_check.py
```

**Expected:**
- IB Connection: OK
- Position Sync: OK or showing reasonable lag
- System Resources: OK

---

## 🚨 CRITICAL ISSUES AND FIXES

### Issue 1: option_snapshots Not Updating (CRITICAL)

**Symptoms:**
- Table timestamps are old (more than 10 minutes)
- No new data during market hours
- Scheduler shows task running but no data appears

**Diagnosis Steps:**

```bash
# 1. Check if scheduler is invoking the script
tail -50 logs/scheduler_cron.log | grep "collect_option_data"

# 2. Check if script is running (look for process)
ps aux | grep "collect_option_snapshots"

# 3. Try running script manually to see errors
/home/bigballs/miniconda3/envs/ib/bin/python scripts/collect_option_snapshots.py
```

**Common Causes and Fixes:**

#### Cause A: Script Running But Failing
**Symptoms:** Script runs but exits with errors

**Fix:**
```bash
# Run manually and capture full output
/home/bigballs/miniconda3/envs/ib/bin/python scripts/collect_option_snapshots.py 2>&1 | tee /tmp/collect_debug.log

# Check the debug log
cat /tmp/collect_debug.log
```

**Common Errors:**

1. **Error 200: No security definition found (CRITICAL - Exchange Issue)**
   - **Issue:** Using wrong exchange for option contracts
   - **Root Cause:** Code uses `exchange='CBOE'` for options, but should use `exchange='SMART'`
   - **Location:** `src/v6/pybike/ib_wrapper.py` lines 85-109
   - **Symptoms:**
     ```
     Error 200, reqId 6: No security definition has been found for the request
     Unknown contract: Option(..., exchange='CBOE')
     ```
   - **Fix:**
     ```bash
     # Edit the IB wrapper to use SMART for option contracts
     nano src/v6/pybike/ib_wrapper.py

     # Change line 90 from:
     exchange = str(chain.exchange)  # Uses CBOE

     # To:
     exchange = 'SMART'  # Use SMART for all option contracts

     # Then restart scheduler or manually test:
     /home/bigballs/miniconda3/envs/ib/bin/python scripts/collect_option_snapshots.py
     ```
   - **Explanation:**
     - Stock contracts: Use `exchange='SMART'` ✓ (correct)
     - Option contracts: Should use `exchange='SMART'` NOT `exchange='CBOE'`
     - CBOE is just one of many exchanges where SPY/QQQ/IWM options trade
     - SMART exchange aggregates all exchanges and is the correct choice for ETF options
   - **Note:** After this fix, you may still see SOME Error 200 messages (normal - not all strike/expiry combos exist), but data should be collected successfully

2. **Connection timeout**
   - **Issue:** IB Gateway not responding
   - **Fix:** Restart IB Gateway, check connection settings

3. **Delta Lake write error**
   - **Issue:** Disk full or permissions
   - **Fix:** Check disk space: `df -h`

#### Cause B: Script Not Invoked
**Symptoms:** Scheduler log doesn't show "collect_option_data" task

**Fix:**
```bash
# 1. Check scheduler config
# Read the Delta Lake config table
python3 << 'EOF'
import polars as pl
df = pl.read_parquet('data/lake/scheduler_config/*.parquet')
print(df.filter(pl.col("task_name") == "collect_option_data").to_pandas())
EOF

# 2. Check if task is enabled
# Should show enabled: true, frequency: "5min", market_phase: "market_open"

# 3. If disabled or wrong config, update it:
# (This requires editing the scheduler config table)
```

#### Cause C: Scheduler Not Running
**Symptoms:** No "SCHEDULER CHECK" entries in log

**Fix:**
```bash
# 1. Check if process exists
ps aux | grep scheduler

# 2. If not running, restart cron
sudo service cron restart

# 3. Or manually start scheduler
/home/bigballs/miniconda3/envs/ib/bin/python -m v6.system_monitor.scheduler.scheduler
```

---

### Issue 2: Excessive Error 200 Messages

**Symptoms:**
- Log shows many "Error 200, reqId X: No security definition has been found"
- Different contracts failing repeatedly

**Explanation:**
- **THIS IS OFTEN NORMAL** - Not all strike/expiry combinations exist
- IB Gateway returns Error 200 for invalid contracts
- Script should handle gracefully and skip to next contract

**When to Worry:**
- If ALL contracts fail (no data collected)
- If same contract fails repeatedly
- If data table is not updating

**Fix:**
```bash
# Run script manually and check final summary
/home/bigballs/miniconda3/envs/ib/bin/python scripts/collect_option_snapshots.py 2>&1 | grep -E "SUCCESS|ERROR|Collected"

# Should see some "SUCCESS" messages even if there are Error 200s
```

**If No Success Messages:**
- Check contract selection logic in script
- May need to adjust strike selection range
- May need to verify exchange (CBOE vs others)

---

### Issue 3: Data Collection Too Slow

**Symptoms:**
- Script runs longer than 5 minutes
- Overlaps with next scheduled run
- Scheduler shows task "still running"

**Diagnosis:**
```bash
# Check how long collection takes
time /home/bigballs/miniconda3/envs/ib/bin/python scripts/collect_option_snapshots.py
```

**Fix:**
- **Reduce scope:** Collect fewer contracts/strikes
- **Increase timeout:** Edit scheduler config to increase timeout_seconds
- **Optimize script:** Add parallel processing (if not already)

---

### Issue 4: ib_request_queue Empty After 9:35 AM

**Symptoms:**
- Queue table shows old timestamp (before 9:35 AM)
- No contracts queued for today's trading

**Fix:**
```bash
# 1. Check if 9:35 task ran
tail -100 /tmp/v6_935_et.log 2>/dev/null || echo "Log doesn't exist"

# 2. Manually trigger contract selection
/home/bigballs/miniconda3/envs/ib/bin/python scripts/schedule_935_et.py

# 3. Check script output for errors
# Look for strategy selector issues, IB connection problems
```

---

## 📋 QUICK REFERENCE COMMANDS

### Full System Check (Run every 30 minutes)

```bash
#!/bin/bash
echo "╔════════════════════════════════════════════════════════╗"
echo "║     V6 MARKET OPEN CHECK - $(TZ=America/New_York date)    ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# 1. Current time and phase
echo "⏰ TIME & PHASE:"
TZ=America/New_York date
tail -3 logs/scheduler_cron.log | grep "Phase:" | tail -1
echo ""

# 2. Data freshness
echo "📊 DATA FRESHNESS:"
echo "   option_snapshots:"
ls -lth data/lake/option_snapshots/ | head -2 | tail -1 | awk '{print "     Last update: " $6, $7, $8}'
echo "   ib_request_queue:"
ls -lth data/lake/ib_request_queue/ | head -2 | tail -1 | awk '{print "     Last update: " $6, $7, $8}'
echo ""

# 3. Scheduler health
echo "🔄 SCHEDULER:"
if ps aux | grep -q "[s]cheduler"; then
    echo "   ✓ Scheduler process running"
else
    echo "   ✗ NO SCHEDULER PROCESS - CRITICAL"
fi
echo "   Latest check:"
tail -2 logs/scheduler_cron.log | grep "SCHEDULER CHECK" | tail -1 | awk '{print "     " $0}'
echo ""

# 4. Recent errors
echo "⚠️  RECENT ERRORS:"
tail -100 logs/scheduler_cron.log | grep -i "error\|failed" | tail -3
echo ""

# 5. IB connection
echo "🔌 IB CONNECTION:"
IB_STATUS=$(/home/bigballs/miniconda3/envs/ib/bin/python scripts/health_check.py 2>&1 | grep "IB Connection" | head -1)
echo "   $IB_STATUS"
echo ""

echo "╔════════════════════════════════════════════════════════╗"
echo "║  CHECK COMPLETE - Review results above                 ║"
echo "╚════════════════════════════════════════════════════════╝"
```

### Monitor Real-Time Data Collection

```bash
# Watch scheduler activity
tail -f logs/scheduler_cron.log

# Watch for data updates
watch -n 60 'ls -lth data/lake/option_snapshots/ | head -3'
```

### Quick Data Table Check

```bash
# Check all critical tables at once
echo "=== DATA TABLE STATUS ==="
for table in option_snapshots ib_request_queue futures_snapshots; do
    echo ""
    echo "Table: $table"
    ls -lth data/lake/$table/ 2>/dev/null | head -3 || echo "  Table not found"
done
```

---

## 📊 EXPECTED BEHAVIOR (What's Normal)

### Normal Error 200 Messages

**You WILL see these - they're expected:**
```
Error 200, reqId 6: No security definition has been found for the request
Unknown contract: Option(..., strike=655.0, ...)
Temporary error for SPY 20260217 655.0 P
```

**Why:** Not every strike/expiry combination exists
**When to worry:** If ALL contracts fail or data table not updating

### Normal Scheduler Behavior

**Every minute:**
- Scheduler runs "SCHEDULER CHECK"
- Logs current time and phase

**Every 5 minutes during market hours:**
- Scheduler invokes "collect_option_data" task
- Script runs for 1-3 minutes
- Data written to `option_snapshots` table
- Script exits with success (may have some Error 200s)

**At 9:35 AM:**
- Additional task runs to select today's contracts
- Updates `ib_request_queue` table

---

## 🔧 TROUBLESHOOTING FLOW CHART

```
Market Opens at 9:30 AM
         │
         ▼
    Check Scheduler Phase
         │
    ┌────┴────┐
    │         │
 pre_market  market_open  ◄─── GOOD
    │         │
    ▼         ▼
 Restart    Check Data Collection
 Cron           │
              ┌──┴──┐
         Running?  Not Running
              │      │
              ▼      ▼
        Check   Manually Run
        Data    Script & Debug
        Written
           │
        ┌──┴──┐
     YES      NO
        │      │
        ▼      ▼
    NORMAL   Check Script
             for Errors
                │
             ┌──┴────┐
        Error 200    Other Error
             │          │
             ▼          ▼
          NORMAL    Debug/Fix
          (skip)   Script
```

---

## 📞 ESCALATION PROCEDURES

### When to Escalate

1. **Immediate Escalation (Call/Text):**
   - option_snapshots not updating for >20 minutes during market hours
   - Scheduler completely down (no process, no log entries)
   - IB Gateway won't connect
   - System shows critical errors

2. **Documented Escalation (Email/Ticket):**
   - Recurring Error 200 issues preventing data collection
   - Performance degradation (script running too slow)
   - Configuration needs updating

### Before Escalating

1. **Run Full Diagnostic:**
```bash
# Save all diagnostic info
TZ=America/New_York date > diagnostic_$(date +%Y%m%d_%H%M%S).txt
ps aux | grep -E "python|scheduler" >> diagnostic_*.txt
tail -200 logs/scheduler_cron.log >> diagnostic_*.txt
tail -100 /tmp/v6_intraday.log >> diagnostic_*.txt 2>&1
ls -lth data/lake/option_snapshots/ >> diagnostic_*.txt
/home/bigballs/miniconda3/envs/ib/bin/python scripts/health_check.py >> diagnostic_*.txt 2>&1
```

2. **Attempt Basic Fixes:**
   - Restart scheduler
   - Manually run collection script
   - Check IB Gateway

3. **Preserve State:**
   - Don't delete logs
   - Don't modify tables
   - Document what you tried

---

## ✅ SUCCESS CRITERIA (Market Hours)

System is working correctly if:

- ✅ Scheduler phase shows `market_open`
- ✅ `option_snapshots` updates every 5 minutes (±2 min)
- ✅ IB connection shows OK
- ✅ Scheduler checks in every minute
- ✅ Some Error 200 messages (normal) but data is written
- ✅ `ib_request_queue` updated after 9:35 AM
- ✅ No critical errors in logs

---

## 📚 RELATED DOCUMENTS

- **PRE_TRADING_CHECKLIST.md** - What to check BEFORE market opens
- **SCHEDULER_GUIDE.md** - Detailed scheduler documentation
- **CLAUDE.md** - Project context and rules
- **UNIFIED_SCHEDULER_GUIDE.md** - Scheduler architecture

---

**END OF MARKET OPEN CHECKLIST**
