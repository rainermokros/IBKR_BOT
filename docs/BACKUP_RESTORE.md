# Backup and Restore Guide

This guide covers backup procedures, restore procedures, and disaster recovery for the V6 trading system.

## Table of Contents

- [Backup Procedure](#backup-procedure)
- [Automated Backup Script](#automated-backup-script)
- [Restore Procedure](#restore-procedure)
- [Disaster Recovery](#disaster-recovery)
- [Testing Backups](#testing-backups)

---

## Backup Procedure

### What to Backup

1. **Delta Lake Tables** (Critical)
   - `data/lake/position_updates/` - Position history
   - `data/lake/option_snapshots/` - Option chain snapshots
   - `data/lake/option_legs/` - Option leg details
   - `data/lake/strategy_executions/` - Strategy execution history

2. **Configuration Files** (Important)
   - `config/production.yaml` - Production configuration
   - `.env` - Environment variables

3. **Logs** (Optional, for debugging)
   - `logs/` - Application logs
   - Systemd logs (via `journalctl`)

### Backup Strategy

**Frequency:** Daily (after market close)

**Retention:** 30 days

**Storage:** Local backup directory + optional remote (S3, RSYNC, etc.)

**Compression:** gzip (saves ~80% space)

### Manual Backup

```bash
# Run backup script
./scripts/backup.sh

# Output: backups/backup_20260127_160000.tar.gz
```

**What gets backed up:**
- All Delta Lake tables
- Configuration files
- Backup metadata (timestamp, checksum)

### Backup Script Usage

```bash
# Run backup
./scripts/backup.sh

# Dry-run (show what would be backed up)
./scripts/backup.sh --dry-run

# Custom backup path
./scripts/backup.sh --path /mnt/backups

# Upload to remote (if configured)
./scripts/backup.sh --upload-s3
```

---

## Automated Backup Script

### Location

`scripts/backup.sh`

### Features

- **Incremental backup:** Only backs up changes since last backup
- **Compression:** Uses gzip to reduce backup size
- **Checksums:** Verifies backup integrity
- **Retention:** Automatically cleans old backups (> 30 days)
- **Remote upload:** Optional upload to S3 or RSYNC
- **Logging:** Logs all operations

### Configuration

Edit `scripts/backup.sh` to configure:

```bash
# Backup settings
BACKUP_PATH="backups/"
RETENTION_DAYS=30
COMPRESS=true
UPLOAD_S3=false
S3_BUCKET="s3://my-backups/v6-trading"
UPLOAD_RSYNC=false
RSYNC_DEST="user@remote-server:/backups/v6-trading"
```

### Systemd Timer (Optional)

To automate daily backups, create a systemd timer:

**File:** `/etc/systemd/system/v6-backup.service`

```ini
[Unit]
Description=V6 Trading Bot - Daily backup

[Service]
Type=oneshot
User=trading
WorkingDirectory=/opt/v6-trading
ExecStart=/usr/bin/python /opt/v6-trading/scripts/backup.sh
StandardOutput=journal
StandardError=journal
SyslogIdentifier=v6-backup
```

**File:** `/etc/systemd/system/v6-backup.timer`

```ini
[Unit]
Description=Timer for v6-backup (daily backup after market close)

[Timer]
# Run daily at 5 PM ET (after market close)
OnCalendar=Mon-Fri 17:00
AccuracySec=1h

[Install]
WantedBy=timers.target
```

**Enable timer:**
```bash
sudo systemctl enable v6-backup.timer
sudo systemctl start v6-backup.timer

# Verify
systemctl list-timers v6-backup.timer
```

---

## Restore Procedure

### When to Restore

- Data corruption
- Accidental deletion
- Disaster recovery (server failure)
- Testing backup integrity

### Pre-Restore Checklist

- [ ] Stop all services
- [ ] Verify backup integrity
- [ ] Document current state (logs, positions)
- [ ] Plan restore steps
- [ ] Have rollback plan ready

### Step-by-Step Restore

#### 1. Stop All Services

```bash
# Stop V6 services
systemctl stop v6-trading v6-position-sync v6-dashboard

# Verify stopped
systemctl status v6-trading v6-position-sync v6-dashboard
```

#### 2. Identify Backup to Restore

```bash
# List backups
ls -lh backups/

# Choose backup (e.g., backup_20260127_160000.tar.gz)
# Verify backup integrity
tar -tzf backups/backup_20260127_160000.tar.gz | head -20
```

#### 3. Backup Current State (Rollback)

```bash
# In case restore fails, backup current state
tar -czf backups/emergency_backup_$(date +%Y%m%d_%H%M%S).tar.gz data/lake/
```

#### 4. Extract Backup

```bash
# Extract to temporary directory
tar -xzf backups/backup_20260127_160000.tar.gz -C /tmp/v6-restore/

# Verify contents
ls -lh /tmp/v6-restore/
```

#### 5. Restore Delta Lake Tables

```bash
# Stop any services that might be accessing Delta Lake
systemctl stop v6-trading v6-position-sync

# Backup current Delta Lake (if not done already)
mv data/lake data/lake.backup.$(date +%Y%m%d_%H%M%S)

# Restore from backup
cp -r /tmp/v6-restore/data/lake data/lake

# Verify restored data
ls -lh data/lake/
```

#### 6. Restore Configuration (Optional)

```bash
# If restoring config, backup current config first
cp config/production.yaml config/production.yaml.backup

# Restore config
cp /tmp/v6-restore/config/production.yaml config/production.yaml
```

#### 7. Reconcile with IB

```bash
# Start position sync to reconcile with IB
systemctl start v6-position-sync

# Wait for sync to complete
sleep 60

# Verify sync
# Dashboard → Positions page should match IB account
```

#### 8. Start Services

```bash
# Start all services
systemctl start v6-trading v6-dashboard

# Verify services started
systemctl status v6-trading v6-position-sync v6-dashboard
```

#### 9. Verify Restore

```bash
# Run health check
./scripts/health_check.py

# Check dashboard
# Open http://localhost:8501
# Verify: Positions match IB, Greeks correct, P&L accurate

# Check logs
journalctl -u v6-trading -n 50
```

#### 10. Cleanup (If Successful)

```bash
# Remove temporary restore directory
rm -rf /tmp/v6-restore/

# Remove old Delta Lake backup (after verification)
rm -rf data/lake.backup.*
```

### Rollback (If Restore Fails)

```bash
# Stop services
systemctl stop v6-trading v6-position-sync v6-dashboard

# Restore pre-restore state
rm -rf data/lake
mv data/lake.backup.* data/lake

# Start services
systemctl start v6-trading v6-position-sync v6-dashboard
```

---

## Disaster Recovery

### Recovery Time Objective (RTO)

**Target:** 2 hours

**Breakdown:**
- Backup retrieval: 30 minutes
- Restore process: 1 hour
- Verification: 30 minutes

### Recovery Point Objective (RPO)

**Target:** 1 day

**Explanation:** Maximum acceptable data loss is 1 day (since last backup)

### Disaster Scenarios

#### Scenario 1: Server Failure

**Impact:** Complete system unavailability

**Recovery Steps:**
1. Provision new server
2. Install dependencies (Python, IB Gateway, etc.)
3. Copy project files from git repository
4. Download latest backup from remote storage
5. Restore Delta Lake tables
6. Configure IB Gateway
7. Start services
8. Verify health

**Time to Recovery:** 4-6 hours

#### Scenario 2: Data Corruption

**Impact:** Delta Lake data corrupted, system unusable

**Recovery Steps:**
1. Stop all services
2. Identify corruption (health check, logs)
3. Determine last known good backup
4. Restore from backup
5. Reconcile with IB (force sync)
6. Verify data integrity
7. Start services

**Time to Recovery:** 1-2 hours

#### Scenario 3: IB Gateway Failure

**Impact:** Cannot trade, but data intact

**Recovery Steps:**
1. Restart IB Gateway
2. If restart fails, reinstall IB Gateway
3. Verify IB Gateway login
4. Restart V6 services
5. Verify IB connection

**Time to Recovery:** 15-30 minutes

#### Scenario 4: Accidental Deletion

**Impact:** Critical data deleted

**Recovery Steps:**
1. Stop services to prevent further damage
2. Identify deleted data
3. Restore from backup
4. Reconcile with IB
5. Verify restored data
6. Implement safeguards to prevent recurrence

**Time to Recovery:** 1-2 hours

### Off-Site Backup Strategy

**Options:**

1. **AWS S3**
   - Cost: ~$0.023/GB/month
   - Upload: `aws s3 sync backups/ s3://my-backups/v6-trading/`
   - Retention: Lifecycle policy to delete old backups

2. **RSYNC to Remote Server**
   - Cost: Cost of remote server
   - Upload: `rsync -avz backups/ user@remote:/backups/v6-trading/`
   - Retention: Manual cleanup on remote

3. **Google Cloud Storage**
   - Cost: ~$0.020/GB/month
   - Upload: `gsutil -m rsync -r backups/ gs://my-backups/v6-trading/`

**Recommendation:** Use S3 with lifecycle policy for automatic cleanup

---

## Testing Backups

### Test Backup Integrity

```bash
# Verify backup file is not corrupted
tar -tzf backups/backup_20260127_160000.tar.gz > /dev/null && echo "Backup OK" || echo "Backup CORRUPTED"

# Verify checksum (if generated)
sha256sum -c backups/backup_20260127_160000.tar.gz.sha256
```

### Test Restore Procedure

**Frequency:** Monthly

**Procedure:**
1. Create test environment (separate from production)
2. Copy latest backup to test environment
3. Perform restore (following restore procedure)
4. Verify:
   - Delta Lake tables accessible
   - Data integrity (row counts, checksums)
   - Dashboard displays data correctly
5. Document results

**Success Criteria:**
- All Delta Lake tables restored
- Data integrity verified
- No errors in logs
- Dashboard displays data

### Test Recovery Time

**Frequency:** Quarterly

**Procedure:**
1. Simulate disaster (stop services, delete data)
2. Time the restore procedure
3. Compare to RTO (2 hours)
4. If over RTO, optimize restore procedure

---

## Backup Best Practices

1. **Automate backups:** Use systemd timer or cron job
2. **Test backups regularly:** Monthly integrity checks
3. **Store off-site:** Use S3, RSYNC, or similar
4. **Encrypt backups:** If backing up to cloud
5. **Document procedures:** Keep this guide up to date
6. **Monitor backup failures:** Alert if backup fails
7. **Version control config:** Keep config in git (excluding secrets)
8. **Retain multiple backups:** Don't rely on single backup

---

## Troubleshooting

### Backup Fails

**Symptoms:** Backup script exits with error

**Diagnosis:**
```bash
# Run backup with verbose output
bash -x scripts/backup.sh

# Check disk space
df -h

# Check permissions
ls -la data/lake/
```

**Common Issues:**
- Disk full: Clean up old backups
- Permission denied: Run as correct user (trading)
- File in use: Stop services before backup

### Restore Fails

**Symptoms:** Restore process exits with error

**Diagnosis:**
```bash
# Check backup integrity
tar -tzf backups/backup_YYYYMMDD_HHMMSS.tar.gz

# Check disk space
df -h

# Check logs
journalctl -u v6-trading -n 50
```

**Common Issues:**
- Backup corrupted: Use earlier backup
- Disk full: Free up space
- Permission denied: Run as correct user
- Delta Lake locked: Stop services accessing Delta Lake

### Backup Too Large

**Symptoms:** Backup size > 10GB, slow to upload

**Solutions:**
- **Clean old data:** Delete old Delta Lake snapshots (time travel)
- **Incremental backup:** Only backup changes since last backup
- **Compression:** Enable gzip compression
- **Partitioning:** Partition Delta Lake tables by date

---

**Last updated:** 2026-01-27
