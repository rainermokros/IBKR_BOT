# V6 Trading Bot

**Next-generation automated options trading system with intelligent risk management and full visibility.**

## Overview

V6 Trading Bot is a fully autonomous options trading system designed for personal trading accounts. It features advanced automation, comprehensive risk management, and real-time monitoring.

### Core Features

- **Automated Strategy Entry:** Iron Condors, vertical spreads with custom builders
- **12 Priority-Based Decision Rules:** Catastrophe, trailing stop, time exit, take profit, stop loss, delta/gamma risk, IV crush, DTE roll, VIX exit, portfolio limits
- **Real-Time Position Synchronization:** IB ↔ Delta Lake with hybrid streaming
- **Comprehensive Risk Management:** Exit rules + portfolio controls + circuit breaker
- **Enhanced Monitoring Dashboard:** Real-time alerts, Greeks, P&L, positions
- **Production-Grade Deployment:** Systemd services, health checks, automated backups

### Success Criteria

- Better risk-adjusted returns than v5 (lower drawdown, higher Sharpe ratio)
- Full visibility into all system operations in real-time

## Tech Stack

- **Python:** 3.11+
- **IB API:** ib_async
- **Data Storage:** Delta Lake (ACID transactions, time-travel)
- **Dashboard:** Streamlit
- **Deployment:** systemd, Linux

## Quick Start

### Prerequisites

- Python 3.11 or higher
- Interactive Brokers account with API access
- IB Gateway installed and running

### Installation

```bash
# Clone repository
git clone <repository-url>
cd v6

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

### Running in Development

```bash
# Run dashboard (for monitoring)
python scripts/run_dashboard.py

# Run production system
python scripts/run_production.py

# Run health check
python scripts/health_check.py
```

## Documentation

- **[Production Setup Guide](docs/PRODUCTION_SETUP.md)** - Deploy to production
- **[Runbook](docs/RUNBOOK.md)** - Daily operations and incident response
- **[Monitoring Guide](docs/MONITORING.md)** - Metrics, alerts, dashboard usage
- **[Backup & Restore](docs/BACKUP_RESTORE.md)** - Backup procedures and disaster recovery

## Deployment

### Automated Deployment

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
sudo systemctl enable v6-trading v6-dashboard v6-position-sync

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

## Dashboard

Access the monitoring dashboard at: **http://localhost:8501**

### Pages

- **Positions** - View all open positions with Greeks and P&L
- **Portfolio** - Portfolio analytics (Greeks heatmap, P&L time series)
- **Alerts** - View and acknowledge alerts
- **Health** - System health (IB connection, data freshness, resources)

## Testing

```bash
# Run all tests
pytest

# Run integration tests
pytest tests/integration/

# Run with coverage
pytest --cov=src --cov-report=html
```

## Project Structure

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

## Safety

### Risk Limits

- **Portfolio Delta:** ±200
- **Portfolio Gamma:** ±500
- **Single Symbol Concentration:** 30% max
- **Circuit Breaker:** 3 failures in 5 minutes triggers halt

### Dry-Run Mode

For testing without live trading:

```yaml
# config/production.yaml
dry_run: true  # Set to false for production trading
```

### Emergency Shutdown

```bash
# Stop all services immediately
sudo systemctl stop v6-trading v6-position-sync v6-dashboard
```

See [RUNBOOK.md](docs/RUNBOOK.md) for emergency procedures.

## Monitoring

### Health Checks

```bash
# Run health check
./scripts/health_check.py
echo $?  # 0=healthy, 1=degraded, 2=unhealthy
```

### Logs

```bash
# Application logs
tail -f logs/v6_production.log

# Systemd logs
journalctl -u v6-trading -f

# Errors only
journalctl -u v6-trading -p err
```

### Backups

```bash
# Manual backup
./scripts/backup.sh

# List backups
ls -lh backups/
```

## Contributing

This is a personal trading system. Contributions are not accepted at this time.

## License

Proprietary - All rights reserved

## Disclaimer

**This software is for educational purposes only. Options trading involves substantial risk of loss and is not suitable for every investor. You are responsible for your own trading decisions and the risks associated with them.**

---

**Last updated:** 2026-02-07 (v1.2 Trading Optimization)
