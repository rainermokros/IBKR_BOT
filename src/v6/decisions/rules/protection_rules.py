"""
Profit/Loss and Greek Risk Decision Rules

This module implements decision rules for profit/loss management and
Greek-based risk controls. These rules have Priority 2-5.5.

Rules:
- TakeProfit (Priority 2): UPL ≥ 80% → CLOSE (or ≥50% → close 50%)
- StopLoss (Priority 3): UPL ≤ -200% → CLOSE IMMEDIATE
- DeltaRisk (Priority 4): |net_delta| > 0.30 (IC) or >0.40 (spread) → CLOSE
- IVCrush (Priority 5): IV drop >30% AND profit >20% → CLOSE
- IVPercentileExit (Priority 5.5): IV <30th percentile AND profit >20% → CLOSE

Key patterns:
- Profit/loss management (Priority 2-3)
- Portfolio-level Greek risk (Priority 4)
- IV-based exits (Priority 5-5.5)
- Uses PortfolioRiskCalculator for delta checks

Reference: ../v5/caretaker/decision_engine.py for v5 logic
"""

from typing import Optional

from loguru import logger

from src.v6.decisions.models import Decision, DecisionAction, Urgency


class TakeProfit:
    """
    Take profit rule (Priority 2).

    Closes positions when profit targets are reached:
    - UPL ≥ 80% → CLOSE (full exit)
    - UPL ≥ 50% → CLOSE 50% of position (partial exit)

    Priority 2: Very high priority, after catastrophe protection.
    """

    priority = 2
    name = "take_profit"

    def __init__(self):
        """Initialize take profit rule."""
        self.full_tp_threshold = 0.80  # 80% → full exit
        self.partial_tp_threshold = 0.50  # 50% → close 50%
        self.partial_close_ratio = 0.50  # Close 50% of position

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None
    ) -> Optional[Decision]:
        """
        Evaluate take profit conditions.

        Args:
            snapshot: Position snapshot with unrealized_pnl, entry_price
            market_data: Not used for this rule

        Returns:
            Decision with CLOSE or REDUCE if triggered, None otherwise
        """
        try:
            unrealized_pnl = float(snapshot['unrealized_pnl'])
            entry_price = float(snapshot['entry_price'])
        except (KeyError, AttributeError, TypeError) as e:
            logger.warning(f"Could not calculate UPL for take profit: {e}")
            return None

        # Avoid division by zero
        if entry_price == 0:
            return None

        # Calculate UPL percentage
        upl_pct = unrealized_pnl / entry_price

        # Check full take profit
        if upl_pct >= self.full_tp_threshold:
            return Decision(
                action=DecisionAction.CLOSE,
                reason=f"Take profit: UPL {upl_pct*100:.1f}% >= {self.full_tp_threshold*100:.0f}%",
                rule="take_profit_full",
                urgency=Urgency.NORMAL,
                metadata={
                    "upl_pct": upl_pct,
                    "threshold": self.full_tp_threshold,
                }
            )

        # Check partial take profit
        if upl_pct >= self.partial_tp_threshold:
            return Decision(
                action=DecisionAction.REDUCE,
                reason=(
                    f"Partial take profit: UPL {upl_pct*100:.1f}% >= "
                    f"{self.partial_tp_threshold*100:.0f}%, close {self.partial_close_ratio*100:.0f}%"
                ),
                rule="take_profit_partial",
                urgency=Urgency.NORMAL,
                metadata={
                    "upl_pct": upl_pct,
                    "threshold": self.partial_tp_threshold,
                    "close_ratio": self.partial_close_ratio,
                }
            )

        return None


