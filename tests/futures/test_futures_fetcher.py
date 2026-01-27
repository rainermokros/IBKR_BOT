"""
Tests for Futures Fetcher

Unit tests for futures fetcher including IB subscription, change calculations,
and connection management. Uses mocked IB data for testing.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from typing import List

from ib_async import Contract, Ticker

from src.v6.core.futures_fetcher import FuturesFetcher, FuturesSnapshot
from src.v6.config.futures_config import FuturesConfig


@pytest.fixture
def futures_config():
    """Create futures configuration for testing."""
    return FuturesConfig()


@pytest.fixture
def mock_ib():
    """Create mock IB connection."""
    ib = MagicMock()
    ib.isConnected = MagicMock(return_value=True)
    ib.connectAsync = AsyncMock()
    ib.disconnect = AsyncMock()
    ib.qualifyContractsAsync = AsyncMock()
    ib.reqMktData = MagicMock()
    ib.cancelMktData = MagicMock()
    ib.reqHistoricalDataAsync = AsyncMock()
    ib.ticker = MagicMock()
    ib.reqAccountSummaryAsync = AsyncMock()
    return ib


@pytest.fixture
def futures_fetcher(futures_config, mock_ib):
    """Create futures fetcher with mocked IB connection."""
    fetcher = FuturesFetcher(config=futures_config)

    # Replace IB connection with mock
    fetcher.ib_conn.ib = mock_ib
    fetcher.ib_conn._is_connected = True

    return fetcher


@pytest.fixture
def mock_es_contract():
    """Create mock ES futures contract."""
    contract = Contract(
        secType="FUT",
        symbol="ES",
        exchange="CME",
        currency="USD"
    )
    contract.conId = 123456
    return contract


@pytest.fixture
def mock_ticker():
    """Create mock ticker data."""
    ticker = Ticker()
    ticker.bid = 4500.25
    ticker.ask = 4500.50
    ticker.last = 4500.375
    ticker.volume = 100000
    ticker.openInterest = 500000
    ticker.impliedVolatility = 0.18

    return ticker


class TestFuturesFetcher:
    """Test suite for FuturesFetcher."""

    def test_init(self, futures_config):
        """Test futures fetcher initialization."""
        fetcher = FuturesFetcher(config=futures_config)

        assert fetcher.config is not None
        assert fetcher.config.enabled_symbols == ["ES", "NQ", "RTY"]
        assert fetcher.subscriptions == {}
        assert fetcher.price_history == {}
        assert fetcher.circuit_breaker is not None
        assert fetcher.circuit_breaker.state.value == "closed"

    def test_init_default_config(self):
        """Test initialization with default config."""
        fetcher = FuturesFetcher()

        assert fetcher.config is not None
        assert "ES" in fetcher.config.contracts
        assert "NQ" in fetcher.config.contracts
        assert "RTY" in fetcher.config.contracts

    @pytest.mark.asyncio
    async def test_subscribe_to_futures_default(self, futures_fetcher, mock_ib, mock_es_contract):
        """Test subscribing to default futures symbols."""
        # Mock qualify contracts
        mock_ib.qualifyContractsAsync.return_value = [mock_es_contract]

        # Subscribe
        await futures_fetcher.subscribe_to_futures()

        # Verify subscriptions
        assert "ES" in futures_fetcher.subscriptions
        assert "NQ" in futures_fetcher.subscriptions
        assert "RTY" in futures_fetcher.subscriptions

        # Verify IB calls
        assert mock_ib.qualifyContractsAsync.call_count == 3
        assert mock_ib.reqMktData.call_count == 3

    @pytest.mark.asyncio
    async def test_subscribe_to_futures_specific_symbols(self, futures_fetcher, mock_ib, mock_es_contract):
        """Test subscribing to specific symbols."""
        mock_ib.qualifyContractsAsync.return_value = [mock_es_contract]

        await futures_fetcher.subscribe_to_futures(symbols=["ES"])

        assert "ES" in futures_fetcher.subscriptions
        assert "NQ" not in futures_fetcher.subscriptions
        assert "RTY" not in futures_fetcher.subscriptions

    @pytest.mark.asyncio
    async def test_subscribe_disabled_symbol(self, futures_fetcher, mock_ib):
        """Test that disabled symbols are skipped."""
        # Disable NQ
        futures_fetcher.config.enabled_symbols = ["ES", "RTY"]

        mock_contract = Mock()
        mock_ib.qualifyContractsAsync.return_value = [mock_contract]

        await futures_fetcher.subscribe_to_futures()

        # Should only subscribe to ES and RTY
        assert "ES" in futures_fetcher.subscriptions
        assert "RTY" in futures_fetcher.subscriptions
        assert "NQ" not in futures_fetcher.subscriptions

    @pytest.mark.asyncio
    async def test_get_futures_snapshot(self, futures_fetcher, mock_ib, mock_ticker):
        """Test getting futures snapshot."""
        # Setup: Subscribe to ES first
        contract = Contract(secType="FUT", symbol="ES", exchange="CME", currency="USD")
        contract.conId = 123456
        futures_fetcher.subscriptions["ES"] = contract

        # Mock ticker
        mock_ib.ticker.return_value = mock_ticker

        # Mock historical data for changes
        mock_bars = []
        for i in range(60):
            bar = Mock()
            bar.close = 4490.0 + (i * 0.1)
            mock_bars.append(bar)

        mock_ib.reqHistoricalDataAsync.return_value = mock_bars

        # Get snapshot
        snapshot = await futures_fetcher.get_futures_snapshot("ES")

        assert snapshot is not None
        assert snapshot.symbol == "ES"
        assert snapshot.last == 4500.375
        assert snapshot.bid == 4500.25
        assert snapshot.ask == 4500.50
        assert snapshot.volume == 100000
        assert snapshot.implied_vol == 0.18
        assert isinstance(snapshot.timestamp, datetime)

    @pytest.mark.asyncio
    async def test_get_futures_snapshot_not_subscribed(self, futures_fetcher):
        """Test getting snapshot for unsubscribed symbol."""
        snapshot = await futures_fetcher.get_futures_snapshot("ES")

        assert snapshot is None

    @pytest.mark.asyncio
    async def test_calculate_changes(self, futures_fetcher, mock_ib):
        """Test change calculations."""
        # Setup: Subscribe to ES
        contract = Contract(secType="FUT", symbol="ES", exchange="CME", currency="USD")
        futures_fetcher.subscriptions["ES"] = contract

        # Mock historical data
        mock_bars = []
        for i in range(60):
            bar = Mock()
            bar.close = 4490.0 + (i * 0.1)
            mock_bars.append(bar)

        mock_ib.reqHistoricalDataAsync.return_value = mock_bars

        # Calculate changes
        current_price = 4500.0
        changes = await futures_fetcher.calculate_changes("ES", current_price)

        assert "change_1h" in changes
        assert "change_4h" in changes
        assert "change_overnight" in changes
        assert "change_daily" in changes

        # Verify 1h change (should be positive since we're going up)
        assert changes["change_1h"] is not None

    @pytest.mark.asyncio
    async def test_calculate_changes_no_data(self, futures_fetcher, mock_ib):
        """Test change calculations when no historical data available."""
        # Setup: Subscribe to ES
        contract = Contract(secType="FUT", symbol="ES", exchange="CME", currency="USD")
        futures_fetcher.subscriptions["ES"] = contract

        # Mock empty historical data
        mock_ib.reqHistoricalDataAsync.return_value = []

        # Calculate changes
        current_price = 4500.0
        changes = await futures_fetcher.calculate_changes("ES", current_price)

        # All changes should be None
        assert changes["change_1h"] is None
        assert changes["change_4h"] is None
        assert changes["change_overnight"] is None
        assert changes["change_daily"] is None

    @pytest.mark.asyncio
    async def test_unsubscribe_all(self, futures_fetcher, mock_ib):
        """Test unsubscribing from all futures."""
        # Setup: Subscribe to symbols
        contract = Contract(secType="FUT", symbol="ES", exchange="CME", currency="USD")
        futures_fetcher.subscriptions["ES"] = contract
        futures_fetcher.subscriptions["NQ"] = contract
        futures_fetcher.subscriptions["RTY"] = contract

        # Unsubscribe
        await futures_fetcher.unsubscribe_all()

        # Verify
        assert len(futures_fetcher.subscriptions) == 0
        assert mock_ib.cancelMktData.call_count == 3

    @pytest.mark.asyncio
    async def test_get_all_snapshots(self, futures_fetcher, mock_ib, mock_ticker):
        """Test getting all snapshots."""
        # Setup: Subscribe to symbols
        for symbol in ["ES", "NQ", "RTY"]:
            contract = Contract(secType="FUT", symbol=symbol, exchange="CME", currency="USD")
            futures_fetcher.subscriptions[symbol] = contract

        # Mock ticker
        mock_ib.ticker.return_value = mock_ticker
        mock_bars = [Mock(close=4500.0)]
        mock_ib.reqHistoricalDataAsync.return_value = mock_bars

        # Get all snapshots
        snapshots = await futures_fetcher.get_all_snapshots()

        assert len(snapshots) == 3
        assert "ES" in snapshots
        assert "NQ" in snapshots
        assert "RTY" in snapshots

    @pytest.mark.asyncio
    async def test_connection_health(self, futures_fetcher):
        """Test connection health check."""
        health = await futures_fetcher.connection_health()

        assert "ib_connected" in health
        assert "circuit_breaker_state" in health
        assert "active_subscriptions" in health
        assert "healthy" in health

        # Should be healthy if connected and circuit breaker closed
        assert health["circuit_breaker_state"] == "closed"

    @pytest.mark.asyncio
    async def test_circuit_breaker_on_failure(self, futures_fetcher, mock_ib):
        """Test circuit breaker opens on repeated failures."""
        # Force circuit breaker to open
        for _ in range(10):
            futures_fetcher.circuit_breaker.record_failure()

        assert futures_fetcher.circuit_breaker.state.value == "open"

        # Verify can_attempt blocks requests
        assert not futures_fetcher.circuit_breaker.can_attempt()


class TestFuturesSnapshot:
    """Test suite for FuturesSnapshot dataclass."""

    def test_create_snapshot(self):
        """Test creating a futures snapshot."""
        snapshot = FuturesSnapshot(
            symbol="ES",
            timestamp=datetime.now(),
            bid=4500.25,
            ask=4500.50,
            last=4500.375,
            volume=100000,
            change_1h=0.5,
            change_4h=1.2,
            change_overnight=-0.3,
            change_daily=0.8
        )

        assert snapshot.symbol == "ES"
        assert snapshot.last == 4500.375
        assert snapshot.change_1h == 0.5
        assert snapshot.change_daily == 0.8

    def test_create_snapshot_minimal(self):
        """Test creating snapshot with minimal fields."""
        snapshot = FuturesSnapshot(
            symbol="NQ",
            timestamp=datetime.now(),
            bid=15000.0,
            ask=15000.25,
            last=15000.125,
            volume=50000
        )

        assert snapshot.symbol == "NQ"
        assert snapshot.change_1h is None
        assert snapshot.implied_vol is None
