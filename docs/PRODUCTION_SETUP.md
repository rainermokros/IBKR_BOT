# Production Setup Guide

This guide covers deploying the V6 trading system to production.

## Prerequisites

### Software Requirements

- **Python:** 3.11 or higher
- **IB Gateway:** Latest version from Interactive Brokers
- **Operating System:** Linux (Ubuntu 22.04+ recommended) or macOS
- **Systemd:** For service management (Linux only)

### Interactive Brokers Setup

1. **Download IB Gateway:**
   - Go to https://www.interactivebrokers.com/en/trading/ibgateway-stable.php
   - Download and install IB Gateway

2. **Configure IB Gateway:**
   - Start IB Gateway: `./ibgateway &`
   - Login with your production account credentials
   - Configure API settings:
     - Enable ActiveX/Socket Clients: **Checked**
     - Socket port: `7497` (TWS) or `4001` (Gateway)
     - Allow connections from localhost: **Checked**
     - Read-Only API: **Unchecked** (need trading permissions)
     - Extra authentication: **Unchecked** (for local connections)

3. **Test IB Gateway:**
   - Ensure IB Gateway is running and logged in
   - Verify port is accessible: `netstat -an | grep 7497`

## Installation

### 1. Clone and Install Dependencies

```bash
# Navigate to project directory
cd /home/bigballs/project/bot/v6

# Install Python dependencies
uv sync

# Or using pip
pip install -e .
```

### 2. Configure Production Settings

```bash
# Copy example config
cp config/production.yaml.example config/production.yaml

# Edit config with your settings
nano config/production.yaml
```

**Critical settings in `config/production.yaml`:**

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

### 3. Configure Environment Variables (Optional)

```bash
# Copy example env file
cp .env.example .env

# Edit with your settings
nano .env
```

Environment variables override config file settings:

```bash
PRODUCTION_IB_HOST=127.0.0.1
PRODUCTION_IB_PORT=7497
PRODUCTION_IB_CLIENT_ID=1
PRODUCTION_DRY_RUN=false  # Critical: set to false for production
```

### 4. Create Dedicated User (Recommended)

For security, run the trading system as a non-root user:

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

### 5. Deploy Systemd Services

```bash
# Run deployment script
cd /opt/v6-trading
sudo ./scripts/deploy.sh

# This will:
# - Install systemd services
# - Enable services (but not start them)
# - Print next steps
```

### 6. Start Services

```bash
# Start all services
sudo systemctl start v6-trading v6-dashboard v6-position-sync

# Enable services to start on boot
sudo systemctl enable v6-trading v6-dashboard v6-position-sync v6-health-check.timer
```

## Verification

### 1. Check Service Status

```bash
# Check all services
sudo systemctl status v6-trading v6-dashboard v6-position-sync

# Or use status script
./scripts/status.sh
```

Expected output:
```
✓ v6-trading.service - active (running)
✓ v6-dashboard.service - active (running)
✓ v6-position-sync.service - active (running)
```

### 2. Run Health Check

```bash
./scripts/health_check.py
echo $?  # Should output 0 (healthy)
```

### 3. Verify Dashboard Access

Open browser: `http://localhost:8501`

Verify:
- Positions page shows live data
- Portfolio Greeks are updating
- System health shows green indicators
- IB connection status: Connected

### 4. Check Logs

```bash
# View production logs
tail -f logs/v6_production.log

# View systemd logs
journalctl -u v6-trading -f

# View recent errors
journalctl -u v6-trading -p err -n 50
```

## Safety Checklist

Before enabling live trading, verify:

- [ ] IB Gateway is running and logged in
- [ ] Config file has `dry_run: false`
- [ ] Environment variable `PRODUCTION_DRY_RUN=false` (if using .env)
- [ ] Backup is enabled: `backup_enabled: true`
- [ ] Monitoring is enabled: `monitoring_enabled: true`
- [ ] Health check is passing: `./scripts/health_check.py` returns 0
- [ ] Dashboard is accessible and showing live data
- [ ] You have reviewed the runbook: `docs/RUNBOOK.md`
- [ ] You have tested emergency shutdown procedure

## First Week Monitoring

During the first week of production:

1. **Monitor logs daily:**
   ```bash
   journalctl -u v6-trading --since "24 hours ago" | less
   ```

2. **Check health status:**
   ```bash
   ./scripts/status.sh
   ```

3. **Review dashboard:**
   - Check for alerts on Alerts page
   - Verify position sync is working
   - Monitor IB connection status

4. **Verify backups:**
   ```bash
   ls -lh backups/
   ```

5. **Review trades:**
   - Verify all trades are intentional
   - Check that strategies are executing correctly
   - Monitor risk limits

## Troubleshooting

### Services Won't Start

```bash
# Check service logs
journalctl -u v6-trading -n 100

# Common issues:
# - IB Gateway not running
# - Port already in use
# - Config file invalid
```

### IB Connection Failing

```bash
# Verify IB Gateway is running
pgrep -f ibgateway

# Check port is listening
netstat -an | grep 7497

# Test IB connection manually
python -c "from ib_async import IB; import asyncio; asyncio.run(IB().connectAsync('127.0.0.1', 7497, 1))"
```

### Dashboard Not Accessible

```bash
# Check dashboard service
sudo systemctl status v6-dashboard

# Check port is not in use
lsof -i :8501

# Restart dashboard
sudo systemctl restart v6-dashboard
```

## Monitoring

After deployment, monitor the system using:

- **Dashboard:** http://localhost:8501
- **Logs:** `journalctl -u v6-trading -f`
- **Health check:** `./scripts/health_check.py`
- **Status script:** `./scripts/status.sh`

## Next Steps

- Read the runbook: `docs/RUNBOOK.md`
- Set up alerts: Configure `alert_webhook_url` in config
- Configure automated backups: Verify backup script works
- Review monitoring guide: `docs/MONITORING.md`

## Support

For issues or questions:
- Check logs: `journalctl -u v6-trading -n 100`
- Review runbook: `docs/RUNBOOK.md`
- Check IB Gateway status: Ensure it's running and logged in
