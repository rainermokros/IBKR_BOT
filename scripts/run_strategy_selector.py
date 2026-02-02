#!/usr/bin/env python3
"""
Run Strategy Selector - Dynamic Strategy Selection

This script:
1. Waits for fresh option data
2. Uses StrategySelector to evaluate ALL available strategies
3. Selects the best strategy based on composite scoring
4. Executes the selected strategy (paper or live trading)

Strategies evaluated:
- Iron Condor (neutral)
- Bull Put Spread (bullish)
- Bear Call Spread (bearish)

Scoring factors:
- Risk/Reward Ratio (30%)
- Probability of Success (30%)
- Expected Return % (25%)
- IV Rank Context (15%)

Usage:
    # Run with default settings (paper trading)
    python scripts/run_strategy_selector.py

    # Run with live trading
    python scripts/run_strategy_selector.py --live

    # Dry run (no actual execution)
    python scripts/run_strategy_selector.py --dry-run

    # Custom DTE
    python scripts/run_strategy_selector.py --dte 30
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


class StrategySelectorRunner:
    """
    Strategy selector runner - evaluates and executes best strategies.

    Workflow:
    1. Check data freshness
    2. Get underlying prices
    3. Evaluate all strategies using StrategySelector
    4. Select best strategy per symbol
    5. Execute selected strategies
    """

    def __init__(
        self,
        symbols: List[str] = ["SPY", "QQQ", "IWM"],
        quantity: int = 1,
        target_dte: int = 45,
        max_position_size: float = 10000,
        dry_run: bool = True,
    ):
        self.symbols = symbols
        self.quantity = quantity
        self.target_dte = target_dte
        self.max_position_size = max_position_size
        self.dry_run = dry_run

    def _save_execution_to_deltalake(self, analysis, result):
        """
        Save strategy execution to Delta Lake for tracking.
        """
        try:
            strategy = analysis.strategy

            # Create execution record
            execution_record = {
                'execution_id': str(uuid.uuid4())[:12],
                'strategy_id': 1,
                'symbol': strategy.symbol,
                'strategy_type': strategy.strategy_type.value if hasattr(strategy, 'strategy_type') else analysis.strategy_name.lower().replace(" ", "_"),
                'status': 'filled' if result.get('success', False) else 'failed',
                'entry_params': json.dumps({
                    'quantity': self.quantity,
                    'target_dte': self.target_dte,
                    'score': analysis.score,
                    'risk_reward_ratio': analysis.risk_reward_ratio,
                    'probability_of_success': analysis.probability_of_success,
                    'expected_return_pct': analysis.expected_return_pct,
                    'iv_rank': analysis.iv_rank,
                }),
                'entry_time': datetime.now(),
                'fill_time': datetime.now(),
                'close_time': None,
                'legs_json': json.dumps([
                    {
                        'leg_id': f"{str(uuid.uuid4())[:8]}",
                        'conid': None,
                        'right': leg.right.value,
                        'strike': leg.strike,
                        'expiration': leg.expiration.isoformat() if leg.expiration else None,
                        'quantity': leg.quantity,
                        'action': leg.action.value,
                        'status': 'filled',
                        'fill_price': 0.0,
                        'order_id': None,
                        'fill_time': datetime.now().isoformat(),
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

    async def select_best_strategies(self, prices: Dict[str, float]) -> Dict:
        """
        Select best strategies using StrategySelector.

        Returns:
            Dict mapping symbol to best StrategyAnalysis
        """
        from v6.strategies.strategy_selector import StrategySelector

        logger.info("🔍 Evaluating all strategies using StrategySelector...")

        selector = StrategySelector()
        best_strategies = {}

        for symbol, price in prices.items():
            try:
                logger.info(f"\n{'='*80}")
                logger.info(f"Evaluating strategies for {symbol} @ ${price:.2f}")
                logger.info(f"{'='*80}")

                # Analyze all strategies for this symbol
                ranked_strategies = selector.analyze_all_strategies(
                    symbol=symbol,
                    quantity=self.quantity,
                    target_dte=self.target_dte,
                    use_smart_lookup=True
                )

                if ranked_strategies:
                    best = ranked_strategies[0]
                    best_strategies[symbol] = best

                    logger.info(f"\n✅ BEST STRATEGY FOR {symbol}: {best.strategy_name}")
                    logger.info(f"   Score: {best.score:.1f}/100")
                    logger.info(f"   R/R Ratio: {best.risk_reward_ratio:.2f}:1")
                    logger.info(f"   Probability of Success: {best.probability_of_success:.1f}%")
                    logger.info(f"   Expected Return: ${best.expected_return:.2f} ({best.expected_return_pct:.1f}%)")
                    logger.info(f"   IV Rank: {best.iv_rank:.0f}%")
                else:
                    logger.warning(f"   ⚠️  No valid strategies built for {symbol}")

            except Exception as e:
                logger.error(f"   ✗ Error evaluating strategies for {symbol}: {e}")
                import traceback
                logger.error(traceback.format_exc())

        return best_strategies

    async def execute_strategies(self, analyses: Dict) -> bool:
        """Execute selected strategies LIVE with margin checks."""
        logger.info("\n🚀 Executing selected strategies...")

        if self.dry_run:
            logger.info("   🧪 DRY RUN MODE - No actual execution")
        else:
            logger.info("   💰 LIVE TRADING - Real money at risk!")
            logger.warning("   ⚠️  This will place REAL orders!")

        from v6.execution.strategy_executor import StrategyOrderExecutor

        executor = None
        try:
            if not self.dry_run:
                # Create executor
                executor = StrategyOrderExecutor(client_id=997)
                await executor.connect()

                # Get account info
                account = await executor.get_account_summary()

            for symbol, analysis in analyses.items():
                logger.info(f"\n   {symbol}: {analysis.strategy_name}")
                logger.info("   " + "-" * 60)

                # Log strategy details
                strategy = analysis.strategy
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
                    result = {'success': True}  # Simulate success
                else:
                    # LIVE EXECUTION
                    logger.info("")
                    logger.warning("   ⚠️  PLACING LIVE ORDER!")
                    logger.warning("   ⚠️  This is REAL money!")

                    # Execute with all checks
                    result_obj = await executor.execute_strategy_atomic(
                        strategy=strategy,
                        verify_margin=True,
                        max_margin=self.max_position_size,
                    )

                    result = {'success': result_obj.success}

                    if result_obj.success:
                        logger.info(f"   ✅ EXECUTED: Order IDs: {result_obj.order_ids}")
                        logger.info(f"   ✅ Margin used: ${result_obj.margin_required:,.2f}")
                    else:
                        logger.error(f"   ❌ FAILED: {result_obj.error_message}")
                        return False

                # Save execution to Delta Lake
                self._save_execution_to_deltalake(analysis, result)

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
        """Run the full strategy selector workflow."""
        logger.info("=" * 70)
        logger.info("STRATEGY SELECTOR - EVALUATE AND EXECUTE BEST STRATEGIES")
        logger.info("=" * 70)
        logger.info(f"Symbols: {self.symbols}")
        logger.info(f"Quantity: {self.quantity}")
        logger.info(f"Target DTE: {self.target_dte}")
        logger.info(f"Dry run: {self.dry_run}")
        logger.info("-" * 70)

        # Step 1: Check data freshness
        from v6.data.data_freshness import DataFreshnessChecker

        logger.info("\nStep 1: Checking option data freshness...")
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

        # Step 3: Select best strategies
        logger.info("\nStep 3: Selecting best strategies...")
        analyses = await self.select_best_strategies(prices)

        if not analyses:
            logger.error("❌ No strategies selected - cannot continue")
            return False

        logger.info(f"\n✅ Selected {len(analyses)} strategies:")
        for symbol, analysis in analyses.items():
            logger.info(f"   {symbol}: {analysis.strategy_name} (score: {analysis.score:.1f}/100)")

        # Step 4: Execute strategies
        logger.info("\nStep 4: Executing strategies...")
        success = await self.execute_strategies(analyses)

        if success:
            logger.info("\n" + "=" * 70)
            logger.info("✅ STRATEGY SELECTOR COMPLETE")
            logger.info("=" * 70)
            logger.info(f"Strategies executed: {len(analyses)}")
            logger.info(f"Dry run: {self.dry_run}")
            logger.info("=" * 70)
            return True
        else:
            logger.error("\n❌ Execution failed")
            return False


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run strategy selector - evaluate and execute best strategies"
    )

    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["SPY", "QQQ", "IWM"],
        help="Symbols to trade (default: SPY QQQ IWM)"
    )

    parser.add_argument(
        "--quantity",
        type=int,
        default=1,
        help="Number of contracts (default: 1)"
    )

    parser.add_argument(
        "--dte",
        type=int,
        default=45,
        help="Days to expiration (default: 45)"
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

    # Create and run selector
    selector = StrategySelectorRunner(
        symbols=args.symbols,
        quantity=args.quantity,
        target_dte=args.dte,
        dry_run=dry_run,
    )

    try:
        success = await selector.run()
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
