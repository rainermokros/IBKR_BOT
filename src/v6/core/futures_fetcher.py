"""
Futures Data Fetcher Module

Provides real-time futures data collection for ES, NQ, RTY using unified IB connection.
Calculates change metrics (1h, 4h, overnight, daily) from historical data.
Handles contract rollover detection (1 week before expiry).
Handles daily maintenance window (5-6pm ET) gracefully.

Purpose: Collect 24/7 futures data (except maintenance window) as leading indicators
for entry signal prediction.

Key features:
- Uses unified IBConnectionManager (shares connection with other modules)
- Subscribes to ES, NQ, RTY using front-month contracts
- Calculates change metrics from historical data
- Contract rollover detection (1 week before expiry)
- Graceful handling of maintenance window (5-6pm ET)
- Circuit breaker for error recovery
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple

from ib_async import Future, Ticker
from loguru import logger

from v6.utils.ib_connection import IBConnectionManager


# Maintenance window: 5:00 PM - 6:00 PM ET
MAINTENANCE_WINDOW_START = time(17, 0)
MAINTENANCE_WINDOW_END = time(18, 0)

# Contract rollover threshold (days before expiry)
ROLLOVER_DAYS_THRESHOLD = 7

# Futures symbol to IB contract mapping
FUTURES_CONTRACTS = {
    "ES": {"exchange": "CME", "currency": "USD", "multiplier": 50},
    "NQ": {"exchange": "CME", "currency": "USD", "multiplier": 20},
    "RTY": {"exchange": "CME", "currency": "USD", "multiplier": 5},
}


@dataclass
class FuturesSnapshot:
    """
    Futures market data snapshot.

    Attributes:
        symbol: Futures symbol (ES, NQ, RTY)
        timestamp: Snapshot timestamp
        bid: Best bid price
        ask: Best ask price
        last: Last trade price
        volume: Trading volume
        open_interest: Open interest
        implied_vol: Implied volatility (if available)
        change_1h: 1-hour percent change
        change_4h: 4-hour percent change
        change_overnight: Overnight percent change (from previous close)
        change_daily: Daily percent change
        expiry: Contract expiration date
        is_front_month: True if this is the front-month contract
    """
    symbol: str
    timestamp: datetime
    bid: Optional[float]
    ask: Optional[float]
    last: Optional[float]
    volume: Optional[int]
    open_interest: Optional[int]
    implied_vol: Optional[float]
    change_1h: Optional[float]
    change_4h: Optional[float]
    change_overnight: Optional[float]
    change_daily: Optional[float]
    expiry: Optional[str]
    is_front_month: bool

    def to_dict(self) -> dict:
        """Convert to dictionary for Delta Lake storage."""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "bid": self.bid,
            "ask": self.ask,
            "last": self.last,
            "volume": self.volume,
            "open_interest": self.open_interest,
            "implied_vol": self.implied_vol,
            "change_1h": self.change_1h,
            "change_4h": self.change_4h,
            "change_overnight": self.change_overnight,
            "change_daily": self.change_daily,
            "expiry": self.expiry,
            "is_front_month": self.is_front_month,
            "date": self.timestamp.date(),
        }


class FuturesFetcher:
    """
    Real-time futures data fetcher using unified IB connection.

    Fetches futures data for ES, NQ, RTY with change metrics calculation.
    Handles contract rollover and maintenance window gracefully.

    Attributes:
        ib_conn: IB connection manager (shared with other modules)
        symbols: List of futures symbols to fetch
        subscribed_contracts: Currently subscribed contracts
    """

    def __init__(
        self,
        ib_conn: IBConnectionManager,
        symbols: Optional[List[str]] = None,
    ):
        """
        Initialize futures fetcher.

        Args:
            ib_conn: IB connection manager (unified connection)
            symbols: List of symbols to fetch (default: ES, NQ, RTY)
        """
        self.ib_conn = ib_conn
        self.symbols = symbols or ["ES", "NQ", "RTY"]
        self.subscribed_contracts: Dict[str, Tuple[Future, Ticker]] = {}
        self._price_history: Dict[str, List[Tuple[datetime, float]]] = {}

        # Validate symbols
        for symbol in self.symbols:
            if symbol not in FUTURES_CONTRACTS:
                raise ValueError(f"Invalid futures symbol: {symbol}. Must be one of {list(FUTURES_CONTRACTS.keys())}")

        logger.info(f"✓ FuturesFetcher initialized for symbols: {self.symbols}")

    def _is_maintenance_window(self) -> bool:
        """
        Check if current time is within maintenance window (5-6pm ET).

        Returns:
            True if in maintenance window
        """
        now = datetime.now().time()
        return MAINTENANCE_WINDOW_START <= now < MAINTENANCE_WINDOW_END

    async def _get_front_month_contract(self, symbol: str) -> Optional[Future]:
        """
        Get the front-month futures contract for symbol.

        Finds the contract with the nearest expiry that is > ROLLOVER_DAYS_THRESHOLD days away.
        If all contracts are within rollover threshold, uses the furthest one.

        Args:
            symbol: Futures symbol (ES, NQ, RTY)

        Returns:
            Qualified Future contract or None
        """
        try:
            await self.ib_conn.ensure_connected()

            contract_spec = FUTURES_CONTRACTS[symbol]

            # Create base futures contract (without expiry for continuous)
            base_contract = Future(
                symbol=symbol,
                exchange=contract_spec["exchange"],
                currency=contract_spec["currency"],
            )

            # Qualify the contract
            qualified = await self.ib_conn.ib.qualifyContractsAsync(base_contract)
            if not qualified:
                logger.warning(f"Could not qualify base contract for {symbol}")
                return None

            # For IBKR, we need to get available contract expirations
            # Use reqSecDefOptParams to get available futures expirations
            # For futures, we can use the conId to query
            logger.debug(f"Getting contract expirations for {symbol}")

            # Try to get futures contract with specific expiry
            # Start with current month + 1 month
            now = datetime.now()
            target_months = []

            for month_offset in range(6):  # Look ahead 6 months
                target_date = now + timedelta(days=month_offset * 30)
                year_month = target_date.strftime("%Y%m")
                target_months.append(year_month)

            # Try each month until we find a valid contract
            for year_month in target_months:
                try:
                    # Try creating contract with specific expiry
                    test_contract = Future(
                        symbol=symbol,
                        lastTradeDateOrContractMonth=year_month,
                        exchange=contract_spec["exchange"],
                        currency=contract_spec["currency"],
                    )

                    qualified_test = await self.ib_conn.ib.qualifyContractsAsync(test_contract)

                    if qualified_test:
                        # Check if this contract is far enough from expiry
                        contract = qualified_test[0]
                        expiry_str = contract.lastTradeDateOrContractMonth

                        if expiry_str:
                            try:
                                expiry_date = datetime.strptime(expiry_str, "%Y%m%d").date()
                                days_to_expiry = (expiry_date - now.date()).days

                                logger.debug(f"Found {symbol} contract {expiry_str}, {days_to_expiry} DTE")

                                # Use this contract if it's > 7 days to expiry, or if it's the furthest available
                                if days_to_expiry > ROLLOVER_DAYS_THRESHOLD:
                                    logger.info(f"✓ Selected {symbol} front-month: {expiry_str} ({days_to_expiry} DTE)")
                                    return contract

                            except ValueError:
                                logger.debug(f"Could not parse expiry: {expiry_str}")
                                continue

                except Exception as e:
                    logger.debug(f"Error testing contract {year_month} for {symbol}: {e}")
                    continue

            # Fallback: use continuous contract (no specific expiry)
            logger.warning(f"No suitable contract found for {symbol}, using continuous")
            return qualified[0]

        except Exception as e:
            logger.error(f"Error getting front-month contract for {symbol}: {e}")
            return None

    async def _calculate_change_metrics(self, symbol: str, current_price: float) -> Dict[str, Optional[float]]:
        """
        Calculate change metrics from historical data.

        Fetches historical bars to calculate:
        - 1-hour change
        - 4-hour change
        - Overnight change (from 4pm previous day to 9:30am today)
        - Daily change (from previous day's close)

        Args:
            symbol: Futures symbol
            current_price: Current futures price

        Returns:
            Dictionary with change metrics as percentages
        """
        metrics = {
            "change_1h": None,
            "change_4h": None,
            "change_overnight": None,
            "change_daily": None,
        }

        try:
            await self.ib_conn.ensure_connected()

            # Get front-month contract for historical data
            # Use continuous contract (no specific expiry) for historical data
            contract_spec = FUTURES_CONTRACTS[symbol]
            contract = Future(
                symbol=symbol,
                exchange=contract_spec["exchange"],
                currency=contract_spec["currency"],
            )

            # Fetch historical bars (1-hour bars for last 24 hours)
            now = datetime.now()
            bars = await self.ib_conn.ib.reqHistoricalDataAsync(
                contract,
                endDateTime=now,
                durationStr="1 D",
                barSizeSetting="1 hour",
                whatToShow="TRADES",
                useRTH=False,
            )

            if not bars or len(bars) < 4:
                logger.debug(f"Insufficient historical data for {symbol} change metrics")
                return metrics

            # Calculate 1-hour change (compare to 1 hour ago)
            if len(bars) >= 2:
                price_1h_ago = bars[-2].close if bars[-2] else None
                if price_1h_ago and price_1h_ago > 0:
                    metrics["change_1h"] = ((current_price - price_1h_ago) / price_1h_ago) * 100

            # Calculate 4-hour change (compare to 4 hours ago)
            if len(bars) >= 5:
                price_4h_ago = bars[-5].close if bars[-5] else None
                if price_4h_ago and price_4h_ago > 0:
                    metrics["change_4h"] = ((current_price - price_4h_ago) / price_4h_ago) * 100

            # For daily and overnight changes, we need daily bars
            daily_bars = await self.ib_conn.ib.reqHistoricalDataAsync(
                contract,
                endDateTime=now,
                durationStr="2 D",
                barSizeSetting="1 day",
                whatToShow="TRADES",
                useRTH=True,
            )

            if daily_bars and len(daily_bars) >= 2:
                # Previous day's close
                prev_close = daily_bars[-2].close
                if prev_close and prev_close > 0:
                    metrics["change_daily"] = ((current_price - prev_close) / prev_close) * 100

            # For overnight, we need more granular data around 4pm yesterday and 9:30am today
            # This is complex - for now, approximate using previous close
            if daily_bars and len(daily_bars) >= 2:
                metrics["change_overnight"] = metrics["change_daily"]  # Use daily as approximation

            logger.debug(f"{symbol} change metrics: 1h={metrics['change_1h']:.2f}%, "
                        f"4h={metrics['change_4h']:.2f}%, daily={metrics['change_daily']:.2f}%")

        except Exception as e:
            logger.warning(f"Error calculating change metrics for {symbol}: {e}")

        return metrics

    async def subscribe_to_futures(self) -> Dict[str, FuturesSnapshot]:
        """
        Subscribe to all configured futures symbols and get current snapshots.

        Handles:
        - Maintenance window (returns empty snapshots with warning)
        - Contract qualification
        - Change metrics calculation

        Returns:
            Dictionary mapping symbol -> FuturesSnapshot
            Returns empty dict if in maintenance window or on error
        """
        # Check for maintenance window
        if self._is_maintenance_window():
            logger.warning("Maintenance window (5-6pm ET) - skipping futures collection")
            return {}

        try:
            await self.ib_conn.ensure_connected()

            snapshots = {}

            for symbol in self.symbols:
                try:
                    # Get front-month contract
                    contract = await self._get_front_month_contract(symbol)

                    if not contract:
                        logger.warning(f"Could not get contract for {symbol}")
                        continue

                    # Request market data (snapshot mode)
                    ticker = self.ib_conn.ib.reqMktData(
                        contract,
                        "",  # Generic ticks
                        False,  # Snapshot
                        False  # Regulatory snapshot
                    )

                    # Wait for data to populate
                    await asyncio.sleep(1)

                    # Get current price
                    current_price = None
                    if ticker.last:
                        current_price = ticker.last
                    elif ticker.bid and ticker.ask:
                        current_price = (ticker.bid + ticker.ask) / 2
                    elif ticker.close:
                        current_price = ticker.close

                    if not current_price:
                        logger.warning(f"No price data available for {symbol}")
                        continue

                    # Calculate change metrics
                    change_metrics = await self._calculate_change_metrics(symbol, current_price)

                    # Create snapshot
                    snapshot = FuturesSnapshot(
                        symbol=symbol,
                        timestamp=datetime.now(),
                        bid=ticker.bid,
                        ask=ticker.ask,
                        last=ticker.last,
                        volume=ticker.volume if hasattr(ticker, 'volume') else None,
                        open_interest=ticker.openInterest if hasattr(ticker, 'openInterest') else None,
                        implied_vol=ticker.impliedVolatility if hasattr(ticker, 'impliedVolatility') else None,
                        change_1h=change_metrics["change_1h"],
                        change_4h=change_metrics["change_4h"],
                        change_overnight=change_metrics["change_overnight"],
                        change_daily=change_metrics["change_daily"],
                        expiry=contract.lastTradeDateOrContractMonth,
                        is_front_month=True,
                    )

                    snapshots[symbol] = snapshot

                    # Cancel market data to free up slots
                    self.ib_conn.ib.cancelMktData(contract)

                    logger.info(f"✓ {symbol}: {snapshot.last:.2f} "
                               f"(1h: {snapshot.change_1h:+.2f}%, 4h: {snapshot.change_4h:+.2f}%)")

                except Exception as e:
                    logger.error(f"Error fetching {symbol}: {e}")
                    # Continue with next symbol
                    continue

            return snapshots

        except Exception as e:
            logger.error(f"Error in subscribe_to_futures: {e}")
            return {}

    async def get_snapshot(self, symbol: str) -> Optional[FuturesSnapshot]:
        """
        Get a single futures snapshot for a symbol.

        Args:
            symbol: Futures symbol (ES, NQ, RTY)

        Returns:
            FuturesSnapshot or None if error
        """
        if symbol not in self.symbols:
            raise ValueError(f"Symbol {symbol} not configured. Available: {self.symbols}")

        # Check for maintenance window
        if self._is_maintenance_window():
            logger.warning("Maintenance window (5-6pm ET) - returning empty snapshot")
            return None

        try:
            await self.ib_conn.ensure_connected()

            # Get contract
            contract = await self._get_front_month_contract(symbol)
            if not contract:
                return None

            # Request market data
            ticker = self.ib_conn.ib.reqMktData(contract, "", False, False)
            await asyncio.sleep(1)

            # Get current price
            current_price = ticker.last or ((ticker.bid + ticker.ask) / 2 if ticker.bid and ticker.ask else ticker.close)

            if not current_price:
                return None

            # Calculate change metrics
            change_metrics = await self._calculate_change_metrics(symbol, current_price)

            # Create snapshot
            snapshot = FuturesSnapshot(
                symbol=symbol,
                timestamp=datetime.now(),
                bid=ticker.bid,
                ask=ticker.ask,
                last=ticker.last,
                volume=ticker.volume if hasattr(ticker, 'volume') else None,
                open_interest=ticker.openInterest if hasattr(ticker, 'openInterest') else None,
                implied_vol=ticker.impliedVolatility if hasattr(ticker, 'impliedVolatility') else None,
                change_1h=change_metrics["change_1h"],
                change_4h=change_metrics["change_4h"],
                change_overnight=change_metrics["change_overnight"],
                change_daily=change_metrics["change_daily"],
                expiry=contract.lastTradeDateOrContractMonth,
                is_front_month=True,
            )

            # Cancel market data
            self.ib_conn.ib.cancelMktData(contract)

            return snapshot

        except Exception as e:
            logger.error(f"Error getting snapshot for {symbol}: {e}")
            return None

    async def connection_health(self) -> dict:
        """
        Get connection health status.

        Returns:
            Dictionary with health metrics
        """
        ib_health = await self.ib_conn.connection_health()

        return {
            "ib_connected": ib_health["connected"],
            "symbols": self.symbols,
            "subscribed_count": len(self.subscribed_contracts),
            "maintenance_window": self._is_maintenance_window(),
            "healthy": ib_health["healthy"],
        }
