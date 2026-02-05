#!/usr/bin/env python
"""
Backfill Worker for Option Snapshots

Processes failed collection attempts from the queue.
Runs in background to recover missed data windows.

Key features:
- Processes queue items with retry logic
- Automatic reconnection handling
- Removes Error 200 items from queue
- Runs continuously or in batch mode
"""

import asyncio
import sys
import signal
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from loguru import logger
from ib_async import IB, Stock, Option
import polars as pl

from v6.system_monitor.data.option_snapshots import OptionSnapshotsTable
from v6.data.collection_queue import CollectionQueue
from v6.utils.collection_retry import classify_error


class BackfillWorker:
    """Background worker that processes failed collection attempts."""

    def __init__(self, client_id: int = 9981):
        """
        Initialize backfill worker.

        Args:
            client_id: IBKR client ID (different from main collector)
        """
        self.client_id = client_id
        self.queue = CollectionQueue()
        self.running = False
        self.ib = None

    async def collect_snapshot(
        self,
        symbol: str,
        target_time: datetime,
        strikes: list,
        expiry: str
    ) -> dict:
        """
        Collect option snapshot for backfill.

        Returns dict with success status and snapshots.
        """
        try:
            # Ensure connection
            if not self.ib or not self.ib.isConnected():
                logger.info("Connecting to IBKR...")
                if not self.ib:
                    self.ib = IB()
                await self.ib.connectAsync(host="127.0.0.1", port=4002, clientId=self.client_id, timeout=10)
                await asyncio.sleep(1)

            today = target_time.date()
            yearmonth = today.year * 100 + today.month

            # Get stock price
            stock = Stock(symbol, 'SMART', 'USD')
            await self.ib.qualifyContractsAsync(stock)
            ticker = self.ib.reqMktData(stock, "", False, False)
            await asyncio.sleep(1)

            current_price = ticker.marketPrice() if hasattr(ticker, 'marketPrice') else ticker.last

            all_snapshots = []

            for strike in strikes:
                for right in ['P', 'C']:
                    try:
                        option = Option(symbol, expiry, strike, right, 'SMART')
                        qualified = await self.ib.qualifyContractsAsync(option)

                        if not qualified or not qualified[0]:
                            continue

                        option = qualified[0]
                        mt = self.ib.reqMktData(option, "", False, False)
                        await asyncio.sleep(1)

                        if mt and (mt.bid or mt.ask or mt.last):
                            snapshot = {
                                "timestamp": target_time,  # Use original target time
                                "symbol": symbol,
                                "strike": float(strike),
                                "expiry": expiry,
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

                    except Exception as e:
                        # Error 200 - skip these contracts
                        if "Error 200" in str(e):
                            continue
                        logger.debug(f"Error: {e}")
                        continue

            if all_snapshots:
                return {
                    "success": True,
                    "snapshots": all_snapshots,
                    "error": None
                }
            else:
                return {
                    "success": False,
                    "snapshots": [],
                    "error": Exception("No data collected")
                }

        except Exception as e:
            error = classify_error(e)
            return {
                "success": False,
                "snapshots": [],
                "error": error
            }

    async def process_queue_item(self, item) -> bool:
        """
        Process a single queue item.

        Args:
            item: QueueItem to process

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"🔄 Processing {item.symbol} from {item.target_time} (attempt {item.retry_count + 1}/{item.max_retries})")

        # Ensure IB connection
        if not self.ib or not self.ib.isConnected():
            logger.warning("IB connection lost, reconnecting...")
            try:
                if not self.ib:
                    self.ib = IB()
                await self.ib.connectAsync(host="127.0.0.1", port=4002, clientId=self.client_id, timeout=10)
                logger.success("✓ Reconnected to IB Gateway")
            except Exception as e:
                logger.error(f"✗ Failed to reconnect: {e}")
                return False

        try:
            # Calculate strikes (same logic as main collector)
            # Use current price as approximation (historical price not available)
            stock = Stock(item.symbol, 'SMART', 'USD')
            await self.ib.qualifyContractsAsync(stock)
            ticker = self.ib.reqMktData(stock, "", False, False)
            await asyncio.sleep(1)

            current_price = ticker.marketPrice() if hasattr(ticker, 'marketPrice') else ticker.last

            # Find chains and expiry
            chains = await self.ib.reqSecDefOptParamsAsync(item.symbol, '', 'STK', stock.conId)
            if not chains:
                raise Exception("No chains available")

            chain = None
            for c in chains:
                if c.exchange == 'SMART' and c.tradingClass == item.symbol:
                    chain = c
                    break

            if not chain:
                raise Exception("No SMART exchange chain found")

            # Find target expiry (45-75 DTE from target_time)
            target_expiry = None
            for exp in chain.expirations:
                try:
                    exp_date = datetime.strptime(exp, "%Y%m%d")
                    dte = (exp_date - item.target_time).days
                    if 45 <= dte <= 75:
                        target_expiry = exp
                        break
                except ValueError:
                    continue

            if not target_expiry:
                raise Exception("No suitable expiration found")

            # Calculate strikes
            min_strike = int(current_price * 0.92)
            max_strike = int(current_price * 1.08)
            strikes = list(range(min_strike, max_strike + 1, 5))

            # Collect snapshot
            result = await self.collect_snapshot(
                symbol=item.symbol,
                target_time=item.target_time,
                strikes=strikes,
                expiry=target_expiry
            )

            if result["success"] and result["snapshots"]:
                # Save to Delta Lake
                df = pl.DataFrame(result["snapshots"])
                table = OptionSnapshotsTable()
                table.append_snapshot(df)

                logger.success(f"✓ Backfilled {len(result['snapshots'])} contracts for {item.symbol} at {item.target_time}")
                return True
            else:
                error = result.get("error")
                error_msg = error.message if hasattr(error, 'message') else str(error)
                logger.error(f"Failed backfill for {item.symbol}: {error_msg}")
                return False

        except Exception as e:
            logger.error(f"Error processing queue item: {e}")
            return False

    async def run_batch(self, max_items: int = 10):
        """
        Process a batch of queue items.

        Args:
            max_items: Maximum items to process
        """
        logger.info("=" * 70)
        logger.info("BACKFILL WORKER - BATCH MODE")
        logger.info("=" * 70)

        # Initialize IB connection
        self.ib = IB()
        try:
            logger.info(f"Connecting to IB Gateway with clientId={self.client_id}...")
            await self.ib.connectAsync(host="127.0.0.1", port=4002, clientId=self.client_id, timeout=10)
            logger.success(f"✓ Connected to IB Gateway")
        except Exception as e:
            logger.error(f"✗ Failed to connect to IB Gateway: {e}")
            return

        try:
            # Get pending items
            items = self.queue.get_pending(limit=max_items)

            if not items:
                logger.info("No pending items in queue")
                return

            logger.info(f"Found {len(items)} pending items to process")

            processed = 0
            succeeded = 0

            for item in items:
                # Mark as in progress
                self.queue.mark_in_progress(item.symbol, item.target_time)

                try:
                    success = await self.process_queue_item(item)
                    processed += 1

                    if success:
                        succeeded += 1
                        # Mark as completed
                        self.queue.mark_completed(item.symbol, item.target_time)
                    else:
                        # Increment retry count
                        self.queue.increment_retry(item.symbol, item.target_time)

                except Exception as e:
                    logger.error(f"Error processing item: {e}")
                    # Increment retry count on error
                    self.queue.increment_retry(item.symbol, item.target_time)

            logger.info(f"\n{'='*70}")
            logger.info(f"BACKFILL BATCH COMPLETE")
            logger.info(f"Processed: {processed}/{len(items)}")
            logger.info(f"Succeeded: {succeeded}")
            logger.info(f"{'='*70}")

            # Show queue stats
            stats = self.queue.get_stats()
            logger.info(f"Queue status: {stats}")

        finally:
            self.ib.disconnect()

    async def run_continuous(self, interval_seconds: int = 300):
        """
        Run continuously, processing queue items at intervals.

        Args:
            interval_seconds: Seconds between queue checks
        """
        logger.info("=" * 70)
        logger.info("BACKFILL WORKER - CONTINUOUS MODE")
        logger.info(f"Check interval: {interval_seconds}s")
        logger.info("=" * 70)

        self.running = True

        while self.running:
            try:
                await self.run_batch(max_items=5)

                if self.queue.get_stats()['pending'] == 0:
                    logger.info("Queue empty, sleeping...")
                else:
                    logger.info("More items remain, will continue next batch")

                await asyncio.sleep(interval_seconds)

            except Exception as e:
                logger.error(f"Error in continuous mode: {e}")
                await asyncio.sleep(60)  # Wait 1 min before retry

    def stop(self):
        """Stop the continuous worker."""
        logger.info("Stopping backfill worker...")
        self.running = False


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Backfill worker for option snapshots")
    parser.add_argument("--mode", choices=["batch", "continuous"], default="batch",
                        help="Run mode: batch (once) or continuous (daemon)")
    parser.add_argument("--items", type=int, default=10,
                        help="Max items to process in batch mode")
    parser.add_argument("--interval", type=int, default=300,
                        help="Check interval in seconds (continuous mode)")

    args = parser.parse_args()

    worker = BackfillWorker(client_id=9981)

    if args.mode == "batch":
        await worker.run_batch(max_items=args.items)
    else:
        # Continuous mode with signal handling
        def signal_handler(sig, frame):
            worker.stop()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        await worker.run_continuous(interval_seconds=args.interval)


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
