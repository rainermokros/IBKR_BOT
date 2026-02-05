"""
Time and Gamma Risk Decision Rules

This module implements decision rules for time-based and gamma risk management.
These rules have Priority 6-8 (lower priority than protection rules).

Rules:
- DTERoll (Priority 6): 21-25 DTE → ROLL, ≤21 DTE → ROLL (force)
- GammaRisk (Priority 7): |gamma| > 0.10 AND DTE < 14 → CLOSE
- TimeExit (Priority 8): DTE ≤ 1 → CLOSE (last day before expiration)

Key patterns:
- Time-based roll decisions (Priority 6)
- Gamma risk near expiration (Priority 7)
- Time-based exit to avoid assignment risk (Priority 8)
- ROLL action includes metadata for execution layer

Reference: ../v5/caretaker/decision_engine.py for v5 logic
"""

from datetime import date, datetime
from typing import Optional

from loguru import logger

from v6.strategy_builder.decision_engine.models import Decision, DecisionAction, Urgency


class DTERoll:
    """
    DTE-based roll rule (Priority 6).

    Recommends rolling positions to 45 DTE:
    - 21 ≤ DTE ≤ 25 → ROLL (recommend roll to 45 DTE)
    - DTE ≤ 21 → ROLL (force roll to 45 DTE)

    Priority 6: Medium priority, after Greek risk rules.

    ROLL action means "close current position, open same strategy with 45 DTE".
    The execution layer (Phase 4) handles the actual roll operation.
    """

    priority = 6
    name = "dte_roll"

    def __init__(self):
        """Initialize DTE roll rule."""
        self.roll_start_dte = 25  # Start considering roll at 25 DTE
        self.roll_force_dte = 21  # Force roll at 21 DTE
        self.roll_to_dte = 45  # Target DTE for roll

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None
    ) -> Optional[Decision]:
        """
        Evaluate DTE roll conditions.

        Args:
            snapshot: Position snapshot with expiry date
            market_data: Not used for this rule

        Returns:
            Decision with ROLL action if DTE condition met, None otherwise
        """
        try:
            expiry = snapshot['expiry']

            # Handle both date and datetime
            if isinstance(expiry, datetime):
                expiry_date = expiry.date()
            else:
                expiry_date = expiry

            dte = (expiry_date - date.today()).days
        except (KeyError, AttributeError, TypeError) as e:
            logger.warning(f"Could not calculate DTE for roll rule: {e}")
            return None

        # Check if roll is needed
        if dte <= self.roll_start_dte:
            # Determine if this is a force roll
            is_force = dte <= self.roll_force_dte

            urgency = Urgency.HIGH if is_force else Urgency.NORMAL

            return Decision(
                action=DecisionAction.ROLL,
                reason=(
                    f"DTE roll: {dte} days (force={is_force}), roll to {self.roll_to_dte} DTE"
                ),
                rule="dte_roll",
                urgency=urgency,
                metadata={
                    "current_dte": dte,
                    "roll_to_dte": self.roll_to_dte,
                    "force_roll": is_force,
                }
            )

        return None


class GammaRisk:
    """
    Gamma risk exit rule (Priority 7).

    Closes positions when gamma is too high near expiration:
    - |gamma| > 0.10 AND DTE < 14 → CLOSE

    High gamma near expiration is dangerous because delta changes rapidly.

    Priority 7: Medium-low priority, after DTE roll.
    """

    priority = 7
    name = "gamma_risk"

    def __init__(self):
        """Initialize gamma risk rule."""
        self.gamma_threshold = 0.10  # Gamma threshold
        self.dte_threshold = 14  # Days to expiration

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None
    ) -> Optional[Decision]:
        """
        Evaluate gamma risk conditions.

        Args:
            snapshot: Position snapshot with gamma, expiry
            market_data: Not used for this rule

        Returns:
            Decision with CLOSE if gamma risk detected, None otherwise
        """
        try:
            # Get gamma from snapshot
            # Note: Greeks may be nested or flat depending on snapshot structure
            if hasattr(snapshot, 'gamma'):
                gamma = float(snapshot['gamma'])
            elif hasattr(snapshot, 'greeks'):
                # Greeks object
                greeks = snapshot['greeks']
                if hasattr(greeks, 'gamma'):
                    gamma = float(greeks['gamma'])
                else:
                    return None
            else:
                return None

            # Get DTE
            expiry = snapshot['expiry']
            if isinstance(expiry, datetime):
                expiry_date = expiry.date()
            else:
                expiry_date = expiry

            dte = (expiry_date - date.today()).days
        except (KeyError, AttributeError, TypeError) as e:
            logger.warning(f"Could not extract gamma/DTE for gamma risk: {e}")
            return None

        # Check gamma threshold
        if abs(gamma) <= self.gamma_threshold:
            return None

        # Check DTE threshold
        if dte >= self.dte_threshold:
            return None

        # Both conditions met: high gamma near expiration
        return Decision(
            action=DecisionAction.CLOSE,
            reason=(
                f"Gamma risk: |gamma| {abs(gamma):.3f} > {self.gamma_threshold:.2f}, "
                f"DTE {dte} < {self.dte_threshold}"
            ),
            rule="gamma_risk",
            urgency=Urgency.HIGH,
            metadata={
                "gamma": gamma,
                "dte": dte,
                "gamma_threshold": self.gamma_threshold,
                "dte_threshold": self.dte_threshold,
            }
        )


class TimeExit:
    """
    Time-based exit rule (Priority 8).

    Closes positions on the last day before expiration to avoid assignment risk:
    - DTE ≤ 1 → CLOSE

    Priority 8: Lowest priority, only executes if no other rules trigger.

    This is a safety net to prevent assignment risk on expiration day.
    """

    priority = 8
    name = "time_exit"

    def __init__(self):
        """Initialize time exit rule."""
        self.dte_threshold = 1  # Last day before expiration

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None
    ) -> Optional[Decision]:
        """
        Evaluate time exit conditions.

        Args:
            snapshot: Position snapshot with expiry
            market_data: Not used for this rule

        Returns:
            Decision with CLOSE if DTE condition met, None otherwise
        """
        try:
            expiry = snapshot['expiry']

            # Handle both date and datetime
            if isinstance(expiry, datetime):
                expiry_date = expiry.date()
            else:
                expiry_date = expiry

            dte = (expiry_date - date.today()).days
        except (KeyError, AttributeError, TypeError) as e:
            logger.warning(f"Could not calculate DTE for time exit: {e}")
            return None

        # Check DTE threshold
        if dte <= self.dte_threshold:
            return Decision(
                action=DecisionAction.CLOSE,
                reason=f"Time exit: DTE {dte} <= {self.dte_threshold} (avoid assignment risk)",
                rule="time_exit",
                urgency=Urgency.IMMEDIATE,
                metadata={
                    "dte": dte,
                    "threshold": self.dte_threshold,
                }
            )

        return None
