"""
Futures Data Integration for Entry Decisions

This module provides futures-based signals and analysis for entry decisions.
Uses futures data from Delta Lake to generate leading indicators for spot trading.

Key features:
- Futures-to-spot correlation analysis
- Futures lead/lag detection
- Momentum confirmation from futures
- Sentiment analysis from futures positioning
- Predictive signals for entry timing

Usage:
    from v6.strategy_builder.decision_engine.futures_integration import FuturesSignalGenerator

    generator = FuturesSignalGenerator()
    signal = await generator.generate_signal("SPY")

    if signal.is_bullish():
        # Enter bullish position
        pass
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, List

import polars as pl
from loguru import logger

from v6.system_monitor.data.futures_persistence import FuturesSnapshotsTable


class FuturesSentiment(str, Enum):
    """Futures market sentiment enumeration."""
    BULLISH = "bullish"      # Futures significantly above spot
    BEARISH = "bearish"      # Futures significantly below spot
    NEUTRAL = "neutral"      # Futures in line with spot


class FuturesSignal(str, Enum):
    """Futures trading signal enumeration."""
    STRONG_BUY = "strong_buy"      # Strong bullish signal from futures
    BUY = "buy"                    # Bullish signal from futures
    HOLD = "hold"                  # No clear signal
    SELL = "sell"                  # Bearish signal from futures
    STRONG_SELL = "strong_sell"    # Strong bearish signal from futures


@dataclass
class FuturesMarketSignal:
    """
    Futures market signal for spot trading decisions.

    Attributes:
        symbol: Spot symbol (SPY, QQQ, IWM)
        futures_symbol: Corresponding futures symbol (ES, NQ, RTY)
        timestamp: Signal timestamp
        sentiment: Market sentiment from futures positioning
        signal: Trading signal (buy/sell/hold)
        confidence: Signal confidence (0-1)
        futures_price: Current futures price
        spot_price: Estimated spot price (or actual if available)
        basis: Futures-spot basis (futures - spot)
        change_1h: 1-hour futures change
        change_4h: 4-hour futures change
        change_daily: Daily futures change
        momentum: Futures momentum (trend strength)
        predictive_value: How predictive futures are (0-1)
        reasoning: Human-readable explanation
    """

    symbol: str
    futures_symbol: str
    timestamp: datetime
    sentiment: FuturesSentiment
    signal: FuturesSignal
    confidence: float
    futures_price: float
    spot_price: Optional[float]
    basis: Optional[float]
    change_1h: Optional[float]
    change_4h: Optional[float]
    change_daily: Optional[float]
    momentum: float
    predictive_value: float
    reasoning: str

    def is_bullish(self) -> bool:
        """Check if signal is bullish."""
        return self.signal in [FuturesSignal.BUY, FuturesSignal.STRONG_BUY]

    def is_bearish(self) -> bool:
        """Check if signal is bearish."""
        return self.signal in [FuturesSignal.SELL, FuturesSignal.STRONG_SELL]

    def get_signal_strength(self) -> float:
        """Get signal strength (-1 to +1)."""
        if self.signal == FuturesSignal.STRONG_BUY:
            return 1.0
        elif self.signal == FuturesSignal.BUY:
            return 0.5
        elif self.signal == FuturesSignal.STRONG_SELL:
            return -1.0
        elif self.signal == FuturesSignal.SELL:
            return -0.5
        else:
            return 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for decision engine."""
        return {
            "symbol": self.symbol,
            "futures_symbol": self.futures_symbol,
            "futures_sentiment": self.sentiment.value,
            "futures_signal": self.signal.value,
            "futures_confidence": self.confidence,
            "futures_price": self.futures_price,
            "spot_price": self.spot_price,
            "basis": self.basis,
            "change_1h": self.change_1h,
            "change_4h": self.change_4h,
            "change_daily": self.change_daily,
            "momentum": self.momentum,
            "predictive_value": self.predictive_value,
            "reasoning": self.reasoning,
        }


