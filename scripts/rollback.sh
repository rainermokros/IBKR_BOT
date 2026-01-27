#!/bin/bash
# Rollback script for V6 trading system
# Rolls back to previous version

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
DEPLOY_DIR="/opt/v6-trading"

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
echo "V6 Trading Bot - Rollback"
echo "=========================================="
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   log_error "This script must be run as root"
   echo "Use: sudo ./scripts/rollback.sh"
   exit 1
fi

# Check arguments
if [ $# -eq 0 ]; then
    log_error "Usage: ./scripts/rollback.sh <commit|tag>"
    echo "Example: ./scripts/rollback.sh abc123f"
    echo "Example: ./scripts/rollback.sh v1.0.0"
    exit 1
fi

TARGET=$1

# Stop services
log_info "Stopping services..."
systemctl stop v6-trading v6-dashboard v6-position-sync
log_info "✓ Services stopped"

# Backup current state
log_info "Backing up current state..."
if [ -f "$DEPLOY_DIR/scripts/backup.sh" ]; then
    cd "$DEPLOY_DIR"
    sudo -u trading ./scripts/backup.sh
    log_info "✓ Backup created"
else
    log_warn "Backup script not found, skipping backup"
fi

# Rollback code
log_info "Rolling back to $TARGET..."
cd "$DEPLOY_DIR"
if [ -d ".git" ]; then
    sudo -u trading git checkout "$TARGET"
    log_info "✓ Code rolled back to $TARGET"
else
    log_error "Not a git repository, cannot rollback"
    exit 1
fi

# Install dependencies
log_info "Reinstalling dependencies..."
if command -v uv &> /dev/null; then
    sudo -u trading uv sync
elif command -v pip &> /dev/null; then
    sudo -u trading pip install -e .
else
    log_error "No package manager found"
    exit 1
fi
log_info "✓ Dependencies reinstalled"

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
        log_error "Health check: Failed - Check logs manually"
    fi
else
    log_warn "Health check script not found, skipping"
fi

# Summary
echo ""
log_info "=========================================="
log_info "Rollback Complete!"
log_info "=========================================="
echo ""
echo "Rolled back to: $TARGET"
echo ""
echo "Check service status:"
echo "  systemctl status v6-trading v6-dashboard v6-position-sync"
echo ""
echo "View logs:"
echo "  journalctl -u v6-trading -f"
echo ""
