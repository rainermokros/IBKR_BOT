"""
Data Collector - Continuous Option Chain Collection

This module provides a background service that continuously fetches and stores
option contract data for SPY, QQQ, IWM to Delta Lake.

Key features:
- Fetches option chains every 5 minutes (configurable)
- Calculates and stores IV Rank from historical data
- Logs all snapshots to Delta Lake for backtesting and ML training
- Runs as background task in paper trading system
- Graceful shutdown and error handling

Usage:
    from src.v6.scripts.data_collector import DataCollector

    collector = DataCollector(
        symbols=["SPY", "QQQ", "IWM"],
        collection_interval=300  # 5 minutes
    )

    await collector.start()
    # Runs in background...
    await collector.stop()
"""

import asyncio
from datetime import datetime
from typing import List, Optional

from loguru import logger

from src.v6.config.paper_config import PaperTradingConfig
from src.v6.core.market_data_fetcher import OptionDataFetcher
from src.v6.data.option_snapshots import OptionSnapshotsTable
from src.v6.utils.ib_connection import IBConnectionManager


class DataCollector:
    """
    Continuous option data collection service.

    Fetches option chains at regular intervals and stores them to Delta Lake.
    Calculates IV Rank, VIX, and trend indicators for entry signals.

    Attributes:
        ib_conn: IB connection manager
        option_fetcher: Option data fetcher
        option_snapshots_table: Delta Lake table for storage
        symbols: List of symbols to collect
        collection_interval: Seconds between collection cycles
        running: True if collector is running
        _collection_task: Background collection task
    """

    def __init__(
        self,
        ib_conn: IBConnectionManager,
        option_snapshots_table: OptionSnapshotsTable,
        symbols: Optional[List[str]] = None,
        collection_interval: int = 300,  # 5 minutes
    ):
        """
        Initialize data collector.

        Args:
            ib_conn: IB connection manager
            option_snapshots_table: Delta Lake table for storage
            symbols: List of symbols to collect (default: SPY, QQQ, IWM)
            collection_interval: Seconds between collection cycles (default: 300s)
        """
        self.ib_conn = ib_conn
        self.option_snapshots_table = option_snapshots_table
        self.symbols = symbols or ["SPY", "QQQ", "IWM"]
        self.collection_interval = collection_interval
        self.running = False
        self._collection_task: Optional[asyncio.Task] = None

        # Create option data fetcher
        self.option_fetcher = OptionDataFetcher(
            ib_conn=ib_conn,
            option_snapshots_table=option_snapshots_table,
            symbols=symbols,
        )

        logger.info(
            f"✓ DataCollector initialized: "
            f"symbols={self.symbols}, "
            f"interval={self.collection_interval}s"
        )

    async def start(self):
        """
        Start data collection service.

        Starts background task that continuously collects option data.
        """
        if self.running:
            logger.warning("DataCollector already running")
            return

        self.running = True
        self._collection_task = asyncio.create_task(self._collection_loop())

        logger.info("✓ DataCollector started")

    async def stop(self):
        """
        Stop data collection service.

        Stops background task and performs final collection cycle.
        """
        if not self.running:
            logger.warning("DataCollector not running")
            return

        logger.info("Stopping DataCollector...")
        self.running = False

        # Cancel collection task
        if self._collection_task and not self._collection_task.done():
            self._collection_task.cancel()
            try:
                await self._collection_task
            except asyncio.CancelledError:
                pass

        logger.info("✓ DataCollector stopped")

    async def _collection_loop(self):
        """
        Continuous collection loop.

        Fetches option chains for all symbols at regular intervals.
        Handles errors gracefully and continues running.
        """
        logger.info(f"Starting collection loop (interval: {self.collection_interval}s)")

        while self.running:
            try:
                # Run collection cycle
                await self._collect_all_symbols()

                # Wait for next interval
                await asyncio.sleep(self.collection_interval)

            except asyncio.CancelledError:
                logger.info("Collection loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in collection loop: {e}", exc_info=True)
                # Continue running despite errors
                await asyncio.sleep(60)  # Wait 1 minute before retrying

    async def _collect_all_symbols(self):
        """
        Collect option chains for all symbols.

        Fetches option chain, IV Rank, VIX, and trend for each symbol.
        Stores snapshots to Delta Lake.
        """
        logger.info(f"Starting collection cycle for {len(self.symbols)} symbols...")

        start_time = datetime.now()
        total_contracts = 0

        for symbol in self.symbols:
            try:
                # Fetch option chain and market data
                market_data = await self.option_fetcher.get_market_data(symbol)

                # Write snapshots to Delta Lake
                contracts = market_data.get("option_chain", [])
                if contracts:
                    written = self.option_snapshots_table.write_snapshots(contracts)
                    total_contracts += written

                    logger.info(
                        f"✓ {symbol}: {written} contracts written, "
                        f"IV Rank={market_data['iv_rank']:.1f}, "
                        f"VIX={market_data['vix']:.2f}, "
                        f"Trend={market_data['underlying_trend']}"
                    )
                else:
                    logger.warning(f"No contracts fetched for {symbol}")

            except Exception as e:
                logger.error(f"Error collecting data for {symbol}: {e}")
                continue

        elapsed = (datetime.now() - start_time).total_seconds()

        logger.info(
            f"✓ Collection cycle complete: "
            f"{total_contracts} contracts written in {elapsed:.1f}s"
        )

    async def collect_once(self) -> dict:
        """
        Run a single collection cycle.

        Useful for testing or manual collection.

        Returns:
            dict: Collection results with stats for each symbol
        """
        logger.info("Running single collection cycle...")

        results = {}

        for symbol in self.symbols:
            try:
                # Fetch option chain and market data
                market_data = await self.option_fetcher.get_market_data(symbol)

                # Write snapshots to Delta Lake
                contracts = market_data.get("option_chain", [])
                written = 0
                if contracts:
                    written = self.option_snapshots_table.write_snapshots(contracts)

                results[symbol] = {
                    "contracts_written": written,
                    "iv_rank": market_data["iv_rank"],
                    "vix": market_data["vix"],
                    "trend": market_data["underlying_trend"],
                    "timestamp": market_data["timestamp"],
                }

            except Exception as e:
                logger.error(f"Error collecting data for {symbol}: {e}")
                results[symbol] = {
                    "error": str(e),
                }

        return results

    async def get_latest_market_data(self, symbol: str) -> dict:
        """
        Get latest market data for symbol.

        Fetches current market data without storing to Delta Lake.
        Useful for entry signal evaluation.

        Args:
            symbol: Underlying symbol (SPY, QQQ, IWM)

        Returns:
            dict: Market data including iv_rank, vix, trend, underlying_price
        """
        try:
            # Fetch market data (without option chain to save time)
            iv_rank = await self.option_fetcher.calculate_iv_rank(symbol)
            vix = await self.option_fetcher.get_vix()
            trend = await self.option_fetcher.get_underlying_trend(symbol)

            # Fetch underlying price
            underlying_price = await self._get_underlying_price(symbol)

            return {
                "symbol": symbol,
                "iv_rank": iv_rank,
                "vix": vix,
                "underlying_trend": trend,
                "underlying_price": underlying_price,
                "timestamp": datetime.now(),
            }

        except Exception as e:
            logger.error(f"Error getting market data for {symbol}: {e}")
            return {
                "symbol": symbol,
                "iv_rank": 50.0,
                "vix": 18.0,
                "underlying_trend": "neutral",
                "underlying_price": 0.0,
                "timestamp": datetime.now(),
            }

    async def _get_underlying_price(self, symbol: str) -> float:
        """Get current underlying price from IB."""
        try:
            from ib_async import Contract

            await self.ib_conn.ensure_connected()

            stock_contract = Contract(
                secType="STK",
                symbol=symbol,
                exchange="SMART",
                currency="USD"
            )

            # Qualify contract
            qualified_contracts = await self.ib_conn.ib.qualifyContractsAsync(stock_contract)
            if not qualified_contracts:
                logger.warning(f"Could not qualify contract for {symbol}")
                return 0.0

            stock_contract = qualified_contracts[0]

            # Get current price using reqMktData (returns ticker object)
            ticker = self.ib_conn.ib.reqMktData(stock_contract)

            # Wait for ticker to update with price
            import asyncio
            for _ in range(10):  # Wait up to 1 second
                await asyncio.sleep(0.1)
                if ticker.last and ticker.last > 0:
                    price = float(ticker.last)
                    logger.debug(f"{symbol} underlying price: ${price:.2f}")
                    # Cancel the market data subscription
                    self.ib_conn.ib.cancelMktData(ticker.contract)
                    return price

            logger.warning(f"Timeout waiting for price for {symbol}")
            self.ib_conn.ib.cancelMktData(ticker.contract)
            return 0.0

        except Exception as e:
            logger.error(f"Error fetching underlying price for {symbol}: {e}")
            return 0.0

    def get_collection_stats(self) -> dict:
        """
        Get collection statistics.

        Returns:
            dict: Stats including running status, interval, table stats
        """
        table_stats = self.option_snapshots_table.get_snapshot_stats()

        return {
            "running": self.running,
            "symbols": self.symbols,
            "collection_interval": self.collection_interval,
            "table_stats": table_stats,
        }

    async def health_check(self) -> dict:
        """
        Perform health check on data collector.

        Returns:
            dict: Health status including IB connection and collection status
        """
        collector_health = {
            "running": self.running,
            "healthy": True,
            "errors": [],
        }

        # Check IB connection
        try:
            fetcher_health = await self.option_fetcher.connection_health()
            collector_health["ib_connected"] = fetcher_health["ib_connected"]
            collector_health["circuit_breaker_state"] = fetcher_health["circuit_breaker_state"]

            if not fetcher_health["healthy"]:
                collector_health["healthy"] = False
                collector_health["errors"].append("IB connection unhealthy")

        except Exception as e:
            collector_health["healthy"] = False
            collector_health["errors"].append(f"IB connection error: {e}")

        # Check Delta Lake table
        try:
            table_stats = self.option_snapshots_table.get_snapshot_stats()
            collector_health["table_rows"] = table_stats["total_rows"]
            collector_health["symbols"] = table_stats["symbols"]

            if table_stats["total_rows"] == 0 and self.running:
                collector_health["errors"].append("No data collected yet")

        except Exception as e:
            collector_health["healthy"] = False
            collector_health["errors"].append(f"Table error: {e}")

        return collector_health


async def main():
    """
    Main entry point for running data collector standalone.

    Usage:
        python -m src.v6.scripts.data_collector
    """
    from src.v6.config.paper_config import PaperTradingConfig

    # Load config
    config = PaperTradingConfig.load_from_file("config/paper_trading.yaml")

    # Create IB connection
    ib_conn = IBConnectionManager(
        host=config.ib_host,
        port=config.ib_port,
        client_id=config.ib_client_id,
    )

    # Create option snapshots table
    option_snapshots_table = OptionSnapshotsTable(
        table_path=f"{config.data_dir}/option_snapshots",
    )

    # Create data collector
    collector = DataCollector(
        ib_conn=ib_conn,
        option_snapshots_table=option_snapshots_table,
        symbols=config.allowed_symbols,
        collection_interval=300,  # 5 minutes
    )

    # Connect to IB
    await ib_conn.connect()

    # Start collector
    await collector.start()

    logger.info("Data collector running. Press Ctrl+C to stop.")

    try:
        # Run forever
        while collector.running:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, stopping...")
    finally:
        await collector.stop()
        await ib_conn.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
