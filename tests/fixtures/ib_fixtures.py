"""
IB connection and API response fixtures for testing.

Provides realistic mock IB connections, portfolio data, positions, and market data
for integration testing without requiring actual IB connections.

Usage:
    @pytest.fixture
    def mock_ib(mock_ib_connection):
        return mock_ib

    def test_something(mock_ib):
        # Use mock_ib like a real IB connection
        pass
"""

import pytest
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, Mock
from typing import Optional

from ib_async import Contract, PortfolioItem, Position


@pytest.fixture
def mock_ib_connection():
    """
    Create a mock IB connection with realistic async responses.

    Provides a fully mocked IB connection object with async methods
    that simulate real IB API behavior without network calls.

    Returns:
        MagicMock: Mock IB connection with:
            - ib: Mock IB object
            - ensure_connected(): AsyncMock that connects successfully
            - reqPositions(): AsyncMock that returns positions
            - reqAccountSummary(): AsyncMock that returns account data
            - disconnect(): Mock that disconnects cleanly

    Example:
        def test_with_ib(mock_ib_connection):
            ib = mock_ib_connection
            await ib.ensure_connected()
            positions = await ib.reqPositions()
    """
    ib_conn = MagicMock()

    # Create mock IB object
    ib_conn.ib = MagicMock()
    ib_conn.ib.clientId = 1
    ib_conn.ib.isConnected = MagicMock(return_value=True)

    # Async methods
    ib_conn.ensure_connected = AsyncMock()
    ib_conn.disconnect = MagicMock()
    ib_conn.reqPositions = AsyncMock()
    ib_conn.reqAccountSummary = AsyncMock()
    ib_conn.reqMarketDataType = AsyncMock()
    ib_conn.qualifyContracts = AsyncMock()

    # Order methods
    ib_conn.placeOrder = MagicMock()
    ib_conn.cancelOrder = MagicMock()

    # Market data methods
    ib_conn.reqMktData = MagicMock()
    ib_conn.cancelMktData = MagicMock()

    # Set up default returns
    ib_conn.ensure_connected.return_value = None
    ib_conn.reqPositions.return_value = []
    ib_conn.reqAccountSummary.return_value = {}
    ib_conn.qualifyContracts.return_value = []

    return ib_conn


@pytest.fixture
def mock_portfolio_response():
    """
    Create mock portfolio response with realistic account data.

    Returns sample portfolio items as returned by IB's reqPositions().

    Returns:
        list[PortfolioItem]: List of mock portfolio items with:
            - account: "DU1234567"
            - contract: Mock contract
            - position: Positive/negative quantities
            - marketPrice: Realistic market prices
            - marketValue: Calculated from price * quantity * 100
            - averageCost: Realistic cost basis
            - unrealizedPNL: Calculated P&L
            - realizedPNL: Realized gains/losses

    Example:
        def test_portfolio(mock_portfolio_response):
            for item in mock_portfolio_response:
                assert item.account == "DU1234567"
    """
    items = []

    # SPY Call position
    spy_call_contract = Contract(
        secType="OPT",
        symbol="SPY",
        lastTradeDateOrContractMonth="20260320",
        strike=460,
        right="C",
        exchange="SMART",
        currency="USD",
    )
    spy_call_contract.conId = 123456789

    items.append(
        PortfolioItem(
            account="DU1234567",
            contract=spy_call_contract,
            position=1,
            marketPrice=2.50,
            marketValue=250.0,
            averageCost=2.00,
            unrealizedPNL=50.0,
            realizedPNL=0.0,
        )
    )

    # SPY Put position
    spy_put_contract = Contract(
        secType="OPT",
        symbol="SPY",
        lastTradeDateOrContractMonth="20260320",
        strike=440,
        right="P",
        exchange="SMART",
        currency="USD",
    )
    spy_put_contract.conId = 987654321

    items.append(
        PortfolioItem(
            account="DU1234567",
            contract=spy_put_contract,
            position=-1,
            marketPrice=1.75,
            marketValue=-175.0,
            averageCost=1.50,
            unrealizedPNL=-25.0,
            realizedPNL=0.0,
        )
    )

    return items


