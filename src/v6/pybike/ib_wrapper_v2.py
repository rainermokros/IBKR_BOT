"""
IB Wrapper - Simplified interface for IB Gateway connections (FIXED VERSION)

Uses reqMktDepth() to get option chain data directly without qualifying individual contracts.
"""

import asyncio
from typing import List, Dict, Optional
from ib_async import IB, Stock, Option
from loguru import logger


class IBWrapperFixed:
    """
    Fixed wrapper that uses snapshot market data for option chains.

    This version uses reqMarketDataType() and reqMktData() with generic option
    contracts to get live data without qualifying each contract individually.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 4002, client_id: int = None):
        """Initialize IB wrapper."""
        import random
        self.host = host
        self.port = port
        self.client_id = client_id if client_id is not None else random.randint(1000, 9999)
        self.ib = IB()
        self._connected = False

    async def connect(self, host: Optional[str] = None, port: Optional[int] = None, timeout: int = 10):
        """Connect to IB Gateway."""
        ib_host = host or self.host
        ib_port = port or self.port

        logger.info(f"Connecting to IB Gateway at {ib_host}:{ib_port}...")
        await self.ib.connectAsync(host=ib_host, port=ib_port, clientId=self.client_id, timeout=timeout)
        self._connected = True
        logger.success(f"✓ Connected to IB Gateway")

    async def disconnect(self):
        """Disconnect from IB Gateway."""
        if self._connected:
            self.ib.disconnect()
            self._connected = False
            logger.info("Disconnected from IB Gateway")

    async def get_option_snapshots(self, symbol: str) -> List[Dict]:
        """
        Get option chain data using reqSecDefOptParamsAsync and qualifying contracts.

        Args:
            symbol: Stock/ETF symbol (e.g., SPY, QQQ, IWM)

        Returns:
            List of option contracts with Greeks and pricing data
        """
        if not self._connected:
            raise ConnectionError("Not connected to IB Gateway")

        logger.info(f"Fetching option snapshots for {symbol}...")

        try:
            # Get stock contract
            stock = Stock(symbol, 'SMART', 'USD')
            await self.ib.qualifyContractsAsync(stock)

            # Get current price
            ticker = self.ib.reqMktData(stock, "", False, False)
            await asyncio.sleep(1)
            current_price = ticker.marketPrice() if hasattr(ticker, 'marketPrice') else 0
            logger.info(f"Current price for {symbol}: {current_price}")

            # Get option chain parameters
            chains = await self.ib.reqSecDefOptParamsAsync(symbol, '', 'STK', stock.conId)
            if not chains:
                logger.warning(f"No option chains found for {symbol}")
                return []

            # Find the best chain (prefer one with SMART exchange or most expirations)
            chain = max(chains, key=lambda c: len(c.expirations))
            logger.info(f"Using {chain.exchange} with {len(chain.expirations)} expirations, {len(chain.strikes)} strikes")
            logger.info(f"Chain tradingClass: {chain.tradingClass}, multiplier: {chain.multiplier}")

            # Find ATM strikes (within ±2% of current price for better liquidity)
            min_strike = current_price * 0.98
            max_strike = current_price * 1.02
            strikes = sorted([s for s in chain.strikes if min_strike <= s <= max_strike])[:10]
            logger.info(f"Selected {len(strikes)} ATM strikes")

            # Select nearest expirations (within 45 days)
            from datetime import datetime, timedelta
            max_date = (datetime.now() + timedelta(days=45)).strftime("%Y%m%d")
            expirations = sorted([e for e in chain.expirations if e <= max_date])[:3]
            logger.info(f"Using {len(expirations)} near-term expirations: {expirations}")

            if not expirations or not strikes:
                logger.warning(f"No valid expirations or strikes for {symbol}")
                return []

            # Collect market data for each contract
            snapshots = []
            for expiry in expirations:
                for strike in strikes:
                    for right in ['P', 'C']:
                        try:
                            # Create option contract with proper parameters
                            option = Option(
                                symbol=symbol,
                                lastTradeDateOrContractMonth=expiry,
                                strike=strike,
                                right='PUT' if right == 'P' else 'CALL',
                                exchange='SMART',
                                currency='USD'
                            )

                            # Try to qualify the contract
                            qualified = await self.ib.qualifyContractsAsync(option)
                            if not qualified:
                                logger.debug(f"Contract not qualified: {symbol} {expiry} {strike} {right}")
                                continue

                            option = qualified[0]

                            # Request market data with snapshot
                            mt = self.ib.reqMktData(option, "", False, True)
                            await asyncio.sleep(0.05)  # Small delay

                            # Check if we got valid market data
                            if mt and (mt.bid or mt.ask or mt.last):
                                snapshot = {
                                    "strike": float(strike),
                                    "expiry": str(expiry),
                                    "right": 'CALL' if right == 'C' else 'PUT',
                                    "bid": float(mt.bid) if mt.bid else 0.0,
                                    "ask": float(mt.ask) if mt.ask else 0.0,
                                    "last": float(mt.last) if mt.last else 0.0,
                                    "volume": int(mt.volume) if hasattr(mt, 'volume') and mt.volume else 0,
                                    "open_interest": int(mt.openInterest) if hasattr(mt, 'openInterest') and mt.openInterest else 0,
                                }

                                # Add Greeks if available
                                if hasattr(mt, 'modelGreeks') and mt.modelGreeks:
                                    snapshot.update({
                                        "implied_vol": float(mt.modelGreeks.impliedVol) if mt.modelGreeks.impliedVol else 0.0,
                                        "delta": float(mt.modelGreeks.delta) if mt.modelGreeks.delta else 0.0,
                                        "gamma": float(mt.modelGreeks.gamma) if mt.modelGreeks.gamma else 0.0,
                                        "theta": float(mt.modelGreeks.theta) if mt.modelGreeks.theta else 0.0,
                                        "vega": float(mt.modelGreeks.vega) if mt.modelGreeks.vega else 0.0,
                                    })
                                else:
                                    snapshot.update({
                                        "implied_vol": 0.0, "delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0
                                    })

                                snapshots.append(snapshot)
                                logger.debug(f"✓ Got data: {symbol} {expiry} {strike} {right}")

                        except Exception as e:
                            if "Error 200" not in str(e):
                                logger.debug(f"Error for {symbol} {expiry} {strike} {right}: {e}")
                            continue

            logger.info(f"Collected {len(snapshots)} snapshots for {symbol}")
            return snapshots

        except Exception as e:
            logger.error(f"Error fetching option chains: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
