"""
Market data fixtures for testing options market data.

Provides realistic option chains, Greeks snapshots, and market conditions
for testing trading decisions and strategy execution.

Usage:
    @pytest.fixture
    def option_chain(mock_option_chain):
        return option_chain

    def test_chain(option_chain):
        assert len(option_chain["calls"]) > 0
"""

import pytest
from datetime import date, datetime
from typing import Optional


@pytest.fixture
def mock_option_chain():
    """
    Create a realistic option chain with multiple strikes and expirations.

    Returns a complete option chain for SPY with calls, puts, bid/ask spreads,
    implied volatility, and Greeks. Strikes centered around current price.

    Returns:
        dict: Option chain with:
            - symbol: SPY
            - underlying_price: Current underlying price (455.0)
            - expirations: List of expiration dates
            - calls: Dict of call options keyed by strike
            - puts: Dict of put options keyed by strike
            - Each option has:
                - strike: Strike price
                - expiration: Expiration date
                - dte: Days to expiration
                - bid: Best bid
                - ask: Best ask
                - last: Last trade price
                - volume: Trading volume
                - open_interest: Open interest
                - iv: Implied volatility (0-1)
                - delta: Option delta
                - gamma: Option gamma
                - theta: Option theta (per day)
                - vega: Option vega (per 1% IV change)

    Example:
        def test_option_chain(mock_option_chain):
            chain = mock_option_chain
            assert chain["symbol"] == "SPY"
            assert 450 in chain["puts"]
            assert 460 in chain["calls"]
    """
    underlying_price = 455.0
    strikes = [
        430,
        435,
        440,
        445,
        450,  # ATM puts
        455,  # ATM
        460,  # ATM calls
        465,
        470,
        475,
        480,
    ]
    expirations = [
        date(2026, 2, 20),  # ~30 DTE
        date(2026, 3, 20),  # ~60 DTE
        date(2026, 6, 20),  # ~150 DTE
    ]

    calls = {}
    puts = {}

    for exp in expirations:
        dte = (exp - date.today()).days

        for strike in strikes:
            # Calculate realistic Greeks using simplified Black-Scholes
            moneyness = (underlying_price - strike) / underlying_price
            time_factor = dte / 365.0

            # Delta: Sigmoid around ATM
            delta = 1 / (1 + abs(moneyness * 10))
            if strike < underlying_price:
                call_delta = delta
                put_delta = delta - 1
            else:
                call_delta = delta
                put_delta = delta - 1

            # Gamma: Peak at ATM, decay with time
            gamma = 0.03 / (1 + abs(moneyness * 5)) * (1 / (1 + time_factor))

            # Theta: Decay accelerates near expiration
            theta = -gamma * underlying_price**2 * 0.1 / (1 + time_factor)

            # Vega: Higher with more time
            vega = 0.1 * (dte / 365.0) * (1 / (1 + abs(moneyness * 2)))

            # IV: Smile effect (higher OTM)
            iv = 0.18 + 0.02 * abs(moneyness) * 2

            # Prices: Intrinsic + time value
            intrinsic_call = max(0, underlying_price - strike)
            intrinsic_put = max(0, strike - underlying_price)
            time_value = gamma * underlying_price * 2

            call_bid = max(0.05, intrinsic_call + time_value - 0.02)
            call_ask = call_bid + 0.02
            put_bid = max(0.05, intrinsic_put + time_value - 0.02)
            put_ask = put_bid + 0.02

            calls[strike] = {
                "strike": strike,
                "expiration": exp,
                "dte": dte,
                "bid": round(call_bid, 2),
                "ask": round(call_ask, 2),
                "last": round((call_bid + call_ask) / 2, 2),
                "volume": 500 + int(abs(moneyness) * 1000),
                "open_interest": 2000 + int(abs(moneyness) * 3000),
                "iv": round(iv, 4),
                "delta": round(call_delta, 4),
                "gamma": round(gamma, 4),
                "theta": round(theta, 2),
                "vega": round(vega, 2),
            }

            puts[strike] = {
                "strike": strike,
                "expiration": exp,
                "dte": dte,
                "bid": round(put_bid, 2),
                "ask": round(put_ask, 2),
                "last": round((put_bid + put_ask) / 2, 2),
                "volume": 500 + int(abs(moneyness) * 1000),
                "open_interest": 2000 + int(abs(moneyness) * 3000),
                "iv": round(iv, 4),
                "delta": round(put_delta, 4),
                "gamma": round(gamma, 4),
                "theta": round(theta, 2),
                "vega": round(vega, 2),
            }

    return {
        "symbol": "SPY",
        "underlying_price": underlying_price,
        "expirations": expirations,
        "calls": calls,
        "puts": puts,
        "timestamp": datetime.now(),
    }


