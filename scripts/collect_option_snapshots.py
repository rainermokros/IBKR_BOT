#!/usr/bin/env python
"""
Option Snapshots Collection with Retry and Backfill

Collects option data for SPY, QQQ, IWM ETFs with:
- Automatic retry with exponential backoff
- Backfill queue for failed collections
- Connection resilience and auto-reconnect
- Error classification and smart retry logic

DTE Range: 45-75 days (targets 45+ DTE for strategy positioning)

Author: Enhanced 2026-02-05
Status: PRODUCTION with retry logic
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
from v6.data.collection_queue import CollectionQueue
from v6.utils.collection_retry import retry_with_backoff, classify_error


async def collect_with_reconnect(ib: IB, symbol: str) -> dict:
    """
    Collect option data for a single symbol with reconnection handling.

    Returns dict with:
        - success: bool
        - snapshots: list of snapshot dicts
        - error: str if failed
    """
    try:
        # Check connection
        if not ib.isConnected():
            logger.warning(f"Connection lost for {symbol}, reconnecting...")
            await ib.connectAsync(host="127.0.0.1", port=4002, clientId=9980, timeout=10)
            await asyncio.sleep(1)

        today = date.today()
        yearmonth = today.year * 100 + today.month

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

        # Find weekly expirations
        chains = await ib.reqSecDefOptParamsAsync(symbol, '', 'STK', stock.conId)
        if not chains:
            raise Exception("No chains available")

        # Find SMART exchange chain
        chain = None
        for c in chains:
            if c.exchange == 'SMART' and c.tradingClass == symbol:
                chain = c
                break

        if not chain:
            raise Exception("No SMART exchange chain found")

        # Filter for 45-75 DTE expirations
        now = datetime.now()
        target_expiry = None
        for exp in chain.expirations:
            try:
                exp_date = datetime.strptime(exp, "%Y%m%d")
                dte = (exp_date - now).days
                if 45 <= dte <= 75:
                    target_expiry = exp
                    break
            except ValueError:
                continue

        if not target_expiry:
            raise Exception("No suitable expiration found (45-75 DTE)")

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
                    option = Option(symbol, target_expiry, strike, right, 'SMART')
                    qualified = await ib.qualifyContractsAsync(option)

                    if not qualified or not qualified[0]:
                        continue

                    option = qualified[0]
                    mt = ib.reqMktData(option, "", False, False)
                    await asyncio.sleep(1)

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
                    # Error 200 is normal - contract doesn't exist
                    if "Error 200" not in str(e):
                        logger.debug(f"Error collecting {strike}{right}: {e}")
                    continue

        if not all_snapshots:
            raise Exception("No data collected")

        logger.info(f"Collected {len(all_snapshots)} contracts for {symbol}")

        return {
            "success": True,
            "snapshots": all_snapshots,
            "error": None
        }

    except Exception as e:
        error = classify_error(e)
        logger.error(f"Failed to collect {symbol}: {error.error_type} - {error.message}")
        return {
            "success": False,
            "snapshots": [],
            "error": error
        }


async def collect_option_data():
    """Collect option data for SPY, QQQ, IWM with retry logic."""

    logger.remove()
    logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>")

    logger.info("=" * 70)
    logger.info("OPTION DATA COLLECTION WITH RETRY - SPY, QQQ, IWM")
    logger.info("=" * 70)

    # Initialize queue
    queue = CollectionQueue()
    target_time = datetime.now()

    # Use assigned clientId from CLIENT_ID_REFERENCE.md
    client_id = 9980  # Data collection scripts (9980-9994 range)
    logger.info(f"Using clientId: {client_id}")

    ib = IB()
    await ib.connectAsync(host="127.0.0.1", port=4002, clientId=client_id, timeout=10)

    try:
        total_collected = 0
        symbols = ["SPY", "QQQ", "IWM"]

        for symbol in symbols:
            logger.info(f"\n{'='*70}")

            # Collection function with retry
            async def collect_symbol():
                return await collect_with_reconnect(ib, symbol)

            # Execute with retry logic
            result = await retry_with_backoff(
                func=collect_symbol,
                symbol=symbol,
                queue=queue,
                target_time=target_time,
                max_retries=3,
                base_delay=1.0,
                max_delay=10.0
            )

            if result and result.get("success"):
                # Save to Delta Lake
                snapshots = result["snapshots"]
                if snapshots:
                    logger.info(f"Saving {len(snapshots)} contracts for {symbol}...")
                    df = pl.DataFrame(snapshots)
                    table = OptionSnapshotsTable()
                    table.append_snapshot(df)
                    logger.success(f"✓ SAVED {len(snapshots)} contracts for {symbol}")
                    total_collected += len(snapshots)
            else:
                logger.error(f"❌ Failed to collect {symbol} after all retries")

        logger.info(f"\n{'='*70}")
        logger.info(f"TOTAL COLLECTED: {total_collected} contracts")
        logger.info(f"{'='*70}")

        # Show queue stats
        stats = queue.get_stats()
        if stats['pending'] > 0:
            logger.warning(f"⚠️  {stats['pending']} items in backfill queue")

        return 0 if total_collected > 0 else 1

    finally:
        ib.disconnect()


if __name__ == "__main__":
    exit_code = asyncio.run(collect_option_data())
    sys.exit(exit_code)
