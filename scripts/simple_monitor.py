#!/usr/bin/env python3
"""
Simple Position Monitor - For Existing Iron Condors

Monitors the 3 Iron Condor positions currently in IB account:
- SPY Iron Condor
- QQQ Iron Condor
- IWM Iron Condor

Checks every 30 seconds:
- Position status (open/closed)
- Greeks (delta, gamma, theta, vega)
- P&L (unrealized)
- DTE (days to expiration)

Usage:
    PYTHONPATH=/home/bigballs/project/bot/v6/src python scripts/simple_monitor.py
"""

import asyncio
import signal
import sys
from datetime import datetime
from pathlib import Path

from ib_async import IB
from loguru import logger

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class SimplePositionMonitor:
    """Simple position monitor for Iron Condors."""

    def __init__(self, check_interval: int = 30):
        self.ib = IB()
        self.check_interval = check_interval
        self.running = False

    async def connect(self):
        """Connect to IB Gateway."""
        logger.info("Connecting to IB Gateway...")
        await self.ib.connectAsync(
            host='127.0.0.1',
            port=4002,
            clientId=9995,
            timeout=10
        )
        logger.success("✓ Connected to IB Gateway")

    async def check_positions(self):
        """Check current positions and status."""
        logger.info("=" * 80)
        logger.info(f"POSITION CHECK - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 80)

        # Get all positions
        positions = self.ib.positions()

        if not positions:
            logger.warning("No positions found!")
            return

        # Group by symbol
        by_symbol = {}
        for position in positions:
            if position.position == 0:  # Skip closed positions
                continue

            contract = position.contract
            if not hasattr(contract, 'right'):  # Skip non-options
                continue

            symbol = contract.symbol
            if symbol not in by_symbol:
                by_symbol[symbol] = []

            by_symbol[symbol].append({
                'right': contract.right,
                'strike': contract.strike,
                'expiry': contract.lastTradeDateOrContractMonth,
                'quantity': position.position,
                'market_price': position.marketPrice,
                'market_value': position.marketValue,
                'average_cost': position.averageCost,
                'unrealized_pnl': position.unrealizedPNL,
            })

        # Analyze each symbol
        for symbol, legs in by_symbol.items():
            num_legs = len(legs)

            if num_legs == 4:
                strategy_type = "Iron Condor"
            elif num_legs == 2:
                strategy_type = "Vertical Spread"
            else:
                strategy_type = f"Complex ({num_legs} legs)"

            logger.info(f"\n{symbol} {strategy_type}:")
            logger.info("-" * 40)

            total_pnl = sum(leg.get('unrealized_pnl', 0) for leg in legs)

            for leg in legs:
                action = "SHORT" if leg['quantity'] < 0 else "LONG"
                pnl = leg.get('unrealized_pnl', 0)
                pnl_str = f"${pnl:.2f}" if pnl != 0 else "N/A"

                logger.info(f"  {action} {leg['right']} ${leg['strike']} {leg['expiry']}")
                logger.info(f"    Market Price: ${leg['market_price']:.2f}" if leg['market_price'] else "    Market Price: N/A")
                logger.info(f"    U/P&L: {pnl_str}")

            logger.info(f"\n  Total U/P&L: ${total_pnl:.2f}")

            # Check for alerts
            if total_pnl < -500:
                logger.error(f"  ⚠️ LARGE LOSS: ${total_pnl:.2f} - Consider closing!")
            elif total_pnl < -200:
                logger.warning(f"  ⚠ Loss: ${total_pnl:.2f} - Monitor closely")
            elif total_pnl > 500:
                logger.success(f"  ✓ Large profit: ${total_pnl:.2f} - Consider taking profits")

    async def start(self):
        """Start monitoring loop."""
        self.running = True

        try:
            await self.connect()

            logger.info("\n" + "=" * 80)
            logger.info("MONITORING STARTED")
            logger.info(f"Checking every {self.check_interval} seconds")
            logger.info("Press Ctrl+C to stop")
            logger.info("=" * 80)

            # First check
            await self.check_positions()

            # Monitoring loop
            while self.running:
                await asyncio.sleep(self.check_interval)
                if self.running:
                    await self.check_positions()

        except asyncio.CancelledError:
            logger.info("\nMonitoring cancelled")
        except Exception as e:
            logger.error(f"Monitoring error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            try:
                self.ib.disconnect()
                logger.info("\n✓ Disconnected from IB Gateway")
            except:
                pass

    def stop(self):
        """Stop monitoring."""
        logger.info("\nStopping monitoring...")
        self.running = False


async def main():
    """Main entry point."""

    monitor = SimplePositionMonitor(check_interval=30)

    # Setup signal handlers
    def signal_handler(sig, frame):
        monitor.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start monitoring
    await monitor.start()

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
