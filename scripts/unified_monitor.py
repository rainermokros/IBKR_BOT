#!/usr/bin/env python3
"""
Unified Position Monitor - Single Script for All Monitoring

Combines three separate scripts into one efficient monitoring solution:
1. sync_positions.py - Sync IB positions to Delta Lake
2. refresh_option_data.py - Update market data for held positions
3. simple_monitor.py - Real-time P&L monitoring and alerts

Benefits:
- Single IB connection (more efficient)
- Atomic data snapshot (consistent state)
- Coordinated monitoring (all checks at once)
- Reduced IB API load

Schedule: Every 5 minutes during market hours (can be adjusted)
Usage:
    PYTHONPATH=/home/bigballs/project/bot/v6/src python scripts/unified_monitor.py
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict

import numpy as np
import polars as pl
from deltalake import DeltaTable, write_deltalake
from ib_async import IB
from loguru import logger

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class UnifiedMonitor:
    """
    Unified position monitoring system.

    Combines:
    - Position sync to Delta Lake
    - Market data refresh for held positions
    - P&L calculation and alerts
    """

    def __init__(self, check_interval: int = 300):
        """
        Initialize unified monitor.

        Args:
            check_interval: Seconds between checks (default: 300 = 5 minutes)
        """
        self.ib = IB()
        self.check_interval = check_interval
        self.running = False

        # Alert thresholds
        self.alert_loss_large = 500    # Alert if loss > $500
        self.alert_loss_warning = 200  # Warning if loss > $200
        self.alert_profit_large = 500  # Alert if profit > $500

    async def connect(self) -> bool:
        """Connect to IB Gateway."""
        try:
            logger.info("Connecting to IB Gateway...")
            await self.ib.connectAsync(
                host='127.0.0.1',
                port=4002,
                clientId=9950,  # Unique for unified monitor
                timeout=10
            )
            logger.success("✓ Connected to IB Gateway")
            return True
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False

    async def fetch_positions(self) -> List[Dict]:
        """
        Fetch current option positions from IB.

        Returns:
            List of position dictionaries
        """
        # Wait for positions to load
        await asyncio.sleep(0.5)

        positions = list(self.ib.positions())

        if not positions:
            return []

        option_positions = []
        for position in positions:
            if position.position == 0:
                continue  # Skip closed positions

            contract = position.contract
            if not hasattr(contract, 'right'):
                continue  # Skip non-options

            option_positions.append({
                'conid': contract.conId,
                'symbol': contract.symbol,
                'right': contract.right,
                'strike': contract.strike,
                'expiry': contract.lastTradeDateOrContractMonth,
                'position': position.position,
                'average_cost': position.avgCost,
            })

        return option_positions

    async def fetch_market_data(self, positions: List[Dict]) -> List[Dict]:
        """
        Fetch current market data for positions.

        Args:
            positions: List of position dicts

        Returns:
            List of positions with market data
        """
        from ib_async import Option

        if not positions:
            return []

        logger.info("Fetching market data for positions...")

        enriched_positions = []

        for pos in positions:
            try:
                # Create contract
                contract = Option(
                    symbol=pos['symbol'],
                    lastTradeDateOrContractMonth=pos['expiry'],
                    strike=pos['strike'],
                    right=pos['right'],
                    exchange='SMART',
                    currency='USD'
                )

                # Qualify contract
                qualified = await self.ib.qualifyContractsAsync(contract)
                if not qualified:
                    logger.warning(f"Could not qualify contract for {pos['symbol']} {pos['right']} ${pos['strike']}")
                    continue

                contract = qualified[0]

                # Request market data
                ticker = self.ib.ticker(contract)
                await asyncio.sleep(0.2)  # Rate limiting

                market_price = ticker.marketPrice()
                market_value = ticker.marketValue() if hasattr(ticker, 'marketValue') else None

                # Calculate unrealized P&L
                if market_price is not None:
                    unrealized_pnl = (market_price - pos['average_cost']) * abs(pos['position']) * 100 if pos['average_cost'] else np.nan
                else:
                    unrealized_pnl = np.nan

                pos_with_market = {
                    **pos,
                    'market_price': market_price if market_price is not None else np.nan,
                    'market_value': market_value if market_value is not None else np.nan,
                    'unrealized_pnl': unrealized_pnl,
                }

                enriched_positions.append(pos_with_market)

            except Exception as e:
                logger.warning(f"Failed to fetch market data for {pos['symbol']} {pos['right']} ${pos['strike']}: {e}")
                # Add position without market data
                enriched_positions.append({
                    **pos,
                    'market_price': np.nan,
                    'market_value': np.nan,
                    'unrealized_pnl': np.nan,
                })

        return enriched_positions

    def sync_to_delta_lake(self, positions: List[Dict]) -> None:
        """
        Sync positions to Delta Lake.

        Args:
            positions: List of position dicts with market data
        """
        if not positions:
            logger.info("No positions to sync")
            return

        # Add metadata
        for pos in positions:
            pos['timestamp'] = datetime.now()
            pos['date'] = datetime.now().date()

        # Create DataFrame
        df = pl.DataFrame(positions)

        # Write to Delta Lake (overwrite = current state)
        try:
            write_deltalake(
                'data/lake/position_updates',
                df,
                mode='overwrite',
            )
            logger.success(f"✓ Synced {len(positions)} positions to Delta Lake")
        except Exception as e:
            logger.error(f"Failed to sync to Delta Lake: {e}")
            raise

    def analyze_positions(self, positions: List[Dict]) -> Dict:
        """
        Analyze positions and calculate P&L by symbol.

        Args:
            positions: List of position dicts

        Returns:
            Analysis dict with P&L by symbol
        """
        # Group by symbol
        by_symbol = {}
        for pos in positions:
            symbol = pos['symbol']
            if symbol not in by_symbol:
                by_symbol[symbol] = []
            by_symbol[symbol].append(pos)

        analysis = {
            'symbols': {},
            'total_pnl': 0,
            'alerts': [],
        }

        for symbol, pos_list in by_symbol.items():
            num_legs = len(pos_list)

            if num_legs == 4:
                strategy_type = "Iron Condor"
            elif num_legs == 2:
                strategy_type = "Vertical Spread"
            else:
                strategy_type = f"Complex ({num_legs} legs)"

            # Calculate total P&L for this symbol
            total_pnl = sum(p.get('unrealized_pnl', 0) for p in pos_list if not np.isnan(p.get('unrealized_pnl', np.nan)))

            analysis['symbols'][symbol] = {
                'strategy': strategy_type,
                'legs': num_legs,
                'total_pnl': total_pnl,
            }
            analysis['total_pnl'] += total_pnl

            # Generate alerts
            if total_pnl < -self.alert_loss_large:
                alert = f"🚨 LARGE LOSS: {symbol} {strategy_type} ${total_pnl:.2f} - CONSIDER CLOSING!"
                analysis['alerts'].append(('critical', alert))
                logger.critical(alert)
            elif total_pnl < -self.alert_loss_warning:
                alert = f"⚠️ WARNING: {symbol} {strategy_type} ${total_pnl:.2f} - Monitor closely"
                analysis['alerts'].append(('warning', alert))
                logger.warning(alert)
            elif total_pnl > self.alert_profit_large:
                alert = f"✓ LARGE PROFIT: {symbol} {strategy_type} ${total_pnl:.2f} - Consider taking profits"
                analysis['alerts'].append(('info', alert))
                logger.success(alert)

        return analysis

    async def check_and_monitor(self) -> Dict:
        """
        Run full monitoring cycle.

        Returns:
            Monitoring results dict
        """
        logger.info("=" * 80)
        logger.info(f"MONITORING CYCLE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 80)

        # 1. Fetch positions
        positions = await self.fetch_positions()

        if not positions:
            logger.info("No open positions found")
            return {
                'positions': [],
                'analysis': None,
            }

        logger.info(f"Found {len(positions)} option positions")

        # 2. Fetch market data
        positions_with_market = await self.fetch_market_data(positions)

        # 3. Sync to Delta Lake
        self.sync_to_delta_lake(positions_with_market)

        # 4. Analyze and alert
        analysis = self.analyze_positions(positions_with_market)

        # 5. Summary
        logger.info("\n" + "-" * 80)
        logger.info("POSITION SUMMARY")
        logger.info("-" * 80)

        for symbol, data in analysis['symbols'].items():
            logger.info(f"\n{symbol} {data['strategy']} ({data['legs']} legs)")
            logger.info(f"  U/P&L: ${data['total_pnl']:.2f}")

        logger.info(f"\nTotal U/P&L: ${analysis['total_pnl']:.2f}")

        if analysis['alerts']:
            logger.info(f"\n{len(analysis['alerts'])} alert(s) generated")

        return {
            'positions': positions_with_market,
            'analysis': analysis,
        }

    async def start(self):
        """Start continuous monitoring loop."""
        self.running = True

        if not await self.connect():
            logger.error("Failed to connect, cannot start monitoring")
            return

        logger.info("\n" + "=" * 80)
        logger.info("UNIFIED MONITOR STARTED")
        logger.info(f"Checking every {self.check_interval} seconds")
        logger.info("Press Ctrl+C to stop")
        logger.info("=" * 80)

        try:
            # First check
            await self.check_and_monitor()

            # Monitoring loop
            while self.running:
                await asyncio.sleep(self.check_interval)
                if self.running:
                    await self.check_and_monitor()

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
        logger.info("\nStopping unified monitor...")
        self.running = False


async def main():
    """Main entry point."""

    monitor = UnifiedMonitor(check_interval=300)  # 5 minutes

    # Setup signal handlers
    import signal

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
