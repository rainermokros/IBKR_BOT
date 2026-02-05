#!/usr/bin/env python3
"""
Execute Best Strategies - Using v6 EntryWorkflow Infrastructure

Analyzes ALL strategy types (Iron Condor, Call Spreads, Put Spreads) and
executes the BEST one for each symbol based on score (return/risk).

Uses StrategySelector to find best opportunities, then executes via
EntryWorkflow with proper risk checks and DecisionEngine.

Strategy Types Analyzed:
- Iron Condor (neutral market)
- Bull Put Spread (bullish market)
- Bear Call Spread (bearish market)

The best strategy (highest score) for each symbol is executed automatically.

Proper v6 Infrastructure:
- StrategySelector: Analyzes and scores ALL strategy types
- StrategyBuilderFactory: Returns appropriate builder for strategy type
- EntryWorkflow: Proper execution with risk checks
- DecisionEngine: 12-priority decision rules
- OrderExecutionEngine: Order placement
- StrategyRepository: Persistence

Schedule: 10:00 AM (after strategy analysis at 9:45)
Usage:
    PYTHONPATH=/home/bigballs/project/bot/v6/src python scripts/execute_best_strategies.py
    PYTHONPATH=/home/bigballs/project/bot/v6/src python scripts/execute_best_strategies.py --dry-run
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from v6.strategy_builder.strategy_selector import StrategySelector
from v6.strategy_builder.decision_engine.engine import DecisionEngine
from v6.strategy_builder.repository import StrategyRepository
from v6.risk_manager.trading_workflows.entry import EntryWorkflow
from v6.system_monitor.execution_engine.engine import OrderExecutionEngine
from v6.utils.ib_connection import IBConnectionManager
from v6.system_monitor.alert_system.manager import AlertManager


async def initialize_entry_workflow(dry_run: bool = False) -> EntryWorkflow:
    """
    Initialize EntryWorkflow with all required dependencies.

    Args:
        dry_run: If True, simulate orders without placing them

    Returns:
        Initialized EntryWorkflow
    """
    logger.info("Initializing EntryWorkflow...")

    # 1. IB Connection
    ib_conn = IBConnectionManager(
        host="127.0.0.1",
        port=4002,
        client_id=9971,  # Unique for strategy execution
    )
    await ib_conn.connect()
    logger.success("✓ IB Connected")

    # 2. Decision Engine
    decision_engine = DecisionEngine()
    logger.success("✓ DecisionEngine initialized")

    # 3. Alert Manager (optional but recommended)
    try:
        alert_manager = AlertManager()
        await alert_manager.initialize()
        decision_engine.alert_manager = alert_manager
        logger.success("✓ AlertManager initialized")
    except Exception as e:
        logger.warning(f"Could not initialize AlertManager: {e}")
        logger.info("Continuing without alerts...")
        alert_manager = None

    # 4. Order Execution Engine
    execution_engine = OrderExecutionEngine(
        ib_conn=ib_conn,
        dry_run=dry_run,
    )
    logger.success(f"✓ OrderExecutionEngine initialized (dry_run={dry_run})")

    # 5. Strategy Repository
    strategy_repo = StrategyRepository()
    logger.success("✓ StrategyRepository initialized")

    # 6. Entry Workflow (uses StrategyBuilderFactory internally)
    entry_workflow = EntryWorkflow(
        decision_engine=decision_engine,
        execution_engine=execution_engine,
        strategy_repo=strategy_repo,
        max_portfolio_delta=0.3,  # 30 delta limit
        max_positions_per_symbol=5,
    )
    logger.success("✓ EntryWorkflow initialized (uses StrategyBuilderFactory)")

    return entry_workflow


async def execute_symbol_strategy(
    entry_workflow: EntryWorkflow,
    selector: StrategySelector,
    symbol: str,
    dry_run: bool = False,
    min_score: float = 70.0
) -> dict:
    """
    Analyze and execute best strategy for symbol.

    Args:
        entry_workflow: Initialized EntryWorkflow
        selector: StrategySelector instance
        symbol: Underlying symbol
        dry_run: Simulate without real orders
        min_score: Minimum score to execute

    Returns:
        dict: Execution results
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"EXECUTING STRATEGY FOR {symbol}")
    logger.info(f"{'='*80}")

    try:
        # Get best strategy
        analyses = await selector.analyze_all_strategies(
            symbol=symbol,
            quantity=1,
            target_dte=45,
            use_smart_lookup=True
        )

        if not analyses:
            logger.warning(f"No strategies available for {symbol}")
            return {
                'symbol': symbol,
                'success': False,
                'reason': 'No strategies built'
            }

        # Find best strategy
        best = max(analyses, key=lambda a: a.score)

        logger.info(f"Best strategy: {best.strategy_name}")
        logger.info(f"Score: {best.score:.1f}/100")
        logger.info(f"Credit: ${best.credit:.2f}")
        logger.info(f"Max risk: ${best.max_risk:.2f}")
        logger.info(f"Probability of success: {best.probability_of_success:.1f}%")

        # Check if meets threshold
        if best.score < min_score:
            logger.warning(f"Score {best.score:.1f} below threshold {min_score}")
            logger.info(f"Skipping execution for {symbol}")
            return {
                'symbol': symbol,
                'success': False,
                'reason': f'Score {best.score:.1f} < {min_score}',
                'best_strategy': best.strategy_name,
                'score': best.score
            }

        # Execute via EntryWorkflow
        logger.info(f"\nExecuting {best.strategy_name} for {symbol}...")

        # Estimate underlying price from option snapshots (ATM point)
        # This avoids competing with the option data collector for IB market data
        import polars as pl
        from deltalake import DeltaTable

        try:
            # Load latest option data for symbol
            dt = DeltaTable('data/lake/option_snapshots')
            df = pl.from_pandas(dt.to_pandas())

            # Filter for symbol and latest data
            symbol_data = df.filter(
                (pl.col('symbol') == symbol) &
                (pl.col('bid') > 0) & (pl.col('ask') > 0)
            ).sort('timestamp', descending=True).head(100)

            if len(symbol_data) == 0:
                raise ValueError("No option data found")

            # Find ATM point: where call and put prices are closest
            symbol_data = symbol_data.with_columns(
                (pl.col('bid') + pl.col('ask')).alias('mid_price')
            )

            # Group by strike and get both calls and puts
            calls = symbol_data.filter(pl.col('right') == 'CALL').group_by('strike').agg(
                pl.col('mid_price').mean().alias('call_price')
            )
            puts = symbol_data.filter(pl.col('right') == 'PUT').group_by('strike').agg(
                pl.col('mid_price').mean().alias('put_price')
            )

            # Find ATM strike where call and put prices cross
            joined = calls.join(puts, on='strike', how='inner')
            joined = joined.with_columns(
                (pl.col('call_price') - pl.col('put_price')).abs().alias('price_diff')
            )

            atm_row = joined.sort('price_diff').row(0, named=True)
            underlying_price = float(atm_row['strike'])

            logger.info(f"Estimated {symbol} price from options: ${underlying_price:.2f}")

        except Exception as e:
            logger.error(f"Failed to estimate {symbol} price from options: {e}")
            raise
            logger.error(f"Could not fetch valid price for {symbol}: {underlying_price}")
            return {
                'symbol': symbol,
                'success': False,
                'reason': f'Could not fetch underlying price: {underlying_price}',
                'best_strategy': best.strategy_name,
                'score': best.score
            }

        logger.info(f"Current {symbol} price: ${underlying_price:.2f}")

        # Execute entry
        execution = await entry_workflow.execute_entry(
            symbol=symbol,
            strategy_type=best.strategy.strategy_type,
            params={
                'underlying_price': underlying_price,
                'dte': 45,
                'quantity': 1,
            }
        )

        if execution and execution.status != 'failed':
            logger.success(f"✓ Successfully executed {best.strategy_name} for {symbol}")
            logger.info(f"Execution ID: {execution.execution_id}")

            # Show legs
            for leg in execution.legs:
                logger.info(f"  {leg.action.value} {leg.right} ${leg.strike} x{leg.quantity}")

            return {
                'symbol': symbol,
                'success': True,
                'strategy': best.strategy_name,
                'score': best.score,
                'credit': best.credit,
                'execution_id': execution.execution_id,
                'status': execution.status,
            }
        else:
            logger.error(f"✗ Execution failed for {symbol}")
            return {
                'symbol': symbol,
                'success': False,
                'reason': execution.status if execution else 'Unknown error',
                'best_strategy': best.strategy_name,
                'score': best.score
            }

    except Exception as e:
        logger.error(f"Failed to execute strategy for {symbol}: {e}")
        import traceback
        traceback.print_exc()

        return {
            'symbol': symbol,
            'success': False,
            'reason': str(e)
        }