class StopLoss:
    """
    Stop loss rule (Priority 3).

    Closes positions when loss limits are breached:
    - UPL ≤ -200% → CLOSE IMMEDIATE (hard stop)
    - DTE < 7 AND UPL ≤ -50% → CLOSE IMMEDIATE (accelerated stop near expiry)

    Priority 3: Very high priority, after take profit.
    """

    priority = 3
    name = "stop_loss"

    def __init__(self):
        """Initialize stop loss rule."""
        self.hard_sl_threshold = -2.00  # -200% (hard stop)
        self.accelerated_sl_threshold = -0.50  # -50% (accelerated)
        self.accelerated_dte_threshold = 7  # Days to expiration

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None
    ) -> Optional[Decision]:
        """
        Evaluate stop loss conditions.

        Args:
            snapshot: Position snapshot with unrealized_pnl, entry_price, expiry
            market_data: Not used for this rule

        Returns:
            Decision with CLOSE + IMMEDIATE if triggered, None otherwise
        """
        try:
            unrealized_pnl = float(snapshot['unrealized_pnl'])
            entry_price = float(snapshot['entry_price'])
        except (KeyError, AttributeError, TypeError) as e:
            logger.warning(f"Could not calculate UPL for stop loss: {e}")
            return None

        # Avoid division by zero
        if entry_price == 0:
            return None

        # Calculate UPL percentage
        upl_pct = unrealized_pnl / entry_price

        # Check hard stop loss
        if upl_pct <= self.hard_sl_threshold:
            return Decision(
                action=DecisionAction.CLOSE,
                reason=f"Stop loss: UPL {upl_pct*100:.1f}% <= {self.hard_sl_threshold*100:.0f}%",
                rule="stop_loss_hard",
                urgency=Urgency.IMMEDIATE,
                metadata={
                    "upl_pct": upl_pct,
                    "threshold": self.hard_sl_threshold,
                }
            )

        # Check accelerated stop loss (near expiry)
        try:
            from datetime import date

            expiry = snapshot['expiry']

            # Handle both date and datetime
            if isinstance(expiry, date):
                expiry_date = expiry
            else:
                expiry_date = expiry.date()

            dte = (expiry_date - date.today()).days

            if dte < self.accelerated_dte_threshold and upl_pct <= self.accelerated_sl_threshold:
                return Decision(
                    action=DecisionAction.CLOSE,
                    reason=(
                        f"Accelerated stop loss: DTE={dte}, UPL {upl_pct*100:.1f}% <= "
                        f"{self.accelerated_sl_threshold*100:.0f}%"
                    ),
                    rule="stop_loss_accelerated",
                    urgency=Urgency.IMMEDIATE,
                    metadata={
                        "upl_pct": upl_pct,
                        "threshold": self.accelerated_sl_threshold,
                        "dte": dte,
                    }
                )
        except (KeyError, AttributeError, TypeError) as e:
            logger.debug(f"Could not check accelerated stop loss (DTE): {e}")

        return None


class DeltaRisk:
    """
    Portfolio delta risk rule (Priority 4).

    Checks portfolio-level delta exposure and closes positions if delta
    exceeds limits:
    - Iron Condors: |net_delta| > 0.30 → CLOSE
    - Vertical Spreads: |net_delta| > 0.40 → CLOSE

    Priority 4: High priority, after stop loss.

    This rule requires PortfolioRiskCalculator for portfolio-level delta checks.
    """

    priority = 4
    name = "delta_risk"

    def __init__(self):
        """Initialize delta risk rule."""
        self.ic_delta_limit = 0.30  # Iron Condor delta limit
        self.spread_delta_limit = 0.40  # Vertical spread delta limit

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None
    ) -> Optional[Decision]:
        """
        Evaluate portfolio delta risk conditions.

        Args:
            snapshot: Position snapshot with symbol, strategy_type
            market_data: Optional dict with portfolio-level data:
                - "portfolio_delta": Net portfolio delta
                - "delta_per_symbol": Dict of delta per symbol

        Returns:
            Decision with CLOSE if delta limit exceeded, None otherwise
        """
        if not market_data:
            return None

        try:
            strategy_type = str(snapshot['strategy_type'])
            symbol = str(snapshot['symbol'])
        except (KeyError, AttributeError, TypeError) as e:
            logger.warning(f"Could not extract position data for delta risk: {e}")
            return None

        # Get delta limit for this strategy type
        if strategy_type == 'iron_condor':
            delta_limit = self.ic_delta_limit
        elif strategy_type in ['vertical_spread', 'calendar_spread']:
            delta_limit = self.spread_delta_limit
        else:
            # No delta limit for other strategies
            return None

        # Check portfolio-level delta
        portfolio_delta = market_data.get("portfolio_delta")
        if portfolio_delta is None:
            return None

        if abs(portfolio_delta) > delta_limit:
            return Decision(
                action=DecisionAction.CLOSE,
                reason=(
                    f"Delta risk: Portfolio delta {portfolio_delta:.3f} exceeds "
                    f"limit {delta_limit:.2f} for {strategy_type}"
                ),
                rule="delta_risk_portfolio",
                urgency=Urgency.HIGH,
                metadata={
                    "portfolio_delta": portfolio_delta,
                    "delta_limit": delta_limit,
                    "strategy_type": strategy_type,
                }
            )

        # Check per-symbol delta (more granular)
        delta_per_symbol = market_data.get("delta_per_symbol", {})
        if delta_per_symbol and symbol in delta_per_symbol:
            symbol_delta = delta_per_symbol[symbol]
            if abs(symbol_delta) > delta_limit:
                return Decision(
                    action=DecisionAction.CLOSE,
                    reason=(
                        f"Delta risk: {symbol} delta {symbol_delta:.3f} exceeds "
                        f"limit {delta_limit:.2f}"
                    ),
                    rule="delta_risk_symbol",
                    urgency=Urgency.HIGH,
                    metadata={
                        "symbol": symbol,
                        "symbol_delta": symbol_delta,
                        "delta_limit": delta_limit,
                    }
                )

        return None


