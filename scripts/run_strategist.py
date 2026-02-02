#!/usr/bin/env python3
"""
⚠️  OBSOLETE - Use run_strategy_selector.py instead ⚠️

This script is DEPRECATED and kept for reference only.
It only builds Iron Condors without evaluating other strategies.

Use run_strategy_selector.py which:
- Evaluates ALL available strategies (Iron Condor, Bull Put Spread, Bear Call Spread)
- Uses StrategySelector to score and rank strategies
- Selects the best strategy based on composite scoring

Migration: Replace calls to this script with run_strategy_selector.py

--- ORIGINAL DOCUMENTATION BELOW ---

Run Strategist - Build and Execute Option Positions

This script:
1. Waits for fresh option data
2. Builds strategies using Iron Condor builder
3. Executes positions (paper or live trading)

Usage:
    # Run with default settings (paper trading)
    python scripts/run_strategist.py

    # Run with live trading
    python scripts/run_strategist.py --live

    # Dry run (no actual execution)
    python scripts/run_strategist.py --dry-run

    # Custom strategy parameters
    python scripts/run_strategist.py --put-width 5 --call-width 5 --dte 30
"""

import argparse
import asyncio
import json
import uuid
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import polars as pl
from deltalake import write_deltalake
from loguru import logger

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class StrategistRunner:
    """
    Main strategist runner - builds and executes strategies.

    Workflow:
    1. Check data freshness
    2. Get underlying prices
    3. Build strategies
    4. Validate strategies
    5. Execute strategies
    """

    def __init__(
        self,
        symbols: List[str] = ["SPY"],
        put_width: int = 10,
        call_width: int = 10,
        dte: int = 45,
        delta_target: float = 0.16,
        max_position_size: float = 10000,
        dry_run: bool = True,
    ):
        self.symbols = symbols
        self.put_width = put_width
        self.call_width = call_width
        self.dte = dte
        self.delta_target = delta_target
        self.max_position_size = max_position_size
        self.dry_run = dry_run

    def _save_execution_to_deltalake(self, strategy, result):
        """
        Save strategy execution to Delta Lake for tracking.

        This ensures all executions are logged for:
        - Dashboard display
        - Historical analysis
        - Performance tracking
        """
        try:
            import json
            import uuid
            from datetime import datetime
            import polars as pl
            from deltalake import write_deltalake

            # Create execution record
            execution_record = {
                'execution_id': str(uuid.uuid4())[:12],
                'strategy_id': 1,
                'symbol': strategy.symbol,
                'strategy_type': strategy.strategy_type.value if hasattr(strategy, 'strategy_type') else 'iron_condor',
                'status': 'filled' if result.success else 'failed',
                'entry_params': json.dumps({
                    'put_width': self.put_width,
                    'call_width': self.call_width,
                    'dte': self.dte,
                    'delta_target': self.delta_target,
                }),
                'entry_time': datetime.now(),
                'fill_time': datetime.now(),
                'close_time': None,
                'legs_json': json.dumps([
                    {
                        'right': leg.right.value,
                        'action': leg.action.value,
                        'strike': leg.strike,
                        'quantity': leg.quantity,
                    }
                    for leg in strategy.legs
                ]),
            }

            # Write to Delta Lake
            df = pl.DataFrame([execution_record])
            write_deltalake('data/lake/strategy_executions', df, mode='append')

            logger.info(f"   💾 Saved execution {execution_record['execution_id']} to Delta Lake")

        except Exception as e:
            logger.error(f"   ❌ Failed to save to Delta Lake: {e}")
            # Don't fail the trade if logging fails
            import traceback
            logger.debug(traceback.format_exc())

    async def get_underlying_prices(self) -> Dict[str, float]:
        """Get current underlying prices from market data."""
        logger.info("📊 Fetching underlying prices...")

        prices = {}
        try:
            df = pl.read_delta("data/lake/market_bars")

            for symbol in self.symbols:
                symbol_df = df.filter(
                    (pl.col("symbol") == symbol) &
                    (pl.col("interval") == "1d")
                ).sort("timestamp", descending=True).head(1)

                if len(symbol_df) > 0:
                    price = symbol_df.select(pl.col("close")).item()
                    prices[symbol] = price
                    logger.info(f"   {symbol}: ${price:.2f}")
                else:
                    logger.warning(f"   ⚠️  No price data for {symbol}")

        except Exception as e:
            logger.error(f"   ✗ Error fetching prices: {e}")

        return prices

    async def build_strategies(self, prices: Dict[str, float]) -> List:
        """Build strategies from Delta Lake (REAL contracts)."""
        logger.info("🔨 Building strategies from Delta Lake (REAL contracts)...")

        from v6.strategies.deltalake_builder import DeltaLakeStrategyBuilder

        builder = DeltaLakeStrategyBuilder()
        strategies = []

        for symbol, price in prices.items():
            try:
                logger.info(f"   Building Iron Condor for {symbol} @ ${price:.2f}")

                # Build from Delta Lake (REAL contracts!)
                strategy = await builder.build_iron_condor(
                    symbol=symbol,
                    underlying_price=price,
                    put_width=self.put_width,
                    call_width=self.call_width,
                    target_dte=self.dte,
                )

                if strategy:
                    logger.info(f"   ✅ Strategy built from Delta Lake")
                    logger.info(f"      Source: option_snapshots (REAL data)")
                    logger.info(f"      Legs: {len(strategy.legs)}")
                    logger.info(f"      Expiration: {strategy.legs[0].expiration}")
                    logger.info(f"      Strikes: {[leg.strike for leg in strategy.legs]}")
                    strategies.append(strategy)
                else:
                    logger.warning(f"   ⚠️  Failed to build strategy for {symbol}")

            except Exception as e:
                logger.error(f"   ✗ Error building strategy for {symbol}: {e}")
                import traceback
                logger.error(traceback.format_exc())

        return strategies

    async def execute_strategies(self, strategies: List) -> bool:
        """Execute built strategies LIVE with margin checks."""
        logger.info("🚀 Executing strategies LIVE with margin checks...")

        if self.dry_run:
            logger.info("   🧪 DRY RUN MODE - No actual execution")
        else:
            logger.info("   💰 LIVE TRADING - Real money at risk!")
            logger.warning("   ⚠️  This will place REAL orders!")

        from v6.execution.strategy_executor import StrategyOrderExecutor, execute_strategy_with_checks

        executor = None
        try:
            if not self.dry_run:
                # Create executor
                executor = StrategyOrderExecutor(client_id=997)
                await executor.connect()

                # Get account info
                account = await executor.get_account_summary()

            for i, strategy in enumerate(strategies, 1):
                logger.info(f"\n   Strategy {i}/{len(strategies)}: {strategy.symbol}")
                logger.info("   " + "-" * 60)

                # Log strategy details
                logger.info(f"   Type: {strategy.strategy_type}")
                logger.info(f"   Symbol: {strategy.symbol}")
                logger.info(f"   Legs: {len(strategy.legs)}")

                for j, leg in enumerate(strategy.legs, 1):
                    action_icon = "🟢" if leg.action.value == "BUY" else "🔴"
                    logger.info(
                        f"   Leg {j}: {action_icon} {leg.action.value} {leg.right.value} "
                        f"${leg.strike} {leg.expiration}"
                    )

                if self.dry_run:
                    logger.info("   ✅ DRY RUN - Strategy would be executed")
                    logger.info(f"      Would check margin and place atomic order")
                else:
                    # LIVE EXECUTION
                    logger.info("")
                    logger.warning("   ⚠️  PLACING LIVE ORDER!")
                    logger.warning("   ⚠️  This is REAL money!")

                    # Execute with all checks
                    result = await executor.execute_strategy_atomic(
                        strategy=strategy,
                        verify_margin=True,
                        max_margin=self.max_position_size,
                    )

                    if result.success:
                        logger.info(f"   ✅ EXECUTED: Order IDs: {result.order_ids}")
                        logger.info(f"   ✅ Margin used: ${result.margin_required:,.2f}")

                        # ✅ SAVE EXECUTION TO DELTA LAKE
                        logger.info("   💾 Saving execution to Delta Lake...")
                        self._save_execution_to_deltalake(strategy, result)

                    else:
                        logger.error(f"   ❌ FAILED: {result.error_message}")
                        return False

            return True

        except Exception as e:
            logger.error(f"❌ Error during execution: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

        finally:
            if executor and executor.connected:
                await executor.disconnect()
                logger.info("✅ Disconnected from IB Gateway")

    async def run(self):
        """Run the full strategist workflow."""
        logger.info("=" * 70)
        logger.info("STRATEGIST - BUILD AND EXECUTE POSITIONS")
        logger.info("=" * 70)
        logger.info(f"Symbols: {self.symbols}")
        logger.info(f"Put width: ${self.put_width}")
        logger.info(f"Call width: ${self.call_width}")
        logger.info(f"DTE: {self.dte} days")
        logger.info(f"Delta target: {self.delta_target}")
        logger.info(f"Dry run: {self.dry_run}")
        logger.info("-" * 70)

        # Step 1: Check data freshness
        from v6.data.data_freshness import DataFreshnessChecker

        logger.info("Step 1: Checking option data freshness...")
        checker = DataFreshnessChecker(symbols=self.symbols)

        is_fresh = await checker.wait_for_fresh_data(
            max_age_minutes=5,
            timeout_seconds=120
        )

        if not is_fresh:
            logger.error("❌ Data is stale - cannot continue")
            return False

        # Step 2: Get underlying prices
        logger.info("\nStep 2: Getting underlying prices...")
        prices = await self.get_underlying_prices()

        if not prices:
            logger.error("❌ No prices available - cannot continue")
            return False

        # Step 3: Build strategies
        logger.info("\nStep 3: Building strategies...")
        strategies = await self.build_strategies(prices)

        if not strategies:
            logger.error("❌ No strategies built - cannot continue")
            return False

        logger.info(f"\n✅ Built {len(strategies)} strategies")

        # Step 4: Execute strategies
        logger.info("\nStep 4: Executing strategies...")
        success = await self.execute_strategies(strategies)

        if success:
            logger.info("\n" + "=" * 70)
            logger.info("✅ STRATEGIST COMPLETE")
            logger.info("=" * 70)
            logger.info(f"Strategies built: {len(strategies)}")
            logger.info(f"Dry run: {self.dry_run}")
            logger.info("=" * 70)
            return True
        else:
            logger.error("\n❌ Execution failed")
            return False


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run strategist - build and execute option positions"
    )

    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["SPY"],
        help="Symbols to trade (default: SPY)"
    )

    parser.add_argument(
        "--put-width",
        type=int,
        default=10,
        help="Put spread width in dollars (default: 10)"
    )

    parser.add_argument(
        "--call-width",
        type=int,
        default=10,
        help="Call spread width in dollars (default: 10)"
    )

    parser.add_argument(
        "--dte",
        type=int,
        default=45,
        help="Days to expiration (default: 45)"
    )

    parser.add_argument(
        "--delta-target",
        type=float,
        default=0.16,
        help="Delta target for short strikes (default: 0.16)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run - no actual execution"
    )

    parser.add_argument(
        "--live",
        action="store_true",
        help="Live trading (uses real money)"
    )

    args = parser.parse_args()

    # Configure logging
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>"
    )

    # Determine if dry run
    dry_run = not args.live

    # Create and run strategist
    strategist = StrategistRunner(
        symbols=args.symbols,
        put_width=args.put_width,
        call_width=args.call_width,
        dte=args.dte,
        delta_target=args.delta_target,
        dry_run=dry_run,
    )

    try:
        success = await strategist.run()
        return 0 if success else 1

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("\n⚠️  Interrupted by user")
        sys.exit(130)