async def main(dry_run: bool = False):
    """Execute best strategies for all symbols."""

    logger.info("=" * 80)
    logger.info("EXECUTE BEST STRATEGIES - v6 EntryWorkflow Infrastructure")
    logger.info("=" * 80)
    logger.info(f"Time: {datetime.now()}")
    logger.info(f"Mode: {'DRY RUN (simulation)' if dry_run else 'LIVE TRADING'}")
    logger.info("")

    # Initialize
    try:
        entry_workflow = await initialize_entry_workflow(dry_run=dry_run)
        selector = StrategySelector()
    except Exception as e:
        logger.error(f"Failed to initialize EntryWorkflow: {e}")
        import traceback
        traceback.print_exc()
        return 1

    symbols = ["SPY", "QQQ", "IWM"]
    results = []

    for symbol in symbols:
        result = await execute_symbol_strategy(
            entry_workflow=entry_workflow,
            selector=selector,
            symbol=symbol,
            dry_run=dry_run,
            min_score=70.0
        )
        results.append(result)

    # Cleanup
    try:
        await entry_workflow.execution_engine.ib_conn.disconnect()
        logger.info("✓ Disconnected from IB")
    except:
        pass

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("EXECUTION SUMMARY")
    logger.info("=" * 80)

    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]

    logger.info(f"\n✓ Successfully executed: {len(successful)}/{len(symbols)}")

    for result in successful:
        logger.info(f"  {result['symbol']}: {result['strategy']} (Score: {result['score']:.1f}, Exec ID: {result.get('execution_id', 'N/A')})")

    if failed:
        logger.warning(f"\n✗ Skipped: {len(failed)}/{len(symbols)}")
        for result in failed:
            logger.warning(f"  {result['symbol']}: {result.get('reason', 'Unknown')}")

    logger.info(f"\nTotal credits: ${sum(r.get('credit', 0) for r in successful):.2f}")
    logger.success("\n" + "=" * 80)
    logger.success("EXECUTION COMPLETE")
    logger.success("=" * 80)

    return 0 if len(successful) > 0 else 1


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Execute best options strategies")
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simulate orders without placing them (default: False)'
    )
    parser.add_argument(
        '--min-score',
        type=float,
        default=70.0,
        help='Minimum strategy score to execute (default: 70.0)'
    )

    args = parser.parse_args()

    exit_code = asyncio.run(main(dry_run=args.dry_run))
    sys.exit(exit_code)
