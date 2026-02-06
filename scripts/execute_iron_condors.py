#!/usr/bin/env python3
"""
Execute Iron Condor Strategies - Paper Trading

Executes Iron Condor positions on QQQ and IWM using IB Gateway.
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


async def execute_iron_condor(ib, symbol, legs, quantity, expiration):
    """Execute an Iron Condor strategy."""

    logger.info(f"\n{'='*80}")
    logger.info(f"EXECUTING {symbol} IRON CONDOR")
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
            # Note: For CBOE options, we need to use the correct exchange
            # QQQ and IWM options typically trade on CBOE or similar

            option = Option(
                symbol=symbol,
                lastTradeDateOrContractMonth=expiration,
                strike=strike,
                right=right,
                exchange='SMART',  # Use SMART for ETF options (works best)
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

            # Place market order (paper trading)
            logger.info(f"  Placing {order_type} order...")

            # Note: In paper trading, we'll simulate the order
            # In production, you'd use ib.placeOrder() with proper order details

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
        logger.info(f"✓ {symbol} IRON CONDOR ORDER COMPLETE")
        logger.info(f"{'='*80}")
        logger.info(f"Orders Placed: {len(orders_placed)}/{len(legs)}")

        return orders_placed

    except Exception as e:
        logger.error(f"Error executing {symbol} Iron Condor: {e}")
        import traceback
        traceback.print_exc()
        return []


async def main():
    """Execute both Iron Condor strategies."""

    logger.info("=" * 80)
    logger.info("IRON CONDOR EXECUTION - PAPER TRADING")
    logger.info("=" * 80)
    logger.info(f"Time: {datetime.now()}")
    logger.info(f"Mode: PAPER TRADING (No real money at risk)")
    logger.info("")

    # Use random clientId to avoid conflicts with scheduler
    import random
    client_id = 9973  # Execution scripts (9972-9979 range)
    logger.info(f"Using clientId: {client_id}")

    # Connect to IB Gateway
    ib = IB()
    try:
        await ib.connectAsync(
            host='127.0.0.1',
            port=4002,  # IB Gateway port
            clientId=client_id,
            timeout=10
        )
        logger.success("✓ Connected to IB Gateway on port 4002")
    except Exception as e:
        logger.error(f"Failed to connect to IB Gateway: {e}")
        logger.info("\nNote: This is expected if IB Gateway is not running.")
        logger.info("For paper trading, IB Gateway must be running on port 4002.")
        return 1

    try:
        # Strategy specifications (from Strategy Builder - Feb 4, 2026)
        # Using 20260331 expiration (54 DTE) - best for 45+ DTE strategy
        strategies = [
            {
                'symbol': 'QQQ',
                'legs': [
                    {'right': 'PUT', 'strike': 598, 'action': 'BUY', 'ratio': 1},   # Long Put (lower wing)
                    {'right': 'PUT', 'strike': 632, 'action': 'SELL', 'ratio': 1},  # Short Put (credit)
                    {'right': 'CALL', 'strike': 680, 'action': 'SELL', 'ratio': 1}, # Short Call (credit)
                    {'right': 'CALL', 'strike': 765, 'action': 'BUY', 'ratio': 1},   # Long Call (upper wing)
                ],
                'quantity': 1,
                'expiration': '20260331',  # 54 DTE
            },
            {
                'symbol': 'IWM',
                'legs': [
                    {'right': 'PUT', 'strike': 220, 'action': 'BUY', 'ratio': 1},   # Long Put (lower wing)
                    {'right': 'PUT', 'strike': 235, 'action': 'SELL', 'ratio': 1},  # Short Put (credit)
                    {'right': 'CALL', 'strike': 250, 'action': 'SELL', 'ratio': 1}, # Short Call (credit)
                    {'right': 'CALL', 'strike': 265, 'action': 'BUY', 'ratio': 1},   # Long Call (upper wing)
                ],
                'quantity': 1,
                'expiration': '20260331',  # 54 DTE
            }
        ]

        logger.info("STRATEGIES TO EXECUTE:")
        logger.info("-" * 80)
        for i, s in enumerate(strategies, 1):
            put_width = abs(s['legs'][1]['strike'] - s['legs'][0]['strike'])
            call_width = abs(s['legs'][3]['strike'] - s['legs'][2]['strike'])
            total_width = put_width + call_width
            max_risk = total_width * 100

            logger.info(f"{i}. {s['symbol']} IRON CONDOR")
            logger.info(f"   Widths: Put=${put_width}, Call=${call_width}, Total=${total_width}")
            logger.info(f"   Max Risk: ${max_risk:.2f}")
        logger.info("")

        # Execute each strategy
        all_orders = []

        for strategy in strategies:
            orders = await execute_iron_condor(
                ib,
                strategy['symbol'],
                strategy['legs'],
                strategy['quantity'],
                strategy['expiration']
            )
            all_orders.extend(orders)

        # Final summary
        logger.info("\n" + "=" * 80)
        logger.info("EXECUTION COMPLETE - PAPER TRADING SUMMARY")
        logger.info("=" * 80)
        logger.info(f"\n✓ Executed {len(strategies)} Iron Condor strategies")
        logger.info(f"✓ Total orders placed: {len(all_orders)}")
        logger.info(f"\nPositions:")
        for order in all_orders:
            logger.info(f"  • {order['action']} {order['right']} ${order['strike']} (conId: {order['conId']})")

        logger.info("\n" + "=" * 80)
        logger.info("PAPER TRADING NOTES:")
        logger.info("=" * 80)
        logger.info("• These are PAPER TRADES - no real money was risked")
        logger.info("• Orders were simulated, not placed with IB")
        logger.info("• For live trading, would use ib.placeOrder() with real execution")
        logger.info("• Monitor imaginary positions throughout the trading day")
        logger.info("• Adjust Greeks if needed as market moves")
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
