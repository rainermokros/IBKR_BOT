"""
Catastrophe and Protection Decision Rules

This module implements the highest priority decision rules for catastrophe protection
and single-leg position management. These rules have Priority 1-1.5 (highest).

Rules:
- CatastropheProtection (Priority 1): Market crash or IV explosion → CLOSE IMMEDIATE
- SingleLegExit (Priority 1.3): TP/SL/DTE checks for LONG/SHORT strategies
- TrailingStopLoss (Priority 1.4): Dynamic trailing stop at 40% of peak
- VIXExit (Priority 1.5): VIX > 35 or +5 points → CLOSE

Key patterns:
- Highest priority rules (1-1.5)
- IMMEDIATE urgency for catastrophe protection
- State management for trailing stop (track peak UPL)
- Market data dependency (VIX, IV, underlying change)

Reference: ../v5/caretaker/decision_engine.py for v5 logic
"""

from datetime import date, datetime
from typing import Optional

from loguru import logger

from src.v6.decisions.models import Decision, DecisionAction, Urgency


class CatastropheProtection:
    """
    Catastrophe protection rule (Priority 1).

    Monitors for market crashes and IV explosions. Triggers immediate close
    if underlying drops >3% in 1 hour or IV spikes >50%.

    Priority 1: Highest priority, executes before all other rules.
    """

    priority = 1
    name = "catastrophe_protection"

    def __init__(self):
        """Initialize catastrophe protection rule."""
        self.market_drop_threshold = -0.03  # -3%
        self.iv_spike_threshold = 0.50  # +50%

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None
    ) -> Optional[Decision]:
        """
        Evaluate catastrophe protection conditions.

        Args:
            snapshot: Position snapshot (Polars Row or dict-like)
            market_data: Optional dict with market data:
                - "1h_change": Underlying 1-hour price change (decimal)
                - "iv_change_percent": IV change percentage (decimal)

        Returns:
            Decision with CLOSE + IMMEDIATE if catastrophe detected, None otherwise
        """
        if not market_data:
            return None

        # Check underlying 1-hour change (market crash)
        hour_change = market_data.get("1h_change", 0)
        if hour_change < self.market_drop_threshold:
            # Market crash detected
            symbol = getattr(snapshot, 'symbol', 'UNKNOWN')
            return Decision(
                action=DecisionAction.CLOSE,
                reason=f"Market crash: {symbol} down {hour_change*100:.1f}%",
                rule="catastrophe_3pct_drop",
                urgency=Urgency.IMMEDIATE,
                metadata={
                    "hour_change": hour_change,
                    "threshold": self.market_drop_threshold,
                }
            )

        # Check IV spike (IV explosion)
        iv_change = market_data.get("iv_change_percent", 0)
        if iv_change > self.iv_spike_threshold:
            # IV explosion detected
            symbol = getattr(snapshot, 'symbol', 'UNKNOWN')
            return Decision(
                action=DecisionAction.CLOSE,
                reason=f"IV explosion: +{iv_change*100:.1f}%",
                rule="catastrophe_iv_spike",
                urgency=Urgency.IMMEDIATE,
                metadata={
                    "iv_change_percent": iv_change,
                    "threshold": self.iv_spike_threshold,
                }
            )

        return None


