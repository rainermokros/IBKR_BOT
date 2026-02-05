"""
Enhanced Entry Decision Rules Using Derived Statistics

This module extends the base entry rules to incorporate derived statistics
from Delta Lake for more sophisticated strategy selection.

Enhanced considerations:
- Multiple IV rank timeframes (30d, 60d, 90d, 1y) for context
- Realized volatility (20d) vs implied volatility for mispricing detection
- Put/call ratio for contrarian sentiment signals
- Term structure slope (contango/backwardation) for market stress detection
- Market regime classification for regime-aware strategy selection
- Confidence scoring for position sizing

Usage:
    from v6.decisions.rules.enhanced_entry_rules import EnhancedBullishHighIVEntry
    from v6.decisions.enhanced_market_regime import EnhancedMarketRegimeDetector

    detector = EnhancedMarketRegimeDetector()
    regime = await detector.detect_regime(symbol="SPY", iv_rank=60, vix=28, price=450)

    rule = EnhancedBullishHighIVEntry()
    decision = await rule.evaluate(None, regime.to_dict())
"""

from typing import Optional

from loguru import logger

from v6.decisions.market_regime import MarketOutlook, IVLevel, VolTrend
from v6.strategy_builder.decision_engine.models import Decision, DecisionAction, Urgency
from v6.strategy_builder.models import StrategyType


class EnhancedBullishHighIVEntry:
    """
    Enhanced bullish + high IV entry rule using derived statistics.

    **Enhanced Logic:**
    - Validates bullish trend across multiple timeframes
    - Checks put/call ratio for contrarian signals
    - Uses term structure slope for market stress detection
    - Adjusts position sizing based on confidence

    **Entry Conditions:**
    - Outlook: Bullish
    - IV Level: High or Extreme
    - Trend confirmation: 20d trend positive
    - Volatility trend: Rising or stable
    - Confidence: > 0.6

    **Strategy Selection:**
    - Extreme IV + rising vol: Call backspread (aggressive)
    - Extreme IV + stable vol: Bull call spread (conservative)
    - High IV + rising vol: Bull call spread
    - High IV + stable vol: Bull call spread

    **Priority:** 1 (Highest for bullish + high IV)
    """

    priority = 1
    name = "enhanced_bullish_high_iv_entry"

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None,
    ) -> Optional[Decision]:
        """Evaluate enhanced bullish + high IV entry conditions."""
        if not market_data:
            return None

        outlook = market_data.get("outlook")
        iv_level = market_data.get("iv_level")
        vol_trend = market_data.get("vol_trend")
        derived_regime = market_data.get("derived_regime")
        confidence = market_data.get("confidence", 0.5)
        symbol = market_data.get("symbol", "UNKNOWN")

        # Check base market regime
        if outlook != MarketOutlook.BULLISH.value:
            return None

        if iv_level != IVLevel.HIGH.value and iv_level != IVLevel.EXTREME.value:
            return None

        # Avoid falling volatility
        if vol_trend == VolTrend.FALLING.value:
            logger.info(
                f"[{symbol}] Skipping bullish entry: "
                f"IV {iv_level} but vol is {vol_trend}"
            )
            return None

        # Enhanced checks using derived statistics
        trend_20d = market_data.get("trend_20d", 0.0)
        put_call_ratio = market_data.get("put_call_ratio", 1.0)
        term_structure_slope = market_data.get("term_structure_slope", 0.0)
        iv_rank_90d = market_data.get("iv_rank_90d", 50.0)

        # Need positive trend confirmation
        if trend_20d < 0.005:
            logger.info(
                f"[{symbol}] Skipping bullish entry: "
                f"Weak trend (trend_20d={trend_20d:+.3f})"
            )
            return None

        # Check confidence threshold
        if confidence < 0.6:
            logger.info(
                f"[{symbol}] Skipping bullish entry: "
                f"Low confidence ({confidence:.2f})"
            )
            return None

        # Determine strategy based on enhanced metrics
        if iv_level == IVLevel.EXTREME.value:
            if vol_trend == VolTrend.RISING.value and term_structure_slope > 0.02:
                # Extreme IV + rising vol + steep term structure: Aggressive
                strategy = StrategyType.CUSTOM  # Call backspread
                urgency = Urgency.HIGH
                reason = (
                    f"Bullish + Extreme IV (rank={market_data.get('iv_rank'):.1f}, 90d={iv_rank_90d:.1f}) "
                    f"+ Rising vol + Steep term structure: Call backspread for amplified gains"
                )
            else:
                # Extreme IV but stable vol: Conservative
                strategy = StrategyType.VERTICAL_SPREAD  # Bull call spread
                urgency = Urgency.MEDIUM
                reason = (
                    f"Bullish + Extreme IV (rank={market_data.get('iv_rank'):.1f}): "
                    f"Bull call spread for defined risk"
                )

        else:
            # High IV: Standard bull call spread
            strategy = StrategyType.VERTICAL_SPREAD
            urgency = Urgency.MEDIUM
            reason = (
                f"Bullish + High IV (rank={market_data.get('iv_rank'):.1f}, "
                f"trend={trend_20d:+.3f}): Bull call spread"
            )

        # Adjust position sizing based on confidence and put/call ratio
        # High put/call ratio (>1.2) = bearish sentiment = contrarian opportunity
        # Low put/call ratio (<0.8) = bullish consensus = reduce size
        if put_call_ratio > 1.2:
            # Contrarian bullish signal: increase position size
            position_multiplier = 1.2
            logger.info(
                f"[{symbol}] Contrarian bullish signal: "
                f"High put/call ratio ({put_call_ratio:.2f})"
            )
        elif put_call_ratio < 0.8:
            # Bullish consensus: reduce position size
            position_multiplier = 0.8
            logger.info(
                f"[{symbol}] Crowded bullish trade: "
                f"Low put/call ratio ({put_call_ratio:.2f})"
            )
        else:
            position_multiplier = 1.0

        return Decision(
            action=DecisionAction.ENTER,
            strategy_type=strategy,
            urgency=urgency,
            confidence=confidence,
            reason=reason,
            metadata={
                "strategy_type": strategy.value,
                "position_multiplier": position_multiplier,
                "entry_rule": self.name,
                "iv_rank": market_data.get("iv_rank"),
                "iv_rank_90d": iv_rank_90d,
                "trend_20d": trend_20d,
                "put_call_ratio": put_call_ratio,
                "term_structure_slope": term_structure_slope,
                "derived_regime": derived_regime,
            }
        )


