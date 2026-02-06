# ET-Based Scheduler - Installation Complete ✅

## Conda Environment Integration FIXED

All cron jobs now use the **"ib" conda environment** at:
```
/home/bigballs/miniconda3/envs/ib/bin/python
```

### What Changed

**Before (BROKEN):**
```cron
*/5 9-16 * * 1-5 bigballs cd /home/bigballs/project/bot/v6 && /home/bigballs/project/bot/v6/scripts/cron_wrapper.sh scripts/collect_option_snapshots.py >> /tmp/v6_intraday.log 2>&1
```

**After (FIXED):**
```cron
*/5 9-16 * * 1-5 bigballs cd /home/bigballs/project/bot/v6 && /home/bigballs/project/bot/v6/scripts/cron_wrapper.sh /home/bigballs/miniconda3/envs/ib/bin/python scripts/collect_option_snapshots.py >> /tmp/v6_intraday.log 2>&1
```

### How It Works

The `cron_wrapper.sh` now accepts two arguments:
1. **Python path** (first argument) - Full path to conda Python interpreter
2. **Script path** (second argument) - Script to execute

Example:
```bash
./scripts/cron_wrapper.sh /home/bigballs/miniconda3/envs/ib/bin/python scripts/health_check.py
```

## Installation Commands

### Quick Install

```bash
cd /home/bigballs/project/bot/v6

# 1. Test the setup
./scripts/test_scheduler.sh

# 2. Install to cron
sudo ./scripts/install_scheduler.sh

# 3. Verify installation
cat /etc/cron.d/v6-trading

# 4. Monitor logs
tail -f /tmp/v6_health.log
```

### Manual Install (Alternative)

```bash
# Copy crontab
sudo cp crontab.txt /etc/cron.d/v6-trading

# Set permissions
sudo chmod 644 /etc/cron.d/v6-trading

# Restart cron
sudo service cron restart
```

## Verification

### Test Individual Script

```bash
cd /home/bigballs/project/bot/v6

# Test with conda environment
./scripts/cron_wrapper.sh /home/bigballs/miniconda3/envs/ib/bin/python scripts/health_check.py
```

Expected output:
```
[INFO] Trading Day: True
[INFO] Market Hours: True
[INFO] Market Phase: market_open
[INFO] Python: /home/bigballs/miniconda3/envs/ib/bin/python
[INFO] Executing: scripts/health_check.py
```

### Check Cron Installation

```bash
# View all scheduled tasks
cat /etc/cron.d/v6-trading

# Check if cron is running
sudo service cron status

# Monitor cron execution
sudo tail -f /var/log/syslog | grep CRON
```

### Test with Cron Environment

Cron runs with minimal environment. To test exactly as cron would run:

```bash
# Simulate cron environment
env -i PATH=/usr/bin:/bin HOME=/home/bigballs USER=bigballs \
    /home/bigballs/project/bot/v6/scripts/cron_wrapper.sh \
    /home/bigballs/miniconda3/envs/ib/bin/python \
    scripts/health_check.py
```

## Schedule Overview

### Pre-Market (Before 9:30 AM ET)
- 8:00 AM - Queue option contracts (>20 DTE)
- 8:30 AM - Load overnight market data
- 8:45 AM - Verify IB Gateway
- 9:35 AM - Queue contracts for trading day

### Market Hours (9:30 AM - 4:00 PM ET)
- Every 5 min - Collect option snapshots (258 contracts)
- Every 5 min - Collect futures data (ES/NQ/RTY)
- Hourly - Update intraday statistics

### Post-Market (After 4:00 PM ET)
- 4:15 PM - Final market snapshot
- 6:00 PM - Calculate daily statistics
- 6:30 PM - Data quality validation

### Weekly
- Saturday 10 AM - Load historical data
- Saturday 11 AM - Audit data integrity
- Sunday 8 AM - Cleanup old data

### Monitoring
- Every 15 min - Health check
- Every hour - Position validation

## Dashboard Configuration

1. Start dashboard:
```bash
cd /home/bigballs/project/bot/v6
streamlit run src/v6/dashboard/app.py --server.port 8501
```

2. Open browser: http://localhost:8501

3. Click "⏰ Scheduler" in sidebar

4. Configure tasks:
   - Enable/disable individual tasks
   - Edit schedule times
   - View execution logs
   - Run tasks manually

## Troubleshooting

### Script Not Running

```bash
# Check if Python path is correct
ls -la /home/bigballs/miniconda3/envs/ib/bin/python

# Test wrapper manually
cd /home/bigballs/project/bot/v6
./scripts/cron_wrapper.sh /home/bigballs/miniconda3/envs/ib/bin/python scripts/health_check.py

# Check cron logs
tail -f /tmp/v6_health.log
```

### Import Errors

If you see "ModuleNotFoundError", ensure dependencies are installed in the "ib" environment:

```bash
conda activate ib
pip install -r requirements.txt  # or your install command
```

### Permission Denied

```bash
# Make scripts executable
chmod +x scripts/cron_wrapper.sh
find scripts -name "*.py" -exec chmod +x {} \;
```

### Cron Not Executing

```bash
# Check cron service
sudo service cron status

# Restart cron
sudo service cron restart

# View system cron logs
sudo tail -f /var/log/syslog | grep CRON
```

## File Locations

- **Cron config:** `/etc/cron.d/v6-trading`
- **Cron wrapper:** `scripts/cron_wrapper.sh`
- **Python interpreter:** `/home/bigballs/miniconda3/envs/ib/bin/python`
- **Scheduler config:** `src/v6/config/scheduler_config.py`
- **Dashboard:** `src/v6/dashboard/pages/8_scheduler.py`
- **Log files:** `logs/scheduler/` and `/tmp/v6_*.log`

## Uninstallation

```bash
# Remove cron file
sudo rm /etc/cron.d/v6-trading

# Restart cron
sudo service cron restart

# Verify
crontab -l | grep v6  # Should be empty
```

## Support

For issues:
1. Check logs: `tail -f /tmp/v6_*.log`
2. Review: `SCHEDULER_GUIDE.md`
3. Test: `./scripts/test_scheduler.sh`
4. Check dashboard: http://localhost:8501

---

**Status:** ✅ Ready to use with conda "ib" environment!
**Python:** 3.11.13
**Timezone:** America/New_York (ET)
**Holiday Awareness:** Enabled (NYSE 2026 calendar)