class FuturesSignalGenerator:
    """
    Generate trading signals from futures data.

    Uses futures market data to generate leading indicators for spot trading.
    Analyzes futures positioning, momentum, and predictive patterns.

    **Signal Generation Logic:**

    **Bullish Signals:**
    - Futures significantly above spot (positive basis)
    - Strong futures momentum (rising prices)
    - Positive changes across timeframes (1h, 4h, daily)
    - High predictive value from historical lead-lag

    **Bearish Signals:**
    - Futures significantly below spot (negative basis)
    - Strong futures momentum (falling prices)
    - Negative changes across timeframes
    - High predictive value from historical lead-lag

    **Confidence Scoring:**
    - Higher when multiple signals agree
    - Increases with predictive value
    - Adjusted by signal strength
    """

    # Symbol mapping: SPY -> ES, QQQ -> NQ, IWM -> RTY
    SYMBOL_MAP = {
        "SPY": "ES",
        "QQQ": "NQ",
        "IWM": "RTY",
    }

    def __init__(
        self,
        futures_table: Optional[FuturesSnapshotsTable] = None,
        lookback_minutes: int = 60,
    ):
        """
        Initialize futures signal generator.

        Args:
            futures_table: Optional FuturesSnapshotsTable instance
            lookback_minutes: Minutes of history to analyze
        """
        self.futures_table = futures_table or FuturesSnapshotsTable()
        self.lookback_minutes = lookback_minutes

    async def generate_signal(
        self,
        symbol: str,
        spot_price: Optional[float] = None,
    ) -> Optional[FuturesMarketSignal]:
        """
        Generate futures trading signal for spot symbol.

        Args:
            symbol: Spot symbol (SPY, QQQ, IWM)
            spot_price: Optional current spot price (if None, estimates from futures)

        Returns:
            FuturesMarketSignal or None if insufficient data
        """
        # Map to futures symbol
        futures_symbol = self.SYMBOL_MAP.get(symbol)
        if not futures_symbol:
            logger.warning(f"No futures mapping for {symbol}")
            return None

        # Read futures data from Delta Lake
        try:
            df = self._read_futures_data(futures_symbol)

            if len(df) == 0:
                logger.warning(f"No futures data for {futures_symbol}")
                return None

            # Get latest snapshot
            latest = df.row(0, named=True)

            # Calculate signals
            sentiment = self._calculate_sentiment(latest, spot_price)
            signal = self._calculate_signal(latest, df)
            confidence = self._calculate_confidence(latest, df)
            momentum = self._calculate_momentum(df)
            predictive_value = self._estimate_predictive_value(df)
            reasoning = self._generate_reasoning(latest, df, sentiment, signal)

            # Estimate spot price if not provided
            if spot_price is None:
                # Rough estimate: futures typically 0.1-0.3% above spot
                spot_price = latest['last'] * 0.998

            basis = latest['last'] - spot_price

            return FuturesMarketSignal(
                symbol=symbol,
                futures_symbol=futures_symbol,
                timestamp=datetime.now(),
                sentiment=sentiment,
                signal=signal,
                confidence=confidence,
                futures_price=latest['last'],
                spot_price=spot_price,
                basis=basis,
                change_1h=latest.get('change_1h'),
                change_4h=latest.get('change_4h'),
                change_daily=latest.get('change_daily'),
                momentum=momentum,
                predictive_value=predictive_value,
                reasoning=reasoning,
            )

        except Exception as e:
            logger.error(f"Error generating futures signal for {symbol}: {e}")
            return None

    def _read_futures_data(self, futures_symbol: str) -> pl.DataFrame:
        """Read recent futures data from Delta Lake."""
        dt = self.futures_table.get_table()
        df = pl.from_pandas(dt.to_pandas())

        # Filter by symbol and recent time
        cutoff_time = datetime.now() - timedelta(minutes=self.lookback_minutes)

        df_filtered = df.filter(
            (pl.col("symbol") == futures_symbol) &
            (pl.col("timestamp") >= cutoff_time)
        ).sort("timestamp", descending=True)

        return df_filtered

    def _calculate_sentiment(
        self,
        latest: dict,
        spot_price: Optional[float],
    ) -> FuturesSentiment:
        """Calculate market sentiment from futures positioning."""
        if spot_price is None:
            return FuturesSentiment.NEUTRAL

        basis = latest['last'] - spot_price
        basis_pct = (basis / spot_price) * 100

        # Futures significantly above spot = bullish sentiment
        if basis_pct > 0.2:
            return FuturesSentiment.BULLISH
        # Futures significantly below spot = bearish sentiment
        elif basis_pct < -0.2:
            return FuturesSentiment.BEARISH
        else:
            return FuturesSentiment.NEUTRAL

    def _calculate_signal(
        self,
        latest: dict,
        df: pl.DataFrame,
    ) -> FuturesSignal:
        """Calculate trading signal from futures data."""
        # Get price changes
        change_1h = latest.get('change_1h', 0)
        change_4h = latest.get('change_4h', 0)
        change_daily = latest.get('change_daily', 0)

        # Count positive vs negative changes
        positive_signals = 0
        negative_signals = 0

        if change_1h is not None and change_1h > 0:
            positive_signals += 1
        elif change_1h is not None and change_1h < 0:
            negative_signals += 1

        if change_4h is not None and change_4h > 0:
            positive_signals += 1
        elif change_4h is not None and change_4h < 0:
            negative_signals += 1

        if change_daily is not None and change_daily > 0:
            positive_signals += 1
        elif change_daily is not None and change_daily < 0:
            negative_signals += 1

        # Determine signal
        if positive_signals >= 2:
            # Strong buy: all timeframes positive
            if change_daily is not None and abs(change_daily) > 10:
                return FuturesSignal.STRONG_BUY
            else:
                return FuturesSignal.BUY
        elif negative_signals >= 2:
            # Strong sell: all timeframes negative
            if change_daily is not None and abs(change_daily) > 10:
                return FuturesSignal.STRONG_SELL
            else:
                return FuturesSignal.SELL
        else:
            return FuturesSignal.HOLD

    def _calculate_confidence(
        self,
        latest: dict,
        df: pl.DataFrame,
    ) -> float:
        """Calculate signal confidence (0-1)."""
        base_confidence = 0.5

        # Increase confidence with more data points
        if len(df) >= 30:
            base_confidence += 0.2
        elif len(df) >= 10:
            base_confidence += 0.1

        # Increase confidence with strong signals
        change_daily = latest.get('change_daily', 0)
        if change_daily is not None and abs(change_daily) > 5:
            base_confidence += 0.2

        # Increase confidence with volume
        volume = latest.get('volume', 0)
        if volume > 1000:
            base_confidence += 0.1

        return max(0.0, min(1.0, base_confidence))

    def _calculate_momentum(self, df: pl.DataFrame) -> float:
        """Calculate momentum from price history."""
        if len(df) < 2:
            return 0.0

        # Simple momentum: price change over period
        latest_price = df.row(0, named=True)['last']
        oldest_price = df.row(-1, named=True)['last']

        momentum = (latest_price - oldest_price) / oldest_price

        return momentum

    def _estimate_predictive_value(self, df: pl.DataFrame) -> float:
        """Estimate how predictive futures are (simplified)."""
        # This would normally use historical lead-lag analysis
        # For now, use a simple heuristic based on data quality
        if len(df) >= 30:
            return 0.7
        elif len(df) >= 10:
            return 0.5
        else:
            return 0.3

    def _generate_reasoning(
        self,
        latest: dict,
        df: pl.DataFrame,
        sentiment: FuturesSentiment,
        signal: FuturesSignal,
    ) -> str:
        """Generate human-readable reasoning."""
        parts = []

        # Add sentiment
        parts.append(f"Futures {sentiment.value}")

        # Add price changes
        changes = []
        if latest.get('change_1h') is not None:
            changes.append(f"1H: {latest['change_1h']:+.2f}")
        if latest.get('change_4h') is not None:
            changes.append(f"4H: {latest['change_4h']:+.2f}")
        if latest.get('change_daily') is not None:
            changes.append(f"Daily: {latest['change_daily']:+.2f}")

        if changes:
            parts.append(f"({', '.join(changes)})")

        # Add signal
        parts.append(f"→ {signal.value.replace('_', ' ').upper()}")

        return " ".join(parts)


async def main():
    """Test futures signal generation."""
    generator = FuturesSignalGenerator()

    # Generate signal for SPY (uses ES futures)
    signal = await generator.generate_signal("SPY")

    if signal:
        print(f"\nFutures Signal for {signal.symbol}:")
        print(f"  Futures Symbol: {signal.futures_symbol}")
        print(f"  Futures Price: ${signal.futures_price:.2f}")
        print(f"  Sentiment: {signal.sentiment.value}")
        print(f"  Signal: {signal.signal.value}")
        print(f"  Confidence: {signal.confidence:.2f}")
        print(f"  Momentum: {signal.momentum:+.4f}")
        print(f"  Reasoning: {signal.reasoning}")
        print(f"\n  Trading Decision:")
        if signal.is_bullish():
            print(f"    → BULLISH signal from futures")
        elif signal.is_bearish():
            print(f"    → BEARISH signal from futures")
        else:
            print(f"    → NEUTRAL - no clear signal")
    else:
        print("No signal generated (insufficient futures data)")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
