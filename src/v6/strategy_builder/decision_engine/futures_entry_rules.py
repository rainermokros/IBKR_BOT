"""
Futures-Based Entry Rules

These entry rules incorporate futures market signals for enhanced timing
and confirmation of spot trading entries.

Key features:
- Uses futures as leading indicator for spot entries
- Confirms spot signals with futures positioning
- Adjusts position sizing based on futures confidence
- Implements contrarian strategies when futures diverge from spot

Usage:
    from v6.decisions.rules.futures_entry_rules import FuturesBullishEntry
    from v6.decisions.futures_integration import FuturesSignalGenerator

    # Register with decision engine
    engine.register_rule(FuturesBullishEntry())
"""

from typing import Optional

from loguru import logger

from v6.strategy_builder.decision_engine.models import Decision, DecisionAction, Urgency
from v6.decisions.futures_integration import (
    FuturesSignalGenerator,
    FuturesSentiment,
    FuturesSignal,
)
from v6.strategy_builder.models import StrategyType


class FuturesBullishEntry:
    """
    Bullish entry rule with futures confirmation.

    **Entry Logic:**
    - Base: Bullish outlook from market regime
    - Confirmation: Futures show bullish signal
    - Enhancement: Higher position size with strong futures confidence

    **Priority:** 1 (High priority when futures confirm)

    **Entry Conditions:**
    - Market outlook: Bullish
    - Futures sentiment: Bullish or Neutral
    - Futures signal: BUY or STRONG_BUY
    - Futures confidence: > 0.5
    """

    priority = 1
    name = "futures_bullish_entry"

    def __init__(self):
        """Initialize with futures signal generator."""
        self.signal_generator = FuturesSignalGenerator()

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None,
    ) -> Optional[Decision]:
        """Evaluate bullish entry with futures confirmation."""
        if not market_data:
            return None

        outlook = market_data.get("outlook")
        symbol = market_data.get("symbol", "UNKNOWN")

        # Check base market outlook
        if outlook != "bullish":
            return None

        # Get futures signal
        futures_signal = await self.signal_generator.generate_signal(symbol)

        if not futures_signal:
            logger.debug(f"[{symbol}] No futures signal available")
            return None

        # Check futures confirmation
        if not futures_signal.is_bullish():
            logger.info(
                f"[{symbol}] Futures do not confirm bullish entry: "
                f"{futures_signal.signal.value} ({futures_signal.reasoning})"
            )
            return None

        # Check confidence threshold
        if futures_signal.confidence < 0.5:
            logger.info(
                f"[{symbol}] Low futures confidence: {futures_signal.confidence:.2f}"
            )
            return None

        # Determine strategy and urgency
        if futures_signal.signal == FuturesSignal.STRONG_BUY:
            urgency = Urgency.HIGH
            strategy = StrategyType.VERTICAL_SPREAD  # Bull call spread
            reason = (
                f"Bullish entry with STRONG futures confirmation: "
                f"{futures_signal.reasoning}"
            )
        else:
            urgency = Urgency.MEDIUM
            strategy = StrategyType.VERTICAL_SPREAD  # Bull call spread
            reason = (
                f"Bullish entry with futures confirmation: "
                f"{futures_signal.reasoning}"
            )

        # Position sizing based on futures confidence
        position_multiplier = 0.8 + (futures_signal.confidence * 0.4)  # 0.8-1.2x

        return Decision(
            action=DecisionAction.ENTER,
            strategy_type=strategy,
            urgency=urgency,
            reason=reason,
            rule=self.name,
            metadata={
                "strategy_type": strategy.value,
                "position_multiplier": position_multiplier,
                "futures_confidence": futures_signal.confidence,
                "futures_signal": futures_signal.signal.value,
                "futures_momentum": futures_signal.momentum,
                "entry_rule": self.name,
            }
        )


class FuturesBearishEntry:
    """
    Bearish entry rule with futures confirmation.

    **Priority:** 2
    """

    priority = 2
    name = "futures_bearish_entry"

    def __init__(self):
        """Initialize with futures signal generator."""
        self.signal_generator = FuturesSignalGenerator()

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None,
    ) -> Optional[Decision]:
        """Evaluate bearish entry with futures confirmation."""
        if not market_data:
            return None

        outlook = market_data.get("outlook")
        symbol = market_data.get("symbol", "UNKNOWN")

        if outlook != "bearish":
            return None

        futures_signal = await self.signal_generator.generate_signal(symbol)

        if not futures_signal:
            return None

        if not futures_signal.is_bearish():
            logger.info(
                f"[{symbol}] Futures do not confirm bearish entry: "
                f"{futures_signal.signal.value}"
            )
            return None

        if futures_signal.confidence < 0.5:
            return None

        strategy = StrategyType.VERTICAL_SPREAD  # Bear put spread
        urgency = Urgency.MEDIUM

        if futures_signal.signal == FuturesSignal.STRONG_SELL:
            urgency = Urgency.HIGH
            reason = (
                f"Bearish entry with STRONG futures confirmation: "
                f"{futures_signal.reasoning}"
            )
        else:
            reason = (
                f"Bearish entry with futures confirmation: "
                f"{futures_signal.reasoning}"
            )

        position_multiplier = 0.8 + (futures_signal.confidence * 0.4)

        return Decision(
            action=DecisionAction.ENTER,
            strategy_type=strategy,
            urgency=urgency,
            reason=reason,
            rule=self.name,
            metadata={
                "strategy_type": strategy.value,
                "position_multiplier": position_multiplier,
                "futures_confidence": futures_signal.confidence,
                "futures_signal": futures_signal.signal.value,
                "entry_rule": self.name,
            }
        )


