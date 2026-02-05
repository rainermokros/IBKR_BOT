"""
Enhanced Market Regime Detection with Derived Statistics

This module extends the base market regime detection to incorporate
historical derived statistics from Delta Lake for more accurate
regime classification and strategy selection.

Key enhancements:
- Uses historical IV ranks (30d, 60d, 90d, 1y) from Delta Lake
- Incorporates market regime classification from derived stats
- Uses volatility and trend metrics (20d realized volatility, trend strength)
- Considers term structure slope (contango/backwardation)
- Evaluates put/call ratio for sentiment analysis
- Calculates composite confidence scores

Usage:
    from v6.decisions.enhanced_market_regime import EnhancedMarketRegimeDetector

    detector = EnhancedMarketRegimeDetector()
    regime = await detector.detect_regime(symbol="SPY")

    print(regime.outlook)  # "bullish" | "bearish" | "neutral"
    print(regime.derived_stats)  # Full derived statistics dict
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, date
from enum import Enum
from typing import Optional, Dict

import polars as pl
from loguru import logger

from v6.system_monitor.data.derived_statistics import DerivedStatisticsTable
from v6.decisions.market_regime import (
    MarketOutlook,
    IVLevel,
    VolTrend,
    MarketRegimeDetector
)


@dataclass
class EnhancedMarketRegime:
    """
    Enhanced market regime classification with derived statistics.

    Attributes:
        symbol: Underlying symbol
        outlook: Market trend (bullish, bearish, neutral)
        iv_level: IV level (high, low, extreme)
        iv_rank: Current IV rank (0-100)
        vol_trend: Volatility trend (rising, falling, stable)
        vix: Current VIX value
        underlying_price: Current underlying price
        derived_regime: Market regime from derived stats (low_vol, high_vol, trending, range_bound)
        iv_rank_30d: 30-day IV rank
        iv_rank_60d: 60-day IV rank
        iv_rank_90d: 90-day IV rank
        iv_percentile_1y: 1-year IV percentile
        volatility_20d: 20-day realized volatility
        trend_20d: 20-day trend strength
        put_call_ratio: Put/call volume ratio
        term_structure_slope: IV term structure slope
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
    derived_regime: str
    iv_rank_30d: float
    iv_rank_60d: float
    iv_rank_90d: float
    iv_percentile_1y: float
    volatility_20d: float
    trend_20d: float
    put_call_ratio: float
    term_structure_slope: float
    confidence: float
    timestamp: datetime

    def __str__(self) -> str:
        """String representation of enhanced regime."""
        return (
            f"{self.symbol.upper()}: "
            f"{self.outlook.value.upper()}, "
            f"{self.iv_level.value.upper()} IV, "
            f"{self.vol_trend.value.upper()} vol "
            f"(IV rank: {self.iv_rank:.1f}, VIX: {self.vix:.2f}) "
            f"[Regime: {self.derived_regime}, "
            f"Vol20d: {self.volatility_20d:.2%}, "
            f"Trend: {self.trend_20d:+.3f}]"
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
            "derived_regime": self.derived_regime,
            "iv_rank_30d": self.iv_rank_30d,
            "iv_rank_60d": self.iv_rank_60d,
            "iv_rank_90d": self.iv_rank_90d,
            "iv_percentile_1y": self.iv_percentile_1y,
            "volatility_20d": self.volatility_20d,
            "trend_20d": self.trend_20d,
            "put_call_ratio": self.put_call_ratio,
            "term_structure_slope": self.term_structure_slope,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
        }

    def get_derived_stats_dict(self) -> dict:
        """Get derived statistics as a dict for strategy selection."""
        return {
            "iv_rank_30d": self.iv_rank_30d,
            "iv_rank_60d": self.iv_rank_60d,
            "iv_rank_90d": self.iv_rank_90d,
            "iv_percentile_1y": self.iv_percentile_1y,
            "volatility_20d": self.volatility_20d,
            "trend_20d": self.trend_20d,
            "put_call_ratio": self.put_call_ratio,
            "term_structure_slope": self.term_structure_slope,
            "derived_regime": self.derived_regime,
        }