class IVCrush:
    """
    IV crush exit rule (Priority 5).

    Closes positions when IV drops significantly while in profit:
    - IV drop > 30% AND current profit > 20% → CLOSE

    Prevents IV crush from eroding gains after earnings or events.

    Priority 5: Medium-high priority, after delta risk.
    """

    priority = 5
    name = "iv_crush"

    def __init__(self):
        """Initialize IV crush rule."""
        self.iv_drop_threshold = -0.30  # -30% IV change
        self.profit_threshold = 0.20  # 20% profit required

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None
    ) -> Optional[Decision]:
        """
        Evaluate IV crush conditions.

        Args:
            snapshot: Position snapshot with unrealized_pnl, entry_price
            market_data: Optional dict with market data:
                - "iv_change_percent": IV change since entry (decimal)

        Returns:
            Decision with CLOSE if IV crush detected, None otherwise
        """
        if not market_data:
            return None

        iv_change = market_data.get("iv_change_percent")
        if iv_change is None:
            return None

        # Check IV drop threshold
        if iv_change > self.iv_drop_threshold:
            return None

        # Check profit threshold
        try:
            unrealized_pnl = float(snapshot['unrealized_pnl'])
            entry_price = float(snapshot['entry_price'])
        except (KeyError, AttributeError, TypeError) as e:
            logger.warning(f"Could not calculate UPL for IV crush: {e}")
            return None

        if entry_price == 0:
            return None

        upl_pct = unrealized_pnl / entry_price

        # Both conditions must be true
        if iv_change <= self.iv_drop_threshold and upl_pct >= self.profit_threshold:
            return Decision(
                action=DecisionAction.CLOSE,
                reason=(
                    f"IV crush: IV {iv_change*100:.1f}% (drop >{abs(self.iv_drop_threshold)*100:.0f}%), "
                    f"profit {upl_pct*100:.1f}% >= {self.profit_threshold*100:.0f}%"
                ),
                rule="iv_crush",
                urgency=Urgency.NORMAL,
                metadata={
                    "iv_change_percent": iv_change,
                    "upl_pct": upl_pct,
                    "iv_drop_threshold": self.iv_drop_threshold,
                    "profit_threshold": self.profit_threshold,
                }
            )

        return None


class IVPercentileExit:
    """
    IV percentile exit rule (Priority 5.5).

    Closes positions when IV is low (below 30th percentile) and in profit:
    - IV < 30th percentile AND current profit > 20% → CLOSE

    Low IV environment with profits = good exit signal (IV likely to rise).

    Priority 5.5: Medium priority, after IV crush.
    """

    priority = 5.5
    name = "iv_percentile_exit"

    def __init__(self):
        """Initialize IV percentile exit rule."""
        self.iv_percentile_threshold = 0.30  # 30th percentile
        self.profit_threshold = 0.20  # 20% profit required

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None
    ) -> Optional[Decision]:
        """
        Evaluate IV percentile exit conditions.

        Args:
            snapshot: Position snapshot with unrealized_pnl, entry_price
            market_data: Optional dict with market data:
                - "iv_percentile": Current IV percentile (0-1)

        Returns:
            Decision with CLOSE if IV percentile condition met, None otherwise
        """
        if not market_data:
            return None

        iv_percentile = market_data.get("iv_percentile")
        if iv_percentile is None:
            return None

        # Check IV percentile threshold
        if iv_percentile >= self.iv_percentile_threshold:
            return None

        # Check profit threshold
        try:
            unrealized_pnl = float(snapshot['unrealized_pnl'])
            entry_price = float(snapshot['entry_price'])
        except (KeyError, AttributeError, TypeError) as e:
            logger.warning(f"Could not calculate UPL for IV percentile exit: {e}")
            return None

        if entry_price == 0:
            return None

        upl_pct = unrealized_pnl / entry_price

        # Both conditions must be true
        if iv_percentile < self.iv_percentile_threshold and upl_pct >= self.profit_threshold:
            return Decision(
                action=DecisionAction.CLOSE,
                reason=(
                    f"IV percentile exit: IV {iv_percentile*100:.0f}th percentile < "
                    f"{self.iv_percentile_threshold*100:.0f}, profit {upl_pct*100:.1f}% >= "
                    f"{self.profit_threshold*100:.0f}%"
                ),
                rule="iv_percentile_exit",
                urgency=Urgency.NORMAL,
                metadata={
                    "iv_percentile": iv_percentile,
                    "upl_pct": upl_pct,
                    "iv_percentile_threshold": self.iv_percentile_threshold,
                    "profit_threshold": self.profit_threshold,
                }
            )

        return None
