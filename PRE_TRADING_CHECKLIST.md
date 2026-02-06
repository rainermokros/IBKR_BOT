# Pre-Trading System Checklist - V6 Options Trading Bot

> **Purpose:** Comprehensive verification guide for agents to ensure smooth operation before trading hours (9:30 AM ET)

> **Last Updated:** 2026-02-04

---

## 🚨 CRITICAL REMINDERS

- **Current Directory:** Always operate from `/home/bigballs/project/bot/v6/`
- **Trading Hours:** 9:30 AM - 4:00 PM ET (Monday-Friday, NYSE calendar)
- **Error Context:** Health check errors before 9:30 AM can be **IGNORED** (pre-market errors are expected)

---

## ⏰ TIMELINE - Pre-Trading Tasks

### Before 8:00 AM ET
- [ ] System is running (cron jobs active)
- [ ] IB Gateway connection is alive

### 8:00 AM ET - Queue Option Contracts (>20 DTE)
- **Script:** `scripts/queue_option_contracts.py`
- **Purpose:** Queue all option contracts with >20 days to expiration for consulting
- **Log:** `/tmp/v6_pre_market.log`

### 8:30 AM ET - Load Enhanced Market Data
- **Script:** `scripts/load_enhanced_market_data.py`
- **Purpose:** Load overnight market data for SPY, QQQ, IWM
- **Log:** `/tmp/v6_pre_market.log`

### 8:45 AM ET - Validate IB Connection
- **Script:** `scripts/validate_ib_connection.py`
- **Purpose:** Verify IB Gateway is ready for market open
- **Log:** `/tmp/v6_validation.log`

### 9:35 AM ET - Queue Trading Day Contracts
- **Script:** `scripts/schedule_935_et.py`
- **Purpose:** Queue specific option contracts selected for today's trading
- **Log:** `/tmp/v6_935_et.log`

### Starting 9:30 AM ET - Intraday Data Collection
- **Frequency:** Every 5 minutes
- **Scripts:**
  - `scripts/collect_option_snapshots.py` - Option chain data (258 contracts)
  - `scripts/collect_futures_snapshots.py` - Futures data (ES, NQ, RTY)
- **Log:** `/tmp/v6_intraday.log`

---

## 🔍 PRE-TRADING VERIFICATION STEPS

### Step 1: Verify Current Time and Phase

```bash
# Check current time in ET
TZ=America/New_York date

# Calculate minutes to market open
python3 -c "from datetime import datetime; now = datetime.now(); market_open = now.replace(hour=9, minute=30, second=0, microsecond=0); diff = int((market_open - now).total_seconds() / 60); print(f'Minutes until 9:30 AM: {diff}')"
```

**Expected Output:**
- Should show current Eastern Time
- If before 9:30 AM, shows minutes remaining

---

### Step 2: Check Scheduler Status

```bash
# Verify scheduler is running
ps aux | grep -E "scheduler|python" | grep -v grep

# Check recent scheduler activity
tail -50 logs/scheduler_cron.log

# Verify current phase
tail -10 logs/scheduler_cron.log | grep "Phase:"
```

**Expected Output:**
- Python process with "scheduler" in command line
- Logs showing "SCHEDULER CHECK" every minute
- Phase should be:
  - `pre_market` before 9:30 AM
  - `market_open` during 9:30 AM - 4:00 PM
  - `post_market` after 4:00 PM

---

### Step 3: Verify IB Connection

```bash
# Run health check (automatically checks IB connection)
/home/bigballs/miniconda3/envs/ib/bin/python scripts/health_check.py
```

**Expected Output:**
```
✓ IB Connection: IB connection OK
```

**If Failing:**
- Check IB Gateway is running
- Verify connection settings in `.env`
- Restart IB Gateway if necessary

---

### Step 4: Check Delta Lake Tables

#### 4.1 Verify option_snapshots Table (CRITICAL - Updated every 5 min)

```bash
# Check last update time
ls -lth data/lake/option_snapshots/ | head -5

# Should show recent timestamps (within 10 minutes during market hours)
# Example: "Feb 4 09:25" would indicate data from 9:25 AM
```

