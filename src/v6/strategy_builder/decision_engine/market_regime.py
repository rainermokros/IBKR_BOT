"""
Market Regime Detection Module

Analyzes market data to determine:
1. Market Outlook (Bullish, Bearish, Neutral/Sideways)
2. IV Level (High, Low)
3. Volatility Trend (Rising, Falling, Stable)

This regime detection drives strategy selection using the standard options
strategy matrix based on market outlook and implied volatility.

Usage:
    from v6.decisions.market_regime import MarketRegimeDetector

    detector = MarketRegimeDetector()
    regime = await detector.detect_regime(symbol="SPY")

    print(regime.outlook)  # "bullish" | "bearish" | "neutral"
    print(regime.iv_level)  # "high" | "low"
    print(regime.vol_trend)  # "rising" | "falling" | "stable"
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

import polars as pl
from loguru import logger


class MarketOutlook(str, Enum):
    """Market outlook/trend enumeration."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"  # Sideways/range-bound


class IVLevel(str, Enum):
    """Implied volatility level classification."""

    HIGH = "high"      # IV Rank > 50 (expensive options)
    LOW = "low"        # IV Rank < 50 (cheap options)
    EXTREME = "extreme"  # IV Rank > 75 (very expensive)


class VolTrend(str, Enum):
    """Volatility trend enumeration."""

    RISING = "rising"      # IV increasing
    FALLING = "falling"    # IV decreasing (IV crush)
    STABLE = "stable"      # IV stable


@dataclass
class MarketRegime:
    """
    Market regime classification.

    Attributes:
        symbol: Underlying symbol
        outlook: Market trend (bullish, bearish, neutral)
        iv_level: IV level (high, low, extreme)
        iv_rank: Current IV rank (0-100)
        vol_trend: Volatility trend (rising, falling, stable)
        vix: Current VIX value
        underlying_price: Current underlying price
        confidence: Confidence score (0-1) for this classification
        timestamp: When regime was detected
    """

    symbol: str
    outlook: MarketOutlook
    iv_level: IVLevel
    iv_rank: float
    vol_trend: VolTrend
    vix: float
    underlying_price: float
    confidence: float
    timestamp: datetime

    def __str__(self) -> str:
        """String representation of regime."""
        return (
            f"{self.symbol.upper()}: "
            f"{self.outlook.value.upper()}, "
            f"{self.iv_level.value.upper()} IV, "
            f"{self.vol_trend.value.upper()} vol "
            f"(IV rank: {self.iv_rank:.1f}, VIX: {self.vix:.2f})"
        )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "outlook": self.outlook.value,
            "iv_level": self.iv_level.value,
            "iv_rank": self.iv_rank,
            "vol_trend": self.vol_trend.value,
            "vix": self.vix,
            "underlying_price": self.underlying_price,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
        }