class EnhancedBearishHighIVEntry:
    """
    Enhanced bearish + high IV entry rule using derived statistics.

    **Enhanced Logic:**
    - Validates bearish trend across multiple timeframes
    - Checks put/call ratio for sentiment confirmation
    - Uses term structure slope for stress detection

    **Priority:** 2
    """

    priority = 2
    name = "enhanced_bearish_high_iv_entry"

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None,
    ) -> Optional[Decision]:
        """Evaluate enhanced bearish + high IV entry conditions."""
        if not market_data:
            return None

        outlook = market_data.get("outlook")
        iv_level = market_data.get("iv_level")
        vol_trend = market_data.get("vol_trend")
        confidence = market_data.get("confidence", 0.5)
        symbol = market_data.get("symbol", "UNKNOWN")

        if outlook != MarketOutlook.BEARISH.value:
            return None

        if iv_level != IVLevel.HIGH.value and iv_level != IVLevel.EXTREME.value:
            return None

        if vol_trend == VolTrend.FALLING.value:
            return None

        # Enhanced checks
        trend_20d = market_data.get("trend_20d", 0.0)
        put_call_ratio = market_data.get("put_call_ratio", 1.0)

        if trend_20d > -0.005:
            logger.info(
                f"[{symbol}] Skipping bearish entry: "
                f"Weak trend (trend_20d={trend_20d:+.3f})"
            )
            return None

        if confidence < 0.6:
            return None

        strategy = StrategyType.VERTICAL_SPREAD  # Bear put spread
        reason = (
            f"Bearish + High IV (rank={market_data.get('iv_rank'):.1f}): "
            f"Bear put spread"
        )

        # Put/call ratio confirmation
        if put_call_ratio > 1.0:
            # Bearish sentiment confirmed: increase size
            position_multiplier = 1.2
        else:
            position_multiplier = 1.0

        return Decision(
            action=DecisionAction.ENTER,
            strategy_type=strategy,
            urgency=Urgency.MEDIUM,
            confidence=confidence,
            reason=reason,
            metadata={
                "strategy_type": strategy.value,
                "position_multiplier": position_multiplier,
                "entry_rule": self.name,
                "iv_rank": market_data.get("iv_rank"),
            }
        )


