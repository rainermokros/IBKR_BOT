# Phase 7 Plan 3: Production Deployment

**Phase:** 7
**Plan:** 03
**Type:** Implementation
**Granularity:** plan
**Depends on:** None (can run in parallel with 7-01, 7-02)
**Files modified:** (tracked after execution)

## Objective

Automate production deployment with systemd services, monitoring setup, runbooks for common incidents, and comprehensive documentation for operating the V6 trading system in production.

## Execution Context

@~/.claude/get-shit-done/workflows/execute-plan.md
@~/.claude/get-shit-done/templates/phase-prompt.md
@~/.claude/get-shit-done/references/checkpoints.md
@~/.claude/get-shit-done/references/tdd.md

## Context

### Project State
@.planning/STATE.md
@.planning/ROADMAP.md
@.planning/PROJECT.md

### Completed Phases
@.planning/phases/1-architecture-infrastructure/1-03-SUMMARY.md (IB connection management)
@.planning/phases/2-position-synchronization/2-03-SUMMARY.md (Position sync)
@.planning/phases/6-monitoring-dashboard/6-03-SUMMARY.md (Dashboard)

### Expertise Areas
~/.claude/skills/expertise/ib-async-api/SKILL.md (IB connection reliability)
~/.claude/skills/expertise/position-manager/SKILL.md (Production monitoring)
~/.claude/skills/expertise/delta-lake-lakehouse/SKILL.md (Delta Lake operations)

### System Components
@src/v6/utils/ib_connection.py (IB connection manager)
@src/v6/data/reconciliation.py (Position reconciliation)
@src/v6/dashboard/app.py (Monitoring dashboard)
@scripts/run_dashboard.py (Dashboard startup)

## Tasks

### Task 1: Create Production Configuration
**Type:** auto

Set up production configuration with security, logging, and monitoring settings.

**Steps:**
1. Create `src/v6/config/production_config.py` with:
   - `ProductionConfig` dataclass:
     - `ib_host`, `ib_port`, `ib_client_id` (production IB gateway)
     - `dry_run: bool = False` (production mode)
     - `log_level: str = "INFO"` (production logging)
     - `log_file: str = "logs/v6_production.log"`
     - `max_log_size_mb: int = 100` (log rotation)
     - `log_backup_count: int = 10`
     - `monitoring_enabled: bool = True`
     - `alert_webhook_url: Optional[str]` (optional webhook for alerts)
     - `backup_enabled: bool = True`
     - `backup_path: str = "backups/"`
     - `health_check_interval: int = 60` (seconds)
2. Create `config/production.yaml.example`:
   - Production IB gateway credentials
   - Logging configuration
   - Monitoring settings
   - Backup configuration
3. Update `.env.example` with production variables:
   - `PRODUCTION_IB_HOST=127.0.0.1`
   - `PRODUCTION_IB_PORT=7497` (or 4001 for IB gateway)
   - `PRODUCTION_IB_CLIENT_ID=1`
   - `PRODUCTION_LOG_LEVEL=INFO`
   - `PRODUCTION_ALERT_WEBHOOK_URL=`
   - `PRODUCTION_BACKUP_PATH=backups/`
4. Create `src/v6/config/loader.py` with:
   - `load_config(env: str)` - Load config for environment (dev/paper/production)
   - `validate_production_config()` - Validate production settings
   - `merge_config_with_env()` - Override config with environment variables
5. Document production setup in `docs/PRODUCTION_SETUP.md`

**Acceptance Criteria:**
- Production config enforces dry_run=False with warning
- Config validates critical settings (IB credentials, log path, backup path)
- Environment variables override config file settings
- Example config provided for users

### Task 2: Implement Systemd Services
**Type:** auto

Create systemd services for automated startup, monitoring, and restart of system components.

