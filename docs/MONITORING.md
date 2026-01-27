# Monitoring Guide

This guide covers monitoring the V6 trading system, including metrics, alerts, dashboard usage, and log analysis.

## Table of Contents

- [Metrics to Monitor](#metrics-to-monitor)
- [Alert Thresholds](#alert-thresholds)
- [Dashboard Usage](#dashboard-usage)
- [Log Analysis](#log-analysis)

---

## Metrics to Monitor

### Portfolio Metrics

#### 1. Portfolio Greeks

**Why:** Measure overall risk exposure

**Metrics:**
- **Delta:** Net directional exposure (target: ±200)
- **Gamma:** Rate of delta change (target: ±500)
- **Theta:** Time decay (should be positive, collecting premium)
- **Vega:** Volatility exposure (monitor for IV changes)
- **Rho:** Interest rate exposure (usually minor)

**Dashboard:** Portfolio page → Greeks heatmap

**Alert:** If delta/gamma exceed limits

#### 2. P&L (Profit and Loss)

**Why:** Track trading performance

**Metrics:**
- **Realized P&L:** Closed positions profit/loss
- **Unrealized P&L:** Open positions mark-to-market
- **Total P&L:** Realized + Unrealized
- **Daily P&L:** P&L change today
- **Max Drawdown:** Largest peak-to-trough decline

**Dashboard:** Portfolio page → P&L time series

**Alert:** If daily loss > $1000 or drawdown > 10%

#### 3. Position Count

**Why:** Monitor portfolio size and complexity

**Metrics:**
- **Total positions:** Number of open positions
- **By symbol:** Positions per symbol (watch for concentration)
- **By strategy:** Positions per strategy type

**Dashboard:** Positions page → Position count

**Alert:** If > 20 positions or single symbol > 30% of portfolio

### Trading Metrics

#### 4. Order Execution

**Why:** Ensure orders are executing correctly

**Metrics:**
- **Order success rate:** % of orders filled vs rejected
- **Order latency:** Time from signal to execution (target: < 5 seconds)
- **Order queue depth:** Number of pending orders

**Dashboard:** Alerts page → Order-related alerts

**Alert:** If order rejection rate > 10% or latency > 10 seconds

#### 5. Strategy Performance

**Why:** Evaluate which strategies are profitable

**Metrics:**
- **Win rate:** % of profitable trades per strategy
- **Average P&L per trade:** Per strategy
- **Hold time:** Average days in position

**Dashboard:** Portfolio page → Strategy breakdown

**Alert:** If strategy win rate < 40%

### System Metrics

#### 6. IB Connection

**Why:** Critical for trading operations

**Metrics:**
- **Connection status:** Connected/disconnected
- **Connection age:** Time since last reconnect
- **Heartbeat latency:** Time to receive response from IB

**Dashboard:** Health page → IB Connection Status

**Alert:** If disconnected or heartbeat latency > 5 seconds

#### 7. Data Freshness

**Why:** Ensure system has current data for decisions

**Metrics:**
- **Position sync lag:** Time since last position update (target: < 5 min)
- **Greeks update lag:** Time since last Greeks calculation (target: < 5 min)
- **Decision run lag:** Time since last decision engine run (target: < 1 min)

**Dashboard:** Health page → Data Freshness

**Alert:** If any lag > 10 minutes

#### 8. System Resources

**Why:** Prevent system overload

**Metrics:**
- **CPU usage:** % CPU utilization (target: < 80%)
- **Memory usage:** % RAM utilization (target: < 80%)
- **Disk usage:** % disk utilization (target: < 90%)
- **Network I/O:** Data transfer rate

**Dashboard:** Health page → System Metrics

**Alert:** If any metric > 90%

---

## Alert Thresholds

### Critical Alerts (Immediate Action Required)

| Alert | Threshold | Action |
|-------|-----------|--------|
| IB Disconnected | Connection lost | Restart IB Gateway, check logs |
| Circuit Breaker Tripped | 3 failures in 5 min | Identify root cause, reset circuit breaker |
| Position Sync Failure | Lag > 15 minutes | Restart position sync service |
| Disk Space Critical | Usage > 95% | Clean up old logs/backups |
| Memory Critical | Usage > 95% | Restart services, investigate memory leak |

### Warning Alerts (Monitor Closely)

| Alert | Threshold | Action |
|-------|-----------|--------|
| Delta Limit | \|Delta\| > 180 (90% of limit) | Monitor, reduce new positions |
| Gamma Limit | \|Gamma\| > 450 (90% of limit) | Monitor, reduce new positions |
| Concentration | Single symbol > 25% | Monitor, avoid adding more |
| Order Rejection | Rejection rate > 5% | Investigate rejection reason |
| Data Stale | Any lag > 10 min | Check sync service |

### Info Alerts (Informational)

| Alert | Threshold | Action |
|-------|-----------|--------|
| Position Opened | New position entered | Verify intended |
| Position Closed | Position exited | Review P&L |
| Strategy Triggered | Decision rule triggered | Review decision |

---

## Dashboard Usage

### Accessing the Dashboard

**URL:** http://localhost:8501

**Login:** No authentication required (add reverse proxy with auth for production)

### Pages

#### 1. Positions Page

**Purpose:** View all open positions with details

**Features:**
- **Position list:** Symbol, strike, expiry, right, quantity, Greeks, P&L
- **Filter by symbol:** Select specific symbol to view
- **Filter by strategy:** Select specific strategy type
- **Sort by columns:** Click column headers to sort
- **Auto-refresh:** Toggle auto-refresh (5s, 30s, 60s, off)

**Key Metrics:**
- Total positions
- Total delta, gamma, theta, vega
- Total unrealized P&L

**Actions:**
- Click position to view details
- Export positions to CSV

#### 2. Portfolio Page

**Purpose:** View portfolio-level analytics

**Features:**
- **Greeks heatmap:** Visual representation of Greeks by symbol
- **P&L time series:** P&L over time (daily, weekly, monthly)
- **Portfolio summary:** Total Greeks, total P&L, position count
- **Strategy breakdown:** P&L by strategy type

**Key Metrics:**
- Portfolio Greeks (aggregated)
- Total P&L (realized + unrealized)
- Win rate by strategy

**Actions:**
- Adjust time range for P&L chart
- Filter by symbol for Greeks heatmap

#### 3. Alerts Page

**Purpose:** View and manage alerts

**Features:**
- **Active alerts:** Unacknowledged alerts
- **Alert history:** Past alerts with timestamps
- **Severity filter:** Show critical, warning, or info alerts
- **Acknowledge alerts:** Mark alerts as acknowledged

**Alert Types:**
- Position alerts (opened, closed, adjusted)
- Risk alerts (delta limit, gamma limit)
- System alerts (IB disconnected, sync failed)
- Order alerts (rejected, filled)

**Actions:**
- Acknowledge alerts to dismiss
- Filter by severity or type
- Export alerts to CSV

#### 4. Health Page

**Purpose:** Monitor system health

**Features:**
- **IB connection status:** Connected/disconnected, last update
- **Data freshness:** Position sync, Greeks update, decision run lags
- **System metrics:** CPU, memory, disk usage
- **Active strategies:** Strategies consuming streaming slots
- **Health alerts:** Auto-generated health issues

**Actions:**
- Reconnect to IB (if disconnected)
- Force sync (if position sync lagged)
- Clear queue backlog (if queue backed up)

### Auto-Refresh

All pages support auto-refresh:
- **5 seconds:** Real-time monitoring (recommended for trading hours)
- **30 seconds:** Moderate refresh
- **60 seconds:** Low refresh (after hours)
- **Off:** Manual refresh only

**Tip:** Use 5s refresh during trading hours, off after hours to save resources.

### Keyboard Shortcuts

- **Ctrl + R:** Manual refresh
- **Ctrl + F:** Focus search/filter
- **Esc:** Clear filters

---

## Log Analysis

### Log Locations

#### System Logs (Journald)

**Location:** Managed by systemd

**View logs:**
```bash
# Live logs
journalctl -u v6-trading -f

# Last 100 lines
journalctl -u v6-trading -n 100

# Logs since today
journalctl -u v6-trading --since "today"

# Logs with errors only
journalctl -u v6-trading -p err

# Logs for all services
journalctl -u "v6-*" -f
```

#### Application Logs (Loguru)

**Location:** `/opt/v6-trading/logs/v6_production.log`

**Features:**
- Automatic rotation (100MB per file)
- Compression (zip)
- Retention (10 backups)

**View logs:**
```bash
# Live logs
tail -f logs/v6_production.log

# Last 100 lines
tail -n 100 logs/v6_production.log

# Search for errors
grep ERROR logs/v6_production.log

# Search for specific symbol
grep "SPY" logs/v6_production.log
```

### Log Patterns

#### Normal Operation

```
INFO | 2026-01-27 09:30:00 | production:start | ✓ Connected to IB
INFO | 2026-01-27 09:30:05 | position_streamer:update | Position updated: SPY 12345678
INFO | 2026-01-27 09:31:00 | decision_engine:run | Decision: HOLD for position XYZ
```

#### Warning Patterns

```
WARNING | 2026-01-27 09:30:00 | ib_connection:reconnect | Connection lost, reconnecting...
WARNING | 2026-01-27 09:31:00 | position_sync:lag | Position sync lagged: 320s
WARNING | 2026-01-27 09:32:00 | portfolio:delta | Portfolio delta approaching limit: 180/200
```

#### Error Patterns

```
ERROR | 2026-01-27 09:30:00 | order_execution:rejected | Order rejected: Insufficient buying power
ERROR | 2026-01-27 09:31:00 | ib_connection:failed | Failed to connect after 3 attempts
ERROR | 2026-01-27 09:32:00 | position_sync:failed | Position sync failed: API rate limit
```

#### Critical Patterns

```
CRITICAL | 2026-01-27 09:30:00 | circuit_breaker:open | Circuit breaker OPEN after 3 failures
CRITICAL | 2026-01-27 09:31:00 | position_sync:naked | NAKEDED POSITION: Position in Delta Lake but missing from IB
CRITICAL | 2026-01-27 09:32:00 | portfolio:delta_limit | Portfolio delta limit exceeded: 250/200
```

### Common Log Queries

#### Find all errors in last hour:
```bash
journalctl -u v6-trading --since "1 hour ago" -p err
```

#### Find order rejections:
```bash
journalctl -u v6-trading | grep -i "order rejected"
```

#### Find position sync issues:
```bash
journalctl -u v6-position-sync | grep -i "error\|warning"
```

#### Find IB connection issues:
```bash
journalctl -u v6-trading | grep -i "connection\|disconnect"
```

#### Find circuit breaker events:
```bash
journalctl -u v6-trading | grep -i "circuit breaker"
```

### Log Analysis Tools

#### Grep for patterns:
```bash
# Count errors
journalctl -u v6-trading -p err | wc -l

# Find specific symbol
journalctl -u v6-trading | grep "SPY"

# Find time range
journalctl -u v6-trading --since "09:00" --until "16:00"
```

#### Export logs for analysis:
```bash
# Export to file
journalctl -u v6-trading --since "24 hours ago" > logs.txt

# Export to CSV (if structured logs)
journalctl -u v6-trading -o csv > logs.csv
```

### Log Retention

**Systemd logs:**
- Retention: 7 days (default)
- Max size: 4GB (default)

**Application logs:**
- Retention: 10 files × 100MB = 1GB
- Compression: Zip (saves ~80% space)

**Adjust retention:**
```bash
# Systemd logs (in /etc/systemd/journald.conf)
SystemMaxUse=1G
MaxRetentionSec=30day

# Application logs (in config)
log_backup_count: 30  # Keep 30 backup files
```

---

## Proactive Monitoring

### Daily Checks

1. **Morning:** Check IB connection, dashboard, health status
2. **During trading:** Monitor alerts, P&L, Greeks
3. **After hours:** Review logs, check backups

### Weekly Checks

1. **Review performance:** P&L, win rate, drawdown
2. **Analyze logs:** Errors, warnings, patterns
3. **Verify backups:** Test restore (dry-run)

### Monthly Checks

1. **Strategy review:** Evaluate strategy performance
2. **Risk limits:** Adjust if needed
3. **System maintenance:** Updates, cleanups

---

## Alert Integration

### Configure Webhook Alerts

Edit `config/production.yaml`:

```yaml
monitoring:
  enabled: true
  alert_webhook_url: "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```

Or set environment variable:

```bash
export PRODUCTION_ALERT_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```

### Alert Format

Alerts are sent as JSON:

```json
{
  "text": "[CRITICAL] IB connection failed and could not reconnect"
}
```

### Supported Webhooks

- **Slack:** Incoming webhook
- **Discord:** Webhook
- **Microsoft Teams:** Incoming webhook
- **Custom:** Any webhook accepting JSON POST

---

**Last updated:** 2026-01-27
