# V6 Trading Bot - Startup Guide

**Last updated:** 2026-01-28

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Prerequisites & Installation](#prerequisites--installation)
4. [Configuration](#configuration)
5. [Running the System](#running-the-system)
6. [Dashboard Guide](#dashboard-guide)
7. [Monitoring & Maintenance](#monitoring--maintenance)
8. [Troubleshooting](#troubleshooting)
9. [Key Integrations](#key-integrations)
10. [Next Steps](#next-steps)

---

## Overview

### What is V6?

**V6** is a next-generation automated options trading system designed for personal trading accounts. It features:

- **Fully Autonomous Trading** - Iron Condors, vertical spreads with custom builders
- **12 Priority-Based Decision Rules** - Catastrophe, trailing stop, time exit, take profit, stop loss, delta/gamma risk, IV crush, DTE roll, VIX exit, portfolio limits
- **Real-Time Position Synchronization** - IB ↔ Delta Lake with hybrid streaming
- **Comprehensive Risk Management** - Exit rules + portfolio controls + circuit breaker
- **Enhanced Monitoring Dashboard** - Real-time alerts, Greeks, P&L, positions
- **Production-Grade Deployment** - Systemd services, health checks, automated backups

### Success Criteria

- Better risk-adjusted returns than v5 (lower drawdown, higher Sharpe ratio)
- Full visibility into all system operations in real-time

### Tech Stack

| Component | Technology |
|-----------|------------|
| **Language** | Python 3.11+ |
| **IB API** | ib_async |
| **Storage** | Delta Lake (ACID transactions, time-travel) |
| **Dashboard** | Streamlit |
| **Deployment** | systemd, Linux |

### Project Progress

**8 Phases - 87.5% Complete:**

1. ✅ Architecture & Infrastructure (Delta Lake, IB connection, base models)
2. ✅ Position Synchronization (real-time streaming, persistence, reconciliation)
3. ✅ Decision Rules Engine (12 priority rules, risk calculations, alerts)
4. ✅ Strategy Execution (automated builders, order execution, workflows)
5. ✅ Risk Management (portfolio controls, circuit breakers, trailing stops)
6. ✅ Monitoring Dashboard (real-time display, Greeks visualization, alerts)
7. ✅ Testing & Deployment (integration tests, paper trading, production)
8. 🆕 **Futures Data Collection** (ES, NQ, RTY for leading indicators)

---

## Quick Start

### 30-Second Setup

```bash
# 1. Navigate to project
cd /home/bigballs/project/bot/v6

# 2. Install dependencies
uv sync

# 3. Configure IB Gateway (paper trading)
# - Port: 7497 (paper), 7496 (production)
# - Enable ActiveX/Socket Clients
# - Read-Only API: Unchecked

# 4. Copy config
cp config/paper_trading.yaml.example config/paper_trading.yaml

# 5. Run system
python -m src.v6.orchestration.paper_trader
```

### Access Dashboard

```bash
# Start dashboard (separate terminal)
streamlit run src/v6/dashboard/app.py --server.port 8501
```

Visit: **http://localhost:8501**

---

## Prerequisites & Installation

### Requirements

- **Python:** 3.11 or higher
- **IB Gateway:** Latest version from Interactive Brokers
- **Operating System:** Linux (Ubuntu 22.04+) or macOS
- **Systemd:** For service management (Linux only)

### Interactive Brokers Setup

#### 1. Create IB Paper Trading Account

1. Log in to your IBKR account
2. Navigate to **Account Management** → **Settings** → **Paper Trading Account**
3. Enable paper trading account
4. Note your paper trading account ID

#### 2. Configure IB Gateway

1. Download and install IB Gateway
2. Start IB Gateway
3. Configure API settings:
   - **Enable ActiveX/Socket Clients:** Checked
   - **Socket port:** `7497` (paper) or `7496` (production)
   - **Allow connections from localhost:** Checked
   - **Read-Only API:** Unchecked (need trading permissions)
4. Log in with your paper trading credentials

#### 3. Verify Connection

```bash
# Test IB connection
python -c "
import ib_async
import asyncio

async def test():
    ib = ib_async.IB()
    await ib.connectAsync(host='127.0.0.1', port=7497, clientId=2)
    print(f'Connected: {ib.isConnected()}')
    await ib.disconnect()

asyncio.run(test())
"
```

### Installation

```bash
# Navigate to project
cd /home/bigballs/project/bot/v6

# Install dependencies
uv sync

# Or using pip
pip install -e .

# Configure production settings
cp config/production.yaml.example config/production.yaml
nano config/production.yaml

# Configure environment variables (optional)
cp .env.example .env
nano .env
```

### Create Dedicated User (Recommended)

```bash
# Create user
sudo useradd -r -s /bin/bash -d /opt/v6-trading trading

# Create directory
sudo mkdir -p /opt/v6-trading
sudo chown trading:trading /opt/v6-trading

# Copy project files
sudo cp -r . /opt/v6-trading/
sudo chown -R trading:trading /opt/v6-trading
```

---

## Configuration

### Paper Trading Config

Edit `config/paper_trading.yaml`:

```yaml
# IB Gateway Connection (Paper Trading Account)
ib_host: "127.0.0.1"
ib_port: 7497  # Must be 7497 for paper trading
ib_client_id: 2

# Safety Limits (enforced)
dry_run: true  # Always true for paper trading
max_positions: 5  # Maximum concurrent positions
max_order_size: 1  # Maximum contracts per order
allowed_symbols:
  - SPY
  - QQQ
  - IWM

# Paper Trading Tracking
paper_start_date: "2026-01-27T00:00:00"
paper_starting_capital: 100000.0
```

### Production Config

Edit `config/production.yaml`:

```yaml
ib:
  host: "127.0.0.1"
  port: 7497         # 7497 for TWS, 4001 for Gateway
  client_id: 1

dry_run: false  # MUST be false for production trading!

logging:
  level: "INFO"
  file: "logs/v6_production.log"

monitoring:
  enabled: true
  alert_webhook_url: ""  # Optional: Add Slack/Discord webhook

backup:
  enabled: true
  path: "backups/"
```

### Environment Variables (Optional)

```bash
# Production settings
PRODUCTION_IB_HOST=127.0.0.1
PRODUCTION_IB_PORT=7497
PRODUCTION_IB_CLIENT_ID=1
PRODUCTION_DRY_RUN=false  # Critical: set to false for production
```

---

## Running the System

### Development Mode

```bash
# Run dashboard (for monitoring)
python scripts/run_dashboard.py

# Run production system
python scripts/run_production.py

# Run health check
python scripts/health_check.py
```

### Paper Trading

```bash
# Run paper trader
python -m src.v6.orchestration.paper_trader
```

The paper trader will:
1. Connect to IB paper trading account
2. Run entry cycle (check market conditions, generate signals)
3. Run monitoring cycle (track positions, evaluate exit decisions)
4. Run exit cycle (close positions when triggered)
5. Log all trades with `[PAPER]` prefix

### Production Deployment

```bash
# Deploy to production (installs systemd services)
sudo ./scripts/deploy.sh

# Update system
sudo ./scripts/update.sh

# Rollback to previous version
sudo ./scripts/rollback.sh <commit-or-tag>

# Check system status
./scripts/status.sh
```

### Systemd Services

After deployment, manage services with systemd:

```bash
# Start services
sudo systemctl start v6-trading v6-dashboard v6-position-sync

# Enable services (start on boot)
sudo systemctl enable v6-trading v6-dashboard v6-position-sync v6-health-check.timer

# Check service status
systemctl status v6-trading

# View logs
journalctl -u v6-trading -f
```

### Services

- **v6-trading.service** - Main trading system
- **v6-dashboard.service** - Monitoring dashboard
- **v6-position-sync.service** - Position synchronization
- **v6-health-check.timer** - Periodic health checks (every 5 minutes)
- **v6-trading.timer** - Daily restart for stability

### Emergency Shutdown

```bash
# Stop all services immediately
sudo systemctl stop v6-trading v6-position-sync v6-dashboard
```

---

## Dashboard Guide

### Access

**URL:** http://localhost:8501

### Pages

#### 1. Positions Page
- **Purpose:** View all open positions with details
- **Features:**
  - Position list (symbol, strike, expiry, right, quantity, Greeks, P&L)
  - Filter by symbol and strategy
  - Sort by columns
  - Auto-refresh (5s, 30s, 60s, off)
- **Key Metrics:** Total positions, Greeks totals, unrealized P&L

#### 2. Portfolio Page
- **Purpose:** View portfolio-level analytics
- **Features:**
  - Greeks heatmap
  - P&L time series (daily, weekly, monthly)
  - Portfolio summary
  - Strategy breakdown
- **Key Metrics:** Portfolio Greeks, total P&L, win rate by strategy

#### 3. Alerts Page
- **Purpose:** View and manage alerts
- **Features:**
  - Active alerts (unacknowledged)
  - Alert history
  - Severity filter (critical, warning, info)
  - Acknowledge alerts
- **Alert Types:** Position alerts, risk alerts, system alerts, order alerts

#### 4. Health Page
- **Purpose:** Monitor system health
- **Features:**
  - IB connection status
  - Data freshness (position sync, Greeks update, decision run lags)
  - System metrics (CPU, memory, disk usage)
  - Active strategies
- **Actions:** Reconnect to IB, force sync, clear queue backlog

#### 5. Futures Page (NEW)
- **Purpose:** Monitor futures data
- **Features:**
  - Real-time futures display (ES, NQ, RTY)
  - Futures vs spot comparison charts
  - Correlation analysis (ES-SPY, NQ-QQQ, RTY-IWM)
  - Lead-lag analysis
  - Predictive value assessment

### Auto-Refresh

All pages support auto-refresh:
- **5 seconds:** Real-time monitoring (recommended during trading hours)
- **30 seconds:** Moderate refresh
- **60 seconds:** Low refresh (after hours)
- **Off:** Manual refresh only

---

## Monitoring & Maintenance

### Daily Checklist (Before Market Open)

**Time:** 30 minutes before market open (8:30 AM ET)

1. **Check IB Gateway:**
   ```bash
   pgrep -f ibgateway
   systemctl status ib-gateway
   ```
   - Verify: Account balance, buying power

2. **Check System Status:**
   ```bash
   ./scripts/status.sh
   systemctl status v6-trading v6-dashboard v6-position-sync
   ```
   - Verify: All services are active
   - Check: No errors in recent logs

3. **Review Dashboard:**
   - Open: http://localhost:8501
   - Check: Positions page (verify all positions synced)
   - Check: Portfolio Greeks (verify risk exposure)
   - Check: Alerts page (acknowledge any alerts)
   - Check: System Health (verify IB connected, data fresh)

4. **Check Health Status:**
   ```bash
   ./scripts/health_check.py
   echo $?  # Should be 0 (healthy)
   ```

5. **Verify Risk Limits:**
   - Portfolio delta within limits (±200)
   - Portfolio gamma within limits (±500)
   - No single symbol concentration >30%

### End-of-Day Checklist (After Market Close)

**Time:** 30 minutes after market close (4:30 PM ET)

1. **Verify All Positions Synced:**
   ```bash
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
   ./scripts/backup.sh
   ```

4. **Review Day's Performance:**
   - Dashboard: Portfolio P&L
   - Dashboard: Greeks chart
   - Check: Any trades executed today
   - Check: Any alerts triggered

5. **Check Logs:**
   ```bash
   journalctl -u v6-trading --since "today" | less
   ```

### Weekly Tasks

**Day:** Friday afternoon or weekend

1. **Review Performance:**
   - Dashboard: Weekly P&L
   - Dashboard: Greeks trends
   - Analyze: Winning vs losing trades

2. **Check Logs:**
   ```bash
   journalctl -u v6-trading --since "7 days ago" -p warning
   ```

3. **Verify Backups:**
   ```bash
   ls -lh backups/
   ```

4. **Update Strategies** (if needed)

5. **System Maintenance:**
   - Check: Disk space (should be < 90%)
   - Check: Memory usage (should be < 90%)
   - Update: System packages if security updates

### Health Checks

```bash
# Run health check
./scripts/health_check.py
echo $?  # 0=healthy, 1=degraded, 2=unhealthy

# Check all services
./scripts/status.sh

# View logs
tail -f logs/v6_production.log

# Systemd logs
journalctl -u v6-trading -f

# Errors only
journalctl -u v6-trading -p err
```

### Backup Strategy

**Frequency:** Daily (after market close)
**Retention:** 30 days
**Storage:** Local backup directory + optional remote (S3, RSYNC)

```bash
# Manual backup
./scripts/backup.sh

# List backups
ls -lh backups/
```

---

## Troubleshooting

### Common Issues

#### 1. IB Gateway Disconnected

**Symptoms:**
- Dashboard shows: IB Connection: Disconnected
- Logs show: "IB connection lost"

**Resolution:**
```bash
# Check IB Gateway process
pgrep -f ibgateway

# Check IB Gateway logs
tail -f /home/trading/Jts/ibgateway.log

# Restart IB Gateway
systemctl restart ib-gateway

# Restart V6 services
systemctl restart v6-trading v6-position-sync
```

#### 2. Position Sync Lagged

**Symptoms:**
- Dashboard shows: Position sync lag > 5 minutes
- Health check: Position sync degraded

**Resolution:**
```bash
# Restart position sync service
systemctl restart v6-position-sync

# Force manual sync (via dashboard: click "Force Sync" button)
```

#### 3. Order Rejected

**Symptoms:**
- Dashboard alerts: "Order rejected"
- Logs show: "Order rejected by IB"

**Common Reasons:**
- Insufficient buying power
- Outside market hours
- Incorrect order parameters
- Risk limit exceeded

**Resolution:**
1. Identify rejection reason from logs
2. Fix underlying issue
3. Retry order if appropriate

#### 4. Circuit Breaker Triggered

**Symptoms:**
- Dashboard shows: Trading halted
- Logs show: "Circuit breaker tripped"

**Resolution:**
1. Identify root cause
2. Fix root cause
3. Reset circuit breaker (wait 60s or restart service)

#### 5. Dashboard Down

**Symptoms:**
- http://localhost:8501 not accessible

**Resolution:**
```bash
# Restart dashboard service
systemctl restart v6-dashboard

# Check port conflict
lsof -i :8501
```

### Getting Help

**Logs:**
- Application logs: `logs/v6_production.log`
- Systemd logs: `journalctl -u v6-trading -f`

**Documentation:**
- Runbook: `docs/RUNBOOK.md`
- Monitoring: `docs/MONITORING.md`
- Backup: `docs/BACKUP_RESTORE.md`

---

## Key Integrations

### 1. Data Collection System

**Overview:**
Collects option chain data for SPY, QQQ, IWM every 5 minutes and stores to Delta Lake.

**Components:**
- **OptionDataFetcher** - Fetches complete option chains from IB API
- **OptionSnapshotsTable** - Delta Lake table for storage
- **DataCollector** - Background service for continuous collection

**Usage:**
```bash
# Start collection (automatically started by paper trader)
python -m src.v6.orchestration.paper_trader

# Test collection manually
python -m src.v6.scripts.test_data_collection
```

**Data Stored:**
- 15 columns per contract
- Partitioned by symbol and yearmonth
- Idempotent writes (no duplicates)

### 2. Derived Statistics

**Overview:**
Calculates and stores 27 historical market statistics daily from option snapshots.

**Metrics:**
- IV statistics (min, max, mean, median, percentiles)
- IV ranks (30d, 60d, 90d, 1y)
- Greeks statistics
- Volume & OI data
- Market regime classification

**Usage:**
```bash
# Calculate statistics
python -m src/v6.scripts.derive_statistics

# Schedule daily (crontab)
0 18 * * 1-5 python -m src/v6.scripts.schedule_derived_statistics --once
```

**Data Stored:**
- 27 metrics per day per symbol
- Partitioned by symbol and yearmonth

### 3. Futures Data Integration

**Overview:**
Collects futures data (ES, NQ, RTY) as leading indicators for spot trading.

**Purpose:**
- Futures trade 23 hours/day vs 6.5 hours for equities
- Early market signals
- Confirmation for spot trades
- Momentum tracking

**Futures Tracked:**
- **ES** (E-mini S&P 500) → SPY leading indicator
- **NQ** (E-mini Nasdaq 100) → QQQ leading indicator
- **RTY** (E-mini Russell 2000) → IWM leading indicator

**Data Points:**
- Price (bid, ask, last)
- Volume, open interest
- % change (1h, 4h, overnight, daily)
- Implied volatility

**Usage:**
```bash
# Load futures data
python -m src.v6.scripts.load_futures_data

# View in dashboard
# Visit: http://localhost:8501 → Futures page
```

**Dashboard Features:**
- Real-time futures display with color coding
- Futures vs spot comparison charts
- Correlation analysis (ES-SPY, NQ-QQQ, RTY-IWM)
- Lead-lag analysis
- Predictive value assessment

### 4. Unified Scheduler

**Overview:**
ONE crontab entry to rule them all - NYSE calendar aware, market hours aware.

**Setup:**
```bash
# Edit crontab
crontab -e

# Add this single line (runs every minute during market hours)
* * * * * cd /home/bigballs/project/bot/v6 && python -m src.v6.scheduler.unified_scheduler >> /home/bigballs/project/bot/v6/logs/scheduler_cron.log 2>&1
```

**What It Does:**
- **Pre-Market (8:30-9:30 AM ET):**
  - Load historical market data (SPY, QQQ, IWM)
  - Calculate derived statistics
  - Load futures data (ES, NQ, RTY)
- **Market Open (9:30 AM - 4:00 PM ET):**
  - Every 5 minutes: Collect option snapshots
  - Every 5 minutes: Collect futures snapshots
  - Every 30 minutes: Update derived statistics
- **Post-Market (4:00-6:00 PM ET):**
  - Calculate final daily statistics
  - Load missing data
- **After 6:00 PM ET:**
  - Sleep until next trading day
- **Weekends & Holidays:**
  - Do nothing (NYSE calendar aware)

---

## Risk Limits

### Portfolio Limits

- **Portfolio Delta:** ±200
- **Portfolio Gamma:** ±500
- **Single Symbol Concentration:** 30% max
- **Circuit Breaker:** 3 failures in 5 minutes triggers halt

### Safety Limits (Paper Trading)

- `max_positions: 5`
- `max_order_size: 1`
- `allowed_symbols: SPY, QQQ, IWM`
- `dry_run: true`

---

## Next Steps

### Immediate Actions

1. **Set up IB Gateway** (paper trading)
2. **Configure system** (copy and edit configs)
3. **Run paper trading** (validate strategies)
4. **Monitor dashboard** (verify operations)
5. **Collect data** (2-4 weeks for historical IV Rank)

### Paper Trading Validation

Before transitioning to production, ensure:

- [ ] Paper trading runs for at least 1-2 weeks
- [ ] Win rate >60%
- [ ] Sharpe ratio >1.0
- [ ] Max drawdown <10%
- [ ] All safety limits tested
- [ ] No errors in logs for at least 1 week
- [ ] Dashboard displays all metrics correctly
- [ ] IB connection stable

### Futures Integration

**After 2-4 weeks** of futures data collection:
1. Run correlation analysis to assess predictive value
2. If valuable: Integrate futures signals into DecisionEngine
3. If not valuable: Continue collection for research

### Production Transition

```bash
# Week 1-2: Conservative
max_positions: 3
max_order_size: 1

# Week 3-4: Moderate
max_positions: 5
max_order_size: 2

# Week 5+: Production (after validation)
max_positions: 10
max_order_size: 5
```

---

## File Structure

```
v6/
├── caretaker/          # Decision engine, monitoring
├── config/             # Configuration files
├── data/               # Delta Lake tables
├── docs/               # Documentation
├── execution/          # Order execution engine
├── scripts/            # Utility and deployment scripts
├── src/v6/             # Source code
│   ├── config/         # Configuration modules
│   ├── dashboard/      # Streamlit dashboard
│   ├── data/           # Data repositories
│   ├── execution/      # Order execution
│   ├── orchestration/  # Production orchestrator
│   ├── strategies/     # Strategy builders
│   └── utils/          # Utilities (IB connection, etc.)
├── strategies/         # Strategy definitions
├── systemd/            # Systemd service files
└── tests/              # Test suite
```

---

## Summary

**V6 Trading System** is a production-ready, fully autonomous options trading bot with:

- ✅ **Complete automation** - Entry, monitoring, adjustment, exit
- ✅ **Comprehensive risk management** - 12 decision rules, portfolio controls, circuit breakers
- ✅ **Enhanced monitoring** - Real-time dashboard with alerts, Greeks, P&L
- ✅ **Production deployment** - Systemd services, health checks, backups
- ✅ **Paper trading validation** - Test strategies without risk
- ✅ **Futures integration** - Leading indicators for enhanced signals
- ✅ **Data collection** - Option chains, derived statistics, futures data

**Status:** Ready to deploy ✓

**Next:** Set up IB Gateway, configure system, and start paper trading!

---

**For issues or questions:**
- Check logs: `logs/v6_production.log` or `journalctl -u v6-trading -f`
- Review runbook: `docs/RUNBOOK.md`
- Check IB Gateway status: Ensure it's running and logged in
---

*Last updated: January 28, 2026*
*Project Status: Production Ready ✓*
