"""
Market Data Fetcher Module

Provides option chain data collection for SPY, QQQ, IWM using IB API.
Calculates IV Rank from historical Delta Lake data, gets VIX data,
and determines underlying trend for entry signal prediction.

Purpose: Collect real-time option data for analysis, backtesting, and ML training.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import polars as pl
from ib_async import IB, Contract, Option
from loguru import logger

from src.v6.data.option_snapshots import OptionSnapshotsTable
from src.v6.core.models import OptionContract
from src.v6.utils.ib_connection import IBConnectionManager, CircuitBreaker


# Note: OptionContract is now in src/v6/core/models.py to avoid circular imports


class OptionDataFetcher:
    """
    Real-time option data fetcher with IB API integration.

    Fetches complete option chains for ETFs, calculates market indicators
    (IV Rank, VIX, trend), and manages connection lifecycle.

    Attributes:
        ib_conn: IB connection manager
        symbols: List of symbols to fetch (SPY, QQQ, IWM)
        option_snapshots_table: Delta Lake table for persistence
        circuit_breaker: Circuit breaker for error handling
        _vix_contract: Cached VIX contract
    """

    # Symbol to IB contract mapping
    SYMBOL_CONIDS = {
        "SPY": 756733,
        "QQQ": 625607,
        "IWM": 317476919,
        "VIX": 2713937,  # VIX index
    }

    def __init__(
        self,
        ib_conn: IBConnectionManager,
        option_snapshots_table: OptionSnapshotsTable,
        symbols: Optional[List[str]] = None,
    ):
        """
        Initialize option data fetcher.

        Args:
            ib_conn: IB connection manager
            option_snapshots_table: Delta Lake table for persistence
            symbols: List of symbols to fetch (default: SPY, QQQ, IWM)
        """
        self.ib_conn = ib_conn
        self.option_snapshots_table = option_snapshots_table
        self.symbols = symbols or ["SPY", "QQQ", "IWM"]
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=60)
        self._vix_contract: Optional[Contract] = None

        logger.info(f"✓ OptionDataFetcher initialized for symbols: {self.symbols}")

    async def find_best_expiration(
        self,
        symbol: str,
        target_dte: int = 45,
        min_dte: int = 21,
        max_dte: int = 60
    ) -> Optional[str]:
        """
        Find the best expiration date from actual IB option chain.

        Strategy:
        - Prefer expirations >= target_dte (45+ days better than < 45)
        - If none >= target_dte, use highest available below target
        - Must be >= min_dte (21 days closing threshold)

        Args:
            symbol: Underlying symbol
            target_dte: Target days to expiration (default: 45)
            min_dte: Minimum acceptable DTE - closing threshold (default: 21)
            max_dte: Maximum acceptable DTE (default: 60)

        Returns:
            Expiration date string (YYYYMMDD) with best DTE, or None
        """
        try:
            await self.ib_conn.ensure_connected()

            # Get stock contract
            from ib_async import Contract
            stock_contract = Contract(
                secType="STK",
                symbol=symbol,
                exchange="SMART",
                currency="USD"
            )

            qualified_contracts = await self.ib_conn.ib.qualifyContractsAsync(stock_contract)
            if not qualified_contracts:
                logger.error(f"Failed to qualify stock contract for {symbol}")
                return None

            stock_contract = qualified_contracts[0]

            # Get option chain from IB
            chain = await self.ib_conn.ib.reqSecDefOptParamsAsync(
                stock_contract.symbol,
                "",
                stock_contract.secType,
                stock_contract.conId
            )

            if not chain:
                logger.warning(f"No option chain data for {symbol}")
                return None

            # Find best expiration with preference for >= target_dte
            best_expiry = None
            best_dte_above_target = None  # Best DTE >= target
            best_dte_below_target = None  # Best DTE < target (fallback)
            now = datetime.now()

            for exp_data in chain:
                expirations = exp_data.expirations

                for expiry in expirations:
                    try:
                        expiry_date = datetime.strptime(expiry, "%Y%m%d")
                        dte = (expiry_date - now).days

                        # Check if within acceptable range
                        if min_dte <= dte <= max_dte:
                            if dte >= target_dte:
                                # Prefer expirations >= target (45+)
                                if best_dte_above_target is None or dte < best_dte_above_target:
                                    best_dte_above_target = dte
                                    best_expiry = expiry
                            else:
                                # Fallback: below target but >= min
                                if best_dte_below_target is None or dte > best_dte_below_target:
                                    best_dte_below_target = dte
                                    # Only use below-target if no above-target found
                                    if best_expiry is None:
                                        best_expiry = expiry
                    except ValueError:
                        continue

                # Found expirations in this chain, no need to check others
                if best_expiry:
                    break

            if best_expiry:
                expiry_date = datetime.strptime(best_expiry, "%Y%m%d")
                dte = (expiry_date - now).days
                preference = "above" if dte >= target_dte else "below"
                logger.info(
                    f"✓ Best expiration for {symbol}: {best_expiry} "
                    f"({dte} DTE, {preference} target={target_dte}, min={min_dte})"
                )
                return best_expiry
            else:
                logger.warning(
                    f"No expirations found for {symbol} within {min_dte}-{max_dte} DTE range"
                )
                return None

        except Exception as e:
            logger.error(f"Error finding best expiration for {symbol}: {e}")
            self.circuit_breaker.record_failure()
            return None

    async def fetch_option_chain(self, symbol: str) -> List[OptionContract]:
        """
        Fetch complete option chain for symbol.

        Fetches all puts and calls for all available strikes and expirations.
        Includes Greeks, IV, and market data.

        Args:
            symbol: Underlying symbol (SPY, QQQ, IWM)

        Returns:
            List[OptionContract]: All option contracts

        Raises:
            ValueError: If symbol not in allowed list
            ConnectionError: If IB connection fails
        """
        if symbol not in self.symbols:
            raise ValueError(f"Symbol {symbol} not in allowed list: {self.symbols}")

        if not self.circuit_breaker.can_attempt():
            logger.warning(f"Circuit breaker OPEN - skipping {symbol} option chain")
            return []

        try:
            await self.ib_conn.ensure_connected()

            # Get underlying stock contract
            stock_contract = Contract(
                secType="STK",
                symbol=symbol,
                exchange="SMART",
                currency="USD"
            )

            qualified_contracts = await self.ib_conn.ib.qualifyContractsAsync(stock_contract)
            if not qualified_contracts:
                logger.error(f"Failed to qualify stock contract for {symbol}")
                self.circuit_breaker.record_failure()
                return []

            stock_contract = qualified_contracts[0]
            logger.info(f"✓ Qualified {symbol} stock contract: conId={stock_contract.conId}")

            # Request option chain
            ticker = self.ib_conn.ib.reqMktData(
                stock_contract,
                "",  # Generic ticks
                False,  # Snapshot
                False  # Regulatory snapshot
            )

            # Wait for ticker data
            await asyncio.sleep(1)

            # Get option chain from IB
            # IB provides option chain through reqSecDefOptParams
            chain = await self.ib_conn.ib.reqSecDefOptParamsAsync(
                stock_contract.symbol,
                "",
                stock_contract.secType,
                stock_contract.conId
            )

            if not chain:
                logger.warning(f"No option chain data for {symbol}")
                return []

            contracts = []

            # Process each expiration
            for exp_data in chain:
                exchange = exp_data.exchange
                underlying_conid = exp_data.underlyingConId
                trading_class = exp_data.tradingClass
                expirations = exp_data.expirations
                strikes = exp_data.strikes

                logger.info(
                    f"Found {len(expirations)} expirations and {len(strikes)} strikes "
                    f"for {symbol} on {exchange}"
                )

                # Fetch option data for each expiration and strike
                # To avoid rate limits, we'll focus on near-term expirations (DTE 0-60)
                now = datetime.now()
                filtered_expirations = []

                for expiry in expirations:
                    try:
                        expiry_date = datetime.strptime(expiry, "%Y%m%d")
                        dte = (expiry_date - now).days
                        if 0 <= dte <= 60:  # Focus on 0-60 DTE
                            filtered_expirations.append(expiry)
                    except ValueError:
                        continue

                logger.info(f"Fetching {len(filtered_expirations)} near-term expirations for {symbol}")

                # Limit strikes to ATM range (e.g., underlying ±20%)
                # Get underlying price
                underlying_price = ticker.last if ticker.last else 0
                if not underlying_price:
                    logger.warning(f"No underlying price for {symbol}, using midpoint")
                    underlying_price = (ticker.bid + ticker.ask) / 2 if ticker.bid and ticker.ask else 0

                if underlying_price:
                    min_strike = underlying_price * 0.8
                    max_strike = underlying_price * 1.2
                    filtered_strikes = [s for s in strikes if min_strike <= s <= max_strike]
                else:
                    filtered_strikes = strikes

                logger.info(f"Fetching {len(filtered_strikes)} strikes for {symbol}")

                # Fetch contracts for each expiration and strike
                for expiry in filtered_expirations[:5]:  # Limit to 5 expirations
                    for right in ['P', 'C']:  # Put and Call
                        for strike in filtered_strikes:
                            try:
                                # Create option contract
                                option_contract = Option(
                                    symbol=symbol,
                                    lastTradeDateOrContractMonth=expiry,
                                    strike=strike,
                                    right=right,
                                    exchange=exchange,
                                    currency="USD"
                                )

                                # Qualify contract
                                qualified_options = await self.ib_conn.ib.qualifyContractsAsync(
                                    option_contract
                                )

                                if not qualified_options:
                                    continue

                                option_contract = qualified_options[0]

                                # Request market data
                                option_ticker = self.ib_conn.ib.reqMktData(
                                    option_contract,
                                    "100,101,104,105,106",  # Greeks and IV
                                    False,
                                    False
                                )

                                # Wait for data
                                await asyncio.sleep(0.01)  # Small delay to avoid rate limit

                                # Extract contract data
                                contract = OptionContract(
                                    symbol=symbol,
                                    timestamp=datetime.now(),
                                    strike=strike,
                                    expiry=expiry,
                                    right=right,
                                    bid=option_ticker.bid if option_ticker.bid else 0,
                                    ask=option_ticker.ask if option_ticker.ask else 0,
                                    last=option_ticker.last if option_ticker.last else 0,
                                    volume=option_ticker.volume if option_ticker.volume else 0,
                                    open_interest=option_ticker.openInterest if option_ticker.openInterest else None,
                                    iv=option_ticker.impliedVolatility if hasattr(option_ticker, 'impliedVolatility') else None,
                                    delta=self._get_greek(option_ticker, 'delta'),
                                    gamma=self._get_greek(option_ticker, 'gamma'),
                                    theta=self._get_greek(option_ticker, 'theta'),
                                    vega=self._get_greek(option_ticker, 'vega'),
                                )

                                contracts.append(contract)

                                # Cancel market data to free up slots
                                self.ib_conn.ib.cancelMktData(option_contract)

                            except Exception as e:
                                logger.debug(f"Error fetching option data: {e}")
                                continue

            logger.info(f"✓ Fetched {len(contracts)} option contracts for {symbol}")
            self.circuit_breaker.record_success()
            return contracts

        except Exception as e:
            logger.error(f"Error fetching option chain for {symbol}: {e}")
            self.circuit_breaker.record_failure()
            return []

    def _get_greek(self, ticker, greek_name: str) -> Optional[float]:
        """Extract Greek value from ticker."""
        try:
            if hasattr(ticker, 'modelGreeks'):
                greeks = ticker.modelGreeks
                if greeks and hasattr(greeks, greek_name):
                    return getattr(greeks, greek_name)
            return None
        except Exception:
            return None

    async def calculate_iv_rank(self, symbol: str) -> float:
        """
        Calculate IV Rank from historical Delta Lake data.

        IV Rank = (Current IV - Min IV) / (Max IV - Min IV) * 100
        Uses 30-60 days of historical IV data.

        Args:
            symbol: Underlying symbol (SPY, QQQ, IWM)

        Returns:
            float: IV Rank (0-100)
        """
        try:
            # Read historical IV data from Delta Lake
            dt = self.option_snapshots_table.get_table()

            # Get last 60 days of data
            end_date = datetime.now()
            start_date = end_date - timedelta(days=60)

            df = pl.from_pandas(dt.to_pandas())

            # Filter by symbol and date range
            df = df.filter(
                (pl.col("symbol") == symbol) &
                (pl.col("timestamp") >= start_date) &
                (pl.col("timestamp") <= end_date) &
                (pl.col("iv").is_not_null())
            )

            if len(df) < 30:
                logger.warning(f"Not enough IV data for {symbol} (n={len(df)})")
                return 50.0  # Default to mid-range

            # Get daily IV averages (use ATM options or average all)
            daily_iv = df.group_dynamic(
                "timestamp",
                every="1d",
                period="1d"
            ).agg(
                pl.col("iv").mean().alias("avg_iv")
            ).drop_nulls()

            if len(daily_iv) < 30:
                logger.warning(f"Not enough daily IV data for {symbol} (n={len(daily_iv)})")
                return 50.0

            # Calculate IV Rank
            min_iv = daily_iv.select(pl.col("avg_iv").min()).item()
            max_iv = daily_iv.select(pl.col("avg_iv").max()).item()
            current_iv = daily_iv.select(pl.col("avg_iv").last()).item()

            if max_iv == min_iv:
                return 50.0

            iv_rank = ((current_iv - min_iv) / (max_iv - min_iv)) * 100

            logger.info(f"{symbol} IV Rank: {iv_rank:.1f} (IV: {current_iv:.2%}, Range: {min_iv:.2%}-{max_iv:.2%})")

            return round(iv_rank, 1)

        except Exception as e:
            logger.error(f"Error calculating IV rank for {symbol}: {e}")
            return 50.0  # Default to mid-range

    async def get_vix(self) -> float:
        """
        Get current VIX value from IB.

        Fetches $VIX index value as market fear gauge.

        Returns:
            float: VIX value
        """
        try:
            if not self.circuit_breaker.can_attempt():
                logger.warning("Circuit breaker OPEN - using default VIX")
                return 18.0

            await self.ib_conn.ensure_connected()

            # Get or create VIX contract
            if self._vix_contract is None:
                self._vix_contract = Contract(
                    secType="IND",
                    symbol="VIX",
                    exchange="CBOE",
                    currency="USD"
                )

                qualified = await self.ib_conn.ib.qualifyContractsAsync(self._vix_contract)
                if qualified:
                    self._vix_contract = qualified[0]
                else:
                    logger.warning("Failed to qualify VIX contract")
                    return 18.0

            # Request VIX data
            ticker = self.ib_conn.ib.reqMktData(
                self._vix_contract,
                "",
                False,
                False
            )

            await asyncio.sleep(1)

            vix_value = ticker.last if ticker.last else 18.0

            logger.info(f"VIX: {vix_value:.2f}")
            self.circuit_breaker.record_success()

            return vix_value

        except Exception as e:
            logger.error(f"Error fetching VIX: {e}")
            self.circuit_breaker.record_failure()
            return 18.0  # Default value

    async def get_underlying_trend(self, symbol: str) -> str:
        """
        Determine underlying trend (uptrend/downtrend/neutral).

        Uses simple moving average crossover logic:
        - Uptrend: Price > SMA(20) and SMA(20) > SMA(50)
        - Downtrend: Price < SMA(20) and SMA(20) < SMA(50)
        - Neutral: Neither condition met

        Args:
            symbol: Underlying symbol (SPY, QQQ, IWM)

        Returns:
            str: Trend ("uptrend", "downtrend", "neutral")
        """
        try:
            await self.ib_conn.ensure_connected()

            # Get stock contract
            stock_contract = Contract(
                secType="STK",
                symbol=symbol,
                exchange="SMART",
                currency="USD"
            )

            # Fetch historical data for SMA calculation
            # Get 50 days of daily bars
            bars = await self.ib_conn.ib.reqHistoricalDataAsync(
                stock_contract,
                endDateTime=datetime.now(),
                durationStr="50 D",
                barSizeSetting="1 day",
                whatToShow="TRADES",
                useRTH=True
            )

            if not bars or len(bars) < 50:
                logger.warning(f"Not enough historical data for trend calculation for {symbol}")
                return "neutral"

            # Calculate SMAs
            closes = [bar.close for bar in bars]

            # Current price
            current_price = closes[-1]

            # SMA(20)
            sma20 = sum(closes[-20:]) / 20

            # SMA(50)
            sma50 = sum(closes[-50:]) / 50

            # Determine trend
            if current_price > sma20 and sma20 > sma50:
                trend = "uptrend"
            elif current_price < sma20 and sma20 < sma50:
                trend = "downtrend"
            else:
                trend = "neutral"

            logger.info(
                f"{symbol} trend: {trend} "
                f"(Price: {current_price:.2f}, SMA20: {sma20:.2f}, SMA50: {sma50:.2f})"
            )

            return trend

        except Exception as e:
            logger.error(f"Error calculating trend for {symbol}: {e}")
            return "neutral"

    async def get_market_data(self, symbol: str) -> Dict[str, any]:
        """
        Get comprehensive market data for symbol.

        Fetches option chain, IV Rank, VIX, and trend in one call.

        Args:
            symbol: Underlying symbol (SPY, QQQ, IWM)

        Returns:
            dict: Market data including iv_rank, vix, trend, option_chain
        """
        try:
            # Fetch all market data in parallel
            iv_rank_task = asyncio.create_task(self.calculate_iv_rank(symbol))
            vix_task = asyncio.create_task(self.get_vix())
            trend_task = asyncio.create_task(self.get_underlying_trend(symbol))
            option_chain_task = asyncio.create_task(self.fetch_option_chain(symbol))

            # Wait for completion
            iv_rank = await iv_rank_task
            vix = await vix_task
            trend = await trend_task
            option_chain = await option_chain_task

            return {
                "symbol": symbol,
                "iv_rank": iv_rank,
                "vix": vix,
                "underlying_trend": trend,
                "option_chain": option_chain,
                "timestamp": datetime.now(),
            }

        except Exception as e:
            logger.error(f"Error getting market data for {symbol}: {e}")
            return {
                "symbol": symbol,
                "iv_rank": 50.0,
                "vix": 18.0,
                "underlying_trend": "neutral",
                "option_chain": [],
                "timestamp": datetime.now(),
            }

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
            "symbols": self.symbols,
            "healthy": ib_health["healthy"] and self.circuit_breaker.can_attempt()
        }
