#!/usr/bin/env python
"""
Option Snapshots Collection - WORKING VERSION

Successfully collects option data for SPY, QQQ, IWM ETFs.
Uses weekly expirations (45+ DTE) for strategy positions.

Key Fix: Uses Option() without tradingClass parameter, which causes
ambiguity errors with IB Gateway. Basic qualification works for weekly
expirations like 20260331 (54 DTE).

DTE Range: 45-75 days (targets 45+ DTE for strategy positioning)

Author: Fixed 2026-02-04
Status: PRODUCTION - Successfully collecting data
"""

import asyncio
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from loguru import logger
from ib_async import IB, Stock, Option
import polars as pl

from v6.system_monitor.data.option_snapshots import OptionSnapshotsTable


async def collect_option_data():
    """Collect option data for SPY, QQQ, IWM using weekly expirations."""

    logger.remove()
    logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>")

    logger.info("=" * 70)
    logger.info("OPTION DATA COLLECTION - SPY, QQQ, IWM")
    logger.info("=" * 70)

    import random
    client_id = random.randint(100, 999)
    logger.info(f"Using clientId: {client_id}")

    ib = IB()
    await ib.connectAsync(host="127.0.0.1", port=4002, clientId=client_id, timeout=10)

    try:
        total_collected = 0
        today = date.today()
        yearmonth = today.year * 100 + today.month

        for symbol in ["SPY", "QQQ", "IWM"]:
            logger.info(f"\n{'='*70}")
            logger.info(f"COLLECTING {symbol}")
            logger.info(f"{'='*70}")

            # Get stock price
            stock = Stock(symbol, 'SMART', 'USD')
            await ib.qualifyContractsAsync(stock)
            ticker = ib.reqMktData(stock, "", False, False)
            await asyncio.sleep(1)

            current_price = ticker.marketPrice() if hasattr(ticker, 'marketPrice') else ticker.last
            logger.info(f"{symbol} Price: {current_price}")

            # Find weekly expirations 15-30 DTE (these work with basic Option())
            chains = await ib.reqSecDefOptParamsAsync(symbol, '', 'STK', stock.conId)
            if not chains:
                logger.warning(f"No chains for {symbol}")
                continue

            # Find SMART exchange chain
            chain = None
            for c in chains:
                if c.exchange == 'SMART' and c.tradingClass == symbol:
                    chain = c
                    break

            if not chain:
                logger.warning(f"No SMART/{symbol} chain found")
                continue

            # Filter for 45-75 DTE expirations (target 45+ DTE for strategy positioning)
            now = datetime.now()
            target_expiry = None
            for exp in chain.expirations:
                try:
                    exp_date = datetime.strptime(exp, "%Y%m%d")
                    dte = (exp_date - now).days
                    # Use 45-75 DTE range (strategy positioning range)
                    if 45 <= dte <= 75:
                        target_expiry = exp
                        break
                except ValueError:
                    continue

            if not target_expiry:
                logger.warning(f"No suitable expiration found for {symbol}")
                continue

            logger.info(f"Using expiration: {target_expiry}")

            # Calculate strikes around ATM (±8%)
            min_strike = int(current_price * 0.92)
            max_strike = int(current_price * 1.08)
            strikes = list(range(min_strike, max_strike + 1, 5))
            logger.info(f"Testing {len(strikes)} strikes from {min_strike} to {max_strike}")

            all_snapshots = []

            for strike in strikes:
                for right in ['P', 'C']:
                    try:
                        # KEY: Use basic Option() WITHOUT tradingClass parameter
                        option = Option(symbol, target_expiry, strike, right, 'SMART')
                        qualified = await ib.qualifyContractsAsync(option)

                        if not qualified or not qualified[0]:
                            continue

                        option = qualified[0]
                        mt = ib.reqMktData(option, "", False, False)
                        await asyncio.sleep(1)  # Increased from 0.15s - 45+ DTE options take longer

                        if mt and (mt.bid or mt.ask or mt.last):
                            snapshot = {
                                "timestamp": datetime.now(),
                                "symbol": symbol,
                                "strike": float(strike),
                                "expiry": target_expiry,
                                "right": "CALL" if right == "C" else "PUT",
                                "bid": float(mt.bid) if mt.bid else 0.0,
                                "ask": float(mt.ask) if mt.ask else 0.0,
                                "last": float(mt.last) if mt.last else 0.0,
                                "volume": int(mt.volume) if hasattr(mt, "volume") else 0,
                                "open_interest": int(mt.openInterest) if hasattr(mt, "openInterest") else 0,
                                "iv": 0.0, "delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0,
                                "date": today,
                                "yearmonth": yearmonth,
                            }

                            # Add Greeks if available
                            if hasattr(mt, "modelGreeks") and mt.modelGreeks:
                                snapshot["iv"] = float(mt.modelGreeks.impliedVol) if mt.modelGreeks.impliedVol else 0.0
                                snapshot["delta"] = float(mt.modelGreeks.delta) if mt.modelGreeks.delta else 0.0
                                snapshot["gamma"] = float(mt.modelGreeks.gamma) if mt.modelGreeks.gamma else 0.0
                                snapshot["theta"] = float(mt.modelGreeks.theta) if mt.modelGreeks.theta else 0.0
                                snapshot["vega"] = float(mt.modelGreeks.vega) if mt.modelGreeks.vega else 0.0

                            all_snapshots.append(snapshot)
                            logger.success(f"✓ {symbol} {target_expiry} {strike}{right} bid={mt.bid} ask={mt.ask}")

                    except Exception as e:
                        # Error 200 is normal - some contracts don't exist
                        if "Error 200" not in str(e):
                            logger.debug(f"Error: {e}")
                        continue

            # Save to Delta Lake
            if all_snapshots:
                logger.info(f"Saving {len(all_snapshots)} contracts for {symbol}...")
                df = pl.DataFrame(all_snapshots)
                table = OptionSnapshotsTable()
                table.append_snapshot(df)
                logger.success(f"✓ SAVED {len(all_snapshots)} contracts for {symbol}")
                total_collected += len(all_snapshots)
            else:
                logger.warning(f"No data collected for {symbol}")

        logger.info(f"\n{'='*70}")
        logger.info(f"TOTAL COLLECTED: {total_collected} contracts")
        logger.info(f"{'='*70}")

        return 0 if total_collected > 0 else 1

    finally:
        ib.disconnect()


if __name__ == "__main__":
    exit_code = asyncio.run(collect_option_data())
    sys.exit(exit_code)
