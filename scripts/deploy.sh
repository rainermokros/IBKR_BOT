#!/bin/bash
# Deployment script for V6 trading system
# Installs dependencies, creates user, sets up systemd services

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="/opt/v6-trading"
USER="trading"
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "=========================================="
echo "V6 Trading Bot - Deployment"
echo "=========================================="
echo ""

if [ "$DRY_RUN" = "true" ]; then
    echo -e "${YELLOW}DRY RUN MODE - No changes will be made${NC}"
    echo ""
fi

# Functions
run_cmd() {
    if [ "$DRY_RUN" = "true" ]; then
        echo -e "${YELLOW}[DRY-RUN]${NC} $1"
    else
        echo -e "${GREEN}[EXEC]${NC} $1"
        eval "$1"
    fi
}

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
log_info "Checking prerequisites..."

# Check Python version
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | awk '{print $2}')
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
    if [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -ge 11 ]; then
        log_info "✓ Python $PYTHON_VERSION (>= 3.11)"
    else
        log_error "Python 3.11+ required, found $PYTHON_VERSION"
        exit 1
    fi
else
    log_error "Python 3 not found"
    exit 1
fi

# Check for IB Gateway
if pgrep -f ibgateway &> /dev/null; then
    log_info "✓ IB Gateway is running"
else
    log_warn "IB Gateway not running (install and start before using)"
fi

# Check for uv or pip
if command -v uv &> /dev/null; then
    PACKAGE_MANAGER="uv"
    log_info "✓ uv package manager found"
elif command -v pip &> /dev/null; then
    PACKAGE_MANAGER="pip"
    log_info "✓ pip package manager found"
else
    log_error "No package manager found (uv or pip required)"
    exit 1
fi

# Create user
log_info "Creating user '$USER'..."
if id "$USER" &>/dev/null; then
    log_info "✓ User '$USER' already exists"
else
    run_cmd "sudo useradd -r -s /bin/bash -d $DEPLOY_DIR $USER"
    run_cmd "sudo mkdir -p $DEPLOY_DIR"
    run_cmd "sudo chown $USER:$USER $DEPLOY_DIR"
    log_info "✓ Created user '$USER'"
fi

# Create deploy directory
log_info "Creating deploy directory..."
run_cmd "sudo mkdir -p $DEPLOY_DIR"

# Copy project files
log_info "Copying project files..."
run_cmd "sudo cp -r $PROJECT_DIR/* $DEPLOY_DIR/"
run_cmd "sudo chown -R $USER:$USER $DEPLOY_DIR"
log_info "✓ Project files copied to $DEPLOY_DIR"

# Install dependencies
log_info "Installing Python dependencies..."
cd "$DEPLOY_DIR"
if [ "$PACKAGE_MANAGER" = "uv" ]; then
    run_cmd "cd $DEPLOY_DIR && uv sync"
else
    run_cmd "cd $DEPLOY_DIR && pip install -e ."
fi
log_info "✓ Dependencies installed"

# Install systemd services
log_info "Installing systemd services..."
if [ -f "$DEPLOY_DIR/scripts/install_services.sh" ]; then
    run_cmd "cd $DEPLOY_DIR && sudo ./scripts/install_services.sh"
    log_info "✓ Systemd services installed"
else
    log_error "install_services.sh not found"
    exit 1
fi

# Create necessary directories
log_info "Creating data directories..."
run_cmd "mkdir -p $DEPLOY_DIR/logs"
run_cmd "mkdir -p $DEPLOY_DIR/backups"
run_cmd "mkdir -p $DEPLOY_DIR/data/lake"
run_cmd "sudo chown -R $USER:$USER $DEPLOY_DIR/logs $DEPLOY_DIR/backups $DEPLOY_DIR/data"
log_info "✓ Data directories created"

# Set permissions
log_info "Setting permissions..."
run_cmd "chmod +x $DEPLOY_DIR/scripts/*.sh"
run_cmd "chmod +x $DEPLOY_DIR/scripts/*.py"
log_info "✓ Permissions set"

# Summary
echo ""
log_info "=========================================="
log_info "Deployment Complete!"
log_info "=========================================="
echo ""
log_info "Next steps:"
echo ""
echo "1. Configure production settings:"
echo "   cp $DEPLOY_DIR/config/production.yaml.example $DEPLOY_DIR/config/production.yaml"
echo "   nano $DEPLOY_DIR/config/production.yaml"
echo ""
echo "2. Configure environment variables (optional):"
echo "   cp $DEPLOY_DIR/.env.example $DEPLOY_DIR/.env"
echo "   nano $DEPLOY_DIR/.env"
echo ""
echo "3. Ensure IB Gateway is running and logged in"
echo ""
echo "4. Start services:"
echo "   sudo systemctl start v6-trading v6-dashboard v6-position-sync"
echo ""
echo "5. Enable services (start on boot):"
echo "   sudo systemctl enable v6-trading v6-dashboard v6-position-sync"
echo ""
echo "6. Check service status:"
echo "   systemctl status v6-trading v6-dashboard v6-position-sync"
echo ""
echo "7. Check logs:"
echo "   journalctl -u v6-trading -f"
echo ""
echo "8. Access dashboard:"
echo "   http://localhost:8501"
echo ""
echo "For more information, see: $DEPLOY_DIR/docs/PRODUCTION_SETUP.md"
echo ""

if [ "$DRY_RUN" = "true" ]; then
    log_warn "This was a dry run - no changes were made"
    log_warn "Run without --dry-run to perform actual deployment"
fi
