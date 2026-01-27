#!/bin/bash
# Update script for V6 trading system
# Pulls latest code, updates dependencies, restarts services

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
DEPLOY_DIR="/opt/v6-trading"
BACKUP_BEFORE_UPDATE=true

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

echo "=========================================="
echo "V6 Trading Bot - Update"
echo "=========================================="
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   log_error "This script must be run as root"
   echo "Use: sudo ./scripts/update.sh"
   exit 1
fi

# Backup before update
if [ "$BACKUP_BEFORE_UPDATE" = "true" ]; then
    log_info "Creating backup before update..."
    if [ -f "$DEPLOY_DIR/scripts/backup.sh" ]; then
        cd "$DEPLOY_DIR"
        sudo -u trading ./scripts/backup.sh
        log_info "✓ Backup created"
    else
        log_warn "Backup script not found, skipping backup"
    fi
fi

# Stop services
log_info "Stopping services..."
systemctl stop v6-trading v6-dashboard v6-position-sync
log_info "✓ Services stopped"

# Pull latest code
log_info "Pulling latest code..."
cd "$DEPLOY_DIR"
if [ -d ".git" ]; then
    sudo -u trading git pull
    log_info "✓ Code updated"
else
    log_warn "Not a git repository, skipping git pull"
fi

# Install updated dependencies
log_info "Installing dependencies..."
if command -v uv &> /dev/null; then
    sudo -u trading uv sync
elif command -v pip &> /dev/null; then
    sudo -u trading pip install -e .
else
    log_error "No package manager found"
    exit 1
fi
log_info "✓ Dependencies installed"

# Restart services
log_info "Restarting services..."
systemctl start v6-trading v6-dashboard v6-position-sync
log_info "✓ Services restarted"

# Wait for services to start
sleep 5

# Health check
log_info "Running health check..."
if [ -f "$DEPLOY_DIR/scripts/health_check.py" ]; then
    sudo -u trading python3 $DEPLOY_DIR/scripts/health_check.py
    HEALTH_EXIT_CODE=$?

    if [ $HEALTH_EXIT_CODE -eq 0 ]; then
        log_info "✓ Health check passed"
    elif [ $HEALTH_EXIT_CODE -eq 1 ]; then
        log_warn "Health check: Degraded"
    else
        log_error "Health check: Failed - Rolling back update"

        # Rollback
        log_info "Rolling back update..."
        systemctl stop v6-trading v6-dashboard v6-position-sync
        sudo -u trading git checkout -
        sudo -u trading uv sync  # or pip install -e .
        systemctl start v6-trading v6-dashboard v6-position-sync
        log_error "✓ Update rolled back"
        exit 1
    fi
else
    log_warn "Health check script not found, skipping"
fi

# Summary
echo ""
log_info "=========================================="
log_info "Update Complete!"
log_info "=========================================="
echo ""
echo "Services restarted and healthy"
echo ""
echo "Check service status:"
echo "  systemctl status v6-trading v6-dashboard v6-position-sync"
echo ""
echo "View logs:"
echo "  journalctl -u v6-trading -f"
echo ""
