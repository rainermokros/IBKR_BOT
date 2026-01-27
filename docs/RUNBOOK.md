# V6 Trading Bot - Runbook

This runbook provides operational procedures for daily tasks, common incidents, and emergency response.

## Table of Contents

- [Daily Operations](#daily-operations)
- [Common Incidents](#common-incidents)
- [Emergency Procedures](#emergency-procedures)
- [Maintenance Tasks](#maintenance-tasks)

---

## Daily Operations

### Morning Checklist (Before Market Open)

**Time:** 30 minutes before market open (8:30 AM ET)

1. **Check IB Gateway:**
   ```bash
   # Verify IB Gateway is running and logged in
   pgrep -f ibgateway
   systemctl status ib-gateway
   ```
   - If not running: Start IB Gateway and log in
   - Verify: Account balance, buying power

2. **Check System Status:**
   ```bash
   # Check all services
   ./scripts/status.sh

   # Or individual services
   systemctl status v6-trading v6-dashboard v6-position-sync
   ```
   - Verify: All services are active (running)
   - Check: No errors in recent logs

3. **Review Dashboard:**
   - Open: http://localhost:8501
   - Check: Positions page (verify all positions synced)
   - Check: Portfolio Greeks (verify risk exposure)
   - Check: Alerts page (acknowledge any alerts)
   - Check: System Health (verify IB connected, data fresh)

4. **Check Health Status:**
   ```bash
   # Run health check
   ./scripts/health_check.py
   echo $?  # Should be 0 (healthy)
   ```

5. **Verify Risk Limits:**
   - Check: Portfolio delta within limits (±200)
   - Check: Portfolio gamma within limits (±500)
   - Check: No single symbol concentration >30%

6. **Review Logs:**
   ```bash
   # Check for errors since yesterday
   journalctl -u v6-trading --since "24 hours ago" -p err
   ```

### End-of-Day Checklist (After Market Close)

**Time:** 30 minutes after market close (4:30 PM ET)

1. **Verify All Positions Synced:**
   ```bash
   # Check position sync lag
   curl http://localhost:8501/api/health
   ```
   - Verify: Position sync lag < 5 minutes
   - Dashboard: Positions page matches IB account

2. **Run Health Check:**
   ```bash
   ./scripts/health_check.py
   ```

3. **Backup Data:**
   ```bash
   # Manual backup (optional, automatic backup should run)
   ./scripts/backup.sh
   ```

4. **Review Day's Performance:**
   - Dashboard: Portfolio P&L
   - Dashboard: Greeks chart
   - Check: Any trades executed today
   - Check: Any alerts triggered

5. **Check Logs:**
   ```bash
   # Review logs for today
   journalctl -u v6-trading --since "today" | less
   ```

6. **Plan for Tomorrow:**
   - Check: Any positions near exit triggers
   - Check: Market conditions for tomorrow
   - Review: Strategy parameters if needed

### Weekly Tasks

**Day:** Friday afternoon or weekend

1. **Review Performance:**
   - Dashboard: Weekly P&L
   - Dashboard: Greeks trends
   - Analyze: Winning vs losing trades

2. **Check Logs:**
   ```bash
   # Check for warnings/errors
   journalctl -u v6-trading --since "7 days ago" -p warning
   ```

3. **Verify Backups:**
   ```bash
   # List backups
   ls -lh backups/
   ```
   - Verify: Backups created for last 7 days
   - Test: Restore from latest backup (dry-run)

4. **Update Strategies (if needed):**
   - Review: Strategy performance
   - Adjust: Decision engine parameters
   - Test: New strategies in paper trading

5. **System Maintenance:**
   - Check: Disk space (should be < 90%)
   - Check: Memory usage (should be < 90%)
   - Update: System packages if security updates

---

## Common Incidents

### 1. IB Gateway Disconnected

**Symptoms:**
- Dashboard shows: IB Connection: Disconnected
- Logs show: "IB connection lost" or "Connection timeout"
- Health check: IB connection failed

**Diagnosis:**
```bash
# Check IB Gateway process
pgrep -f ibgateway

# Check IB Gateway logs
tail -f /home/trading/Jts/ibgateway.log

# Check IB Gateway service
systemctl status ib-gateway
```

**Resolution:**
1. Restart IB Gateway:
   ```bash
   systemctl restart ib-gateway
   ```

2. If IB Gateway won't start:
   - Check: IB Gateway installation
   - Check: Network connectivity
   - Verify: IB credentials (login to IB account portal)

3. Verify IB Gateway is logged in:
   - Open IB Gateway GUI
   - Verify: Account shows as "logged in"

4. Restart V6 services:
   ```bash
   systemctl restart v6-trading v6-position-sync
   ```

**Prevention:**
- IB Gateway auto-restart: `systemctl enable ib-gateway`
- IB connection auto-reconnect: Built into orchestrator

---

### 2. Position Sync Lagged

**Symptoms:**
- Dashboard shows: Position sync lag > 5 minutes
- Health check: Position sync degraded
- Delta Lake positions don't match IB

**Diagnosis:**
```bash
# Check position sync service
systemctl status v6-position-sync

# Check last sync time
./scripts/health_check.py

# Check logs
journalctl -u v6-position-sync -n 50
```

**Resolution:**
1. Restart position sync service:
   ```bash
   systemctl restart v6-position-sync
   ```

2. Force manual sync:
   ```bash
   # Via dashboard: Click "Force Sync" button
   # Or via script (if available)
   ```

3. Check for IB rate limits:
   - IB API rate limit: 50 requests/second
   - Solution: Wait for rate limit to reset (1-2 minutes)

4. Verify IB connection:
   ```bash
   systemctl status v6-trading
   ```

**Prevention:**
- Position sync auto-restart: Configured in systemd
- Rate limit handling: Built into position streamer

---

### 3. Order Rejected

**Symptoms:**
- Dashboard alerts: "Order rejected"
- Logs show: "Order rejected by IB"
- Position not opened/closed as expected

**Diagnosis:**
```bash
# Check order rejection reason
journalctl -u v6-trading --since "1 hour ago" | grep -i reject

# Check IB account
# Via TWS or Account Management: Verify buying power, margin
```

**Common Reasons:**
1. **Insufficient buying power:**
   - Check: Account balance
   - Solution: Add funds or reduce position size

2. **Outside market hours:**
   - Check: Market is open
   - Solution: Wait for market open

3. **Incorrect order parameters:**
   - Check: Strike, expiry, symbol
   - Solution: Verify strategy parameters

4. **Risk limit exceeded:**
   - Check: Portfolio limits
   - Solution: Reduce exposure or adjust limits

**Resolution:**
1. Identify rejection reason from logs
2. Fix underlying issue
3. Retry order if appropriate

**Prevention:**
- Order validation: Built into order execution engine
- Risk checks: Pre-trade risk limits enforced

---

### 4. Circuit Breaker Triggered

**Symptoms:**
- Dashboard shows: Trading halted
- Logs show: "Circuit breaker tripped"
- No new orders executing

**Diagnosis:**
```bash
# Check circuit breaker status
journalctl -u v6-trading --since "1 hour ago" | grep -i circuit

# Check for failures
journalctl -u v6-trading -p err -n 50
```

**Resolution:**
1. Identify root cause:
   - IB connection failures
   - Order rejections
   - System errors

2. Fix root cause:
   - Reconnect IB: `systemctl restart v6-trading`
   - Fix error: Check logs for error details

3. Reset circuit breaker:
   - Wait for cooldown (60 seconds)
   - Or restart service: `systemctl restart v6-trading`

**Prevention:**
- Circuit breaker: Prevents retry storms during outages
- Auto-recovery: Orchestrator attempts auto-recovery

---

### 5. Dashboard Down

**Symptoms:**
- http://localhost:8501 not accessible
- Dashboard service not running

**Diagnosis:**
```bash
# Check dashboard service
systemctl status v6-dashboard

# Check port availability
lsof -i :8501

# Check logs
journalctl -u v6-dashboard -n 50
```

**Resolution:**
1. Restart dashboard service:
   ```bash
   systemctl restart v6-dashboard
   ```

2. Check port conflict:
   ```bash
   # Kill process using port 8501
   lsof -ti :8501 | xargs kill -9
   systemctl restart v6-dashboard
   ```

3. Check dependencies:
   ```bash
   # Verify Python dependencies installed
   cd /opt/v6-trading
   uv sync
   ```

**Prevention:**
- Dashboard auto-restart: Configured in systemd
- Monitor: Health check includes dashboard accessibility

---

## Emergency Procedures

### 1. Emergency Shutdown

**When to use:** Critical system failure, runaway trading, data corruption

**Steps:**

1. **Stop trading immediately:**
   ```bash
   # Stop trading service (graceful shutdown)
   systemctl stop v6-trading
   ```

2. **Stop position sync:**
   ```bash
   systemctl stop v6-position-sync
   ```

3. **Stop dashboard (optional):**
   ```bash
   systemctl stop v6-dashboard
   ```

4. **Verify all services stopped:**
   ```bash
   systemctl status v6-trading v6-position-sync v6-dashboard
   ```

5. **Review positions:**
   - Check IB account via TWS
   - Verify: All positions accounted for
   - Decide: Close positions manually if needed

6. **Collect logs for analysis:**
   ```bash
   # Save logs
   journalctl -u v6-trading --since "24 hours ago" > emergency_logs.txt
   ```

---

### 2. Manual Position Closure

**When to use:** System unable to close positions automatically, emergency exit

**Steps:**

1. **Stop trading:**
   ```bash
   systemctl stop v6-trading
   ```

2. **List open positions:**
   ```bash
   # Via dashboard: Positions page
   # Or via IB: TWS → Account → Portfolio
   ```

3. **Close positions via TWS:**
   - Open TWS
   - Navigate to: Account → Portfolio
   - Right-click position → Close Position
   - Verify: Order filled

4. **Update Delta Lake:**
   ```bash
   # Force position sync after manual closure
   systemctl start v6-position-sync
   # Or click "Force Sync" on dashboard
   ```

5. **Verify:**
   - Dashboard: Positions page shows no positions
   - IB Account: All positions closed

---

### 3. Restore from Backup

**When to use:** Data corruption, accidental deletion, disaster recovery

**Steps:**

1. **Stop all services:**
   ```bash
   systemctl stop v6-trading v6-position-sync v6-dashboard
   ```

2. **Identify backup to restore:**
   ```bash
   # List backups
   ls -lh backups/

   # Choose backup (e.g., backup_20260127_160000.tar.gz)
   ```

3. **Restore backup:**
   ```bash
   # Extract backup
   tar -xzf backups/backup_20260127_160000.tar.gz -C /tmp/

   # Restore Delta Lake tables
   cp -r /tmp/backup/data/lake/* data/lake/
   ```

4. **Reconcile with IB:**
   ```bash
   # Start position sync to reconcile with IB
   systemctl start v6-position-sync

   # Verify reconciliation
   # Dashboard → Positions page should match IB
   ```

5. **Start services:**
   ```bash
   systemctl start v6-trading v6-dashboard
   ```

6. **Verify:**
   ```bash
   ./scripts/health_check.py
   ./scripts/status.sh
   ```

**See Also:** `docs/BACKUP_RESTORE.md` for detailed backup/restore procedures

---

### 4. Contact Support

**When to use:** Critical issues beyond your expertise, IB API issues

**Information to Collect:**

1. **System status:**
   ```bash
   ./scripts/status.sh > status_report.txt
   ```

2. **Logs:**
   ```bash
   journalctl -u v6-trading --since "24 hours ago" > logs.txt
   ```

3. **Health check:**
   ```bash
   ./scripts/health_check.py > health_check.txt
   ```

4. **Screenshots:**
   - Dashboard error pages
   - IB Gateway status
   - Any error messages

**Contacts:**
- IB API Support: https://www.interactivebrokers.com/en/api.php
- IB Customer Service: Call IB support line
- System Developer: Contact system maintainer

---

## Maintenance Tasks

### Log Rotation

Logs are automatically rotated by systemd and loguru:

- **Systemd logs:** Rotated by journald (auto-cleanup after 7 days)
- **Application logs:** Rotated by loguru (100MB per file, 10 backups)

To manually clean old logs:
```bash
# Clean logs older than 30 days
journalctl --vacuum-time=30d
```

### Backup Cleanup

Backups are retained for 30 days by default. To manually clean:

```bash
# Remove backups older than 30 days
find backups/ -name "backup_*.tar.gz" -mtime +30 -delete
```

### System Updates

**Before updating:**
1. Stop services: `systemctl stop v6-trading v6-dashboard v6-position-sync`
2. Backup data: `./scripts/backup.sh`

**Update system:**
```bash
# Update Python dependencies
cd /opt/v6-trading
uv sync

# Or using pip
pip install --upgrade -e .
```

**After updating:**
1. Start services: `systemctl start v6-trading v6-dashboard v6-position-sync`
2. Verify health: `./scripts/health_check.py`

---

## Appendix

### Useful Commands

```bash
# Service management
systemctl start v6-trading              # Start trading service
systemctl stop v6-trading               # Stop trading service
systemctl restart v6-trading            # Restart trading service
systemctl status v6-trading             # Check service status

# Log viewing
journalctl -u v6-trading -f             # Follow logs in real-time
journalctl -u v6-trading -n 100         # Show last 100 log lines
journalctl -u v6-trading --since "1 hour ago"  # Show recent logs

# Health checks
./scripts/health_check.py               # Run health check
./scripts/status.sh                     # Show system status

# Position sync
systemctl restart v6-position-sync      # Restart position sync

# Dashboard
systemctl restart v6-dashboard          # Restart dashboard
```

### File Locations

- **Config:** `/opt/v6-trading/config/`
- **Logs:** `/opt/v6-trading/logs/`
- **Backups:** `/opt/v6-trading/backups/`
- **Delta Lake:** `/opt/v6-trading/data/lake/`
- **Systemd services:** `/etc/systemd/system/v6-*.service`

### Service Dependencies

```
ib-gateway.service (IB Gateway)
    ↓
v6-trading.service (Main trading system)
    ↓
v6-position-sync.service (Position synchronization)
    ↓
v6-dashboard.service (Monitoring dashboard)
```

### Escalation Path

1. **First:** Check logs and diagnose issue
2. **Second:** Follow runbook procedures
3. **Third:** Contact system developer
4. **Last:** Contact IB support for IB API issues

---

**Last updated:** 2026-01-27
