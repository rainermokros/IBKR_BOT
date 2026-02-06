#!/usr/bin/env python
"""
Targeted Option Collection - Uses ONLY 20260320 Expiration

This is the ONLY expiration that successfully collected data before.
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from loguru import logger
from ib_async import IB, Stock, Option


async def collect_20260320_only():
    """Collect ONLY 20260320 expiration options - proven to work!"""

    logger.remove()
    logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>")

    logger.info("=" * 70)
    logger.info("TARGETED COLLECTION: 20260320 EXPIRATION ONLY")
    logger.info("=" * 70)
    logger.info(f"Time: {datetime.now()}")

    ib = IB()
    await ib.connectAsync(host="127.0.0.1", port=4002, timeout=10)

    try:
        total_collected = 0
        target_expiry = "20260320"

        for symbol in ["SPY", "QQQ", "IWM"]:
            logger.info(f"\n{'='*70}")
            logger.info(f"COLLECTING {symbol} - {target_expiry} ONLY")
            logger.info(f"{'='*70}")

            # Get stock
            stock = Stock(symbol, 'SMART', 'USD')
            await ib.qualifyContractsAsync(stock)

            # Get current price
            ticker = ib.reqMktData(stock, "", False, False)
            await asyncio.sleep(2)

            current_price = ticker.marketPrice() if hasattr(ticker, 'marketPrice') and ticker.marketPrice() else 0
            if not current_price:
                current_price = ticker.last if hasattr(ticker, 'last') else 0

            logger.info(f"Current price: {current_price}")

            if not current_price:
                logger.error(f"Cannot get price for {symbol}")
                continue

            # Get option chains
            chains = await ib.reqSecDefOptParamsAsync(symbol, '', 'STK', stock.conId)
            if not chains:
                logger.warning(f"No chains for {symbol}")
                continue

            # Use chain with most expirations
            chain = max(chains, key=lambda c: len(c.expirations))
            logger.info(f"Found {len(chain.expirations)} expirations")

            # Check if 20260320 exists
            if target_expiry not in chain.expirations:
                logger.warning(f"{target_expiry} not available! Available: {chain.expirations[:10]}")
                continue

            logger.success(f"✓ {target_expiry} available!")

            # Get strikes near ATM
            min_strike = current_price * 0.92
            max_strike = current_price * 1.08
            raw_strikes = [s for s in chain.strikes if min_strike <= s <= max_strike]
            rounded_strikes = sorted(set([round(s) for s in raw_strikes]))[:20]

            logger.info(f"Using {len(rounded_strikes)} strikes: {rounded_strikes[:5]}...")

            # Collect ONLY 20260320 contracts
            snapshots = []
            for strike in rounded_strikes:
                for right in ['P', 'C']:
                    try:
                        option = Option(symbol, target_expiry, strike, right, 'SMART')

                        qualified = await ib.qualifyContractsAsync(option)
                        if not qualified:
                            logger.debug(f"Not qualified: {symbol} {target_expiry} {strike} {right}")
                            continue

                        option = qualified[0]

                        # Request market data
                        mt = ib.reqMktData(option, "", False, False)
                        await asyncio.sleep(0.05)

                        # Check for data
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
                            }

                            # Add Greeks
                            if hasattr(mt, "modelGreeks") and mt.modelGreeks:
                                snapshot["iv"] = float(mt.modelGreeks.impliedVol) if mt.modelGreeks.impliedVol else 0.0
                                snapshot["delta"] = float(mt.modelGreeks.delta) if mt.modelGreeks.delta else 0.0
                                snapshot["gamma"] = float(mt.modelGreeks.gamma) if mt.modelGreeks.gamma else 0.0
                                snapshot["theta"] = float(mt.modelGreeks.theta) if mt.modelGreeks.theta else 0.0
                                snapshot["vega"] = float(mt.modelGreeks.vega) if mt.modelGreeks.vega else 0.0
                            else:
                                snapshot.update({"iv": 0.0, "delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0})

                            snapshots.append(snapshot)
                            logger.success(f"✓ {symbol} {target_expiry} {strike} {right} bid={mt.bid} ask={mt.ask}")

                    except Exception as e:
                        if "Error 200" not in str(e):
                            logger.debug(f"Error: {e}")
                        continue

            # Save to Delta Lake if we got data
            if snapshots:
                logger.success(f"✓ Collected {len(snapshots)} contracts for {symbol}")

                # Import here to avoid issues
                from v6.system_monitor.data.option_snapshots import OptionSnapshotsTable
                import polars as pl

                # Convert to DataFrame
                df = pl.DataFrame(snapshots)

                # Write to table
                table = OptionSnapshotsTable()
                table.append_snapshot(df)

                logger.success(f"✓ SAVED to option_snapshots table")
                total_collected += len(snapshots)
            else:
                logger.warning(f"No data collected for {symbol}")

        logger.info(f"\n{'='*70}")
        logger.info(f"TOTAL COLLECTED: {total_collected} contracts")
        logger.info(f"{'='*70}")

        return 0 if total_collected > 0 else 1

    finally:
        ib.disconnect()


if __name__ == "__main__":
    exit_code = asyncio.run(collect_20260320_only())
    sys.exit(exit_code)