class MarketRegimeDetector:
    """
    Detect market regime from market data.

    **Detection Logic:**

    **Market Outlook (Bullish/Bearish/Neutral):**
    - Analyze price trend over multiple timeframes
    - Compare current price to moving averages
    - Calculate momentum indicators
    - Determine overall market direction

    **IV Level (High/Low):**
    - IV Rank > 50 → HIGH IV (expensive options, good for selling premium)
    - IV Rank < 50 → LOW IV (cheap options, good for buying premium)
    - IV Rank > 75 → EXTREME IV (very expensive, extreme caution)

    **Volatility Trend:**
    - Compare current IV to historical IV
    - Calculate IV change over recent period
    - Classify as rising/falling/stable

    **Attributes:**
        lookback_days: Days of historical data to analyze
        short_ma: Short moving average period (days)
        long_ma: Long moving average period (days)
        iv_high_threshold: IV rank threshold for HIGH IV (default: 50)
    """

    def __init__(
        self,
        lookback_days: int = 20,
        short_ma: int = 5,
        long_ma: int = 20,
        iv_high_threshold: float = 50.0,
    ):
        """
        Initialize market regime detector.

        Args:
            lookback_days: Days of historical data for analysis
            short_ma: Short MA period for trend detection
            long_ma: Long MA period for trend detection
            iv_high_threshold: IV rank threshold for HIGH IV classification
        """
        self.lookback_days = lookback_days
        self.short_ma = short_ma
        self.long_ma = long_ma
        self.iv_high_threshold = iv_high_threshold

    async def detect_regime(
        self,
        symbol: str,
        current_iv_rank: float,
        current_vix: float,
        underlying_price: float,
        historical_data: Optional[pl.DataFrame] = None,
    ) -> MarketRegime:
        """
        Detect market regime from current and historical data.

        Args:
            symbol: Underlying symbol (e.g., "SPY")
            current_iv_rank: Current IV rank (0-100)
            current_vix: Current VIX value
            underlying_price: Current underlying price
            historical_data: Optional DataFrame with columns:
                - timestamp: DateTime
                - close: Close price
                - iv_rank: IV rank
                - vix: VIX value
                - iv: Implied volatility

        Returns:
            MarketRegime with outlook, iv_level, and vol_trend
        """
        logger.debug(f"Detecting market regime for {symbol}")

        # Detect market outlook (bullish/bearish/neutral)
        outlook = self._detect_outlook(
            underlying_price,
            historical_data
        )

        # Classify IV level
        iv_level = self._classify_iv_level(current_iv_rank)

        # Detect volatility trend
        vol_trend = self._detect_vol_trend(
            current_iv_rank,
            historical_data
        )

        # Calculate confidence based on data quality and signal strength
        confidence = self._calculate_confidence(
            outlook,
            iv_level,
            historical_data
        )

        regime = MarketRegime(
            symbol=symbol,
            outlook=outlook,
            iv_level=iv_level,
            iv_rank=current_iv_rank,
            vol_trend=vol_trend,
            vix=current_vix,
            underlying_price=underlying_price,
            confidence=confidence,
            timestamp=datetime.now(),
        )

        logger.info(f"Regime detected: {regime}")

        return regime

    def _detect_outlook(
        self,
        current_price: float,
        historical_data: Optional[pl.DataFrame],
    ) -> MarketOutlook:
        """
        Detect market outlook from price trend analysis.

        Uses multiple indicators:
        - Moving average crossover (short MA vs long MA)
        - Price momentum (change over lookback period)
        - Position relative to recent range

        Args:
            current_price: Current underlying price
            historical_data: Historical price data

        Returns:
            MarketOutlook (bullish, bearish, or neutral)
        """
        if historical_data is None or historical_data.is_empty():
            logger.warning("No historical data, defaulting to NEUTRAL")
            return MarketOutlook.NEUTRAL

        try:
            # Calculate moving averages
            df = historical_data.with_columns(
                pl.col("close").cast(pl.Float64)
            ).sort("timestamp")

            # Short and long moving averages
            short_ma_val = df["close"].tail(self.short_ma).mean()
            long_ma_val = df["close"].tail(self.long_ma).mean()

            # Current price position
            price_vs_short_ma = (current_price - short_ma_val) / short_ma_val
            price_vs_long_ma = (current_price - long_ma_val) / long_ma_val

            # Price momentum (change over lookback)
            price_change = (current_price - df["close"].tail(self.lookback_days).first()) / df["close"].tail(self.lookback_days).first()

            # Determine outlook
            # Bullish: Price above both MAs and positive momentum
            if current_price > short_ma_val and current_price > long_ma_val and price_change > 0.01:
                logger.debug(f"Bullish: price=${current_price:.2f} > MA_short=${short_ma_val:.2f}, MA_long=${long_ma_val:.2f}, momentum={price_change:+.2%}")
                return MarketOutlook.BULLISH

            # Bearish: Price below both MAs and negative momentum
            elif current_price < short_ma_val and current_price < long_ma_val and price_change < -0.01:
                logger.debug(f"Bearish: price=${current_price:.2f} < MA_short=${short_ma_val:.2f}, MA_long=${long_ma_val:.2f}, momentum={price_change:+.2%}")
                return MarketOutlook.BEARISH

            # Neutral: Price between MAs or sideways movement
            else:
                logger.debug(f"Neutral: price=${current_price:.2f}, MA_short=${short_ma_val:.2f}, MA_long=${long_ma_val:.2f}, momentum={price_change:+.2%}")
                return MarketOutlook.NEUTRAL

        except Exception as e:
            logger.error(f"Error detecting outlook: {e}")
            return MarketOutlook.NEUTRAL

    def _classify_iv_level(self, iv_rank: float) -> IVLevel:
        """
        Classify IV level from IV rank.

        Args:
            iv_rank: IV rank (0-100 percentile)

        Returns:
            IVLevel (high, low, or extreme)
        """
        if iv_rank > 75:
            return IVLevel.EXTREME
        elif iv_rank > self.iv_high_threshold:
            return IVLevel.HIGH
        else:
            return IVLevel.LOW

    def _detect_vol_trend(
        self,
        current_iv_rank: float,
        historical_data: Optional[pl.DataFrame],
    ) -> VolTrend:
        """
        Detect volatility trend from IV rank history.

        Compares current IV to historical IV to determine if volatility
        is rising, falling, or stable.

        Args:
            current_iv_rank: Current IV rank
            historical_data: Historical data with iv_rank column

        Returns:
            VolTrend (rising, falling, or stable)
        """
        if historical_data is None or historical_data.is_empty():
            logger.warning("No historical data, defaulting to STABLE")
            return VolTrend.STABLE

        try:
            # Get historical IV ranks
            if "iv_rank" not in historical_data.columns:
                return VolTrend.STABLE

            df = historical_data.sort("timestamp")
            historical_iv = df["iv_rank"].tail(self.lookback_days)

            if historical_iv.is_empty():
                return VolTrend.STABLE

            # Calculate average historical IV rank
            avg_historical_iv = historical_iv.mean()

            # Compare current to historical
            iv_change = current_iv_rank - avg_historical_iv

            # Classify trend
            # Rising: IV is significantly higher than historical
            if iv_change > 10:
                logger.debug(f"VOLATILITY RISING: current IV rank {current_iv_rank:.1f} > historical avg {avg_historical_iv:.1f} (+{iv_change:.1f})")
                return VolTrend.RISING

            # Falling: IV is significantly lower than historical
            elif iv_change < -10:
                logger.debug(f"VOLATILITY FALLING: current IV rank {current_iv_rank:.1f} < historical avg {avg_historical_iv:.1f} ({iv_change:.1f})")
                return VolTrend.FALLING

            # Stable: IV is within normal range
            else:
                logger.debug(f"VOLATILITY STABLE: current IV rank {current_iv_rank:.1f} ~ historical avg {avg_historical_iv:.1f} ({iv_change:+.1f})")
                return VolTrend.STABLE

        except Exception as e:
            logger.error(f"Error detecting vol trend: {e}")
            return VolTrend.STABLE

    def _calculate_confidence(
        self,
        outlook: MarketOutlook,
        iv_level: IVLevel,
        historical_data: Optional[pl.DataFrame],
    ) -> float:
        """
        Calculate confidence score for regime detection.

        Higher confidence when:
        - Strong signals (clear trends, extreme IV)
        - More historical data available
        - Consistent indicators

        Args:
            outlook: Detected market outlook
            iv_level: Detected IV level
            historical_data: Historical data for validation

        Returns:
            Confidence score (0.0 to 1.0)
        """
        confidence = 0.5  # Base confidence

        # Increase confidence for extreme IV levels
        if iv_level == IVLevel.EXTREME:
            confidence += 0.2
        elif iv_level == IVLevel.HIGH:
            confidence += 0.1

        # Increase confidence for strong directional signals
        if outlook != MarketOutlook.NEUTRAL:
            confidence += 0.1

        # Increase confidence if we have historical data
        if historical_data is not None and len(historical_data) > self.lookback_days:
            confidence += 0.1

        # Clamp to 0-1 range
        return max(0.0, min(1.0, confidence))


async def main():
    """Test market regime detection."""
    detector = MarketRegimeDetector()

    # Example: Bullish market with high IV
    regime_bullish_high_iv = await detector.detect_regime(
        symbol="SPY",
        current_iv_rank=65.0,
        current_vix=28.0,
        underlying_price=480.0,
        historical_data=None,  # Would pass real data here
    )

    print(f"\n{regime_bullish_high_iv}")

    # Example: Bearish market with low IV
    regime_bearish_low_iv = await detector.detect_regime(
        symbol="SPY",
        current_iv_rank=30.0,
        current_vix=14.0,
        underlying_price=440.0,
        historical_data=None,
    )

    print(f"{regime_bearish_low_iv}\n")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
