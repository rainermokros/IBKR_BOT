# ET-Based Scheduler Implementation Guide

## Overview

The V6 Trading System now uses an **ET-based cron scheduler** with full NYSE holiday awareness. This replaces continuous Python processes with efficient cron-based scheduling.

### Key Features

✅ **NYSE Holiday Aware** - Automatically skips execution on holidays
✅ **ET Timezone** - All times in Eastern Time (NYSE timezone)
✅ **Dashboard Configuration** - Web UI for managing schedules
✅ **Cron-Friendly Scripts** - Single-execution, no infinite loops
✅ **Comprehensive Logging** - Detailed execution logs with timestamps
✅ **Holiday Mode** - Force-run option for maintenance tasks

---

## Architecture

### Components

1. **cron_wrapper.sh** - Holiday-aware bash wrapper for all cron jobs
2. **scheduler_config.py** - Python configuration system with task definitions
3. **Cron Jobs** - Individual scheduled tasks in `/etc/cron.d/v6-trading`
4. **Dashboard Page** - Web UI at http://localhost:8501/?page=8⏰+Scheduler
5. **NYSE Calendar** - Holiday calculations for 2026

### Data Flow

```
Cron Trigger → cron_wrapper.sh → NYSE Check → Script Execution → Logging → Delta Lake
                       ↓
                 Holiday? → Skip
```

---

## Installation

### Quick Install

```bash
cd /home/bigballs/project/bot/v6

# Run installation script
sudo ./scripts/install_scheduler.sh
```

### Manual Install

```bash
# 1. Copy crontab file
sudo cp crontab.txt /etc/cron.d/v6-trading

# 2. Set permissions
sudo chmod 644 /etc/cron.d/v6-trading

# 3. Make scripts executable
chmod +x scripts/cron_wrapper.sh
find scripts -name "*.py" -exec chmod +x {} \;

# 4. Restart cron
sudo service cron restart
```

### Verify Installation

```bash
# View cron jobs
cat /etc/cron.d/v6-trading

# Check if cron is running
sudo service cron status

# Test cron wrapper
./scripts/cron_wrapper.sh scripts/health_check.py
```

---

## Schedule List

### Pre-Market Tasks (Before 9:30 AM ET)

| Time | Script | Purpose | Runtime |
|------|--------|---------|----------|
| 8:00 AM ET | `queue_option_contracts.py` | Queue all contracts >20 DTE | 5-10 min |
| 8:30 AM ET | `load_enhanced_market_data.py` | Fetch overnight data | 5-10 min |
| 8:45 AM ET | `validate_ib_connection.py` | Verify IB Gateway ready | 1 min |
| 9:35 AM ET | `schedule_935_et.py` | Queue contracts for trading | 5 min |

### During Market Hours (9:30 AM - 4:00 PM ET)

| Frequency | Script | Purpose | Runtime |
|-----------|--------|---------|----------|
| Every 5 min | `collect_option_snapshots.py` | Collect option chains (258) | 1 min |
| Every 5 min | `collect_futures_snapshots.py` | Collect ES/NQ/RTY data | 30 sec |
| Hourly | `calculate_intraday_statistics.py` | Update statistics | 2 min |

### Post-Market Tasks (After 4:00 PM ET)

| Time | Script | Purpose | Runtime |
|------|--------|---------|----------|
| 4:15 PM ET | `final_data_collection.py` | Final market snapshot | 5 min |
| 6:00 PM ET | `calculate_daily_statistics.py` | End-of-day statistics | 5 min |
| 6:30 PM ET | `validate_data_quality.py` | Data quality checks | 2 min |

### Weekly Tasks

| Day/Time | Script | Purpose | Runtime |
|----------|--------|---------|----------|
| Saturday 10 AM | `load_historical_data.py` | Fill missing data | 10-20 min |
| Saturday 11 AM | `audit_data_integrity.py` | Weekly audit | 5 min |
| Sunday 8 AM | `cleanup_old_data.py` | Remove stale data | 2 min |

### Monitoring Tasks

| Frequency | Script | Purpose | Runtime |
|-----------|--------|---------|----------|
| Every 15 min | `health_check.py` | System health | 1 min |
| Every hour | `validate_positions.py` | Position reconciliation | 1 min |

---

## Dashboard Management

### Access Scheduler Dashboard

1. Open browser: http://localhost:8501
2. Click "⏰ Scheduler" in sidebar
3. View and manage all scheduled tasks

### Dashboard Features

#### 📅 Schedule Tab

- **NYSE Calendar** - View trading day status and upcoming holidays
- **Task List** - Show all scheduled tasks with status
- **Enable/Disable** - Toggle tasks on/off
- **Run Now** - Manually trigger any task
- **Edit** - Modify task settings (timeout, retries)

#### ➕ Add Task Tab

- Create new scheduled tasks
- Configure frequency, timing, market phase
- Set execution parameters

#### 📜 Logs Tab

- View execution logs from all tasks
- Filter by log level (INFO, WARNING, ERROR)
- Select specific log files
- Real-time log streaming

