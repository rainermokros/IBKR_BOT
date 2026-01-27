#!/bin/bash
# Status check script for V6 trading system
# Shows service status, IB connection, health check, dashboard URL

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "=========================================="
echo "V6 Trading Bot - System Status"
echo "=========================================="
echo ""

# Function to check service status
check_service() {
    SERVICE=$1
    if systemctl is-active --quiet "$SERVICE"; then
        echo -e "${GREEN}✓ $SERVICE: running${NC}"
        return 0
    else
        echo -e "${RED}✗ $SERVICE: stopped${NC}"
        return 1
    fi
}

# Function to check service enabled
check_enabled() {
    SERVICE=$1
    if systemctl is-enabled --quiet "$SERVICE"; then
        echo -e "${GREEN}  Enabled: Yes${NC}"
    else
        echo -e "${YELLOW}  Enabled: No${NC}"
    fi
}

# Check services
echo "=== Service Status ==="
check_service "v6-trading" && check_enabled "v6-trading"
check_service "v6-dashboard" && check_enabled "v6-dashboard"
check_service "v6-position-sync" && check_enabled "v6-position-sync"

# Check timers
echo ""
echo "=== Timer Status ==="
if systemctl is-active --quiet "v6-trading.timer"; then
    echo -e "${GREEN}✓ v6-trading.timer: active${NC}"
else
    echo -e "${YELLOW}○ v6-trading.timer: inactive${NC}"
fi

if systemctl is-active --quiet "v6-health-check.timer"; then
    echo -e "${GREEN}✓ v6-health-check.timer: active${NC}"
else
    echo -e "${YELLOW}○ v6-health-check.timer: inactive${NC}"
fi

# Check IB Gateway
echo ""
echo "=== IB Gateway ==="
if pgrep -f ibgateway &> /dev/null; then
    echo -e "${GREEN}✓ IB Gateway: running${NC}"
else
    echo -e "${RED}✗ IB Gateway: not running${NC}"
fi

# Health check
echo ""
echo "=== Health Check ==="
if [ -f "./scripts/health_check.py" ]; then
    ./scripts/health_check.py > /dev/null 2>&1
    HEALTH_EXIT_CODE=$?

    if [ $HEALTH_EXIT_CODE -eq 0 ]; then
        echo -e "${GREEN}✓ Overall: Healthy${NC}"
    elif [ $HEALTH_EXIT_CODE -eq 1 ]; then
        echo -e "${YELLOW}⚠ Overall: Degraded${NC}"
    else
        echo -e "${RED}✗ Overall: Unhealthy${NC}"
    fi
else
    echo -e "${YELLOW}○ Health check: script not found${NC}"
fi

# Dashboard URL
echo ""
echo "=== Dashboard ==="
echo -e "${BLUE}URL: http://localhost:8501${NC}"
if command -v curl &> /dev/null; then
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8501 | grep -q "200"; then
        echo -e "${GREEN}✓ Dashboard: accessible${NC}"
    else
        echo -e "${RED}✗ Dashboard: not accessible${NC}"
    fi
fi

# Recent log entries
echo ""
echo "=== Recent Logs (v6-trading) ==="
if command -v journalctl &> /dev/null; then
    journalctl -u v6-trading -n 5 --no-pager | grep -E "ERROR|WARNING|INFO" | tail -5
fi

# System resources
echo ""
echo "=== System Resources ==="
if command -v free &> /dev/null; then
    MEM_USAGE=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
    if (( $(echo "$MEM_USAGE > 90" | bc -l) )); then
        echo -e "${RED}✗ Memory: ${MEM_USAGE}%${NC}"
    elif (( $(echo "$MEM_USAGE > 80" | bc -l) )); then
        echo -e "${YELLOW}⚠ Memory: ${MEM_USAGE}%${NC}"
    else
        echo -e "${GREEN}✓ Memory: ${MEM_USAGE}%${NC}"
    fi
fi

if command -v df &> /dev/null; then
    DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
    if [ "$DISK_USAGE" -gt 90 ]; then
        echo -e "${RED}✗ Disk: ${DISK_USAGE}%${NC}"
    elif [ "$DISK_USAGE" -gt 80 ]; then
        echo -e "${YELLOW}⚠ Disk: ${DISK_USAGE}%${NC}"
    else
        echo -e "${GREEN}✓ Disk: ${DISK_USAGE}%${NC}"
    fi
fi

if command -v uptime &> /dev/null; then
    UPTIME=$(uptime -p 2>/dev/null || uptime | awk '{print $3,$4}')
    echo -e "${BLUE}Uptime: $UPTIME${NC}"
fi

# Summary
echo ""
echo "=========================================="
echo "For more details, run:"
echo "  systemctl status v6-trading"
echo "  journalctl -u v6-trading -f"
echo "  ./scripts/health_check.py"
echo "=========================================="
