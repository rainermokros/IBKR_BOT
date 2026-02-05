"""
Entry Decision Rules Based on Market Regime and IV Level

Implements the standard options strategy selection matrix:

Market Outlook    | High IV                    | Low IV
-----------------|----------------------------|---------------------------
Bullish          | Long Call (Debit)         | Bull Put Spread (Credit)
                 | Bull Call Spread (Debit)   | Cash-Secured Put (Credit)
                 | Call Backspread (Debit)    |

Bearish          | Long Put (Debit)           | Bear Call Spread (Credit)
                 | Bear Put Spread (Debit)    |
                 | Put Backspread (Debit)     |

Neutral/Sideways  | Short Straddle (Credit)    | Long Butterfly (Debit)
                 | Short Strangle (Credit)    | Iron Condor (Credit)

Key Concepts:
- HIGH IV (IV rank > 50): Options expensive, good for selling premium
- LOW IV (IV rank < 50): Options cheap, good for buying premium
- Debit strategies: Pay upfront, want movement, long options benefit from IV rise
- Credit strategies: Receive upfront, want stability, IV crush helps
- Sideways in HIGH IV: Sell premium aggressively (straddle/strangle)
- Sideways in LOW IV: Defined-range, low-cost (butterfly/condor)

Usage:
    from v6.decisions.rules.entry_rules import (
        BullishHighIVEntry,
        BullishLowIVEntry,
        BearishHighIVEntry,
        BearishLowIVEntry,
        NeutralHighIVEntry,
        NeutralLowIVEntry,
    )
    from v6.decisions.market_regime import MarketRegimeDetector

    # Register entry rules with DecisionEngine
    engine = DecisionEngine()
    engine.register_rule(BullishHighIVEntry())
    engine.register_rule(BullishLowIVEntry())
    engine.register_rule(BearishHighIVEntry())
    engine.register_rule(BearishLowIVEntry())
    engine.register_rule(NeutralHighIVEntry())
    engine.register_rule(NeutralLowIVEntry())

    # Detect market regime and get entry decision
    detector = MarketRegimeDetector()
    regime = await detector.detect_regime(symbol="SPY, iv_rank=60, vix=28, price=450)

    decision = await engine.evaluate(snapshot=None, market_data=regime.to_dict())

    if decision.action == DecisionAction.ENTER:
        strategy_type = decision.metadata.get("strategy_type")
        # Execute entry...
"""

from typing import Optional

from loguru import logger

from v6.decisions.market_regime import MarketOutlook, MarketRegime, IVLevel, VolTrend
from v6.strategy_builder.decision_engine.models import Decision, DecisionAction, Urgency
from v6.strategy_builder.models import StrategyType