#### ⚙️ Settings Tab

- Global holiday check toggle
- Logging enable/disable
- Timezone configuration

---

## Configuration Files

### config/production.yaml

```yaml
scheduler:
  timezone: "America/New_York"
  log_directory: "logs/scheduler"
  enable_holiday_check: true
  enable_logging: true

  tasks:
    collect_option_snapshots:
      enabled: true
      frequency: "5min"
      market_phase: "market_open"
      timeout_seconds: 300
```

### .env Overrides

```bash
# Disable all tasks
SCHEDULER_ENABLE_ALL=false

# Enable specific task
SCHEDULER_COLLECT_OPTION_SNAPSHOTS_ENABLED=true

# Force run on holidays
SCHEDULER_FORCE_RUN=true
```

---

## Script Development

### Creating Cron-Friendly Scripts

**Requirements:**
1. Single execution (no infinite loops)
2. Accept command-line arguments
3. Return proper exit codes:
   - 0: Success
   - 1: Recoverable error (will retry)
   - 2: Fatal error (do not retry)
4. Use ET timestamps in logs

**Template:**

```python
#!/usr/bin/env python
"""
Script Description

Cron-friendly script for V6 trading system.

Usage:
    python scripts/myscript.py [--arg value]

Exit codes:
    0: Success
    1: Recoverable error
    2: Fatal error
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

def parse_args():
    parser = argparse.ArgumentParser(description="...")
    parser.add_argument("--arg", type=str, default="value")
    return parser.parse_args()

def main():
    args = parse_args()

    logger.info(f"Starting at {datetime.now()}")

    try:
        # Your script logic here
        logger.info("✓ Success")
        return 0
    except Exception as e:
        logger.error(f"✗ Failed: {e}")
        return 2

if __name__ == "__main__":
    sys.exit(main())
```

---

## Holiday Handling

### NYSE Holidays 2026

Automatically skipped by scheduler:
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

### Holiday Mode

**Auto Mode (Default):**
```bash
# Script skips execution on holidays
./scripts/cron_wrapper.sh scripts/health_check.py
```

**Force Run Mode:**
```bash
# Execute even on holidays (for maintenance)
FORCE_RUN=true ./scripts/cron_wrapper.sh scripts/health_check.py
```

**Cron with Force Run:**
```cron
# Force run weekly audit even on holidays
0 10 * * 6 bigballs cd /home/bigballs/project/bot/v6 && FORCE_RUN=true /home/bigballs/project/bot/v6/scripts/cron_wrapper.sh scripts/audit_data_integrity.py >> /tmp/v6_audit.log 2>&1
```

---

## Troubleshooting

### Logs Not Appearing

```bash
# Check if script executed
grep "script_name" /tmp/v6_*.log

# Check cron service
sudo service cron status

# Check system cron logs
sudo tail -f /var/log/syslog | grep CRON
```

### Script Not Running

```bash
# Test script manually
cd /home/bigballs/project/bot/v6
python scripts/health_check.py

# Test with cron wrapper
./scripts/cron_wrapper.sh scripts/health_check.py

# Check file permissions
ls -la scripts/*.py

# Verify Python interpreter
which python
```

### Holiday Check Issues

```bash
# Test NYSE calendar
python -c "
from v6.scheduler.nyse_calendar import NYSECalendar
cal = NYSECalendar()
print(f'Trading day: {cal.is_trading_day()}')
print(f'Market phase: {cal.get_market_phase()}')
"
```

### Dashboard Not Showing Tasks

```bash
# Check config file
cat config/production.yaml | grep -A 50 scheduler

# Reload dashboard
streamlit run src/v6/dashboard/app.py --server.port 8501
```

---

## Monitoring

### Log Files

```bash
# Scheduler logs
tail -f logs/scheduler/unified_scheduler.log
tail -f logs/scheduler/cron_wrapper.log

# Task execution logs
tail -f /tmp/v6_pre_market.log
tail -f /tmp/v6_intraday.log
tail -f /tmp/v6_post_market.log
tail -f /tmp/v6_health.log
```

### Cron Monitoring

```bash
# View active cron jobs
crontab -l

# Check system cron
cat /etc/cron.d/v6-trading

# Monitor cron execution
sudo tail -f /var/log/syslog | grep CRON
```

### Dashboard Monitoring

1. Open http://localhost:8501
2. Navigate to:
   - **System Health** (page 4) - Overall system status
   - **Scheduler** (page 8) - Task execution status
   - **Logs Tab** - Real-time log viewing

---

## Migration from Continuous Processes

### What Changed

**Before:**
- `run_production.py` - Continuous loop with `while True`
- Manual time checking in Python
- Process management with SystemD

**After:**
- Individual cron-friendly scripts
- Cron handles time scheduling
- NYSE calendar in bash wrapper
- Dashboard for configuration

### Migration Steps

1. **Stop old processes:**
   ```bash
   sudo systemctl stop v6-trading
   sudo systemctl disable v6-trading
   ```

