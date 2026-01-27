"""
Futures Fetcher Module

Provides real-time futures data collection for ES, NQ, RTY futures using IB API.
Calculates change metrics (1h, 4h, overnight, daily) from historical price data.
Handles futures contract rolling and subscription lifecycle management.

Purpose: Stream futures data as leading indicators for entry signal prediction.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from ib_async import IB, Contract
from loguru import logger

from src.v6.config.futures_config import FuturesConfig, FuturesContract
from src.v6.utils.ib_connection import IBConnectionManager, CircuitBreaker


@dataclass
class FuturesSnapshot:
    """
    Real-time futures data snapshot.

    Attributes:
        symbol: Futures symbol (ES, NQ, RTY)
        timestamp: Snapshot timestamp
        bid: Best bid price
        ask: Best ask price
        last: Last trade price
        volume: Trading volume
        open_interest: Open interest
        implied_vol: Implied volatility (if available)
        change_1h: Price change over 1 hour
        change_4h: Price change over 4 hours
        change_overnight: Price change overnight (8 hours)
        change_daily: Price change over 24 hours
    """
    symbol: str
    timestamp: datetime
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: Optional[int] = None
    implied_vol: Optional[float] = None
    change_1h: Optional[float] = None
    change_4h: Optional[float] = None
    change_overnight: Optional[float] = None
    change_daily: Optional[float] = None


class FuturesFetcher:
    """
    Real-time futures data fetcher with IB subscription.

    Subscribes to futures market data, calculates change metrics,
    handles contract rolling, and manages connection lifecycle.

    Attributes:
        config: Futures configuration
        ib_conn: IB connection manager
        subscriptions: Active market data subscriptions by symbol
        price_history: Historical price data for change calculations
        circuit_breaker: Circuit breaker for error handling
    """

    def __init__(
        self,
        config: Optional[FuturesConfig] = None,
        ib_host: str = "127.0.0.1",
        ib_port: int = 7497,
        ib_client_id: int = 1
    ):
        """
        Initialize futures fetcher.

        Args:
            config: Futures configuration (uses default if None)
            ib_host: IB gateway host
            ib_port: IB gateway port
            ib_client_id: IB client ID
        """
        self.config = config or FuturesConfig()
        self.ib_conn = IBConnectionManager(
            host=ib_host,
            port=ib_port,
            client_id=ib_client_id
        )
        self.subscriptions: Dict[str, Contract] = {}
        self.price_history: Dict[str, List[tuple[datetime, float]]] = {}
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, timeout=30)

        # Store latest tick data
        self._latest_ticks: Dict[str, dict] = {}

        logger.info(f"✓ FuturesFetcher initialized for symbols: {self.config.enabled_symbols}")

    async def connect(self) -> None:
        """Connect to IB gateway."""
        if self.circuit_breaker.state != CircuitBreaker.CircuitState.CLOSED:
            raise ConnectionError("Circuit breaker is OPEN - cannot connect")

        try:
            await self.ib_conn.connect()
            await self.ib_conn.start_heartbeat()
            logger.info("✓ Connected to IB for futures data")
        except Exception as e:
            self.circuit_breaker.record_failure()
            logger.error(f"Failed to connect: {e}")
            raise

    async def disconnect(self) -> None:
        """Disconnect from IB gateway."""
        await self.unsubscribe_all()
        await self.ib_conn.stop_heartbeat()
        await self.ib_conn.disconnect()
        logger.info("✓ Disconnected from IB")

    async def subscribe_to_futures(self, symbols: Optional[List[str]] = None) -> None:
        """
        Subscribe to real-time futures data.

        Args:
            symbols: List of symbols to subscribe (uses config defaults if None)
        """
        if symbols is None:
            symbols = self.config.enabled_symbols

        await self.ib_conn.ensure_connected()

        for symbol in symbols:
            try:
                if not self.config.is_enabled(symbol):
                    logger.warning(f"Symbol {symbol} not enabled, skipping")
                    continue

                # Get contract specification
                contract_spec = self.config.get_contract(symbol)

                # Create IB contract
                contract = Contract(
                    secType=contract_spec.secType,
                    symbol=contract_spec.symbol,
                    exchange=contract_spec.exchange,
                    currency=contract_spec.currency
                )

                # For continuous futures, leave expiry empty
                if self.config.continuous_futures:
                    contract.lastTradeDateOrContractMonth = ""
                else:
                    contract.lastTradeDateOrContractMonth = contract_spec.lastTradeDateOrContractMonth

                # Qualify contract
                qualified_contracts = await self.ib_conn.ib.qualifyContractsAsync(contract)
                if not qualified_contracts:
                    logger.error(f"Failed to qualify contract for {symbol}")
                    continue

                contract = qualified_contracts[0]
                logger.info(f"✓ Qualified {symbol} contract: conId={contract.conId}")

                # Request market data
                self.ib_conn.ib.reqMktData(contract, "", False, False)
                self.subscriptions[symbol] = contract

                # Initialize price history
                self.price_history[symbol] = []

                # Set up tick handler
                self.ib_conn.ib.barUpdateEvent += self._on_bar_update

                logger.info(f"✓ Subscribed to {symbol} futures data")

            except Exception as e:
                logger.error(f"Failed to subscribe to {symbol}: {e}")
                self.circuit_breaker.record_failure()

        self.circuit_breaker.record_success()

    def _on_bar_update(self, bars, has_new_bar: bool) -> None:
        """
        Handle real-time bar updates from IB.

        Args:
            bars: Bar data from IB
            has_new_bar: Whether this is a new bar
        """
        # This is a placeholder - real-time updates will be handled
        # through ticker updates in production
        pass

    async def get_futures_snapshot(self, symbol: str) -> Optional[FuturesSnapshot]:
        """
        Get current futures snapshot for symbol.

        Fetches latest market data and calculates change metrics.

        Args:
            symbol: Futures symbol (ES, NQ, RTY)

        Returns:
            FuturesSnapshot: Current snapshot or None if unavailable
        """
        if not self.circuit_breaker.can_attempt():
            logger.warning(f"Circuit breaker OPEN - skipping {symbol} snapshot")
            return None

        try:
            if symbol not in self.subscriptions:
                logger.warning(f"Not subscribed to {symbol}, call subscribe_to_futures() first")
                return None

            await self.ib_conn.ensure_connected()
            contract = self.subscriptions[symbol]

            # Get current ticker data
            ticker = self.ib_conn.ib.ticker(contract)

            if ticker is None:
                logger.warning(f"No ticker data for {symbol}")
                return None

            # Extract prices
            bid = ticker.bid if ticker.bid else 0
            ask = ticker.ask if ticker.ask else 0
            last = ticker.last if ticker.last else 0
            volume = ticker.volume if ticker.volume else 0

            if not last:
                logger.warning(f"No price data for {symbol}")
                return None

            # Calculate change metrics
            changes = await self.calculate_changes(symbol, last)

            # Create snapshot
            snapshot = FuturesSnapshot(
                symbol=symbol,
                timestamp=datetime.now(),
                bid=bid,
                ask=ask,
                last=last,
                volume=volume,
                open_interest=ticker.openInterest if ticker.openInterest else None,
                implied_vol=ticker.impliedVolatility if hasattr(ticker, 'impliedVolatility') else None,
                change_1h=changes.get("change_1h"),
                change_4h=changes.get("change_4h"),
                change_overnight=changes.get("change_overnight"),
                change_daily=changes.get("change_daily")
            )

            return snapshot

        except Exception as e:
            logger.error(f"Error fetching snapshot for {symbol}: {e}")
            self.circuit_breaker.record_failure()
            return None

    async def calculate_changes(self, symbol: str, current_price: float) -> Dict[str, float]:
        """
        Calculate price changes over different time windows.

        Fetches historical data and calculates percentage changes.

        Args:
            symbol: Futures symbol
            current_price: Current price

        Returns:
            dict: Change metrics by time window
        """
        changes = {}

        try:
            await self.ib_conn.ensure_connected()
            contract = self.subscriptions[symbol]

            # Get historical data for each time window
            windows = self.config.data_collection.change_windows

            for change_name, duration_minutes in windows.items():
                try:
                    # Calculate duration string for IB
                    duration_str = f"{duration_minutes} S"

                    # Fetch historical bars
                    bars = await self.ib_conn.ib.reqHistoricalDataAsync(
                        contract,
                        endDateTime=datetime.now(),
                        durationStr=duration_str,
                        barSizeSetting="1 min",
                        whatToShow="TRADES",
                        useRTH=False
                    )

                    if bars and len(bars) > 0:
                        # Get oldest price in window
                        old_price = bars[0].close
                        if old_price and old_price > 0:
                            # Calculate percentage change
                            change_pct = ((current_price - old_price) / old_price) * 100
                            changes[change_name] = round(change_pct, 2)
                        else:
                            changes[change_name] = None
                    else:
                        changes[change_name] = None

                except Exception as e:
                    logger.warning(f"Failed to calculate {change_name} for {symbol}: {e}")
                    changes[change_name] = None

            return changes

        except Exception as e:
            logger.error(f"Error calculating changes for {symbol}: {e}")
            return {}

    async def unsubscribe_all(self) -> None:
        """Unsubscribe from all futures data."""
        for symbol, contract in list(self.subscriptions.items()):
            try:
                self.ib_conn.ib.cancelMktData(contract)
                logger.info(f"✓ Unsubscribed from {symbol}")
            except Exception as e:
                logger.error(f"Error unsubscribing from {symbol}: {e}")

        self.subscriptions.clear()
        logger.info("✓ Unsubscribed from all futures")

    async def get_all_snapshots(self) -> Dict[str, FuturesSnapshot]:
        """
        Get snapshots for all subscribed symbols.

        Returns:
            dict: Symbol to FuturesSnapshot mapping
        """
        snapshots = {}

        for symbol in self.subscriptions.keys():
            try:
                snapshot = await self.get_futures_snapshot(symbol)
                if snapshot:
                    snapshots[symbol] = snapshot
            except Exception as e:
                logger.error(f"Error fetching snapshot for {symbol}: {e}")

        return snapshots

    async def connection_health(self) -> dict:
        """
        Get connection health status.

        Returns:
            dict: Health status including connection state and circuit breaker
        """
        ib_health = await self.ib_conn.connection_health()

        return {
            "ib_connected": ib_health["connected"],
            "circuit_breaker_state": self.circuit_breaker.state.value,
            "active_subscriptions": list(self.subscriptions.keys()),
            "healthy": ib_health["healthy"] and self.circuit_breaker.can_attempt()
        }
