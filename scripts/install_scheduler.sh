#!/bin/bash
#
# Install V6 Trading System Scheduler
#
# This script sets up the ET-based cron scheduler with holiday awareness.
# Run as root or with sudo.
#

set -e

echo "=========================================="
echo "V6 Trading System - Scheduler Installation"
echo "=========================================="
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "Error: This script must be run as root (use sudo)"
   exit 1
fi

# Project directory
PROJECT_DIR="/home/bigballs/project/bot/v6"
CRON_FILE="/etc/cron.d/v6-trading"

# Check if project directory exists
if [[ ! -d "$PROJECT_DIR" ]]; then
    echo "Error: Project directory not found: $PROJECT_DIR"
    exit 1
fi

# Check if crontab file exists
CRON_SOURCE="$PROJECT_DIR/crontab.txt"
if [[ ! -f "$CRON_SOURCE" ]]; then
    echo "Error: Crontab file not found: $CRON_SOURCE"
    exit 1
fi

# Backup existing cron file if it exists
if [[ -f "$CRON_FILE" ]]; then
    BACKUP_FILE="${CRON_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    echo "Backing up existing cron file to: $BACKUP_FILE"
    cp "$CRON_FILE" "$BACKUP_FILE"
fi

# Copy crontab file
echo "Installing cron configuration to: $CRON_FILE"
cp "$CRON_SOURCE" "$CRON_FILE"

# Set proper permissions
chmod 644 "$CRON_FILE"
echo "✓ Set permissions: 644"

# Make cron wrapper executable
WRAPPER="$PROJECT_DIR/scripts/cron_wrapper.sh"
if [[ -f "$WRAPPER" ]]; then
    chmod +x "$WRAPPER"
    echo "✓ Made cron wrapper executable: $WRAPPER"
else
    echo "Warning: Cron wrapper not found: $WRAPPER"
fi

# Make scripts executable
echo "Making scripts executable..."
find "$PROJECT_DIR/scripts" -name "*.py" -type f -exec chmod +x {} \;
echo "✓ All Python scripts are now executable"

# Restart cron service
echo ""
echo "Restarting cron service..."
if command -v systemctl &> /dev/null; then
    systemctl restart cron
    echo "✓ Cron service restarted (systemctl)"
elif command -v service &> /dev/null; then
    service cron restart
    echo "✓ Cron service restarted (service)"
else
    echo "Warning: Could not restart cron service automatically"
    echo "Please restart cron manually"
fi

# Verify cron file
echo ""
echo "Verifying cron installation..."
if [[ -f "$CRON_FILE" ]]; then
    echo "✓ Cron file installed: $CRON_FILE"
    echo ""
    echo "Scheduled tasks:"
    grep -v "^#" "$CRON_FILE" | grep -v "^$" | wc -l | xargs echo "  Total jobs:"
    echo ""
    echo "Pre-market tasks:"
    grep "8 \* \* \*" "$CRON_FILE" | grep -v "^#" | wc -l | xargs echo "    "
    echo ""
    echo "Market hours tasks:"
    grep "9-16" "$CRON_FILE" | grep -v "^#" | wc -l | xargs echo "    "
    echo ""
    echo "Post-market tasks:"
    grep "16-18" "$CRON_FILE" | grep -v "^#" | wc -l | xargs echo "    "
fi

echo ""
echo "=========================================="
echo "Installation Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. View scheduled jobs: crontab -l (or cat $CRON_FILE)"
echo "  2. Monitor logs: tail -f /tmp/v6_*.log"
echo "  3. Configure tasks via dashboard: http://localhost:8501 -> Scheduler"
echo "  4. Test individual scripts: cd $PROJECT_DIR && python scripts/health_check.py"
echo ""
echo "To uninstall:"
echo "  sudo rm $CRON_FILE"
echo "  sudo service cron restart"
echo ""