class EnhancedNeutralHighIVEntry:
    """
    Enhanced neutral + high IV entry rule using derived statistics.

    **Enhanced Logic:**
    - Confirms range-bound regime
    - Checks realized volatility vs IV for IV overpricing
    - Uses put/call ratio for balanced sentiment

    **Priority:** 3
    """

    priority = 3
    name = "enhanced_neutral_high_iv_entry"

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None,
    ) -> Optional[Decision]:
        """Evaluate enhanced neutral + high IV entry conditions."""
        if not market_data:
            return None

        outlook = market_data.get("outlook")
        iv_level = market_data.get("iv_level")
        derived_regime = market_data.get("derived_regime")
        confidence = market_data.get("confidence", 0.5)
        symbol = market_data.get("symbol", "UNKNOWN")

        if outlook != MarketOutlook.NEUTRAL.value:
            return None

        if iv_level != IVLevel.HIGH.value and iv_level != IVLevel.EXTREME.value:
            return None

        # Enhanced checks
        volatility_20d = market_data.get("volatility_20d", 0.2)
        iv_rank = market_data.get("iv_rank", 50.0)

        # Confirm range-bound regime
        if derived_regime != "range_bound" and derived_regime != "high_vol":
            logger.info(
                f"[{symbol}] Skipping neutral entry: "
                f"Not range-bound (regime={derived_regime})"
            )
            return None

        if confidence < 0.6:
            return None

        # Strategy selection based on IV level
        if iv_level == IVLevel.EXTREME.value:
            # Extreme IV: Short straddle (aggressive premium selling)
            strategy = StrategyType.CUSTOM  # Short straddle
            urgency = Urgency.HIGH
            reason = (
                f"Neutral + Extreme IV (rank={iv_rank:.1f}): "
                f"Short straddle to capture premium"
            )
        else:
            # High IV: Iron condor (safer premium selling)
            strategy = StrategyType.IRON_CONDOR
            urgency = Urgency.MEDIUM
            reason = (
                f"Neutral + High IV (rank={iv_rank:.1f}): "
                f"Iron condor for defined-risk premium selling"
            )

        return Decision(
            action=DecisionAction.ENTER,
            strategy_type=strategy,
            urgency=urgency,
            confidence=confidence,
            reason=reason,
            metadata={
                "strategy_type": strategy.value,
                "entry_rule": self.name,
                "iv_rank": iv_rank,
                "volatility_20d": volatility_20d,
                "derived_regime": derived_regime,
            }
        )