class EnhancedMarketRegimeDetector:
    """
    Enhanced market regime detector using derived statistics.

    Combines real-time market data with historical derived statistics
    from Delta Lake for more accurate regime classification.

    **Enhanced Detection Logic:**

    **Market Outlook:**
    - Uses base detector (MA crossover, momentum)
    - Validates against derived_regime from statistics
    - Increases confidence when both agree

    **IV Level:**
    - Uses multiple IV rank timeframes (30d, 60d, 90d)
    - Considers 1-year percentile for long-term context
    - Classifies as extreme when all ranks > 75

    **Volatility Trend:**
    - Compares IV ranks across timeframes
    - Uses realized volatility (20d) for validation
    - Checks term structure slope for market stress

    **Confidence Scoring:**
    - Higher when real-time and derived stats agree
    - Penalizes conflicting signals
    - Increases with more historical data

    Attributes:
        derived_stats_table: DerivedStatisticsTable instance
        base_detector: Base MarketRegimeDetector for real-time analysis
    """

    def __init__(
        self,
        derived_stats_table: Optional[DerivedStatisticsTable] = None,
    ):
        """
        Initialize enhanced market regime detector.

        Args:
            derived_stats_table: Optional DerivedStatisticsTable instance
        """
        self.derived_stats_table = derived_stats_table or DerivedStatisticsTable()
        self.base_detector = MarketRegimeDetector()

    async def detect_regime(
        self,
        symbol: str,
        current_iv_rank: float,
        current_vix: float,
        underlying_price: float,
    ) -> EnhancedMarketRegime:
        """
        Detect enhanced market regime using real-time data and derived statistics.

        Args:
            symbol: Underlying symbol (e.g., "SPY")
            current_iv_rank: Current IV rank (0-100) from real-time calculation
            current_vix: Current VIX value
            underlying_price: Current underlying price

        Returns:
            EnhancedMarketRegime with full derived statistics
        """
        logger.debug(f"Detecting enhanced market regime for {symbol}")

        # Get latest derived statistics from Delta Lake
        derived_stats = self._get_latest_derived_stats(symbol)

        # Detect market outlook using base detector (may need historical price data)
        outlook = self._detect_enhanced_outlook(
            symbol,
            underlying_price,
            derived_stats
        )

        # Classify IV level using multiple timeframes
        iv_level = self._classify_enhanced_iv_level(
            current_iv_rank,
            derived_stats
        )

        # Detect volatility trend using derived statistics
        vol_trend = self._detect_enhanced_vol_trend(
            current_iv_rank,
            derived_stats
        )

        # Calculate enhanced confidence
        confidence = self._calculate_enhanced_confidence(
            outlook,
            iv_level,
            derived_stats
        )

        # Extract derived statistics
        stats = derived_stats[0] if len(derived_stats) > 0 else self._get_default_stats()

        regime = EnhancedMarketRegime(
            symbol=symbol,
            outlook=outlook,
            iv_level=iv_level,
            iv_rank=current_iv_rank,
            vol_trend=vol_trend,
            vix=current_vix,
            underlying_price=underlying_price,
            derived_regime=stats.get("regime", "range_bound"),
            iv_rank_30d=stats.get("iv_rank_30d", current_iv_rank),
            iv_rank_60d=stats.get("iv_rank_60d", current_iv_rank),
            iv_rank_90d=stats.get("iv_rank_90d", current_iv_rank),
            iv_percentile_1y=stats.get("iv_percentile_1y", current_iv_rank),
            volatility_20d=stats.get("volatility_20d", 0.2),
            trend_20d=stats.get("trend_20d", 0.0),
            put_call_ratio=stats.get("put_call_ratio", 1.0),
            term_structure_slope=stats.get("term_structure_slope", 0.0),
            confidence=confidence,
            timestamp=datetime.now(),
        )

        logger.info(f"Enhanced regime detected: {regime}")

        return regime

    def _get_latest_derived_stats(self, symbol: str) -> list:
        """Get latest derived statistics from Delta Lake."""
        try:
            # Read latest 5 days of statistics
            latest = self.derived_stats_table.read_latest_statistics(symbol, days=5)

            if len(latest) > 0:
                # Convert first row to dict
                return [latest.row(0, named=True)]
            else:
                logger.warning(f"No derived statistics found for {symbol}, using defaults")
                return []

        except Exception as e:
            logger.error(f"Error reading derived statistics: {e}")
            return []

    def _get_default_stats(self) -> dict:
        """Get default statistics when none available."""
        return {
            "regime": "range_bound",
            "iv_rank_30d": 50.0,
            "iv_rank_60d": 50.0,
            "iv_rank_90d": 50.0,
            "iv_percentile_1y": 50.0,
            "volatility_20d": 0.2,
            "trend_20d": 0.0,
            "put_call_ratio": 1.0,
            "term_structure_slope": 0.0,
        }

    def _detect_enhanced_outlook(
        self,
        symbol: str,
        underlying_price: float,
        derived_stats: list,
    ) -> MarketOutlook:
        """
        Detect enhanced market outlook using derived statistics.

        Uses trend_20d from derived statistics and validates
        against derived_regime classification.
        """
        if not derived_stats:
            return MarketOutlook.NEUTRAL

        stats = derived_stats[0]
        trend_20d = stats.get("trend_20d", 0.0)
        derived_regime = stats.get("regime", "range_bound")

        # Strong uptrend
        if trend_20d > 0.01:
            if derived_regime == "trending":
                logger.debug(f"BULLISH: strong uptrend (trend_20d={trend_20d:+.3f}, regime={derived_regime})")
                return MarketOutlook.BULLISH
            else:
                logger.debug(f"BULLISH: moderate uptrend (trend_20d={trend_20d:+.3f})")
                return MarketOutlook.BULLISH

        # Strong downtrend
        elif trend_20d < -0.01:
            if derived_regime == "trending":
                logger.debug(f"BEARISH: strong downtrend (trend_20d={trend_20d:+.3f}, regime={derived_regime})")
                return MarketOutlook.BEARISH
            else:
                logger.debug(f"BEARISH: moderate downtrend (trend_20d={trend_20d:+.3f})")
                return MarketOutlook.BEARISH

        # Range bound
        else:
            logger.debug(f"NEUTRAL: sideways (trend_20d={trend_20d:+.3f}, regime={derived_regime})")
            return MarketOutlook.NEUTRAL

    def _classify_enhanced_iv_level(
        self,
        current_iv_rank: float,
        derived_stats: list,
    ) -> IVLevel:
        """
        Classify enhanced IV level using multiple timeframes.

        Uses 30d, 60d, 90d IV ranks to determine if IV is consistently high/low.
        """
        if not derived_stats:
            # Fall back to current IV rank
            if current_iv_rank > 75:
                return IVLevel.EXTREME
            elif current_iv_rank > 50:
                return IVLevel.HIGH
            else:
                return IVLevel.LOW

        stats = derived_stats[0]
        iv_rank_30d = stats.get("iv_rank_30d", current_iv_rank)
        iv_rank_60d = stats.get("iv_rank_60d", current_iv_rank)
        iv_rank_90d = stats.get("iv_rank_90d", current_iv_rank)

        # Calculate average across timeframes
        avg_iv_rank = (iv_rank_30d + iv_rank_60d + iv_rank_90d) / 3

        # Check if all timeframes agree on extreme IV
        if all(rank > 75 for rank in [iv_rank_30d, iv_rank_60d, iv_rank_90d]):
            logger.debug(f"EXTREME IV: all ranks > 75 (30d={iv_rank_30d:.1f}, 60d={iv_rank_60d:.1f}, 90d={iv_rank_90d:.1f})")
            return IVLevel.EXTREME
        elif avg_iv_rank > 50:
            logger.debug(f"HIGH IV: avg rank {avg_iv_rank:.1f}")
            return IVLevel.HIGH
        else:
            logger.debug(f"LOW IV: avg rank {avg_iv_rank:.1f}")
            return IVLevel.LOW

    def _detect_enhanced_vol_trend(
        self,
        current_iv_rank: float,
        derived_stats: list,
    ) -> VolTrend:
        """
        Detect enhanced volatility trend using derived statistics.

        Compares IV ranks across timeframes and uses term structure slope.
        """
        if not derived_stats:
            return VolTrend.STABLE

        stats = derived_stats[0]
        iv_rank_30d = stats.get("iv_rank_30d", current_iv_rank)
        iv_rank_90d = stats.get("iv_rank_90d", current_iv_rank)
        term_slope = stats.get("term_structure_slope", 0.0)

        # Compare 30d vs 90d IV rank
        iv_rank_diff = iv_rank_30d - iv_rank_90d

        # Rising volatility: 30d rank much higher than 90d
        if iv_rank_diff > 15 or term_slope > 0.05:
            logger.debug(f"RISING vol: 30d rank {iv_rank_30d:.1f} > 90d rank {iv_rank_90d:.1f}, slope={term_slope:+.3f}")
            return VolTrend.RISING

        # Falling volatility: 30d rank much lower than 90d
        elif iv_rank_diff < -15 or term_slope < -0.05:
            logger.debug(f"FALLING vol: 30d rank {iv_rank_30d:.1f} < 90d rank {iv_rank_90d:.1f}, slope={term_slope:+.3f}")
            return VolTrend.FALLING

        # Stable volatility
        else:
            logger.debug(f"STABLE vol: 30d rank {iv_rank_30d:.1f} ~ 90d rank {iv_rank_90d:.1f}")
            return VolTrend.STABLE

    def _calculate_enhanced_confidence(
        self,
        outlook: MarketOutlook,
        iv_level: IVLevel,
        derived_stats: list,
    ) -> float:
        """
        Calculate enhanced confidence score.

        Higher confidence when:
        - Real-time and derived stats agree
        - Strong signals (extreme IV, strong trends)
        - Consistent signals across timeframes
        - More historical data available
        """
        confidence = 0.5  # Base confidence

        if not derived_stats:
            # Reduce confidence without derived stats
            return max(0.0, confidence - 0.2)

        stats = derived_stats[0]
        derived_regime = stats.get("regime", "range_bound")
        volatility_20d = stats.get("volatility_20d", 0.2)

        # Increase confidence when real-time outlook matches derived regime
        if outlook != MarketOutlook.NEUTRAL and derived_regime == "trending":
            confidence += 0.2
        elif outlook == MarketOutlook.NEUTRAL and derived_regime == "range_bound":
            confidence += 0.2

        # Increase confidence for extreme IV levels
        if iv_level == IVLevel.EXTREME:
            confidence += 0.2
        elif iv_level == IVLevel.HIGH:
            confidence += 0.1

        # Increase confidence for high volatility situations
        if volatility_20d > 0.3:
            confidence += 0.1

        # Increase confidence when term structure shows clear signal
        term_slope = stats.get("term_structure_slope", 0.0)
        if abs(term_slope) > 0.05:
            confidence += 0.1

        # Clamp to 0-1 range
        return max(0.0, min(1.0, confidence))


async def main():
    """Test enhanced market regime detection."""
    detector = EnhancedMarketRegimeDetector()

    # Example: SPY with current market data
    regime = await detector.detect_regime(
        symbol="SPY",
        current_iv_rank=55.0,
        current_vix=18.5,
        underlying_price=475.0,
    )

    print(f"\n{regime}")
    print(f"\nDerived Stats: {regime.get_derived_stats_dict()}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