**Expected:**
- During market hours (9:30 AM - 4:00 PM ET): Last update within 10 minutes
- Before 9:30 AM: May show older data (yesterday's last update)

**If Stale:**
- Check if `collect_option_snapshots.py` is running
- Verify `/tmp/v6_intraday.log` for errors
- Manually trigger collection if needed

#### 4.2 Verify ib_request_queue Table

```bash
# Check last update
ls -lth data/lake/ib_request_queue/ | head -5

# Should show today's date with recent timestamps
```

**Expected:**
- Updated at 8:00 AM (queue >20 DTE contracts)
- Updated again at 9:35 AM (queue today's selected contracts)

**If Missing/Empty:**
- Check if pre-market tasks ran successfully
- Verify `/tmp/v6_pre_market.log` and `/tmp/v6_935_et.log`
- May need to manually run queue scripts

---

### Step 5: Verify System Resources

```bash
# Quick resource check
df -h | grep -E "Filesystem|/$"
free -h | grep Mem
uptime
```

**Expected:**
- Disk usage < 80%
- Memory available > 20%
- Load average reasonable for your system

---

### Step 6: Check Log Files for Errors

```bash
# Pre-market log (8:00 AM, 8:30 AM, 8:45 AM tasks)
tail -100 /tmp/v6_pre_market.log

# Validation log (8:45 AM task)
tail -50 /tmp/v6_validation.log

# 9:35 ET log (option selection)
tail -50 /tmp/v6_935_et.log

# Intraday log (every 5 min starting 9:30 AM)
tail -100 /tmp/v6_intraday.log

# Health check log
tail -50 /tmp/v6_health.log
```

**What to Look For:**
- ✅ "Success" or completion messages
- ❌ Python exceptions or stack traces
- ❌ "Failed" or "Error" messages
- ⚠️ Warnings about missing data or connection issues

---

### Step 7: Verify Cron Configuration

```bash
# Check if system cron is installed
cat /etc/cron.d/v6-trading | head -30

# Verify user cron (unified scheduler)
crontab -l | grep v6
```

**Expected:**
- System cron shows comprehensive schedule (pre-market, intraday, post-market)
- User cron shows unified scheduler running every minute

---

## 📊 CRITICAL DATA TABLES

### Primary Tables

| Table Name | Purpose | Update Frequency | Source Script |
|------------|---------|------------------|---------------|
| `option_snapshots` | Option chain data (258 contracts) | Every 5 min (9:30 AM - 4:00 PM ET) | `collect_option_snapshots.py` |
| `ib_request_queue` | Queue of contracts to collect | 8:00 AM, 9:35 AM | `queue_option_contracts.py`, `schedule_935_et.py` |
| `futures_snapshots` | Futures data (ES, NQ, RTY) | Every 5 min | `collect_futures_snapshots.py` |

### Secondary Tables

| Table Name | Purpose |
|------------|---------|
| `market_bars` | Historical market bar data |
| `position_updates` | Position sync data |
| `scheduler_config` | Task scheduling configuration |
| `alerts` | System alerts and notifications |

---

## 🚨 COMMON ISSUES AND SOLUTIONS

### Issue 0: CRITICAL - Exchange Configuration Error (Error 200)

**⚠️ MOST COMMON ISSUE - Check This First!**

**Symptoms:**
- Script runs but gets `Error 200: No security definition has been found`
- Log shows: `Unknown contract: Option(..., exchange='CBOE')`
- option_snapshots table not updating despite script running

**Root Cause:**
The code uses `exchange='CBOE'` for option contracts, but **should use `exchange='SMART'`**

**Quick Fix:**
```bash
# Edit the IB wrapper
nano src/v6/pybike/ib_wrapper.py

# Find line 90 and change:
exchange = str(chain.exchange)  # Uses CBOE - WRONG

# To:
exchange = 'SMART'  # Use SMART for all option contracts - CORRECT

# Save and exit (Ctrl+X, Y, Enter)

# Test the fix
/home/bigballs/miniconda3/envs/ib/bin/python scripts/collect_option_snapshots.py
```

**Explanation:**
- **Stock contracts:** Use `exchange='SMART'` ✓ (correct)
- **Option contracts:** Should use `exchange='SMART'` NOT `exchange='CBOE'`
- CBOE is just one exchange, but SPY/QQQ/IWM options trade on multiple exchanges
- SMART exchange aggregates all exchanges - always use SMART for ETF options

**After Fix:**
- You may still see SOME Error 200 messages (normal - not all strike/expiry combos exist)
- But data should now be collected successfully
- option_snapshots table should update every 5 minutes

---

### Issue 1: option_snapshots Not Updating (Other Causes)

**Symptoms:**
- `ls -lth data/lake/option_snapshots/` shows old timestamps
- No new data during market hours
- **Already checked Exchange Issue above**

**Diagnosis:**
```bash
# Check if collection script ran
grep "collect_option_snapshots" /tmp/v6_intraday.log | tail -20

# Check for errors
tail -100 /tmp/v6_intraday.log
```

**Solutions:**
1. **FIRST:** Apply the Exchange fix from Issue 0 above
2. Verify scheduler is running (Step 2)
3. Check if market is open (should be 9:30 AM - 4:00 PM ET)
4. Manually trigger collection:
   ```bash
   /home/bigballs/miniconda3/envs/ib/bin/python scripts/collect_option_snapshots.py
   ```

---

### Issue 2: ib_request_queue Empty

**Symptoms:**
- Queue table shows no recent updates
- No contracts queued for collection

**Diagnosis:**
```bash
# Check pre-market task logs
tail -100 /tmp/v6_pre_market.log

# Check 9:35 task log
tail -50 /tmp/v6_935_et.log
```

**Solutions:**
1. If before 8:00 AM: Wait for pre-market tasks
2. If after 8:00 AM but before 9:35 AM:
   - Manually run queue script:
     ```bash
     /home/bigballs/miniconda3/envs/ib/bin/python scripts/queue_option_contracts.py
     ```
3. If after 9:35 AM:
   - Check if 9:35 task ran:
     ```bash
     /home/bigballs/miniconda3/envs/ib/bin/python scripts/schedule_935_et.py
     ```

---

### Issue 3: Health Check Shows "Degraded"

**Symptoms:**
- Position sync shows lag
- Dashboard connection refused

**Diagnosis:**
```bash
# Run full health check
/home/bigballs/miniconda3/envs/ib/bin/python scripts/health_check.py
```

**Solutions:**
1. **Position Sync Lag:** Expected during pre/post-market hours (not critical)
2. **Dashboard Connection Refused:** Dashboard not running (optional, not critical for trading)
3. **IB Connection Failed:** Critical - restart IB Gateway

---

### Issue 4: Scheduler Not Running

**Symptoms:**
- No "SCHEDULER CHECK" entries in logs
- `ps aux | grep scheduler` shows no process

**Diagnosis:**
```bash
# Check if cron is running
service cron status

# Check cron logs
grep CRON /var/log/syslog | tail -20
```

**Solutions:**
1. Restart cron service:
   ```bash
   sudo service cron restart
   ```
2. Verify crontab entry:
   ```bash
   crontab -l
   ```
3. Manually start scheduler (temporary):
   ```bash
   /home/bigballs/miniconda3/envs/ib/bin/python -m v6.system_monitor.scheduler.scheduler
   ```

---

## 📋 QUICK REFERENCE COMMANDS

### Check Everything (5 minutes)
```bash
# 1. Current time and phase
echo "=== TIME CHECK ===" && TZ=America/New_York date

# 2. Scheduler status
echo "=== SCHEDULER ===" && tail -5 logs/scheduler_cron.log | grep Phase

# 3. IB connection
echo "=== IB CONNECTION ===" && /home/bigballs/miniconda3/envs/ib/bin/python scripts/health_check.py 2>&1 | grep -E "IB Connection|Health check"

# 4. Data tables
echo "=== DATA TABLES ===" && ls -lth data/lake/option_snapshots/ | head -2 && ls -lth data/lake/ib_request_queue/ | head -2

# 5. Recent logs
echo "=== RECENT ERRORS ===" && grep -i "error\|failed" /tmp/v6_*.log 2>/dev/null | tail -10
```

### Manually Trigger All Pre-Market Tasks
```bash
# Queue contracts (8:00 AM task)
/home/bigballs/miniconda3/envs/ib/bin/python scripts/queue_option_contracts.py

# Load market data (8:30 AM task)
/home/bigballs/miniconda3/envs/ib/bin/python scripts/load_enhanced_market_data.py

# Validate IB connection (8:45 AM task)
/home/bigballs/miniconda3/envs/ib/bin/python scripts/validate_ib_connection.py

# Queue today's contracts (9:35 AM task)
/home/bigballs/miniconda3/envs/ib/bin/python scripts/schedule_935_et.py
```

### Monitor During Market Hours
```bash
# Watch intraday collection in real-time
tail -f /tmp/v6_intraday.log

# Watch scheduler activity
tail -f logs/scheduler_cron.log

# Check data freshness
watch -n 60 'ls -lth data/lake/option_snapshots/ | head -3'
```

---

## 📞 ESCALATION

### If You Cannot Resolve an Issue

1. **Document Everything:**
   ```bash
   # Save diagnostic output
   TZ=America/New_York date > diagnostic_output.txt
   ps aux | grep -E "python|scheduler" >> diagnostic_output.txt
   tail -100 logs/scheduler_cron.log >> diagnostic_output.txt
   tail -100 /tmp/v6_intraday.log >> diagnostic_output.txt
   ls -lth data/lake/option_snapshots/ >> diagnostic_output.txt
   ```

2. **Check These Files:**
   - `CLAUDE.md` - Project context and rules
   - `SCHEDULER_GUIDE.md` - Scheduler documentation
   - `README.md` - General project information

3. **Preserve State:**
   - Don't delete any log files
   - Don't modify Delta Lake tables
   - Don't restart services unless necessary

---

## ✅ FINAL CHECKLIST (Use at 9:28 AM)

Run this 2-minute comprehensive check:

```bash
#!/bin/bash
echo "╔════════════════════════════════════════════════════════╗"
echo "║     V6 PRE-TRADING SYSTEM CHECK - $(TZ=America/New_York date)      ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# 1. Time check
echo "⏰ TIME TO MARKET OPEN:"
python3 -c "from datetime import datetime; now = datetime.now(); market_open = now.replace(hour=9, minute=30, second=0, microsecond=0); diff = int((market_open - now).total_seconds() / 60); print(f'   Minutes until 9:30 AM: {diff}')"
echo ""

# 2. Scheduler
echo "🔄 SCHEDULER:"
if ps aux | grep -q "[s]cheduler"; then
    echo "   ✓ Scheduler process running"
else
    echo "   ✗ NO SCHEDULER PROCESS - CRITICAL"
fi
echo ""

# 3. IB Connection
echo "🔌 IB CONNECTION:"
IB_STATUS=$(/home/bigballs/miniconda3/envs/ib/bin/python scripts/health_check.py 2>&1 | grep "IB Connection" | head -1)
if echo "$IB_STATUS" | grep -q "OK"; then
    echo "   ✓ $IB_STATUS"
else
    echo "   ✗ $IB_STATUS - CRITICAL"
fi
echo ""

# 4. Data Tables
echo "📊 DATA TABLES:"
OPTION_TIME=$(ls -lth data/lake/option_snapshots/ 2>/dev/null | head -2 | tail -1 | awk '{print $6, $7, $8}')
QUEUE_TIME=$(ls -lth data/lake/ib_request_queue/ 2>/dev/null | head -2 | tail -1 | awk '{print $6, $7, $8}')
echo "   option_snapshots: $OPTION_TIME"
echo "   ib_request_queue: $QUEUE_TIME"
echo ""

# 5. Recent Activity
echo "📋 RECENT ACTIVITY:"
echo "   Pre-market tasks:"
grep -q "queue_option_contracts" /tmp/v6_pre_market.log 2>/dev/null && echo "   ✓ 8:00 AM - Queue contracts" || echo "   ✗ 8:00 AM task not found"
grep -q "load_enhanced_market_data" /tmp/v6_pre_market.log 2>/dev/null && echo "   ✓ 8:30 AM - Load market data" || echo "   ✗ 8:30 AM task not found"
echo ""

echo "╔════════════════════════════════════════════════════════╗"
echo "║  CHECK COMPLETE - Review results above                 ║"
echo "╚════════════════════════════════════════════════════════╝"
```

---

## 📚 ADDITIONAL RESOURCES

### Key Files to Read
- `CLAUDE.md` - Project overview and critical rules
- `SCHEDULER_GUIDE.md` - Detailed scheduler documentation
- `crontab.txt` - Complete cron schedule reference
- `UNIFIED_SCHEDULER_GUIDE.md` - Scheduler architecture

### Log File Locations
- `logs/scheduler_cron.log` - Main scheduler log
- `logs/scheduler/scheduler.log` - Detailed scheduler activity
- `/tmp/v6_pre_market.log` - Pre-market tasks (8:00, 8:30, 8:45)
- `/tmp/v6_validation.log` - IB validation (8:45)
- `/tmp/v6_935_et.log` - 9:35 option selection
- `/tmp/v6_intraday.log` - Every 5-min data collection (9:30-16:00)
- `/tmp/v6_health.log` - Health checks (every 15 min)

### Python Environment
- **Interpreter:** `/home/bigballs/miniconda3/envs/ib/bin/python`
- **Working Directory:** `/home/bigballs/project/bot/v6/`
- **PYTHONPATH:** `/home/bigballs/project/bot/v6/src`

---

## 🎯 SUCCESS CRITERIA

**System is ready for trading if:**

- ✅ Scheduler process is running
- ✅ IB connection shows "OK"
- ✅ `option_snapshots` updated within last 10 minutes (after 9:30 AM)
- ✅ `ib_request_queue` updated today (after 9:35 AM)
- ✅ No critical errors in logs
- ✅ System resources OK (disk < 80%, memory available)

**If any criteria fail:**
1. Check corresponding section above for solutions
2. Run manual commands if needed
3. Escalate if unresolved

---

**END OF CHECKLIST**