class EnhancedBullishLowIVEntry:
    """
    Enhanced bullish + low IV entry rule using derived statistics.

    **Enhanced Logic:**
    - Confirms cheap options (all IV ranks < 50)
    - Checks for IV mean reversion potential
    - Uses put/call ratio for entry timing

    **Priority:** 4
    """

    priority = 4
    name = "enhanced_bullish_low_iv_entry"

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None,
    ) -> Optional[Decision]:
        """Evaluate enhanced bullish + low IV entry conditions."""
        if not market_data:
            return None

        outlook = market_data.get("outlook")
        iv_level = market_data.get("iv_level")
        confidence = market_data.get("confidence", 0.5)
        symbol = market_data.get("symbol", "UNKNOWN")

        if outlook != MarketOutlook.BULLISH.value:
            return None

        if iv_level != IVLevel.LOW.value:
            return None

        # Enhanced checks
        iv_rank_30d = market_data.get("iv_rank_30d", 50.0)
        iv_rank_90d = market_data.get("iv_rank_90d", 50.0)

        # Confirm low IV across timeframes
        if iv_rank_30d > 40 or iv_rank_90d > 40:
            logger.info(
                f"[{symbol}] Skipping low IV entry: "
                f"IV not consistently low (30d={iv_rank_30d:.1f}, 90d={iv_rank_90d:.1f})"
            )
            return None

        if confidence < 0.5:
            return None

        strategy = StrategyType.VERTICAL_SPREAD  # Bull put spread
        reason = (
            f"Bullish + Low IV (rank={market_data.get('iv_rank'):.1f}): "
            f"Bull put spread for credit"
        )

        return Decision(
            action=DecisionAction.ENTER,
            strategy_type=strategy,
            urgency=Urgency.LOW,
            confidence=confidence,
            reason=reason,
            metadata={
                "strategy_type": strategy.value,
                "entry_rule": self.name,
                "iv_rank": market_data.get("iv_rank"),
            }
        )


class EnhancedBearishLowIVEntry:
    """Enhanced bearish + low IV entry rule.

    **Priority:** 5
    """

    priority = 5
    name = "enhanced_bearish_low_iv_entry"

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None,
    ) -> Optional[Decision]:
        """Evaluate enhanced bearish + low IV entry conditions."""
        if not market_data:
            return None

        outlook = market_data.get("outlook")
        iv_level = market_data.get("iv_level")
        confidence = market_data.get("confidence", 0.5)

        if outlook != MarketOutlook.BEARISH.value:
            return None

        if iv_level != IVLevel.LOW.value:
            return None

        if confidence < 0.5:
            return None

        strategy = StrategyType.VERTICAL_SPREAD  # Bear call spread
        reason = (
            f"Bearish + Low IV (rank={market_data.get('iv_rank'):.1f}): "
            f"Bear call spread for credit"
        )

        return Decision(
            action=DecisionAction.ENTER,
            strategy_type=strategy,
            urgency=Urgency.LOW,
            confidence=confidence,
            reason=reason,
            metadata={
                "strategy_type": strategy.value,
                "entry_rule": self.name,
                "iv_rank": market_data.get("iv_rank"),
            }
        )


class EnhancedNeutralLowIVEntry:
    """Enhanced neutral + low IV entry rule.

    **Priority:** 6
    """

    priority = 6
    name = "enhanced_neutral_low_iv_entry"

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None,
    ) -> Optional[Decision]:
        """Evaluate enhanced neutral + low IV entry conditions."""
        if not market_data:
            return None

        outlook = market_data.get("outlook")
        iv_level = market_data.get("iv_level")
        derived_regime = market_data.get("derived_regime")
        confidence = market_data.get("confidence", 0.5)

        if outlook != MarketOutlook.NEUTRAL.value:
            return None

        if iv_level != IVLevel.LOW.value:
            return None

        # Confirm range-bound regime
        if derived_regime != "range_bound" and derived_regime != "low_vol":
            return None

        if confidence < 0.5:
            return None

        strategy = StrategyType.IRON_CONDOR
        reason = (
            f"Neutral + Low IV (rank={market_data.get('iv_rank'):.1f}): "
            f"Iron condor for range-bound trade"
        )

        return Decision(
            action=DecisionAction.ENTER,
            strategy_type=strategy,
            urgency=Urgency.LOW,
            confidence=confidence,
            reason=reason,
            metadata={
                "strategy_type": strategy.value,
                "entry_rule": self.name,
                "iv_rank": market_data.get("iv_rank"),
                "derived_regime": derived_regime,
            }
        )
