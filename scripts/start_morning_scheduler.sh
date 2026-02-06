#!/bin/bash
#
# Morning Scheduler Startup Script
#
# This script runs the morning scheduler at 9:00 AM ET to collect
# historical ETF data (SPY, QQQ, IWM) from IB Gateway.
#
# Usage:
#   ./start_morning_scheduler.sh         # Normal run (time check enforced)
#   ./start_morning_scheduler.sh --force  # Force run (skip time check)
#
# Cron setup:
#   0 9 * * 1-5 /home/bigballs/project/bot/v6/scripts/start_morning_scheduler.sh
#
# Logs to: logs/morning_scheduler_YYYYMMDD.log

set -e  # Exit on error

# Project root directory
PROJECT_ROOT="/home/bigballs/project/bot"
cd "$PROJECT_ROOT"

# Activate virtual environment if it exists
if [ -f "venv/bin/activate" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
elif [ -f "../venv/bin/activate" ]; then
    echo "Activating virtual environment (parent directory)..."
    source ../venv/bin/activate
else
    echo "No virtual environment found, using system Python"
fi

# Create logs directory if it doesn't exist
mkdir -p logs/scheduler

# Log file with date stamp
LOG_FILE="logs/scheduler/morning_scheduler_$(date +%Y%m%d).log"

echo "=========================================="
echo "Morning Scheduler - $(date)"
echo "=========================================="
echo "Project root: $PROJECT_ROOT"
echo "Log file: $LOG_FILE"
echo "=========================================="

# Change to v6 directory (module path)
cd v6

# Run the morning scheduler and capture output
# Pass any arguments (e.g., --force)
if python -m src.v6.scheduler.morning_scheduler "$@" 2>&1 | tee -a "../$LOG_FILE"; then
    # Success
    EXIT_CODE=0
    STATUS="SUCCESS"
else
    # Failure
    EXIT_CODE=$?
    STATUS="FAILED"

    # Optional: Send email on failure (configure if needed)
    # if command -v mail &> /dev/null; then
    #     echo "Morning scheduler failed with exit code $EXIT_CODE. Check log: $LOG_FILE" | \
    #         mail -s "Morning Scheduler Failed - $(date)" your@email.com
    # fi
fi

echo "=========================================="
echo "Status: $STATUS (exit code: $EXIT_CODE)"
echo "=========================================="

exit $EXIT_CODE