**Steps:**
1. Create `systemd/v6-trading.service`:
   - Description: "V6 Trading Bot - Main trading system"
   - ExecStart: `/usr/bin/python /path/to/v6/scripts/run_production.py`
   - Restart: `on-failure`
   - RestartSec: `10`
   - User: `trading`
   - WorkingDirectory: `/opt/v6-trading`
   - EnvironmentFile: `/opt/v6-trading/.env`
   - StandardOutput: `journal`
   - StandardError: `journal`
   - WantedBy: `multi-user.target`
2. Create `systemd/v6-dashboard.service`:
   - Description: "V6 Trading Bot - Monitoring dashboard"
   - ExecStart: `/usr/bin/python /path/to/v6/scripts/run_dashboard.py --headless --port 8501`
   - Restart: `always`
   - User: `trading`
   - WorkingDirectory: `/opt/v6-trading`
   - EnvironmentFile: `/opt/v6-trading/.env`
   - After: `network.target`
3. Create `systemd/v6-position-sync.service`:
   - Description: "V6 Trading Bot - Position synchronization"
   - ExecStart: `/usr/bin/python /path/to/v6/scripts/run_position_sync.py`
   - Restart: `on-failure`
   - User: `trading`
   - WorkingDirectory: `/opt/v6-trading`
4. Create `systemd/v6-trading.timer`:
   - Description: "Timer for v6-trading periodic tasks"
   - OnBootSec: `5min`
   - OnUnitActiveSec: `24h` (daily restart for stability)
