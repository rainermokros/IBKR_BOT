#!/usr/bin/env python3
"""
Verify Current Positions - Delta Lake & IB Status

Checks:
1. Delta Lake strategy_executions table for today's positions
2. IB Gateway for current open positions
3. Recommendations: Execute new strategies or run Risk Manager

Usage:
    PYTHONPATH=/home/bigballs/project/bot/v6/src python scripts/verify_positions.py
"""

import asyncio
import sys
from datetime import date, datetime
from pathlib import Path

import polars as pl
from deltalake import DeltaTable
from ib_async import IB
from loguru import logger

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def check_delta_lake_positions():
    """Check Delta Lake for today's strategy executions."""
    logger.info("=" * 80)
    logger.info("CHECKING DELTA LAKE - Today's Strategy Executions")
    logger.info("=" * 80)

    try:
        dt = DeltaTable('data/lake/strategy_executions')
        df = pl.from_pandas(dt.to_pandas())

        # Filter for today's entries
        today = date.today()
        today_df = df.filter(
            pl.col('entry_time').dt.date() == today
        )

        if len(today_df) == 0:
            logger.info("✓ No positions found in Delta Lake for today")
            return []
        else:
            logger.info(f"Found {len(today_df)} position(s) in Delta Lake for today:")

            for row in today_df.iter_rows(named=True):
                exec_id = row.get('execution_id', 'N/A')[:8]
                symbol = row.get('symbol', 'N/A')
                strategy_type = row.get('strategy_type', 'N/A')
                status = row.get('status', 'N/A')

                logger.info(f"  • {symbol} {strategy_type} (ID: {exec_id}) - {status}")

            return today_df.to_dicts()

    except Exception as e:
        logger.warning(f"Could not check Delta Lake: {e}")
        logger.info("  (Table might not exist yet)")
        return []


async def check_ib_positions():
    """Check IB Gateway for current open positions."""
    logger.info("\n" + "=" * 80)
    logger.info("CHECKING IB GATEWAY - Current Positions")
    logger.info("=" * 80)

    ib = IB()
    try:
        await ib.connectAsync(host='127.0.0.1', port=4002, clientId=9996, timeout=10)
        logger.success("✓ Connected to IB Gateway")

        # Get all positions
        positions = ib.positions()

        if not positions:
            logger.info("✓ No open positions in IB account")
            await ib.disconnect()
            return []
        else:
            logger.info(f"Found {len(positions)} position(s) in IB account:")

            option_positions = []
            for position in positions:
                contract = position.contract
                if hasattr(contract, 'right'):  # It's an option
                    symbol = contract.symbol
                    right = contract.right
                    strike = contract.strike
                    expiry = contract.lastTradeDateOrContractMonth
                    quantity = position.position

                    logger.info(f"  • {symbol} {right} ${strike} {expiry} - Qty: {quantity}")

                    option_positions.append({
                        'symbol': symbol,
                        'right': right,
                        'strike': strike,
                        'expiry': expiry,
                        'quantity': quantity
                    })

            await ib.disconnect()
            return option_positions

    except Exception as e:
        logger.error(f"Failed to connect to IB Gateway: {e}")
        logger.info("  (IB Gateway might not be running)")
        return []


def group_positions_into_strategies(positions):
    """Group individual option positions into strategies."""
    if not positions:
        return []

    # Group by symbol
    by_symbol = {}
    for pos in positions:
        symbol = pos['symbol']
        if symbol not in by_symbol:
            by_symbol[symbol] = []
        by_symbol[symbol].append(pos)

    strategies = []
    for symbol, legs in by_symbol.items():
        # Count legs to determine strategy type
        num_legs = len(legs)

        if num_legs == 4:
            strategy_type = "Iron Condor"
        elif num_legs == 2:
            # Check if it's a spread
            rights = [leg['right'] for leg in legs]
            if 'P' in rights and 'C' in rights:
                strategy_type = "Mixed (Complex)"
            else:
                strategy_type = "Vertical Spread"
        else:
            strategy_type = f"Complex ({num_legs} legs)"

        strategies.append({
            'symbol': symbol,
            'type': strategy_type,
            'legs': num_legs
        })

    return strategies


async def main():
    """Verify current positions and recommend next action."""

    logger.info("=" * 80)
    logger.info("POSITION VERIFICATION")
    logger.info("=" * 80)
    logger.info(f"Time: {datetime.now()}")
    logger.info(f"Date: {date.today()}")
    logger.info("")

    # Check Delta Lake
    dl_positions = check_delta_lake_positions()

    # Check IB Gateway
    ib_positions = await check_ib_positions()

    # Analyze and recommend
    logger.info("\n" + "=" * 80)
    logger.info("ANALYSIS & RECOMMENDATIONS")
    logger.info("=" * 80)

    if dl_positions or ib_positions:
        # We have positions!
        total_dl = len(dl_positions)
        total_ib = len(ib_positions)

        logger.info(f"\n✓ POSITIONS FOUND:")
        logger.info(f"  Delta Lake: {total_dl} strategies")
        logger.info(f"  IB Account: {total_ib} option legs")

        if ib_positions:
            strategies = group_positions_into_strategies(ib_positions)
            logger.info(f"\n  Detected strategies in IB:")
            for s in strategies:
                logger.info(f"    • {s['symbol']} {s['type']} ({s['legs']} legs)")

        logger.info("\n" + "=" * 80)
        logger.info("RECOMMENDATION:")
        logger.info("=" * 80)
        logger.info("✓ Run Risk Manager to monitor and control existing positions")
        logger.info("")
        logger.info("Commands:")
        logger.info("  1. Start PositionMonitoringWorkflow:")
        logger.info("     PYTHONPATH=/home/bigballs/project/bot/v6/src python -c \"")
        logger.info("     import asyncio")
        logger.info("     from v6.risk_manager.trading_workflows.monitoring import PositionMonitoringWorkflow")
        logger.info("     # ... initialize and run monitoring ...")
        logger.info("     \"")
        logger.info("")
        logger.info("  2. Check current status of positions")
        logger.info("     PYTHONPATH=/home/bigballs/project/bot/v6/src python scripts/verify_positions.py")
        logger.info("=" * 80)

        return 1  # Return 1 to signal "have positions, run risk manager"

    else:
        # No positions - recommend execution
        logger.info("\n✓ NO POSITIONS FOUND")
        logger.info("")
        logger.info("Recommendation: Execute new strategies using Strategy Selector")
        logger.info("")
        logger.info("Commands:")
        logger.info("  1. Run Strategy Selector to find best strategies:")
        logger.info("     PYTHONPATH=/home/bigballs/project/bot/v6/src python -c \"")
        logger.info("     import asyncio")
        logger.info("     from v6.strategy_builder.strategy_selector import StrategySelector")
        logger.info("     async def main():")
        logger.info("         selector = StrategySelector()")
        logger.info("         for symbol in ['SPY', 'QQQ', 'IWM']:")
        logger.info("             best = await selector.get_best_strategy(symbol)")
        logger.info("             if best and best.score >= 70:")
        logger.info("                 print(f'Execute {symbol} {best.strategy_name}')")
        logger.info("     asyncio.run(main())")
        logger.info("     \"")
        logger.info("")
        logger.info("  2. Execute using EntryWorkflow (proper v6 infrastructure)")
        logger.info("=" * 80)

        return 0  # Return 0 to signal "no positions, execute new"


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