class BullishHighIVEntry:
    """
    Bullish market + High IV entry decision rule.

    **Rationale:**
    - High IV makes options expensive
    - Buying long calls is costly but benefits from volatility expansion
    - Bull call spread defines risk/cost while maintaining bullish exposure
    - Call backspread amplifies gains if volatility surges

    **Strategies (in order of preference):**
    1. Bull Call Spread (Credit) - Defines risk, still bullish
    2. Call Backspread (2:1) - Amplified bullish bet on vol surge
    3. Long Call (Debit) - Simple bullish exposure, benefits from vol rise

    **Priority:** 1 (Highest priority for bullish + high IV)

    **Market Conditions:**
    - Outlook: Bullish
    - IV Level: High (IV rank > 50)
    - Vol Trend: Rising or Stable (avoid falling vol)
    """

    priority = 1
    name = "bullish_high_iv_entry"

    async def evaluate(
        self,
        snapshot,  # Not used for entry decisions
        market_data: Optional[dict] = None,
    ) -> Optional[Decision]:
        """
        Evaluate bullish + high IV entry conditions.

        Args:
            snapshot: Not used for entry
            market_data: Dict with market data including regime info

        Returns:
            Decision with ENTER action if conditions met, None otherwise
        """
        if not market_data:
            return None

        outlook = market_data.get("outlook")
        iv_level = market_data.get("iv_level")
        vol_trend = market_data.get("vol_trend")
        symbol = market_data.get("symbol", "UNKNOWN")

        # Check market regime
        if outlook != MarketOutlook.BULLISH.value:
            return None  # Not bullish, skip

        if iv_level != IVLevel.HIGH.value and iv_level != IVLevel.EXTREME.value:
            return None  # IV not high enough, skip

        # Additional check: avoid falling volatility (bad for debit strategies)
        if vol_trend == VolTrend.FALLING.value:
            logger.info(
                f"[{symbol}] Skipping bullish entry: "
                f"IV {iv_level} but vol is {vol_trend} (bad for long calls)"
            )
            return None

        # Determine best strategy based on IV level and vol trend
        if iv_level == IVLevel.EXTREME.value:
            # Extreme IV: Use bull call spread to reduce cost
            strategy = StrategyType.VERTICAL_SPREAD  # Bull call spread
            reason = (
                f"Bullish + Extreme IV (rank={market_data.get('iv_rank'):.1f}): "
                f"Bull call spread to reduce cost while maintaining bullish exposure"
            )

        elif vol_trend == VolTrend.RISING.value:
            # Rising vol: Use call backspread to amplify gains
            strategy = StrategyType.CUSTOM  # Call backspread
            reason = (
                f"Bullish + High IV (rank={market_data.get('iv_rank'):.1f}) + Rising vol: "
                f"Call backspread (2:1) to amplify gains from volatility surge"
            )

        else:
            # Stable high IV: Use bull call spread for defined risk
            strategy = StrategyType.VERTICAL_SPREAD  # Bull call spread
            reason = (
                f"Bullish + High IV (rank={market_data.get('iv_rank'):.1f}) + Stable vol: "
                f"Bull call spread (debit) for defined-risk bullish exposure"
            )

        logger.info(f"[{symbol}] ✓ ENTRY SIGNAL: {reason}")

        return Decision(
            action=DecisionAction.ENTER,
            reason=reason,
            rule="bullish_high_iv_entry",
            urgency=Urgency.NORMAL,
            metadata={
                "strategy_type": strategy.value,
                "market_outlook": outlook,
                "iv_level": iv_level,
                "vol_trend": vol_trend,
            }
        )


class BullishLowIVEntry:
    """
    Bullish market + Low IV entry decision rule.

    **Rationale:**
    - Low IV means options are cheap
    - Want to collect premium but need to account for low premium availability
    - Bull put spreads work well: collect premium while maintaining bullish bias
    - Cash-secured puts also work but have naked put risk (margin intensive)

    **Strategies (in order of preference):**
    1. Bull Put Spread (Credit) - Collect premium, defined risk, bullish
    2. Cash-Secured Put (Credit) - Collect premium, but requires margin for naked put
    3. Long Call (Debit) - Cheaper with low IV, benefits from vol expansion

    **Priority:** 2 (High priority for bullish + low IV)

    **Market Conditions:**
    - Outlook: Bullish
    - IV Level: Low (IV rank < 50)
    - Vol Trend: Any (IV crush helps credit strategies)
    """

    priority = 2
    name = "bullish_low_iv_entry"

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None,
    ) -> Optional[Decision]:
        """
        Evaluate bullish + low IV entry conditions.

        Args:
            snapshot: Not used for entry
            market_data: Dict with market data

        Returns:
            Decision with ENTER action if conditions met, None otherwise
        """
        if not market_data:
            return None

        outlook = market_data.get("outlook")
        iv_level = market_data.get("iv_level")
        symbol = market_data.get("symbol", "UNKNOWN")

        # Check market regime
        if outlook != MarketOutlook.BULLISH.value:
            return None  # Not bullish, skip

        if iv_level != IVLevel.LOW.value:
            return None  # IV not low, skip

        iv_rank = market_data.get("iv_rank", 0)
        vol_trend = market_data.get("vol_trend")

        # Low IV: Use credit strategies to collect premium
        # Bull put spread: Collect premium, defined risk, bullish
        strategy = StrategyType.VERTICAL_SPREAD  # Bull put spread
        reason = (
            f"Bullish + Low IV (rank={iv_rank:.1f}): "
            f"Bull put spread (credit) - Collect premium with defined risk, "
            f"benefits from IV crush if vol falls"
        )

        # If IV is very low and stable, consider long calls
        if iv_rank < 30 and vol_trend == VolTrend.STABLE.value:
            strategy = StrategyType.LONG_CALL  # Long call
            reason = (
                f"Bullish + Very Low IV (rank={iv_rank:.1f}): "
                f"Long call (debit) - Cheap premium with low IV, benefits from vol expansion"
            )

        logger.info(f"[{symbol}] ✓ ENTRY SIGNAL: {reason}")

        return Decision(
            action=DecisionAction.ENTER,
            reason=reason,
            rule="bullish_low_iv_entry",
            urgency=Urgency.NORMAL,
            metadata={
                "strategy_type": strategy.value,
                "market_outlook": outlook,
                "iv_level": iv_level,
                "iv_rank": iv_rank,
            }
        )