2. **Install new scheduler:**
   ```bash
   sudo ./scripts/install_scheduler.sh
   ```

3. **Verify execution:**
   ```bash
   tail -f /tmp/v6_*.log
   ```

4. **Monitor via dashboard:**
   - Open http://localhost:8501
   - Check Scheduler page

---

## Best Practices

### 1. Use Cron Wrapper

Always use `cron_wrapper.sh` for holiday awareness:

```cron
# Good
*/5 * * * * /path/to/cron_wrapper.sh scripts/collect.py

# Bad (no holiday check)
*/5 * * * * python scripts/collect.py
```

### 2. Set Proper Timeouts

Prevent hung processes:

```python
# In crontab
timeout 300 python scripts/collect.py  # 5 minute timeout

# Or in script config
task.timeout_seconds = 300
```

### 3. Log Everything

Use structured logging:

```python
logger.info(f"Starting {task_name} at {datetime.now()}")
logger.info(f"Collected {count} records")
logger.info(f"Completed in {duration:.2f}s")
```

### 4. Return Exit Codes

Help cron decide on retries:

```python
return 0  # Success
return 1  # Recoverable error (network issue)
return 2  # Fatal error (config problem)
```

### 5. Test Before Scheduling

Verify scripts work manually:

```bash
# Dry run
python scripts/myscript.py --dry-run

# With timeout
timeout 60 python scripts/myscript.py

# With wrapper
./scripts/cron_wrapper.sh scripts/myscript.py
```

---

## Performance Impact

### Resource Usage

**Before (Continuous):**
- 2-3 Python processes running 24/7
- ~500 MB RAM constant usage
- CPU cycles for time checking loops

**After (Cron):**
- Processes only run when scheduled
- ~100 MB RAM average usage
- No idle CPU usage
- Better resource efficiency

### Disk Usage

- Logs: ~50 MB/day (with rotation)
- Delta Lake: ~1 GB/day option data
- Backups: Configurable

---

## Security

### File Permissions

```bash
# Cron files (read-only)
sudo chmod 644 /etc/cron.d/v6-trading

# Scripts (executable)
chmod 755 scripts/*.py
chmod +x scripts/cron_wrapper.sh

# Config (restricted)
chmod 600 config/production.yaml
chmod 600 .env
```

### IB Gateway Security

- Use paper trading for testing
- Validate connection before market open
- Monitor for unauthorized access
- Check logs for suspicious activity

---

## Uninstallation

### Remove Scheduler

```bash
# Remove cron file
sudo rm /etc/cron.d/v6-trading

# Restart cron
sudo service cron restart

# Verify removal
crontab -l  # Should be empty for v6 tasks
```

### Disable Specific Tasks

```bash
# Edit cron file
sudo nano /etc/cron.d/v6-trading

# Comment out unwanted lines with #
# 0 8 * * 1-5 bigballs ...
```

Or use dashboard:
1. Open Scheduler page
2. Find task
3. Click "Toggle" to disable

---

## Support and Documentation

### Getting Help

1. Check logs: `tail -f logs/scheduler/*.log`
2. Review this guide
3. Check dashboard: http://localhost:8501
4. Run health check: `python scripts/health_check.py`

### Related Documentation

- **Dashboard Guide:** See page 7 in dashboard
- **NYSE Calendar:** `src/v6/scheduler/nyse_calendar.py`
- **Configuration:** `config/production.yaml.example`
- **Environment Variables:** `.env.example`

---

## Changelog

### Version 1.0 (Current)

✅ ET-based scheduling
✅ NYSE holiday awareness
✅ Dashboard configuration UI
✅ Cron-friendly scripts
✅ Comprehensive logging
✅ Force-run mode for maintenance

### Planned Features

- [ ] Slack/Discord notifications for task failures
- [ ] Task dependency management
- [ ] Dynamic schedule adjustment
- [ ] Performance metrics dashboard
- [ ] Automatic retry with exponential backoff

---

## Quick Reference

### Essential Commands

```bash
# Install scheduler
sudo ./scripts/install_scheduler.sh

# View cron jobs
cat /etc/cron.d/v6-trading

# Monitor logs
tail -f /tmp/v6_intraday.log

# Test script
./scripts/cron_wrapper.sh scripts/health_check.py

# Check trading day
python -c "from v6.scheduler.nyse_calendar import NYSECalendar; print(NYSECalendar().is_trading_day())"

# Open dashboard
streamlit run src/v6/dashboard/app.py --server.port 8501
```

### File Locations

- **Cron config:** `/etc/cron.d/v6-trading`
- **Scheduler config:** `src/v6/config/scheduler_config.py`
- **Scripts:** `scripts/*.py`
- **Logs:** `logs/scheduler/` and `/tmp/v6_*.log`
- **Dashboard:** `src/v6/dashboard/pages/8_scheduler.py`

---

**End of Scheduler Guide**

For updates and improvements, see the project README or contact the development team.