@pytest.fixture
def mock_position_data():
    """
    Create mock position data with Greeks for testing.

    Returns realistic option positions with Greeks as used internally
    by the trading system.

    Returns:
        dict: Mock position data with:
            - strategy_id: Unique identifier
            - symbol: Underlying symbol (SPY, QQQ, IWM)
            - strategy_type: Strategy type (IRON_CONDOR, etc.)
            - legs: List of leg dictionaries with Greeks
            - entry_price: Net credit/debit
            - current_price: Current market value
            - greeks: Portfolio-level Greeks (delta, gamma, theta, vega)
            - status: Position status (OPEN, CLOSED, etc.)
            - opened_at: Entry timestamp
            - dte: Days to expiration
            - underlying_price: Current underlying price

    Example:
        def test_position(mock_position_data):
            assert mock_position_data["symbol"] == "SPY"
            assert mock_position_data["greeks"]["delta"] == 0.5
    """
    return {
        "strategy_id": "test-strategy-001",
        "symbol": "SPY",
        "strategy_type": "IRON_CONDOR",
        "entry_price": -1.50,  # Net credit
        "current_price": -1.25,  # Current credit (profit)
        "unrealized_pnl": 25.0,
        "status": "OPEN",
        "opened_at": datetime.now(),
        "dte": 45,
        "underlying_price": 455.0,
        "legs": [
            {
                "leg_id": "leg-001",
                "right": "PUT",
                "strike": 450.0,
                "quantity": -1,
                "action": "SELL",
                "expiration": date(2026, 3, 20),
                "position": -1,
                "avg_fill_price": 1.50,
                "current_price": 1.25,
                "greeks": {
                    "delta": -0.25,
                    "gamma": -0.02,
                    "theta": 5.0,
                    "vega": -10.0,
                },
            },
            {
                "leg_id": "leg-002",
                "right": "PUT",
                "strike": 440.0,
                "quantity": 1,
                "action": "BUY",
                "expiration": date(2026, 3, 20),
                "position": 1,
                "avg_fill_price": 0.75,
                "current_price": 0.50,
                "greeks": {
                    "delta": 0.15,
                    "gamma": 0.01,
                    "theta": -2.0,
                    "vega": 5.0,
                },
            },
            {
                "leg_id": "leg-003",
                "right": "CALL",
                "strike": 460.0,
                "quantity": -1,
                "action": "SELL",
                "expiration": date(2026, 3, 20),
                "position": -1,
                "avg_fill_price": 1.75,
                "current_price": 1.50,
                "greeks": {
                    "delta": -0.30,
                    "gamma": -0.02,
                    "theta": 6.0,
                    "vega": -12.0,
                },
            },
            {
                "leg_id": "leg-004",
                "right": "CALL",
                "strike": 470.0,
                "quantity": 1,
                "action": "BUY",
                "expiration": date(2026, 3, 20),
                "position": 1,
                "avg_fill_price": 0.50,
                "current_price": 0.25,
                "greeks": {
                    "delta": 0.10,
                    "gamma": 0.01,
                    "theta": -1.0,
                    "vega": 3.0,
                },
            },
        ],
        "greeks": {
            "delta": -0.30,  # Sum of leg deltas
            "gamma": -0.02,  # Sum of leg gammas
            "theta": 8.0,  # Sum of leg thetas
            "vega": -14.0,  # Sum of leg vegas
        },
    }


@pytest.fixture
def mock_market_data():
    """
    Create mock market data snapshot with bid/ask and IV.

    Returns realistic market data for option contracts including
    bid/ask spreads, implied volatility, and Greeks.

    Returns:
        dict: Mock market data with:
            - bid: Best bid price
            - ask: Best ask price
            - last: Last trade price
            - volume: Trading volume
            - open_interest: Open interest
            - iv: Implied volatility (0-1)
            - delta: Option delta
            - gamma: Option gamma
            - theta: Option theta (per day)
            - vega: Option vega (per 1% IV change)
            - underlying_price: Current underlying price
            - timestamp: Data timestamp

    Example:
        def test_market_data(mock_market_data):
            assert mock_market_data["bid"] < mock_market_data["ask"]
            assert 0 < mock_market_data["iv"] < 1
    """
    return {
        "bid": 2.45,
        "ask": 2.55,
        "last": 2.50,
        "bid_size": 100,
        "ask_size": 150,
        "volume": 1250,
        "open_interest": 5000,
        "iv": 0.185,  # 18.5% IV
        "delta": 0.45,
        "gamma": 0.025,
        "theta": -0.08,  # -$8 per day per contract
        "vega": 0.15,  # $0.15 per 1% IV change
        "underlying_price": 455.0,
        "timestamp": datetime.now(),
    }


@pytest.fixture
def mock_empty_portfolio():
    """
    Create mock empty portfolio response.

    Returns empty portfolio list for testing edge cases.

    Returns:
        list: Empty list (no positions)

    Example:
        def test_empty_portfolio(mock_empty_portfolio):
            assert len(mock_empty_portfolio) == 0
    """
    return []


@pytest.fixture
def mock_large_portfolio():
    """
    Create mock portfolio with many positions for performance testing.

    Returns 100+ mock positions for testing system performance under load.

    Returns:
        list[PortfolioItem]: List of 100 mock portfolio items

    Example:
        def test_large_portfolio(mock_large_portfolio):
            assert len(mock_large_portfolio) >= 100
    """
    items = []
    symbols = ["SPY", "QQQ", "IWM"]

    for i in range(100):
        symbol = symbols[i % 3]
        strike = 400 + (i % 20) * 5
        right = "C" if i % 2 == 0 else "P"

        contract = Contract(
            secType="OPT",
            symbol=symbol,
            lastTradeDateOrContractMonth="20260320",
            strike=strike,
            right=right,
            exchange="SMART",
            currency="USD",
        )
        contract.conId = 100000000 + i

        items.append(
            PortfolioItem(
                account="DU1234567",
                contract=contract,
                position=1 if i % 2 == 0 else -1,
                marketPrice=2.0 + (i % 10) * 0.1,
                marketValue=(2.0 + (i % 10) * 0.1) * 100,
                averageCost=2.0,
                unrealizedPNL=(i % 10) * 10.0,
                realizedPNL=0.0,
            )
        )

    return items