class BearishHighIVEntry:
    """
    Bearish market + High IV entry decision rule.

    **Rationale:**
    - High IV makes puts expensive
    - Long puts benefit from volatility expansion
    - Bear put spreads define risk/cost while maintaining bearish exposure
    - Put backspread amplifies gains if volatility surges

    **Strategies (in order of preference):**
    1. Bear Put Spread (Debit) - Defines risk, still bearish
    2. Put Backspread (2:1) - Amplified bearish bet on vol surge
    3. Long Put (Debit) - Simple bearish exposure, benefits from vol rise

    **Priority:** 3 (High priority for bearish + high IV)

    **Market Conditions:**
    - Outlook: Bearish
    - IV Level: High (IV rank > 50)
    - Vol Trend: Rising or Stable (avoid falling vol)
    """

    priority = 3
    name = "bearish_high_iv_entry"

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None,
    ) -> Optional[Decision]:
        """
        Evaluate bearish + high IV entry conditions.

        Args:
            snapshot: Not used for entry
            market_data: Dict with market data

        Returns:
            Decision with ENTER action if conditions met, None otherwise
        """
        if not market_data:
            return None

        outlook = market_data.get("outlook")
        iv_level = market_data.get("iv_level")
        vol_trend = market_data.get("vol_trend")
        symbol = market_data.get("symbol", "UNKNOWN")

        # Check market regime
        if outlook != MarketOutlook.BEARISH.value:
            return None  # Not bearish, skip

        if iv_level != IVLevel.HIGH.value and iv_level != IVLevel.EXTREME.value:
            return None  # IV not high enough, skip

        # Avoid falling volatility
        if vol_trend == VolTrend.FALLING.value:
            logger.info(
                f"[{symbol}] Skipping bearish entry: "
                f"IV {iv_level} but vol is {vol_trend} (bad for long puts)"
            )
            return None

        iv_rank = market_data.get("iv_rank", 0)

        # High IV: Use debit strategies for bearish exposure
        # Bear put spread: Defines risk, maintains bearish exposure
        strategy = StrategyType.VERTICAL_SPREAD  # Bear put spread
        reason = (
            f"Bearish + High IV (rank={iv_rank:.1f}): "
            f"Bear put spread (debit) - Defined-risk bearish exposure, "
            f"benefits from volatility expansion"
        )

        # If extreme IV, consider backspread
        if iv_level == IVLevel.EXTREME.value and vol_trend == VolTrend.RISING.value:
            strategy = StrategyType.CUSTOM  # Put backspread
            reason = (
                f"Bearish + Extreme IV (rank={iv_rank:.1f}) + Rising vol: "
                f"Put backspread (2:1) to amplify gains from volatility surge"
            )

        logger.info(f"[{symbol}] ✓ ENTRY SIGNAL: {reason}")

        return Decision(
            action=DecisionAction.ENTER,
            reason=reason,
            rule="bearish_high_iv_entry",
            urgency=Urgency.NORMAL,
            metadata={
                "strategy_type": strategy.value,
                "market_outlook": outlook,
                "iv_level": iv_level,
                "vol_trend": vol_trend,
            }
        )


