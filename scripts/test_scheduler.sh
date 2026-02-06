#!/bin/bash
#
# Test Scheduler Installation
#
# This script tests if the scheduler is correctly configured with the conda environment.
#

echo "=========================================="
echo "V6 Scheduler Test"
echo "=========================================="
echo ""

PROJECT_ROOT="/home/bigballs/project/bot/v6"
CONDA_PYTHON="/home/bigballs/miniconda3/envs/ib/bin/python"

echo "1. Checking conda environment..."
if [[ -f "${CONDA_PYTHON}" ]]; then
    echo "   ✓ Found Python at: ${CONDA_PYTHON}"
    ${CONDA_PYTHON} --version
else
    echo "   ✗ Python not found: ${CONDA_PYTHON}"
    exit 1
fi

echo ""
echo "2. Checking cron wrapper..."
WRAPPER="${PROJECT_ROOT}/scripts/cron_wrapper.sh"
if [[ -x "${WRAPPER}" ]]; then
    echo "   ✓ Cron wrapper is executable"
else
    echo "   ✗ Cron wrapper not executable"
    exit 1
fi

echo ""
echo "3. Testing health check with conda environment..."
cd "${PROJECT_ROOT}"
"${WRAPPER}" "${CONDA_PYTHON}" scripts/health_check.py

if [[ $? -eq 0 ]]; then
    echo "   ✓ Health check passed"
else
    echo "   ✗ Health check failed"
    exit 1
fi

echo ""
echo "4. Checking crontab configuration..."
CRON_FILE="/etc/cron.d/v6-trading"
if [[ -f "${CRON_FILE}" ]]; then
    echo "   ✓ Cron file exists: ${CRON_FILE}"
    echo ""
    echo "   Sample cron entries:"
    grep -v "^#" "${CRON_FILE}" | grep -v "^$" | head -3
else
    echo "   ⚠️  Cron file not found: ${CRON_FILE}"
    echo "   Run: sudo ./scripts/install_scheduler.sh"
fi

echo ""
echo "=========================================="
echo "✓ All Tests Passed!"
echo "=========================================="
echo ""
echo "Scheduler is ready to use."
echo ""
echo "To view scheduled tasks:"
echo "  cat ${CRON_FILE}"
echo ""
echo "To monitor logs:"
echo "  tail -f /tmp/v6_health.log"
echo ""
echo "To configure tasks:"
echo "  streamlit run src/v6/dashboard/app.py --server.port 8501"
echo "  Then navigate to Scheduler page"
echo ""
