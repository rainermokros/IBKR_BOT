#!/bin/bash
# Install systemd services for V6 trading system
# This script is idempotent - can be run multiple times safely

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SERVICES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/systemd"
SYSTEMD_DIR="/etc/systemd/system"
USER="trading"

echo "=========================================="
echo "V6 Trading Bot - Service Installation"
echo "=========================================="

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}Error: This script must be run as root${NC}"
   echo "Use: sudo ./scripts/install_services.sh"
   exit 1
fi

# Check if services directory exists
if [[ ! -d "$SERVICES_DIR" ]]; then
    echo -e "${RED}Error: Systemd services directory not found: $SERVICES_DIR${NC}"
    exit 1
fi

# Check if user exists
if ! id "$USER" &>/dev/null; then
    echo -e "${YELLOW}Warning: User '$USER' does not exist${NC}"
    echo "Creating user '$USER'..."
    useradd -r -s /bin/bash -d /opt/v6-trading "$USER"
    mkdir -p /opt/v6-trading
    chown "$USER:$USER" /opt/v6-trading
    echo -e "${GREEN}✓ Created user '$USER'${NC}"
else
    echo -e "${GREEN}✓ User '$USER' exists${NC}"
fi

# Copy service files
echo ""
echo "Installing systemd services..."

for service in v6-trading.service v6-dashboard.service v6-position-sync.service v6-trading.timer v6-health-check.service v6-health-check.timer ib-gateway.service; do
    if [[ -f "$SERVICES_DIR/$service" ]]; then
        cp "$SERVICES_DIR/$service" "$SYSTEMD_DIR/$service"
        echo -e "${GREEN}✓ Installed $service${NC}"
    else
        echo -e "${YELLOW}Warning: $service not found, skipping${NC}"
    fi
done

# Reload systemd daemon
echo ""
echo "Reloading systemd daemon..."
systemctl daemon-reload
echo -e "${GREEN}✓ Systemd daemon reloaded${NC}"

# Enable services (but don't start them)
echo ""
echo "Enabling services..."

# Enable main services
systemctl enable v6-trading.service 2>/dev/null && echo -e "${GREEN}✓ Enabled v6-trading.service${NC}" || echo -e "${YELLOW}Warning: Failed to enable v6-trading.service${NC}"
systemctl enable v6-dashboard.service 2>/dev/null && echo -e "${GREEN}✓ Enabled v6-dashboard.service${NC}" || echo -e "${YELLOW}Warning: Failed to enable v6-dashboard.service${NC}"
systemctl enable v6-position-sync.service 2>/dev/null && echo -e "${GREEN}✓ Enabled v6-position-sync.service${NC}" || echo -e "${YELLOW}Warning: Failed to enable v6-position-sync.service${NC}"

# Enable timers
systemctl enable v6-trading.timer 2>/dev/null && echo -e "${GREEN}✓ Enabled v6-trading.timer${NC}" || echo -e "${YELLOW}Warning: Failed to enable v6-trading.timer${NC}"
systemctl enable v6-health-check.timer 2>/dev/null && echo -e "${GREEN}✓ Enabled v6-health-check.timer${NC}" || echo -e "${YELLOW}Warning: Failed to enable v6-health-check.timer${NC}"

# Print status
echo ""
echo "=========================================="
echo "Installation Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Configure production settings:"
echo "   cp config/production.yaml.example config/production.yaml"
echo "   nano config/production.yaml"
echo ""
echo "2. Ensure IB Gateway is running:"
echo "   sudo systemctl start ib-gateway"
echo "   sudo systemctl status ib-gateway"
echo ""
echo "3. Start V6 services:"
echo "   sudo systemctl start v6-trading"
echo "   sudo systemctl start v6-dashboard"
echo "   sudo systemctl start v6-position-sync"
echo ""
echo "4. Check service status:"
echo "   systemctl status v6-trading"
echo "   systemctl status v6-dashboard"
echo "   systemctl status v6-position-sync"
echo ""
echo "5. View logs:"
echo "   journalctl -u v6-trading -f"
echo "   journalctl -u v6-dashboard -f"
echo ""
echo "6. Access dashboard:"
echo "   http://localhost:8501"
echo ""
echo "For more information, see: docs/PRODUCTION_SETUP.md"
echo ""