class BearishLowIVEntry:
    """
    Bearish market + Low IV entry decision rule.

    **Rationale:**
    - Low IV means options are cheap
    - Want to generate income from bearish view
    - Bear call spreads work well: collect premium, defined risk, benefits from time decay
    - Premium is low, so focus on time decay rather than IV crush

    **Strategies (in order of preference):**
    1. Bear Call Spread (Credit) - Generate income, time decay helps
    2. Bear Put Spread (Debit) - Cheaper with low IV, but debit strategy

    **Priority:** 4 (High priority for bearish + low IV)

    **Market Conditions:**
    - Outlook: Bearish
    - IV Level: Low (IV rank < 50)
    - Vol Trend: Any (time decay helps credit strategies)
    """

    priority = 4
    name = "bearish_low_iv_entry"

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None,
    ) -> Optional[Decision]:
        """
        Evaluate bearish + low IV entry conditions.

        Args:
            snapshot: Not used for entry
            market_data: Dict with market data

        Returns:
            Decision with ENTER action if conditions met, None otherwise
        """
        if not market_data:
            return None

        outlook = market_data.get("outlook")
        iv_level = market_data.get("iv_level")
        symbol = market_data.get("symbol", "UNKNOWN")

        # Check market regime
        if outlook != MarketOutlook.BEARISH.value:
            return None  # Not bearish, skip

        if iv_level != IVLevel.LOW.value:
            return None  # IV not low, skip

        iv_rank = market_data.get("iv_rank", 0)

        # Low IV + Bearish: Use credit spread to collect premium
        # Bear call spread: Generate income, defined risk, time decay helps
        strategy = StrategyType.VERTICAL_SPREAD  # Bear call spread
        reason = (
            f"Bearish + Low IV (rank={iv_rank:.1f}): "
            f"Bear call spread (credit) - Generate income from time decay, "
            f"defined risk, benefits if stock stays below short strike"
        )

        logger.info(f"[{symbol}] ✓ ENTRY SIGNAL: {reason}")

        return Decision(
            action=DecisionAction.ENTER,
            reason=reason,
            rule="bearish_low_iv_entry",
            urgency=Urgency.NORMAL,
            metadata={
                "strategy_type": strategy.value,
                "market_outlook": outlook,
                "iv_level": iv_level,
                "iv_rank": iv_rank,
            }
        )


class NeutralHighIVEntry:
    """
    Neutral/Sideways market + High IV entry decision rule.

    **Rationale:**
    - High IV means options are expensive (large premiums available)
    - Want to sell premium aggressively to capitalize on high IV
    - Expect IV to decrease ("IV crush") which benefits credit strategies
    - Range-bound market + High IV = Premium selling paradise

    **Strategies (in order of preference):**
    1. Short Straddle (Credit) - Sell both ATM call and put, collect maximum premium
    2. Short Strangle (Credit) - Sell OTM call and put, wider range, slightly less premium

    **Priority:** 5 (High priority for neutral + high IV)

    **Market Conditions:**
    - Outlook: Neutral/Sideways
    - IV Level: High (IV rank > 50)
    - Vol Trend: Falling or Stable (IV crush helps)

    **RISK WARNING:** Short straddles/strangles have unlimited risk and require significant margin. Only for experienced traders.
    """

    priority = 5
    name = "neutral_high_iv_entry"

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None,
    ) -> Optional[Decision]:
        """
        Evaluate neutral + high IV entry conditions.

        Args:
            snapshot: Not used for entry
            market_data: Dict with market data

        Returns:
            Decision with ENTER action if conditions met, None otherwise
        """
        if not market_data:
            return None

        outlook = market_data.get("outlook")
        iv_level = market_data.get("iv_level")
        vol_trend = market_data.get("vol_trend")
        symbol = market_data.get("symbol", "UNKNOWN")

        # Check market regime
        if outlook != MarketOutlook.NEUTRAL.value:
            return None  # Not neutral, skip

        if iv_level != IVLevel.HIGH.value and iv_level != IVLevel.EXTREME.value:
            return None  # IV not high enough, skip

        iv_rank = market_data.get("iv_rank", 0)
        vix = market_data.get("vix", 0)

        # High IV + Neutral: Sell premium aggressively
        # Short straddle: Maximum premium collection, expects IV to drop
        strategy = StrategyType.CUSTOM  # Short straddle
        reason = (
            f"Neutral + High IV (rank={iv_rank:.1f}, VIX={vix:.2f}): "
            f"Short straddle (credit) - Collect large premiums, "
            f"profit from range-bound market + IV crush (IV falling from high levels)"
        )

        # If very high IV, consider strangle for wider range (more safety)
        if iv_rank > 75:
            strategy = StrategyType.CUSTOM  # Short strangle
            reason = (
                f"Neutral + Extreme IV (rank={iv_rank:.1f}): "
                f"Short strangle (credit) - OTM strikes for wider range, "
                f"still collects large premiums with more safety than straddle"
            )

        logger.warning(f"[{symbol}] ✓ ENTRY SIGNAL (HIGH RISK): {reason}")

        return Decision(
            action=DecisionAction.ENTER,
            reason=reason,
            rule="neutral_high_iv_entry",
            urgency=Urgency.NORMAL,
            metadata={
                "strategy_type": strategy.value,
                "market_outlook": outlook,
                "iv_level": iv_level,
                "iv_rank": iv_rank,
                "vix": vix,
                "risk_warning": "Short straddles/strangles have unlimited risk",
            }
        )


