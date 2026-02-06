#!/usr/bin/env python3
"""
Execute ALL Option Strategies - Paper Trading

Executes all 3 strategy types for all 3 symbols:
1. Iron Condor (neutral)
2. Bull Put Spread (bullish)
3. Bear Call Spread (bearish)

Symbols: SPY, QQQ, IWM
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

from ib_async import IB, Option
from loguru import logger

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


async def execute_spread(ib, symbol, legs, quantity, expiration, strategy_name):
    """Execute a vertical spread strategy."""

    logger.info(f"\n{'='*80}")
    logger.info(f"EXECUTING {symbol} {strategy_name}")
    logger.info(f"{'='*80}")

    orders_placed = []

    try:
        # Place each leg order
        for i, leg in enumerate(legs, 1):
            right = leg['right']
            strike = leg['strike']
            action = leg['action']
            ratio = leg['ratio']

            logger.info(f"\nLeg {i}/{len(legs)}: {action} {right} ${strike}")
            logger.info("-" * 40)

            # Create option contract
            option = Option(
                symbol=symbol,
                lastTradeDateOrContractMonth=expiration,
                strike=strike,
                right=right,
                exchange='CBOE',
                currency='USD'
            )

            # Qualify contract
            logger.info(f"  Qualifying contract...")
            qualified = await ib.qualifyContractsAsync(option)

            if not qualified:
                logger.error(f"  ✗ Failed to qualify {right} ${strike}")
                continue

            option = qualified[0]
            logger.info(f"  ✓ Qualified: conId={option.conId}")

            # Determine order action
            if action == 'BUY':
                order_type = 'BUY'
            else:
                order_type = 'SELL'

            # Paper trading - simulate order
            logger.info(f"  ✓ PAPER TRADE: {order_type} {symbol} {right} ${strike} x{ratio}")
            logger.info(f"     Expiration: {expiration}")
            logger.info(f"     Note: Paper trading - no real order placed")

            orders_placed.append({
                'leg': i,
                'action': action,
                'right': right,
                'strike': strike,
                'ratio': ratio,
                'conId': option.conId,
                'status': 'PAPER_TRADE'
            })

        logger.info(f"\n{'='*80}")
        logger.info(f"✓ {symbol} {strategy_name} ORDER COMPLETE")
        logger.info(f"{'='*80}")
        logger.info(f"Orders Placed: {len(orders_placed)}/{len(legs)}")

        return orders_placed

    except Exception as e:
        logger.error(f"Error executing {symbol} {strategy_name}: {e}")
        import traceback
        traceback.print_exc()
        return []


async def main():
    """Execute all 3 strategy types for all 3 symbols."""

    logger.info("=" * 80)
    logger.info("EXECUTE ALL STRATEGIES - PAPER TRADING")
    logger.info("=" * 80)
    logger.info(f"Time: {datetime.now()}")
    logger.info(f"Mode: PAPER TRADING (No real money at risk)")
    logger.info("")

    # Connect to IB Gateway
    ib = IB()
    try:
        await ib.connectAsync(
            host='127.0.0.1',
            port=4002,
            clientId=9970,  # Unique clientId for strategy execution
            timeout=10
        )
        logger.success("✓ Connected to IB Gateway on port 4002")
    except Exception as e:
        logger.error(f"Failed to connect to IB Gateway: {e}")
        logger.info("\nNote: This is expected if IB Gateway is not running.")
        logger.info("For paper trading, IB Gateway must be running on port 4002.")
        return 1

    try:
        # Define all strategies for all symbols
        # Based on fresh option data from 11:37 AM
        strategies = []

        # ===== SPY STRATEGIES =====
        spy_underlying = 690  # Est. from option data

        # SPY Iron Condor (Neutral)
        strategies.append({
            'symbol': 'SPY',
            'name': 'IRON CONDOR',
            'legs': [
                {'right': 'PUT', 'strike': 655, 'action': 'BUY', 'ratio': 1},  # Long put (5% OTM)
                {'right': 'PUT', 'strike': 685, 'action': 'SELL', 'ratio': 1},  # Short put
                {'right': 'CALL', 'strike': 695, 'action': 'SELL', 'ratio': 1},  # Short call
                {'right': 'CALL', 'strike': 725, 'action': 'BUY', 'ratio': 1},  # Long call (5% OTM)
            ],
            'quantity': 1,
            'expiration': '20260320',
        })

        # SPY Bull Put Spread (Bullish)
        strategies.append({
            'symbol': 'SPY',
            'name': 'BULL PUT SPREAD',
            'legs': [
                {'right': 'PUT', 'strike': 685, 'action': 'BUY', 'ratio': 1},  # ITM/ATM put
                {'right': 'PUT', 'strike': 665, 'action': 'SELL', 'ratio': 1},  # OTM put
            ],
            'quantity': 1,
            'expiration': '20260320',
        })

        # SPY Bear Call Spread (Bearish)
        strategies.append({
            'symbol': 'SPY',
            'name': 'BEAR CALL SPREAD',
            'legs': [
                {'right': 'CALL', 'strike': 695, 'action': 'BUY', 'ratio': 1},  # ITM/ATM call
                {'right': 'CALL', 'strike': 725, 'action': 'SELL', 'ratio': 1},  # OTM call
            ],
            'quantity': 1,
            'expiration': '20260320',
        })

        # ===== QQQ STRATEGIES =====
        qqq_underlying = 665  # Est. from option data

        # QQQ Iron Condor (Neutral)
        strategies.append({
            'symbol': 'QQQ',
            'name': 'IRON CONDOR',
            'legs': [
                {'right': 'PUT', 'strike': 598, 'action': 'BUY', 'ratio': 1},
                {'right': 'PUT', 'strike': 632, 'action': 'SELL', 'ratio': 1},
                {'right': 'CALL', 'strike': 680, 'action': 'SELL', 'ratio': 1},
                {'right': 'CALL', 'strike': 765, 'action': 'BUY', 'ratio': 1},
            ],
            'quantity': 1,
            'expiration': '20260320',
        })

        # QQQ Bull Put Spread (Bullish)
        strategies.append({
            'symbol': 'QQQ',
            'name': 'BULL PUT SPREAD',
            'legs': [
                {'right': 'PUT', 'strike': 632, 'action': 'BUY', 'ratio': 1},
                {'right': 'PUT', 'strike': 608, 'action': 'SELL', 'ratio': 1},
            ],
            'quantity': 1,
            'expiration': '20260320',
        })

        # QQQ Bear Call Spread (Bearish)
        strategies.append({
            'symbol': 'QQQ',
            'name': 'BEAR CALL SPREAD',
            'legs': [
                {'right': 'CALL', 'strike': 680, 'action': 'BUY', 'ratio': 1},
                {'right': 'CALL', 'strike': 715, 'action': 'SELL', 'ratio': 1},
            ],
            'quantity': 1,
            'expiration': '20260320',
        })

        # ===== IWM STRATEGIES =====
        iwm_underlying = 245  # Est. from option data

        # IWM Iron Condor (Neutral)
        strategies.append({
            'symbol': 'IWM',
            'name': 'IRON CONDOR',
            'legs': [
                {'right': 'PUT', 'strike': 230, 'action': 'BUY', 'ratio': 1},
                {'right': 'PUT', 'strike': 233, 'action': 'SELL', 'ratio': 1},
                {'right': 'CALL', 'strike': 257, 'action': 'SELL', 'ratio': 1},
                {'right': 'CALL', 'strike': 269, 'action': 'BUY', 'ratio': 1},
            ],
            'quantity': 1,
            'expiration': '20260320',
        })

        # IWM Bull Put Spread (Bullish)
        strategies.append({
            'symbol': 'IWM',
            'name': 'BULL PUT SPREAD',
            'legs': [
                {'right': 'PUT', 'strike': 233, 'action': 'BUY', 'ratio': 1},
                {'right': 'PUT', 'strike': 224, 'action': 'SELL', 'ratio': 1},
            ],
            'quantity': 1,
            'expiration': '20260320',
        })

        # IWM Bear Call Spread (Bearish)
        strategies.append({
            'symbol': 'IWM',
            'name': 'BEAR CALL SPREAD',
            'legs': [
                {'right': 'CALL', 'strike': 257, 'action': 'BUY', 'ratio': 1},
                {'right': 'CALL', 'strike': 270, 'action': 'SELL', 'ratio': 1},
            ],
            'quantity': 1,
            'expiration': '20260320',
        })

        logger.info("STRATEGIES TO EXECUTE:")
        logger.info("-" * 80)
        for i, s in enumerate(strategies, 1):
            logger.info(f"{i}. {s['symbol']} {s['name']}")
        logger.info(f"\nTotal: {len(strategies)} strategies")
        logger.info("")

        # Execute each strategy
        all_orders = []

        for strategy in strategies:
            orders = await execute_spread(
                ib,
                strategy['symbol'],
                strategy['legs'],
                strategy['quantity'],
                strategy['expiration'],
                strategy['name']
            )
            all_orders.extend(orders)

        # Final summary
        logger.info("\n" + "=" * 80)
        logger.info("EXECUTION COMPLETE - PAPER TRADING SUMMARY")
        logger.info("=" * 80)
        logger.info(f"\n✓ Executed {len(strategies)} strategies")
        logger.info(f"✓ Total orders placed: {len(all_orders)}")

        # Group by symbol and strategy
        summary = {}
        for order in all_orders:
            key = f"{order['action']} {order['right']} ${order['strike']}"
            summary[key] = summary.get(key, 0) + 1

        logger.info(f"\nPositions ({len(summary)} unique contracts):")
        for order in all_orders:
            logger.info(f"  • {order['action']} {order['right']} ${order['strike']} (conId: {order['conId']})")

        logger.info("\n" + "=" * 80)
        logger.info("STRATEGY BREAKDOWN:")
        logger.info("=" * 80)
        for i, s in enumerate(strategies, 1):
            logger.info(f"{i}. {s['symbol']} {s['name']}")

        logger.info("\n" + "=" * 80)
        logger.info("PAPER TRADING NOTES:")
        logger.info("=" * 80)
        logger.info("• These are PAPER TRADES - no real money was risked")
        logger.info("• Orders were simulated, not placed with IB")
        logger.info("• For live trading, would use ib.placeOrder() with real execution")
        logger.info("• Risk Manager's PositionMonitoringWorkflow will monitor positions")
        logger.info("• Decision Engine will evaluate exit rules every 30 seconds")
        logger.info("=" * 80)

        return 0

    finally:
        try:
            await ib.disconnect()
            logger.info("\n✓ Disconnected from IB Gateway")
        except Exception as e:
            logger.debug(f"Disconnect note: {e}")


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
