#!/usr/bin/env python3
"""
Start Position Monitoring - Risk Manager

Starts PositionMonitoringWorkflow to monitor all active option strategies.
This is the PROPER way to monitor positions (no custom scripts).

Features:
- Fetches all open strategies from StrategyRepository
- Evaluates each position with DecisionEngine
- Generates alerts for non-HOLD decisions
- Runs continuous monitoring loop (30-second intervals)

Usage:
    PYTHONPATH=/home/bigballs/project/bot/v6/src python scripts/start_monitoring.py
"""

import asyncio
import signal
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from v6.strategy_builder.repository import StrategyRepository
from v6.strategy_builder.decision_engine.engine import DecisionEngine
from v6.system_monitor.alert_system import AlertManager
from v6.risk_manager.trading_workflows.monitoring import PositionMonitoringWorkflow


class MonitoringService:
    """Service to run position monitoring with proper shutdown."""

    def __init__(self):
        self.monitoring_task = None
        self.shutdown_requested = False

    async def initialize(self):
        """Initialize monitoring components."""
        logger.info("=" * 80)
        logger.info("INITIALIZING POSITION MONITORING")
        logger.info("=" * 80)
        logger.info(f"Time: {datetime.now()}")

        # Initialize repository
        logger.info("\n1. Initializing StrategyRepository...")
        self.strategy_repo = StrategyRepository()
        logger.info("   ✓ StrategyRepository ready")

        # Initialize decision engine
        logger.info("\n2. Initializing DecisionEngine...")
        self.decision_engine = DecisionEngine()
        logger.info("   ✓ DecisionEngine ready")

        # Initialize alert manager
        logger.info("\n3. Initializing AlertManager...")
        self.alert_manager = AlertManager()
        await self.alert_manager.initialize()
        logger.info("   ✓ AlertManager ready")

        # Initialize monitoring workflow
        logger.info("\n4. Initializing PositionMonitoringWorkflow...")
        self.monitoring = PositionMonitoringWorkflow(
            decision_engine=self.decision_engine,
            alert_manager=self.alert_manager,
            strategy_repo=self.strategy_repo,
            monitoring_interval=30  # Check every 30 seconds
        )
        logger.info("   ✓ PositionMonitoringWorkflow ready")

        logger.info("\n" + "=" * 80)
        logger.info("MONITORING INITIALIZED")
        logger.info("=" * 80)

    async def start(self):
        """Start monitoring loop."""
        logger.info("\n" + "=" * 80)
        logger.info("STARTING POSITION MONITORING LOOP")
        logger.info("=" * 80)
        logger.info("Press Ctrl+C to stop")
        logger.info("")

        # Run first monitoring cycle immediately
        await self.monitor_once()

        # Start continuous monitoring
        self.monitoring_task = asyncio.create_task(self.monitoring.start_monitoring_loop())

        # Wait for shutdown signal
        while not self.shutdown_requested:
            await asyncio.sleep(1)

        # Stop monitoring
        if self.monitoring_task and not self.monitoring_task.done():
            logger.info("\nStopping monitoring loop...")
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass

    async def monitor_once(self):
        """Run a single monitoring cycle and show results."""
        logger.info("=" * 80)
        logger.info("MONITORING CYCLE - One-Time Check")
        logger.info("=" * 80)

        try:
            decisions = await self.monitoring.monitor_positions()

            if not decisions:
                logger.info("No open positions to monitor")
                return

            logger.info(f"\nMonitored {len(decisions)} position(s):")

            # Group by action
            actions = {}
            for exec_id, decision in decisions.items():
                action = decision.action.value
                if action not in actions:
                    actions[action] = []
                actions[action].append({
                    'id': exec_id[:8],
                    'symbol': decision.metadata.get('symbol', 'N/A'),
                    'reason': decision.reason,
                    'urgency': decision.urgency.value
                })

            # Show summary
            for action, positions in actions.items():
                logger.info(f"\n{action.upper()}: {len(positions)} position(s)")
                for pos in positions:
                    logger.info(f"  • {pos['id']} ({pos['symbol']})")
                    logger.info(f"    Reason: {pos['reason']}")
                    logger.info(f"    Urgency: {pos['urgency']}")

            # Alert if any non-HOLD actions
            hold_count = len(actions.get('HOLD', []))
            non_hold = len(decisions) - hold_count

            if non_hold > 0:
                logger.warning(f"\n⚠️ {non_hold} position(s) require attention!")
            else:
                logger.success(f"\n✓ All {hold_count} positions look good (HOLD)")

        except Exception as e:
            logger.error(f"Monitoring cycle failed: {e}")
            import traceback
            traceback.print_exc()

    async def shutdown(self):
        """Shutdown monitoring service gracefully."""
        logger.info("\n" + "=" * 80)
        logger.info("SHUTTING DOWN MONITORING")
        logger.info("=" * 80)

        self.shutdown_requested = True

        # Flush any pending alerts
        if hasattr(self, 'alert_manager'):
            await self.alert_manager.flush()

        logger.success("✓ Monitoring stopped")


async def main():
    """Main entry point."""

    service = MonitoringService()

    try:
        # Initialize
        await service.initialize()

        # Setup signal handlers for graceful shutdown
        def signal_handler(sig, frame):
            logger.info(f"\nReceived signal {sig}")
            asyncio.create_task(service.shutdown())

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Start monitoring
        await service.start()

    except Exception as e:
        logger.error(f"Monitoring failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        await service.shutdown()

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