@pytest.fixture
def mock_greeks_snapshot():
    """
    Create a Greeks snapshot for portfolio risk calculation.

    Returns realistic Greeks for a portfolio of positions, including
    cross-gamma and vega exposure calculations.

    Returns:
        dict: Greeks snapshot with:
            - timestamp: Snapshot time
            - portfolio_greeks: Aggregate portfolio Greeks
                - delta: Net delta
                - gamma: Net gamma
                - theta: Net theta (per day)
                - vega: Net vega (per 1% IV change)
            - per_symbol_greeks: Greeks broken down by symbol
            - per_position_greeks: Greeks broken down by position
            - risk_metrics: Additional risk metrics
                - total_exposure: Notional exposure
                - beta_weighted_delta: Beta-adjusted delta
                - iv_rank: Current IV rank (0-100)
                - iv_percentile: Current IV percentile (0-100)
                - vega_weighted_gammas: Gamma * vega for each position

    Example:
        def test_greeks(mock_greeks_snapshot):
            portfolio = mock_greeks_snapshot["portfolio_greeks"]
            assert abs(portfolio["delta"]) < 50  # Delta-neutralish
            assert portfolio["theta"] > 0  # Positive theta
    """
    return {
        "timestamp": datetime.now(),
        "portfolio_greeks": {
            "delta": -15.5,  # Slightly bearish
            "gamma": -2.3,  # Negative gamma (short options)
            "theta": 45.2,  # Positive theta (time decay)
            "vega": -120.5,  # Short vega (benefit from IV drop)
        },
        "per_symbol_greeks": {
            "SPY": {
                "delta": -10.5,
                "gamma": -1.5,
                "theta": 30.0,
                "vega": -80.0,
            },
            "QQQ": {
                "delta": -5.0,
                "gamma": -0.8,
                "theta": 15.2,
                "vega": -40.5,
            },
        },
        "per_position_greeks": {
            "test-strategy-001": {
                "delta": -0.30,
                "gamma": -0.02,
                "theta": 8.0,
                "vega": -14.0,
            },
            "test-strategy-002": {
                "delta": -0.25,
                "gamma": -0.015,
                "theta": 7.5,
                "vega": -12.0,
            },
        },
        "risk_metrics": {
            "total_exposure": 250000.0,
            "beta_weighted_delta": -18.5,
            "iv_rank": 35.2,  # 35th percentile
            "iv_percentile": 38.5,
            "vega_weighted_gammas": {
                "test-strategy-001": -0.28,  # gamma * vega
                "test-strategy-002": -0.18,
            },
        },
    }


@pytest.fixture
def mock_low_iv_environment():
    """
    Create a low IV environment (IV crush scenario).

    Returns option chain and Greeks with low IV (IV < 10th percentile).

    Returns:
        dict: Low IV environment data with:
            - iv_rank: Low (5-10)
            - iv_percentile: Low (5-10)
            - option_chain: Chain with low IV values
            - greeks: Greeks in low IV environment

    Example:
        def test_low_iv(mock_low_iv_environment):
            assert mock_low_iv_environment["iv_rank"] < 10
    """
    chain = mock_option_chain()

    # Reduce IV across all options
    for strike, option in chain["calls"].items():
        option["iv"] = 0.08  # 8% IV (very low)
    for strike, option in chain["puts"].items():
        option["iv"] = 0.08

    return {
        "iv_rank": 8.5,
        "iv_percentile": 9.2,
        "option_chain": chain,
        "greeks": {
            "delta": -5.0,
            "gamma": -1.0,
            "theta": 15.0,
            "vega": -50.0,  # Short vega in low IV (benefit from IV rise)
        },
    }


@pytest.fixture
def mock_high_iv_environment():
    """
    Create a high IV environment (elevated risk).

    Returns option chain and Greeks with high IV (IV > 90th percentile).

    Returns:
        dict: High IV environment data with:
            - iv_rank: High (90-95)
            - iv_percentile: High (90-95)
            - option_chain: Chain with high IV values
            - greeks: Greeks in high IV environment

    Example:
        def test_high_iv(mock_high_iv_environment):
            assert mock_high_iv_environment["iv_rank"] > 90
    """
    chain = mock_option_chain()

    # Increase IV across all options
    for strike, option in chain["calls"].items():
        option["iv"] = 0.35  # 35% IV (very high)
    for strike, option in chain["puts"].items():
        option["iv"] = 0.35

    return {
        "iv_rank": 92.5,
        "iv_percentile": 94.0,
        "option_chain": chain,
        "greeks": {
            "delta": -25.0,
            "gamma": -3.5,
            "theta": 80.0,
            "vega": -200.0,  # Large short vega exposure
        },
    }


@pytest.fixture
def mock_volatile_market():
    """
    Create a volatile market scenario (large price swings).

    Returns market data with high volatility and large price movements.

    Returns:
        dict: Volatile market data with:
            - underlying_price: Current price
            - change_1h: 1-hour price change %
            - change_1d: 1-day price change %
            - iv_change: IV change % (from open)
            - vix: VIX level
            - option_chain: Chain with elevated IV
            - greeks: Greeks with increased gamma/vega

    Example:
        def test_volatile(mock_volatile_market):
            assert abs(mock_volatile_market["change_1d"]) > 2.0
    """
    chain = mock_option_chain()

    # Increase IV and widen bid/ask
    for strike, option in chain["calls"].items():
        option["iv"] = 0.28
        option["ask"] = option["bid"] + 0.10  # Wider spreads
        option["gamma"] *= 2.0  # Higher gamma
    for strike, option in chain["puts"].items():
        option["iv"] = 0.28
        option["ask"] = option["bid"] + 0.10
        option["gamma"] *= 2.0

    return {
        "underlying_price": 455.0,
        "change_1h": -1.5,  # Down 1.5% in last hour
        "change_1d": -2.8,  # Down 2.8% on the day
        "iv_change": 15.0,  # IV up 15% from open
        "vix": 28.5,  # Elevated VIX
        "option_chain": chain,
        "greeks": {
            "delta": -35.0,  # Delta shifted negative
            "gamma": -5.0,  # Higher gamma risk
            "theta": 90.0,  # Higher theta benefit
            "vega": -180.0,  # Large vega exposure
        },
    }
