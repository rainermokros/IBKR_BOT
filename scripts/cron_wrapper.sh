#!/bin/bash
#
# Holiday-Aware Cron Wrapper for V6 Trading System
#
# This wrapper checks if today is a NYSE trading day before executing
# the target script. Only runs scripts on trading days.
#
# Usage in crontab:
#   0 8 * * 1-5 /path/to/cron_wrapper.sh /path/to/script.py >> /tmp/v6.log 2>&1
#
# Features:
# - Checks NYSE trading calendar
# - Logs skipped executions (holidays, weekends)
# - Supports force-run mode for maintenance
# - Returns proper exit codes for cron
#

set -euo pipefail

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Python interpreter - first argument is Python path, default to conda ib environment
PYTHON="${1:-/home/bigballs/miniconda3/envs/ib/bin/python}"
SCRIPT_PATH="${2:-}"  # Second argument is the actual script to run

# Shift arguments so $1 is now the first script argument
shift 2
SCRIPT_ARGS=("$@")

# Log file
LOG_DIR="${PROJECT_ROOT}/logs/scheduler"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/cron_wrapper.log"

# Logging function
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date -u +"%Y-%m-%d %H:%M:%S UTC")
    echo "[${timestamp}] [${level}] ${message}" | tee -a "${LOG_FILE}"
}

# Check if trading day using Python
is_trading_day() {
    local check_date="${1:-today}"

    "${PYTHON}" -c "
import sys
sys.path.insert(0, '${PROJECT_ROOT}/src')

from datetime import datetime
from v6.scheduler.nyse_calendar import NYSECalendar

cal = NYSECalendar()

if '${check_date}' == 'today':
    check_dt = datetime.now()
else:
    # Parse date string if provided
    from datetime import date
    y, m, d = map(int, '${check_date}'.split('-'))
    check_dt = datetime.combine(date(y, m, d), datetime.now().time())

is_trading = cal.is_trading_day(check_dt.date())
is_market_hours = cal.is_market_hours(check_dt)
market_phase = cal.get_market_phase(check_dt)

print(f'{is_trading}|{is_market_hours}|{market_phase}')
" 2>/dev/null
}

# Main execution
main() {
    local target_script="$SCRIPT_PATH"
    local script_args=("${SCRIPT_ARGS[@]:-}")

    # Check if Python path is valid
    if [[ ! -f "${PYTHON}" ]]; then
        log "ERROR" "Python interpreter not found: ${PYTHON}"
        exit 1
    fi

    # Check if target script exists
    if [[ ! -f "${target_script}" ]]; then
        log "ERROR" "Script not found: ${target_script}"
        exit 1
    fi

    # Get script name for logging
    local script_name="$(basename "${target_script}")"

    log "INFO" "=================================================="
    log "INFO" "Cron Wrapper: ${script_name}"
    log "INFO" "=================================================="

    # Check if FORCE_RUN is set (for maintenance)
    if [[ "${FORCE_RUN:-}" == "true" ]]; then
        log "WARN" "FORCE_RUN enabled - executing regardless of trading day"
        log "INFO" "Executing: ${target_script} ${script_args[*]:-}"

        # Execute the script
        cd "${PROJECT_ROOT}"
        exec "${PYTHON}" "${target_script}" "${script_args[@]:-}"
    fi

    # Check if today is a trading day
    log "INFO" "Checking if today is a trading day..."
    local trading_result
    trading_result=$(is_trading_day "today")

    if [[ -z "${trading_result}" ]]; then
        log "ERROR" "Failed to check trading day status"
        exit 1
    fi

    IFS='|' read -r is_trading is_market_hours market_phase <<< "${trading_result}"

    log "INFO" "Trading Day: ${is_trading}"
    log "INFO" "Market Hours: ${is_market_hours}"
    log "INFO" "Market Phase: ${market_phase}"

    # Only run if it's a trading day
    if [[ "${is_trading}" != "True" ]]; then
        log "INFO" "Not a trading day - skipping execution"
        log "INFO" "To force run, set FORCE_RUN=true in environment"
        exit 0  # Success - this is expected behavior
    fi

    # Optional: Check if within market hours (for some scripts)
    if [[ "${REQUIRE_MARKET_HOURS:-false}" == "true" ]]; then
        if [[ "${is_market_hours}" != "True" ]]; then
            log "INFO" "Outside market hours - skipping (REQUIRE_MARKET_HOURS=true)"
            exit 0
        fi
    fi

    # Execute the target script
    log "INFO" "Trading day confirmed - executing script"
    log "INFO" "Python: ${PYTHON}"
    log "INFO" "Executing: ${target_script} ${script_args[*]:-}"

    cd "${PROJECT_ROOT}"
    exec "${PYTHON}" "${target_script}" "${script_args[@]:-}"
}

# Run main function
# Note: Arguments already shifted above
main