class FuturesContrarianEntry:
    """
    Contrarian entry rule when futures diverge from spot.

    **Entry Logic:**
    - Spot says one thing, futures say opposite
    - Use futures as leading indicator
    - Enter in direction of futures (contrarian to spot)

    **Priority:** 3 (Medium priority for divergence plays)

    **Entry Conditions:**
    - Futures signal is strong (STRONG_BUY or STRONG_SELL)
    - Futures confidence > 0.7
    - Futures momentum is strong
    - Spot outlook is neutral or opposite
    """

    priority = 3
    name = "futures_contrarian_entry"

    def __init__(self):
        """Initialize with futures signal generator."""
        self.signal_generator = FuturesSignalGenerator()

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None,
    ) -> Optional[Decision]:
        """Evaluate contrarian entry when futures diverge from spot."""
        if not market_data:
            return None

        outlook = market_data.get("outlook")
        symbol = market_data.get("symbol", "UNKNOWN")

        # Get futures signal
        futures_signal = await self.signal_generator.generate_signal(symbol)

        if not futures_signal:
            return None

        # Need strong futures signal
        if futures_signal.signal not in [
            FuturesSignal.STRONG_BUY,
            FuturesSignal.STRONG_SELL,
        ]:
            return None

        # Need high confidence
        if futures_signal.confidence < 0.7:
            return None

        # Need strong momentum
        if abs(futures_signal.momentum) < 0.002:
            return None

        # Check for divergence
        is_bullish_futures = futures_signal.is_bullish()
        is_bullish_spot = outlook == "bullish"

        # If futures and spot agree, not a contrarian play
        if is_bullish_futures == is_bullish_spot:
            return None

        # Generate contrarian signal
        if is_bullish_futures:
            # Futures bullish, spot not: contrarian bullish entry
            strategy = StrategyType.VERTICAL_SPREAD  # Bull call spread
            urgency = Urgency.HIGH
            reason = (
                f"CONTRARIAN: Futures strongly bullish (momentum: {futures_signal.momentum:+.4f}) "
                f"but spot is {outlook} - entering bullish"
            )
        else:
            # Futures bearish, spot not: contrarian bearish entry
            strategy = StrategyType.VERTICAL_SPREAD  # Bear put spread
            urgency = Urgency.HIGH
            reason = (
                f"CONTRARIAN: Futures strongly bearish (momentum: {futures_signal.momentum:+.4f}) "
                f"but spot is {outlook} - entering bearish"
            )

        # Higher position size for contrarian plays (conviction trade)
        position_multiplier = 1.0

        return Decision(
            action=DecisionAction.ENTER,
            strategy_type=strategy,
            urgency=urgency,
            reason=reason,
            rule=self.name,
            metadata={
                "strategy_type": strategy.value,
                "position_multiplier": position_multiplier,
                "futures_confidence": futures_signal.confidence,
                "futures_signal": futures_signal.signal.value,
                "futures_momentum": futures_signal.momentum,
                "spot_outlook": outlook,
                "contrarian": True,
                "entry_rule": self.name,
            }
        )


class FuturesMomentumEntry:
    """
    Momentum-based entry rule using futures data.

    **Entry Logic:**
    - Strong futures momentum (>0.3% in lookback period)
    - Futures confirms direction
    - Ride the momentum

    **Priority:** 4
    """

    priority = 4
    name = "futures_momentum_entry"

    def __init__(self):
        """Initialize with futures signal generator."""
        self.signal_generator = FuturesSignalGenerator()

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None,
    ) -> Optional[Decision]:
        """Evaluate momentum entry from futures."""
        if not market_data:
            return None

        symbol = market_data.get("symbol", "UNKNOWN")

        futures_signal = await self.signal_generator.generate_signal(symbol)

        if not futures_signal:
            return None

        # Need strong momentum
        if abs(futures_signal.momentum) < 0.003:  # 0.3%
            return None

        # Determine direction from momentum
        if futures_signal.momentum > 0:
            # Upward momentum: bullish
            if futures_signal.confidence < 0.6:
                return None

            strategy = StrategyType.VERTICAL_SPREAD  # Bull call spread
            reason = (
                f"Futures momentum entry: Strong upward momentum "
                f"({futures_signal.momentum:+.4f})"
            )
        else:
            # Downward momentum: bearish
            if futures_signal.confidence < 0.6:
                return None

            strategy = StrategyType.VERTICAL_SPREAD  # Bear put spread
            reason = (
                f"Futures momentum entry: Strong downward momentum "
                f"({futures_signal.momentum:+.4f})"
            )

        position_multiplier = 1.0 + (abs(futures_signal.momentum) * 10)  # Scale with momentum

        return Decision(
            action=DecisionAction.ENTER,
            strategy_type=strategy,
            urgency=Urgency.MEDIUM,
            reason=reason,
            rule=self.name,
            metadata={
                "strategy_type": strategy.value,
                "position_multiplier": min(position_multiplier, 1.5),
                "futures_momentum": futures_signal.momentum,
                "futures_confidence": futures_signal.confidence,
                "entry_rule": self.name,
            }
        )