class NeutralLowIVEntry:
    """
    Neutral/Sideways market + Low IV entry decision rule.

    **Rationale:**
    - Low IV means options are cheap (premiums are small)
    - Want strategies that work in low-vol environment
    - Debit strategies: Long butterfly (low cost, defined range)
    - Credit strategies: Iron condor (collects smaller credit, but still benefits from time decay)

    **Strategies (in order of preference):**
    1. Iron Condor (Credit) - Collect premium, defined risk, benefits from time decay
    2. Long Butterfly (Debit) - Low-cost, defined-range play for tight range

    **Priority:** 6 (High priority for neutral + low IV)

    **Market Conditions:**
    - Outlook: Neutral/Sideways
    - IV Level: Low (IV rank < 50)
    - Vol Trend: Stable (prefer stable vol for range-bound strategies)
    """

    priority = 6
    name = "neutral_low_iv_entry"

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None,
    ) -> Optional[Decision]:
        """
        Evaluate neutral + low IV entry conditions.

        Args:
            snapshot: Not used for entry
            market_data: Dict with market data

        Returns:
            Decision with ENTER action if conditions met, None otherwise
        """
        if not market_data:
            return None

        outlook = market_data.get("outlook")
        iv_level = market_data.get("iv_level")
        vol_trend = market_data.get("vol_trend")
        symbol = market_data.get("symbol", "UNKNOWN")

        # Check market regime
        if outlook != MarketOutlook.NEUTRAL.value:
            return None  # Not neutral, skip

        if iv_level != IVLevel.LOW.value:
            return None  # IV not low, skip

        iv_rank = market_data.get("iv_rank", 0)

        # Low IV + Neutral: Use range-bound strategies
        # Iron condor: Collect premium (smaller credit), defined risk, time decay helps
        strategy = StrategyType.IRON_CONDOR
        reason = (
            f"Neutral + Low IV (rank={iv_rank:.1f}): "
            f"Iron condor (credit) - Collect premium (though smaller than high IV), "
            f"defined risk, benefits from time decay in range-bound market"
        )

        # If IV is very low, consider butterfly (debit strategy)
        if iv_rank < 25 and vol_trend == VolTrend.STABLE.value:
            strategy = StrategyType.CUSTOM  # Long butterfly
            reason = (
                f"Neutral + Very Low IV (rank={iv_rank:.1f}): "
                f"Long butterfly (debit) - Low-cost, defined-range play for tight market, "
                f"avoids paying high premiums for long options"
            )

        logger.info(f"[{symbol}] ✓ ENTRY SIGNAL: {reason}")

        return Decision(
            action=DecisionAction.ENTER,
            reason=reason,
            rule="neutral_low_iv_entry",
            urgency=Urgency.NORMAL,
            metadata={
                "strategy_type": strategy.value,
                "market_outlook": outlook,
                "iv_level": iv_level,
                "iv_rank": iv_rank,
                "vol_trend": vol_trend,
            }
        )


# Convenience dictionary for looking up strategy class by regime
STRATEGY_MATRIX = {
    (MarketOutlook.BULLISH, IVLevel.HIGH): BullishHighIVEntry,
    (MarketOutlook.BULLISH, IVLevel.LOW): BullishLowIVEntry,
    (MarketOutlook.BEARISH, IVLevel.HIGH): BearishHighIVEntry,
    (MarketOutlook.BEARISH, IVLevel.LOW): BearishLowIVEntry,
    (MarketOutlook.NEUTRAL, IVLevel.HIGH): NeutralHighIVEntry,
    (MarketOutlook.NEUTRAL, IVLevel.LOW): NeutralLowIVEntry,
}


def get_entry_strategy(outlook: MarketOutlook, iv_level: IVLevel) -> type:
    """
    Get the appropriate entry strategy class for a given market regime.

    Args:
        outlook: Market outlook (bullish, bearish, neutral)
        iv_level: IV level (high, low)

    Returns:
        Strategy class for the given regime

    Example:
        >>> rule_class = get_entry_strategy(MarketOutlook.BULLISH, IVLevel.HIGH)
        >>> rule_instance = rule_class()
        >>> decision = await rule_instance.evaluate(None, market_data)
    """
    return STRATEGY_MATRIX.get((outlook, iv_level))