class SingleLegExit:
    """
    Single-leg exit rule (Priority 1.3).

    For LONG/SHORT strategies (not spreads), checks:
    - Take profit: UPL ≥ 80% → CLOSE
    - Stop loss: UPL ≤ -50% → CLOSE
    - DTE exit: DTE ≤ 21 → CLOSE

    Priority 1.3: Very high priority, but after catastrophe protection.
    """

    priority = 1.3
    name = "single_leg_exit"

    def __init__(self):
        """Initialize single-leg exit rule."""
        self.tp_threshold = 0.80  # 80% profit
        self.sl_threshold = -0.50  # -50% loss
        self.dte_threshold = 21  # Days to expiration

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None
    ) -> Optional[Decision]:
        """
        Evaluate single-leg exit conditions.

        Args:
            snapshot: Position snapshot with fields:
                - strategy_type: Strategy type (LONG/SHORT vs spreads)
                - unrealized_pnl: Current unrealized P&L
                - entry_price: Entry price
                - expiry: Expiration date
            market_data: Not used for this rule

        Returns:
            Decision with CLOSE if triggered, None otherwise
        """
        # Only apply to LONG/SHORT strategies, not spreads
        strategy_type = getattr(snapshot, 'strategy_type', '')
        if strategy_type in ['iron_condor', 'vertical_spread', 'calendar_spread', 'butterfly', 'strangle']:
            return None

        # Calculate UPL percentage
        # Note: For Polars Row, we need to handle different access patterns
        try:
            # Try as Polars Row first
            if hasattr(snapshot, 'unrealized_pnl'):
                unrealized_pnl = float(snapshot['unrealized_pnl'])
            else:
                return None

            if hasattr(snapshot, 'entry_price'):
                entry_price = float(snapshot['entry_price'])
            else:
                return None

            # Avoid division by zero
            if entry_price == 0:
                return None

            upl_pct = unrealized_pnl / entry_price
        except (KeyError, AttributeError, TypeError) as e:
            logger.warning(f"Could not calculate UPL for single-leg exit: {e}")
            return None

        # Check take profit
        if upl_pct >= self.tp_threshold:
            return Decision(
                action=DecisionAction.CLOSE,
                reason=f"Single-leg TP: UPL {upl_pct*100:.1f}% >= {self.tp_threshold*100:.0f}%",
                rule="single_leg_tp",
                urgency=Urgency.NORMAL,
                metadata={
                    "upl_pct": upl_pct,
                    "threshold": self.tp_threshold,
                }
            )

        # Check stop loss
        if upl_pct <= self.sl_threshold:
            return Decision(
                action=DecisionAction.CLOSE,
                reason=f"Single-leg SL: UPL {upl_pct*100:.1f}% <= {self.sl_threshold*100:.0f}%",
                rule="single_leg_sl",
                urgency=Urgency.HIGH,
                metadata={
                    "upl_pct": upl_pct,
                    "threshold": self.sl_threshold,
                }
            )

        # Check DTE
        try:
            if hasattr(snapshot, 'expiry'):
                expiry = snapshot['expiry']

                # Handle both date and datetime
                if isinstance(expiry, datetime):
                    expiry_date = expiry.date()
                else:
                    expiry_date = expiry

                dte = (expiry_date - date.today()).days

                if dte <= self.dte_threshold:
                    return Decision(
                        action=DecisionAction.CLOSE,
                        reason=f"Single-leg DTE: {dte} days <= {self.dte_threshold}",
                        rule="single_leg_dte",
                        urgency=Urgency.NORMAL,
                        metadata={
                            "dte": dte,
                            "threshold": self.dte_threshold,
                        }
                    )
        except (KeyError, AttributeError, TypeError) as e:
            logger.warning(f"Could not calculate DTE for single-leg exit: {e}")

        return None


