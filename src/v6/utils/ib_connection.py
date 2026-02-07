import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from ib_async import IB
from loguru import logger

if TYPE_CHECKING:
    from v6.config.trading_config import IBConnectionConfig


class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, stop requests
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class CircuitBreaker:
    """Circuit breaker to prevent retry storms."""
    failure_threshold: int = 5
    timeout: int = 60  # seconds
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0

    def record_failure(self) -> None:
        """Record a failure and potentially open circuit."""
        self.failure_count += 1
        self.last_failure_time = datetime.now().timestamp()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit breaker OPEN after {self.failure_count} failures")

    def record_success(self) -> None:
        """Record success and close circuit if in half-open."""
        self.failure_count = 0
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            logger.info("Circuit breaker CLOSED after successful recovery")

    def can_attempt(self) -> bool:
        """Check if request should be allowed."""
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            # Check if timeout has passed
            if datetime.now().timestamp() - self.last_failure_time > self.timeout:
                self.state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker HALF_OPEN (testing recovery)")
                return True
            return False
        return True  # HALF_OPEN


class IBConnectionManager:
    """Manages IB connection with retry logic, circuit breaker, and heartbeat."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 1,
        max_retries: int = 3,
        retry_delay: float = 2.0,
        connect_timeout: int = 10,
    ):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.connect_timeout = connect_timeout
        self.ib = IB()
        self.circuit_breaker = CircuitBreaker()
        self._is_connected = False
        self.heartbeat_interval = 30  # seconds
        self._heartbeat_task: Optional[asyncio.Task] = None
        self.last_heartbeat = datetime.now()

    @classmethod
    def from_config(cls, ib_connection_config: Optional["IBConnectionConfig"] = None, config_path: Optional[str] = None) -> "IBConnectionManager":
        """
        Create IBConnectionManager from trading config file.

        Args:
            ib_connection_config: IBConnectionConfig object (optional)
            config_path: Path to trading config file (optional)

        Returns:
            IBConnectionManager instance
        """
        if ib_connection_config is None:
            from v6.config.trading_config import load_trading_config
            trading_config = load_trading_config(config_path)
            ib_connection_config = trading_config.ib_connection

        return cls(
            host=ib_connection_config.host,
            port=ib_connection_config.port,
            client_id=ib_connection_config.client_id,
            max_retries=ib_connection_config.max_retries,
            retry_delay=ib_connection_config.retry_delay,
            connect_timeout=ib_connection_config.connect_timeout,
        )

    async def connect(self) -> None:
        """Connect with exponential backoff retry (Pitfall 2 from research)."""
        if not self.circuit_breaker.can_attempt():
            raise ConnectionError("Circuit breaker is OPEN - blocking IB connection attempt")

        for attempt in range(self.max_retries):
            try:
                await self.ib.connectAsync(
                    host=self.host,
                    port=self.port,
                    clientId=self.client_id,
                    timeout=self.connect_timeout
                )
                self._is_connected = True
                self.circuit_breaker.record_success()
                logger.info(f"Connected to IB on attempt {attempt + 1}")
                return
            except TimeoutError:
                self.circuit_breaker.record_failure()
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay ** attempt  # Exponential backoff: 2s, 4s, 8s
                    logger.warning(f"Connection timeout, retrying in {wait_time}s (attempt {attempt + 1}/{self.max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Failed to connect after {self.max_retries} attempts")
                    raise

    async def disconnect(self) -> None:
        """Clean disconnect."""
        try:
            await self.ib.disconnect()
            self._is_connected = False
            logger.info("Disconnected from IB")
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop_heartbeat()
        await self.disconnect()

    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._is_connected and self.ib.isConnected()

    async def ensure_connected(self) -> None:
        """Ensure connection is active, reconnect if needed."""
        if not self.is_connected:
            logger.warning("Connection lost, attempting reconnect...")
            await self.connect()

    async def _heartbeat_loop(self) -> None:
        """Periodic heartbeat to monitor connection health."""
        while self.is_connected:
            try:
                # Request account summary to verify connection is alive
                # This is lightweight and confirms connection works
                await self.ib.reqAccountSummaryAsync()
                self.last_heartbeat = datetime.now()
                logger.debug("Heartbeat: connection is alive")
            except Exception as e:
                logger.error(f"Heartbeat failed: {e}")
                self._is_connected = False
                break

            await asyncio.sleep(self.heartbeat_interval)

    async def start_heartbeat(self) -> None:
        """Start heartbeat monitoring task."""
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            logger.info("Heartbeat monitoring started")

    async def stop_heartbeat(self) -> None:
        """Stop heartbeat monitoring task."""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            logger.info("Heartbeat monitoring stopped")

    async def connection_health(self) -> dict:
        """Get connection health status."""
        age_seconds = (datetime.now() - self.last_heartbeat).total_seconds()
        return {
            "connected": self.is_connected,
            "last_heartbeat_age_seconds": age_seconds,
            "circuit_breaker_state": self.circuit_breaker.state.value,
            "healthy": self.is_connected and age_seconds < self.heartbeat_interval * 2
        }

    async def get_live_underlying_price(self, symbol: str) -> float:
        """
        Fetch live underlying price from IBKR.

        Args:
            symbol: Underlying symbol (e.g., "SPY")

        Returns:
            Current market price (midpoint of bid/ask)

        Raises:
            ValueError: If price cannot be fetched or is invalid
        """
        await self.ensure_connected()

        # Create stock contract
        import ib_async
        contract = ib_async.Stock(
            symbol=symbol,
            exchange="SMART",
            currency="USD"
        )

        # Request live data
        try:
            ticker = await self.ib.reqTickersAsync(contract)
            if not ticker or len(ticker) == 0:
                raise ValueError(f"No ticker data for {symbol}")

            ticker_data = ticker[0]

            # Use midpoint of bid/ask, fallback to last
            if ticker_data.bid and ticker_data.ask:
                price = (ticker_data.bid + ticker_data.ask) / 2
            elif ticker_data.last:
                price = ticker_data.last
            elif ticker_data.close:
                price = ticker_data.close
            else:
                raise ValueError(f"No valid price data for {symbol}")

            if price <= 0:
                raise ValueError(f"Invalid price for {symbol}: {price}")

            logger.debug(f"Live price for {symbol}: ${price:.2f}")
            return float(price)

        except Exception as e:
            logger.error(f"Failed to fetch live price for {symbol}: {e}")
            raise ValueError(f"Could not fetch live price for {symbol}: {e}")
