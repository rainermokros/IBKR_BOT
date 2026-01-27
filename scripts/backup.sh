#!/bin/bash
# Backup script for V6 trading system
# Backs up Delta Lake tables, configuration files, and logs

set -e

# Configuration
BACKUP_PATH="${BACKUP_PATH:-backups/}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
COMPRESS="${COMPRESS:-true}"
UPLOAD_S3="${UPLOAD_S3:-false}"
S3_BUCKET="${S3_BUCKET:-s3://my-backups/v6-trading}"
UPLOAD_RSYNC="${UPLOAD_RSYNC:-false}"
RSYNC_DEST="${RSYNC_DEST:-user@remote-server:/backups/v6-trading}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Create backup directory
mkdir -p "$BACKUP_PATH"

# Timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="backup_${TIMESTAMP}"
BACKUP_DIR="/tmp/${BACKUP_NAME}"
mkdir -p "$BACKUP_DIR"

log_info "Creating backup: ${BACKUP_NAME}"

# Check if running as correct user (trading)
if [ "$(whoami)" != "trading" ] && [ "$(whoami)" != "root" ]; then
    log_warn "Not running as trading user, may have permission issues"
fi

# Copy Delta Lake tables
log_info "Backing up Delta Lake tables..."
if [ -d "data/lake" ]; then
    mkdir -p "$BACKUP_DIR/data/lake"
    cp -r data/lake/* "$BACKUP_DIR/data/lake/"
    log_info "✓ Delta Lake tables backed up"
else
    log_warn "Delta Lake directory not found: data/lake"
fi

# Copy configuration files
log_info "Backing up configuration files..."
mkdir -p "$BACKUP_DIR/config"
if [ -f "config/production.yaml" ]; then
    cp config/production.yaml "$BACKUP_DIR/config/"
    log_info "✓ Config backed up"
fi
if [ -f ".env" ]; then
    cp .env "$BACKUP_DIR/"
    log_info "✓ Environment variables backed up"
fi

# Copy logs (optional)
log_info "Backing up logs..."
if [ -d "logs" ]; then
    mkdir -p "$BACKUP_DIR/logs"
    cp -r logs/* "$BACKUP_DIR/logs/"
    log_info "✓ Logs backed up"
fi

# Create metadata
log_info "Creating backup metadata..."
cat > "$BACKUP_DIR/metadata.txt" <<EOF
Backup Name: ${BACKUP_NAME}
Timestamp: ${TIMESTAMP}
Date: $(date)
Hostname: $(hostname)
User: $(whoami)
EOF

# Compress backup
if [ "$COMPRESS" = "true" ]; then
    log_info "Compressing backup..."
    tar -czf "${BACKUP_PATH}${BACKUP_NAME}.tar.gz" -C /tmp "$BACKUP_NAME"
    BACKUP_FILE="${BACKUP_PATH}${BACKUP_NAME}.tar.gz"
    log_info "✓ Backup compressed: ${BACKUP_FILE}"
else
    tar -cf "${BACKUP_PATH}${BACKUP_NAME}.tar" -C /tmp "$BACKUP_NAME"
    BACKUP_FILE="${BACKUP_PATH}${BACKUP_NAME}.tar"
    log_info "✓ Backup created: ${BACKUP_FILE}"
fi

# Calculate checksum
log_info "Calculating checksum..."
sha256sum "$BACKUP_FILE" > "${BACKUP_FILE}.sha256"
log_info "✓ Checksum: $(cat ${BACKUP_FILE}.sha256 | cut -d' ' -f1)"

# Clean up temporary directory
rm -rf "$BACKUP_DIR"

# Upload to S3 (if enabled)
if [ "$UPLOAD_S3" = "true" ]; then
    log_info "Uploading to S3..."
    if command -v aws &> /dev/null; then
        aws s3 cp "$BACKUP_FILE" "${S3_BUCKET}/"
        aws s3 cp "${BACKUP_FILE}.sha256" "${S3_BUCKET}/"
        log_info "✓ Uploaded to S3"
    else
        log_error "AWS CLI not found, skipping S3 upload"
    fi
fi

# Upload via RSYNC (if enabled)
if [ "$UPLOAD_RSYNC" = "true" ]; then
    log_info "Uploading via RSYNC..."
    if command -v rsync &> /dev/null; then
        rsync -avz "$BACKUP_FILE" "$RSYNC_DEST"
        rsync -avz "${BACKUP_FILE}.sha256" "$RSYNC_DEST"
        log_info "✓ Uploaded via RSYNC"
    else
        log_error "RSYNC not found, skipping RSYNC upload"
    fi
fi

# Clean old backups
log_info "Cleaning old backups (older than ${RETENTION_DAYS} days)..."
find "$BACKUP_PATH" -name "backup_*.tar.gz" -mtime +${RETENTION_DAYS} -delete
find "$BACKUP_PATH" -name "backup_*.tar.gz.sha256" -mtime +${RETENTION_DAYS} -delete
log_info "✓ Old backups cleaned"

# Summary
BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
BACKUP_COUNT=$(find "$BACKUP_PATH" -name "backup_*.tar.gz" | wc -l)

echo ""
log_info "=========================================="
log_info "Backup Complete!"
log_info "=========================================="
log_info "Backup file: ${BACKUP_FILE}"
log_info "Backup size: ${BACKUP_SIZE}"
log_info "Total backups: ${BACKUP_COUNT}"
log_info "Retention: ${RETENTION_DAYS} days"
log_info "=========================================="