5. Create `scripts/install_services.sh`:
   - Copy systemd files to `/etc/systemd/system/`
   - Reload systemd daemon
   - Enable services (but don't start)
   - Print status instructions
6. Document service management in runbook

**Acceptance Criteria:**
- All services configured with proper restart policies
- Services start in correct order (network → trading → dashboard)
- Services run as non-root user (trading)
- Logs sent to journald for centralized logging
- Timer service schedules daily restart (stability)
- Installation script is idempotent (can run multiple times)

### Task 3: Create Production Orchestrator and Health Checks
**Type:** auto

Implement production orchestrator with health monitoring, auto-recovery, and graceful shutdown.

**Steps:**
1. Create `src/v6/orchestration/production.py` with:
   - `ProductionOrchestrator` class:
     - `async start()` - Connect to IB, start all workflows
     - `async run()` - Main production loop (entry → monitor → exit cycles)
     - `async health_check()` - Check IB connection, position sync, dashboard
     - `auto_recovery()` - Restart failed components (IB connection, sync)
     - `async stop()` - Graceful shutdown (wait for orders to fill, close positions if needed)
     - `send_alert()` - Send alerts to webhook/email if configured
2. Create `scripts/run_production.py`:
   - Parse production config
   - Initialize ProductionOrchestrator
   - Set up signal handlers (SIGINT, SIGTERM, SIGHUP)
   - Run main loop with error handling
   - Log all operations to production log
3. Create `scripts/health_check.py`:
   - Check IB connection status
   - Check position sync lag (last update time)
   - Check dashboard accessibility
   - Check disk space, memory, CPU
   - Return exit code: 0 (healthy), 1 (degraded), 2 (unhealthy)
4. Create systemd unit for health checks: `systemd/v6-health-check.service`:
   - Run every 5 minutes via timer
   - Log health status
   - Send alert if unhealthy
5. Create health check dashboard widget (modify system health page)

**Acceptance Criteria:**
- Orchestrator handles all production workflows
- Health check monitors all critical components
- Auto-recovery reconnects IB if connection drops
- Graceful shutdown waits for pending orders
- Health check script exits with correct codes
- Health check timer runs periodic checks

### Task 4: Create Runbooks and Documentation
**Type:** auto

Document operational procedures for common incidents, daily tasks, and emergency response.

**Steps:**
1. Create `docs/RUNBOOK.md` with:
   - **Daily Operations:**
     - Morning checklist (check IB connection, review positions, check alerts)
     - End-of-day checklist (verify all positions synced, backup data)
     - Weekly tasks (review performance, check logs, update strategies)
   - **Common Incidents:**
     - IB connection disconnected: Reconnect procedure, check gateway
     - Position sync lagged: Restart position sync service, check IB rate limits
     - Order rejected: Check account balance, check market hours, review order details
     - Circuit breaker triggered: Review failures, reset circuit breaker
     - Dashboard down: Restart dashboard service, check port availability
   - **Emergency Procedures:**
     - Emergency shutdown: Graceful exit, close all positions, stop trading
     - Manual position closure: Use TWS to close positions, update Delta Lake
     - Restore from backup: Restore Delta Lake, reconcile with IB
     - Contact support: IB support contact, log collection procedure
2. Create `docs/MONITORING.md` with:
   - Metrics to monitor (portfolio Greeks, P&L, position count, IB latency)
   - Alert thresholds (delta exposure, gamma risk, drawdown, connection failures)
   - Dashboard usage guide (navigate pages, filter data, export reports)
   - Log analysis (log locations, common log patterns, log rotation)
3. Create `docs/BACKUP_RESTORE.md` with:
   - Backup procedure (Delta Lake backup, config backup, log backup)
   - Automated backup script (`scripts/backup.sh`)
   - Restore procedure (step-by-step restore from backup)
   - Disaster recovery (RTO, RPO, off-site backup)
4. Create `scripts/backup.sh`:
   - Backup Delta Lake tables to tar.gz with timestamp
   - Backup config files
   - Upload to remote location (optional, S3/RSYNC)
   - Clean old backups (retain last 30 days)
5. Create `README.md` (if not exists) with:
   - Project overview
   - Quick start (dev setup)
   - Links to detailed docs (PRODUCTION_SETUP, RUNBOOK, MONITORING)

**Acceptance Criteria:**
- Runbook covers all common incidents with clear procedures
- Emergency procedures tested (manually or with dry-run mode)
- Backup script runs successfully and creates valid backups
- Documentation is clear and actionable
- README links to all major docs
- Docs include examples (commands, config snippets, screenshots)

### Task 5: Implement Deployment Automation
**Type:** auto

Create deployment scripts and infrastructure as code for reproducible deployments.

**Steps:**
1. Create `scripts/deploy.sh`:
   - Check prerequisites (Python 3.11+, IB gateway installed)
   - Create user: `trading` (if not exists)
   - Install dependencies: `uv sync` or `pip install -e .`
   - Copy systemd services to `/etc/systemd/system/`
   - Enable services (but don't start)
   - Print next steps (config, start services, check status)
   - Support `--dry-run` flag for testing
2. Create `scripts/update.sh`:
   - Stop services
   - Pull latest code (git pull)
   - Install updated dependencies
   - Restart services
   - Run health check
   - Rollback on failure (git checkout previous version)
3. Create `scripts/rollback.sh`:
   - Stop services
   - Checkout previous version (git tag or commit)
   - Install dependencies
   - Restart services
   - Verify health
4. Create version tagging: Tag releases with semantic versioning (v1.0.0)
5. Create `scripts/status.sh`:
   - Check service status (systemctl status)
   - Check IB connection
   - Check health check result
   - Display dashboard URL
   - Show recent log entries
6. Add deployment tests to `tests/integration/test_deployment.py`:
   - Test: Services start and stop correctly
   - Test: Health check returns correct status
   - Test: Backup script creates valid backup
   - Test: Deployment script is idempotent

**Acceptance Criteria:**
- Deployment script is idempotent (can run multiple times)
- Update script supports rollback on failure
- Rollback script restores previous working version
- Status script shows all critical info
- Deployment tests validate automation
- Scripts support --dry-run for testing

## Verification

### Manual Testing
1. Run deployment in test environment: `sudo ./scripts/deploy.sh --dry-run`
2. Start services: `sudo systemctl start v6-trading v6-dashboard v6-position-sync`
3. Check service status: `./scripts/status.sh`
4. Run health check: `./scripts/health_check.py`
5. Verify dashboard accessible: http://localhost:8501
6. Test graceful shutdown: `sudo systemctl stop v6-trading`
7. Test emergency shutdown: follow RUNBOOK procedures
8. Test backup: `./scripts/backup.sh`

### Automated Checks
```bash
# Test deployment scripts
pytest tests/integration/test_deployment.py -v

# Check service configuration
systemctl status v6-trading v6-dashboard v6-position-sync

# Verify health check
./scripts/health_check.py
echo $?  # Should be 0 (healthy)

# Check logs
journalctl -u v6-trading -n 50
```

## Success Criteria

- [ ] Production configuration enforces safety checks
- [ ] Systemd services installed and start correctly
- [ ] Production orchestrator runs all workflows
- [ ] Health checks monitor all critical components
- [ ] Backup script creates valid backups
- [ ] Deployment scripts are idempotent
- [ ] Runbook covers all common incidents
- [ ] Documentation is clear and comprehensive
- [ ] Deployment tested in staging environment
- [ ] System runs for 1 week without manual intervention
- [ ] All services auto-restart on failure
- [ ] Health check detects and reports issues

## Output

**Created Files:**
- `src/v6/config/production_config.py` (ProductionConfig dataclass)
- `src/v6/config/loader.py` (Config loader with env override)
- `config/production.yaml.example` (example production config)
- `systemd/v6-trading.service` (main trading service)
- `systemd/v6-dashboard.service` (dashboard service)
- `systemd/v6-position-sync.service` (position sync service)
- `systemd/v6-trading.timer` (timer for daily restart)
- `systemd/v6-health-check.service` (health check service)
- `systemd/v6-health-check.timer` (health check timer)
- `src/v6/orchestration/production.py` (ProductionOrchestrator)
- `scripts/run_production.py` (main production script)
- `scripts/health_check.py` (health check script)
- `scripts/install_services.sh` (install systemd services)
- `scripts/backup.sh` (backup script)
- `scripts/deploy.sh` (deployment script)
- `scripts/update.sh` (update script)
- `scripts/rollback.sh` (rollback script)
- `scripts/status.sh` (status check script)
- `tests/integration/test_deployment.py` (deployment tests)
- `docs/PRODUCTION_SETUP.md` (production setup guide)
- `docs/RUNBOOK.md` (operational procedures)
- `docs/MONITORING.md` (monitoring guide)
- `docs/BACKUP_RESTORE.md` (backup and restore procedures)
- `README.md` (project overview with links to docs)

**Modified Files:**
- `.env.example` (add production variables)
- `src/v6/dashboard/pages/4_health.py` (add health check widget)
- `.gitignore` (add config/production.yaml, backups/)

**Systemd Services:**
- `v6-trading.service` - Main trading system
- `v6-dashboard.service` - Monitoring dashboard
- `v6-position-sync.service` - Position synchronization
- `v6-trading.timer` - Daily restart timer
- `v6-health-check.service` - Health check runner
- `v6-health-check.timer` - Periodic health checks

**Documentation:**
- PRODUCTION_SETUP.md with:
  - Prerequisites (Python 3.11+, IB gateway)
  - Configuration (IB credentials, risk limits, logging)
  - Deployment (run deploy.sh, start services)
  - Verification (health check, dashboard)
- RUNBOOK.md with:
  - Daily operations checklist
  - Common incident procedures
  - Emergency procedures
- MONITORING.md with:
  - Metrics and thresholds
  - Dashboard usage
  - Log analysis
- BACKUP_RESTORE.md with:
  - Backup procedure
  - Restore procedure
  - Disaster recovery plan

**Tests Created:**
- 5+ deployment tests (services, health check, backup, deploy)
- All tests passing
- Deployment automation validated

**Deployment Checklist:**
- [ ] Run deploy.sh in test environment
- [ ] Verify all services start correctly
- [ ] Run health checks and confirm healthy
- [ ] Test backup and restore procedures
- [ ] Verify dashboard accessible
- [ ] Test graceful shutdown
- [ ] Test emergency shutdown
- [ ] Train operator on runbook procedures
- [ ] Deploy to production
- [ ] Monitor for 1 week before auto-trading
