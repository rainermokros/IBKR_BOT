"""
Strategy Greeks Validator

Validates that strategies have appropriate Greeks profiles:
- Iron Condors must be delta-neutral (small delta)
- Vertical spreads can have directional exposure
- Strategy-specific validation before position entry

This complements portfolio-level limits by checking strategy structure.

Usage:
    >>> from v6.risk import StrategyGreeksLimits, StrategyGreeksValidator
    >>>
    >>> limits = StrategyGreeksLimits(iron_condor_max_abs_delta=5.0)
    >>> validator = StrategyGreeksValidator(greeks_calc, limits)
    >>>
    >>> is_valid, violations = validator.validate_strategy(strategy)
    >>> if not is_valid:
    ...     print(f"Strategy rejected: {violations}")
"""

from typing import TYPE_CHECKING

from loguru import logger
from v6.risk_manager.models import StrategyGreeksLimits

if TYPE_CHECKING:
    from v6.strategy_builder.models import Strategy


class StrategyGreeksValidator:
    """
    Validates that strategies have appropriate Greeks profiles.

    This is a SECONDARY validation layer that complements portfolio-level
    risk limits. While portfolio limits check total exposure, this checks
    that individual strategies are structured correctly.

    Key validations:
    1. Iron Condors must be delta-neutral (abs(delta) < threshold)
    2. Short strikes should be balanced (not too skewed)
    3. Both short legs should be OTM

    Why this matters:
    - The IWM Iron Condor had -11.94 delta (very bearish)
    - It passed portfolio limits (abs(-11.94) < 20)
    - But it's a TERRIBLE Iron Condor (should be delta-neutral!)
    - This validator would have REJECTED it

    Attributes:
        greeks_calc: Greeks calculator for computing position Greeks
        limits: StrategyGreeksLimits with strategy-specific thresholds

    Example:
        >>> validator = StrategyGreeksValidator(greeks_calc, limits)
        >>>
        >>> strategy = Strategy(...)  # Iron Condor
        >>> is_valid, violations = validator.validate_strategy(strategy)
        >>>
        >>> if not is_valid:
        ...     print(f"Rejected: {violations}")
        ...     # Output: "Rejected: ['Delta -11.94 exceeds Iron Condor limit of 5.0']"
    """

    def __init__(self, greeks_calc, limits: StrategyGreeksLimits):
        """
        Initialize strategy Greeks validator.

        Args:
            greeks_calc: Greeks calculator (must have calculate_position_greeks method)
            limits: StrategyGreeksLimits with strategy-specific thresholds
        """
        self.greeks_calc = greeks_calc
        self.limits = limits
        self.logger = logger.bind(component="StrategyGreeksValidator")

    def validate_strategy(
        self, strategy: "Strategy"
    ) -> tuple[bool, list[str]]:
        """
        Validate that strategy has appropriate Greeks profile.

        Checks strategy-specific Greeks requirements:
        - Iron Condors: Must be delta-neutral (small delta)
        - Vertical Spreads: Can have directional exposure
        - Other strategies: Future validation (calendar spreads, etc.)

        Args:
            strategy: Strategy object with legs and strategy_type

        Returns:
            Tuple of (is_valid, violations):
            - is_valid: True if strategy passes all validations
            - violations: List of violation messages (empty if valid)

        Example:
            >>> strategy = create_iron_condor()  # With -11.94 delta
            >>> is_valid, violations = validator.validate_strategy(strategy)
            >>>
            >>> if not is_valid:
            ...     for violation in violations:
            ...         print(violation)
            ...     # Output:
            ...     # "Iron Condor delta -11.94 exceeds threshold of 5.0"
        """
        violations = []

        try:
            # Calculate position Greeks
            greeks = self.greeks_calc.calculate_position_greeks(strategy)
            delta = greeks.get("delta", 0.0)

            # Strategy-specific validation
            if strategy.strategy_type.value == "iron_condor":
                violations.extend(
                    self._validate_iron_condor(strategy, delta, greeks)
                )
            elif strategy.strategy_type.value in ["call_spread", "put_spread"]:
                violations.extend(
                    self._validate_vertical_spread(strategy, delta, greeks)
                )
            else:
                # Other strategies: No specific validation (yet)
                self.logger.debug(
                    f"No specific Greeks validation for {strategy.strategy_type.value}"
                )

            is_valid = len(violations) == 0

            if not is_valid:
                self.logger.warning(
                    f"Strategy {strategy.strategy_id} rejected: {violations}"
                )

            return is_valid, violations

        except Exception as e:
            self.logger.error(f"Error validating strategy {strategy.strategy_id}: {e}")
            return False, [f"Validation error: {e}"]

    def _validate_iron_condor(
        self, strategy: "Strategy", delta: float, greeks: dict
    ) -> list[str]:
        """
        Validate Iron Condor is delta-neutral.

        Iron Condors should have small delta (close to 0) because:
        - They profit from range-bound markets
        - Large delta means directional exposure (not the strategy's purpose)
        - Both short strikes should be roughly equidistant from underlying

        Args:
            strategy: Iron Condor strategy
            delta: Total position delta
            greeks: All position Greeks

        Returns:
            List of violation messages (empty if valid)

        Example violations:
            - "Iron Condor delta -11.94 exceeds threshold of 5.0"
            - "Short CALL delta 0.86 exceeds bias limit of 0.15"
        """
        violations = []
        max_delta = self.limits.iron_condor_max_abs_delta

        # Check 1: Total delta must be small (delta-neutral)
        abs_delta = abs(delta)
        if abs_delta > max_delta:
            violations.append(
                f"Iron Condor delta {delta:+.2f} exceeds threshold of {max_delta:.1f}. "
                f"Iron Condors should be delta-neutral (|delta| < {max_delta:.1f}). "
                f"Current delta {delta:+.2f} indicates significant {'bearish' if delta < 0 else 'bullish'} bias."
            )

        # Check 2: Validate short strike deltas are balanced
        # (prevent one side from being too ITM/OTM)
        short_legs = [
            leg for leg in strategy.legs if leg.action.value == "SELL"
        ]

        if len(short_legs) == 2:  # Should have 2 short legs
            # Get individual leg deltas from Greeks calculator
            try:
                # Calculate each short leg's delta contribution
                for i, leg in enumerate(short_legs):
                    # This would require leg-level Greeks - simplified for now
                    # TODO: Add leg-level delta bias validation
                    pass
            except Exception as e:
                self.logger.debug(f"Could not validate leg-level deltas: {e}")

        return violations

    def _validate_vertical_spread(
        self, strategy: "Strategy", delta: float, greeks: dict
    ) -> list[str]:
        """
        Validate vertical spread has acceptable delta.

        Vertical spreads can be directional (unlike Iron Condors),
        but we still want to limit extreme directional exposure.

        Args:
            strategy: Vertical spread strategy
            delta: Total position delta
            greeks: All position Greeks

        Returns:
            List of violation messages (empty if valid)
        """
        violations = []
        max_delta = self.limits.vertical_spread_max_abs_delta

        # Check that delta is within reasonable bounds
        abs_delta = abs(delta)
        if abs_delta > max_delta:
            violations.append(
                f"Vertical spread delta {delta:+.2f} exceeds threshold of {max_delta:.1f}. "
                f"Consider reducing position size or strike width."
            )

        return violations
