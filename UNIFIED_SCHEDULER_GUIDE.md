# Unified Scheduler Setup Guide

## 🎯 ONE Crontab Entry to Rule Them All!

Instead of 10+ separate cron jobs, you now have **ONE master scheduler** that:
- Checks NYSE trading calendar
- Only runs on trading days
- Only runs during market hours
- Manages all data collection tasks
- Handles dependencies automatically

---

## 📝 Crontab Entry

### Add This Single Line to Crontab:

```bash
# Edit crontab
crontab -e

# Add this line (runs every minute during market hours)
* * * * * cd /home/bigballs/project/bot/v6 && python -m src.v6.scheduler.unified_scheduler >> /home/bigballs/project/bot/v6/logs/scheduler_cron.log 2>&1
```

### That's It!

**ONE line replaces all these:**
- ❌ Option data collection cron
- ❌ Futures data collection cron
- ❌ Derived statistics cron
- ❌ Historical data loader cron
- ❌ Pre-market tasks
- ❌ Post-market tasks
- ❌ Market hours tasks

---

## 📅 What the Scheduler Does

### Pre-Market (8:30-9:30 AM ET)
- ✅ Load historical market data (SPY, QQQ, IWM OHLCV bars)
- ✅ Load futures data (ES, NQ, RTY from IB)
- ✅ Calculate derived statistics (from yesterday's data)

### Market Open (9:30 AM - 4:00 PM ET)
- ✅ Every 5 minutes: Collect option snapshots (via paper trader)
- ✅ Every 5 minutes: Collect futures snapshots
- ✅ Every 30 minutes: Update derived statistics

### Post-Market (4:00-6:00 PM ET)
- ✅ Calculate final daily statistics
- ✅ Load any missing data
- ✅ Generate end-of-day reports

### After 6:00 PM ET
- ✅ Sleep until next trading day
- ✅ Check every minute for market open

### Weekends & Holidays
- ✅ Do nothing (NYSE calendar aware)
- ✅ Skip all weekends
- ✅ Skip all holidays

---

## 🗓️ NYSE Trading Calendar

The scheduler uses the NYSE calendar to determine:
- Trading days (excludes weekends)
- Trading hours
- Holidays 2026:
  - New Year's Day: January 1
  - MLK Day: January 19
  - Washington's Birthday: February 16
  - Good Friday: April 10
  - Memorial Day: May 25
  - Juneteenth: June 19
  - Independence Day: July 3 (observed)
  - Labor Day: September 7
  - Thanksgiving: November 26
  - Christmas: December 25

---

## ⚙️ Configuration

### Scheduler Configuration

All tasks configured in `src/v6/scheduler/unified_scheduler.py`:

```python
# Task configurations
tasks = {
    "load_historical_data": {
        "interval_minutes": None,  # Run once per day
        "run_phase": "pre_market",
    },
    "calculate_statistics": {
        "interval_minutes": None,  # Run once per day
        "run_phase": "post_market",
    },
    "load_futures_data": {
        "interval_minutes": None,  # Run once per day
        "run_phase": "pre_market",
    },
    "collect_option_data": {
        "interval_minutes": 5,  # Every 5 minutes
        "run_phase": "market_open",
    },
    "collect_futures_data": {
        "interval_minutes": 5,  # Every 5 minutes
        "run_phase": "market_open",
    },
}
```

---

## 📊 Tasks Managed

### 1. Load Historical Data
**Script:** `src/v6/scripts/load_historical_data.py`
**Schedule:** Once per day (pre-market, 8:30 AM ET)
**Data:** SPY, QQQ, IWM OHLCV bars
**Frequency:** Daily
**Source:** Yahoo Finance (free, no IB needed)

### 2. Calculate Derived Statistics
**Script:** `src/v6/scripts/derive_statistics.py`
**Schedule:** Once per day (post-market, 4:30 PM ET)
**Data:** 27 derived statistics
**Source:** Calculated from option snapshots

### 3. Load Futures Data
**Script:** `src/v6/scripts/load_futures_data.py`
**Schedule:** Once per day (pre-market, 8:35 AM ET)
**Data:** ES, NQ, RTY futures
**Source:** IB Gateway (if available)

### 4. Collect Option Data
**Script:** Handled by paper trading system
**Schedule:** Every 5 minutes (9:30 AM - 4:00 PM ET)
**Data:** Option chains for SPY, QQQ, IWM
**Source:** IB Gateway

### 5. Collect Futures Data
**Script:** Handled by futures system
**Schedule:** Every 5 minutes (9:30 AM - 4:00 PM ET)
**Data:** ES, NQ, RTY snapshots
**Source:** IB Gateway

---

## 🔍 Monitoring

### View Scheduler Logs

```bash
# View real-time logs
tail -f logs/scheduler/unified_scheduler.log

# View cron output
tail -f logs/scheduler/scheduler_cron.log
```

### Check What Ran

```bash
# Check scheduler status
python -c "
from src.v6.scheduler.nyse_calendar import NYSECalendar
from datetime import datetime

cal = NYSECalendar()
print(f'Trading day: {cal.is_trading_day()}')
print(f'Market phase: {cal.get_market_phase()}')
print(f'Market open: {cal.is_market_open()}')
print(f'Pre-market: {cal.is_pre_market()}')
print(f'Post-market: {cal.is_post_market()}')
"
```

---

## 🚀 Setup Instructions

### Step 1: Create the Crontab Entry

```bash
# Edit crontab
crontab -e

# Add this single line
* * * * * cd /home/bigballs/project/bot/v6 && python -m src.v6.scheduler.unified_scheduler >> /home/bigballs/project/bot/v6/logs/scheduler_cron.log 2>&1

# Save and exit
```

### Step 2: Verify Crontab

```bash
# List crontabs
crontab -l

# You should see one line like:
# * * * * * cd /home/bigballs/project/bot/v6 && python -m src.v6.scheduler.unified_scheduler ...
```

### Step 3: Test Scheduler (Optional)

```bash
# Run manually to test
python -m src.v6.scheduler.unified_scheduler

# Check logs
tail -f logs/scheduler/unified_scheduler.log
```

### Step 4: Monitor on First Day

```bash
# Watch logs
tail -f logs/scheduler/unified_scheduler.log

# In another terminal, check Delta Lake tables
python -c "
from src.v6.data.market_bars import MarketBarsTable
from src.v6.data.derived_statistics import DerivedStatisticsTable

market_table = MarketBarsTable()
stats_table = DerivedStatisticsTable()

import polars as pl

market_df = pl.from_pandas(market_table.get_table().to_pandas())
stats_df = pl.from_pandas(stats_table.get_table().to_pandas())

print(f'Market Bars: {len(market_df)} rows')
print(f'Derived Stats: {len(stats_df)} rows')
"
```

---

## 📊 Scheduler Output Examples

### Pre-Market Run (8:35 AM ET)

```
======================================================================
UNIFIED SCHEDULER CHECK - 2026-01-28 08:35:00
======================================================================
Day: 2026-01-28 (Trading: True)
Time: 08:35:00 (Phase: pre_market)
----------------------------------------------------------------------
→ Loading historical market data (SPY, QQQ, IWM)...
  ✓ Loaded 15 bars
→ Calculating derived statistics...
  ✓ Saved 3 statistics records
→ Loading futures data...
  ✓ Loaded 3 futures snapshots
✓ Ran 3 tasks
```

### During Market Hours (10:00 AM ET)

```
======================================================================
UNIFIED SCHEDULER CHECK - 2026-01-28 10:00:00
======================================================================
Day: 2026-01-28 (Trading: True)
Time: 10:00:00 (Phase: market_open)
----------------------------------------------------------------------
→ Collecting option data...
  ✓ Paper trader is running (collecting options)
→ Collecting futures data...
  ✓ Futures collection handled separately
✓ Ran 2 tasks
```

### Post-Market (4:30 PM ET)

```
======================================================================
UNIFIED SCHEDULER CHECK - 2026-01-28 16:30:00
======================================================================
Day: 2026-01-28 (Trading: True)
Time: 16:30:00 (Phase: post_market)
----------------------------------------------------------------------
→ Calculating derived statistics...
  ✓ Saved 3 statistics records
✓ Ran 1 task
```

### Weekend (Saturday)

```
======================================================================
UNIFIED SCHEDULER CHECK - 2026-01-31 10:00:00
======================================================================
Day: 2026-01-31 (Trading: False)
Time: 10:00:00 (Phase: closed)
----------------------------------------------------------------------
Not a trading day - sleeping...
```

---

## 🔧 Troubleshooting

### Problem: Scheduler not running

**Solution:**
1. Check crontab: `crontab -l`
2. Check logs: `tail -f logs/scheduler/scheduler_cron.log`
3. Test manually: `python -m src.v6.scheduler.unified_scheduler`

### Problem: Tasks not running

**Solution:**
1. Check scheduler log: `tail -f logs/scheduler/unified_scheduler.log`
2. Check if it's a trading day: `python -c "from src.v6.scheduler.nyse_calendar import NYSECalendar; print(NYSECalendar().is_trading_day())"`
3. Check current phase: `python -c "from src.v6.scheduler.nyse_calendar import NYSECalendar; print(NYSECalendar().get_market_phase())"`

### Problem: Data not loading

**Solution:**
1. Check individual scripts: `python -m src.v6.scripts.load_historical_data`
2. Check table permissions: `ls -la data/lake/`
3. Check error logs for specific script

---

## 📝 Before (Multiple Cron Jobs)

**What you DON'T need anymore:**
```cron
# Option data collection
*/5 9-16 * * 1-5 python -m src.v6.scripts.collect_options

# Calculate statistics
0 18 * * 1-5 python -m src.v6.scripts.derive_statistics

# Futures data
*/5 9-16 * * 1-5 python -m src.v6.scripts.load_futures_data

# Historical data
0 8 * * 1-5 python -m src.v6.scripts.load_historical_data

# Plus 6+ more entries...
```

---

## 🎉 After (One Cron Job)

**What you have NOW:**
```cron
# Single entry
* * * * * cd /home/bigballs/project/bot/v6 && python -m src.v6.scheduler.unified_scheduler >> /home/bigballs/project/bot/v6/logs/scheduler_cron.log 2>&1
```

**That's it!**

---

## 📊 Benefits

### Before (Multiple Cron Jobs)
- ❌ 10+ separate entries
- ❌ Complex timing management
- ❌ No dependency handling
- ❌ Runs on weekends/holidays
- ❌ Hard to debug
- ❌ Easy to forget tasks

### After (Unified Scheduler)
- ✅ ONE crontab entry
- ✅ NYSE calendar aware
- ✅ Market hours aware
- ✅ Dependency management
- ✅ Comprehensive logging
- ✅ Single point of failure
- ✅ Easy to monitor

---

## 📈 Task Schedule Summary

| Time | Task | Frequency |
|------|------|----------|
| 8:30 AM | Load historical data | Daily |
| 8:35 AM | Load futures data | Daily |
| 9:30 AM - 4:00 PM | Collect option data | Every 5 min |
| 9:30 AM - 4:00 PM | Collect futures data | Every 5 min |
| 4:30 PM | Calculate statistics | Daily |
| After 6 PM | Sleep | Until next trading day |

---

## ✅ Summary

**Crontab Entries:**
- **Before:** 10+ entries
- **After:** 1 entry

**Calendar:**
- **Before:** Runs every day (including weekends)
- **After:** NYSE calendar aware (trading days only)

**Timing:**
- **Before:** Fixed times regardless of market hours
- **After:** Market hours aware (pre-market, market open, post-market)

**Management:**
- **Before:** Manual timing, no dependencies
- **After:** Automatic dependency handling

**Status:** Ready to deploy! 🚀

---

**Created:** January 28, 2026
**Status:** Production Ready ✓
**Crontab:** 1 line vs 10+ lines ✓
**NYSE Calendar:** Trading days & holidays ✓
**Logging:** Comprehensive ✓