class TrailingStopLoss:
    """
    Dynamic trailing stop loss rule (Priority 1.4).

    Tracks peak UPL for each position. If peak ≥ 40%, sets trailing stop
    at 40% of peak. If current UPL drops below trailing stop, closes position.

    Priority 1.4: Very high priority, after single-leg exit.

    State management:
    - Tracks peak UPL per position in self._peaks dict
    - Trailing stop = 40% of peak (e.g., peak 80% → stop at 32%)
    """

    priority = 1.4
    name = "trailing_stop_loss"

    def __init__(self):
        """Initialize trailing stop loss rule."""
        self.peak_threshold = 0.40  # 40% peak to activate trailing stop
        self.trail_ratio = 0.40  # Trail at 40% of peak
        self._peaks: dict[str, float] = {}  # strategy_id -> peak UPL%

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None
    ) -> Optional[Decision]:
        """
        Evaluate trailing stop loss conditions.

        Args:
            snapshot: Position snapshot with fields:
                - strategy_id: Unique strategy identifier
                - unrealized_pnl: Current unrealized P&L
                - entry_price: Entry price
            market_data: Not used for this rule

        Returns:
            Decision with CLOSE if trailing stop hit, None otherwise
        """
        try:
            strategy_id = str(snapshot['strategy_id'])
            unrealized_pnl = float(snapshot['unrealized_pnl'])
            entry_price = float(snapshot['entry_price'])
        except (KeyError, AttributeError, TypeError) as e:
            logger.warning(f"Could not extract position data for trailing stop: {e}")
            return None

        # Avoid division by zero
        if entry_price == 0:
            return None

        # Calculate current UPL percentage
        upl_pct = unrealized_pnl / entry_price

        # Update peak if current is higher
        if strategy_id not in self._peaks:
            self._peaks[strategy_id] = upl_pct
        elif upl_pct > self._peaks[strategy_id]:
            self._peaks[strategy_id] = upl_pct

        # Get peak UPL
        peak = self._peaks[strategy_id]

        # Only activate trailing stop if peak >= threshold
        if peak < self.peak_threshold:
            return None

        # Calculate trailing stop (trail_ratio of peak)
        trailing_stop = peak * self.trail_ratio

        # Check if current UPL dropped below trailing stop
        if upl_pct <= trailing_stop:
            return Decision(
                action=DecisionAction.CLOSE,
                reason=(
                    f"Trailing stop: UPL {upl_pct*100:.1f}% <= "
                    f"stop {trailing_stop*100:.1f}% (peak {peak*100:.1f}%)"
                ),
                rule="trailing_stop",
                urgency=Urgency.NORMAL,
                metadata={
                    "upl_pct": upl_pct,
                    "peak": peak,
                    "trailing_stop": trailing_stop,
                    "trail_ratio": self.trail_ratio,
                }
            )

        return None

    def reset_peak(self, strategy_id: str) -> None:
        """
        Reset peak for a position (e.g., after position is closed).

        Args:
            strategy_id: Strategy identifier to reset
        """
        if strategy_id in self._peaks:
            del self._peaks[strategy_id]


class VIXExit:
    """
    VIX-based exit rule (Priority 1.5).

    Closes positions if:
    - VIX > 35 (volatility too high)
    - VIX +5 points from entry (volatility spike)

    Priority 1.5: Very high priority, after trailing stop.
    """

    priority = 1.5
    name = "vix_exit"

    def __init__(self):
        """Initialize VIX exit rule."""
        self.vix_threshold = 35.0  # VIX level threshold
        self.vix_change_threshold = 5.0  # VIX change threshold (points)

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None
    ) -> Optional[Decision]:
        """
        Evaluate VIX exit conditions.

        Args:
            snapshot: Position snapshot
            market_data: Optional dict with market data:
                - "vix": Current VIX value
                - "vix_entry": VIX at position entry (optional)

        Returns:
            Decision with CLOSE if VIX condition met, None otherwise
        """
        if not market_data:
            return None

        vix = market_data.get("vix")
        if vix is None:
            return None

        # Check VIX level threshold
        if vix > self.vix_threshold:
            return Decision(
                action=DecisionAction.CLOSE,
                reason=f"VIX exit: VIX {vix:.1f} > {self.vix_threshold}",
                rule="vix_level",
                urgency=Urgency.HIGH,
                metadata={
                    "vix": vix,
                    "threshold": self.vix_threshold,
                }
            )

        # Check VIX change from entry
        vix_entry = market_data.get("vix_entry")
        if vix_entry is not None:
            vix_change = vix - vix_entry
            if vix_change > self.vix_change_threshold:
                return Decision(
                    action=DecisionAction.CLOSE,
                    reason=f"VIX exit: VIX +{vix_change:.1f} points > {self.vix_change_threshold}",
                    rule="vix_change",
                    urgency=Urgency.HIGH,
                    metadata={
                        "vix": vix,
                        "vix_entry": vix_entry,
                        "vix_change": vix_change,
                        "threshold": self.vix_change_threshold,
                    }
                )

        return None
