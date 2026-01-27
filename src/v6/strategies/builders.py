"""
Strategy Builders for Options Trading

This module provides builder classes for constructing common options strategies.
Builders generate leg specifications based on market conditions and risk parameters.

Key patterns:
- Protocol-based interfaces (from Phase 3)
- dataclass(slots=True) for performance
- Validation in build() and validate() methods
- Type hints for all fields

Supported strategies:
- Iron Condor: Sell OTM put spread + sell OTM call spread
- Vertical Spread: Buy ITM, sell OTM (same expiration)
- Custom: User-defined multi-leg strategies
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol
from loguru import logger

from src.v6.strategies.models import (
    LegSpec,
    Strategy,
    StrategyType,
    OptionRight,
    LegAction,
)


class StrategyBuilder(Protocol):
    """
    Strategy builder protocol.

    All strategy builders must implement this protocol.
    """

    priority: int
    name: str

    def build(
        self,
        symbol: str,
        underlying_price: float,
        params: dict
    ) -> Strategy:
        """
        Build a strategy from parameters.

        Args:
            symbol: Underlying symbol
            underlying_price: Current underlying price
            params: Strategy-specific parameters

        Returns:
            Strategy with leg specifications
        """
        ...

    def validate(self, strategy: Strategy) -> bool:
        """
        Validate a strategy.

        Args:
            strategy: Strategy to validate

        Returns:
            True if valid, False otherwise
        """
        ...


@dataclass(slots=True)
class IronCondorBuilder:
    """
    Iron Condor strategy builder.

    Builds a 4-leg iron condor: sell OTM put spread + sell OTM call spread.

    Example structure:
        - Long Put (lower strike, protection)
        - Short Put (middle strike, credit)
        - Short Call (middle strike, credit)
        - Long Call (higher strike, protection)

    Parameters:
        - put_width: Width of put spread (default: 10)
        - call_width: Width of call spread (default: 10)
        - dte: Days to expiration (default: 45)
        - delta_target: Target delta for short strikes (default: 16, i.e., 0.16 delta)
    """

    priority: int = 10
    name: str = "IronCondorBuilder"

    def build(
        self,
        symbol: str,
        underlying_price: float,
        params: dict
    ) -> Strategy:
        """
        Build an iron condor strategy.

        Args:
            symbol: Underlying symbol
            underlying_price: Current underlying price
            params: Strategy parameters (put_width, call_width, dte, delta_target)

        Returns:
            Strategy with 4 leg specifications

        Raises:
            ValueError: If parameters are invalid
        """
        # Extract parameters with defaults
        put_width = params.get("put_width", 10)
        call_width = params.get("call_width", 10)
        dte = params.get("dte", 45)
        delta_target = params.get("delta_target", 0.16)

        # Validate parameters
        if put_width <= 0:
            raise ValueError(f"put_width must be positive, got {put_width}")
        if call_width <= 0:
            raise ValueError(f"call_width must be positive, got {call_width}")
        if dte <= 0:
            raise ValueError(f"dte must be positive, got {dte}")
        if not (0 < delta_target < 1):
            raise ValueError(f"delta_target must be between 0 and 1, got {delta_target}")

        # Calculate expiration date
        expiration = date.today() + timedelta(days=dte)

        # Calculate strikes (simplified - in production would use option chain data)
        # Short strikes are OTM (approximately delta_target away from ATM)
        # For simplicity, we estimate using underlying price

        # Short call strike (OTM, above current price)
        # Delta 0.16 ≈ 5-10% OTM, use 7% as approximation
        short_call_strike = round((underlying_price * 1.07) / 5) * 5
        long_call_strike = short_call_strike + call_width

        # Short put strike (OTM, below current price)
        # Delta 0.16 ≈ 5-10% OTM, use 7% as approximation
        short_put_strike = round((underlying_price * 0.93) / 5) * 5
        long_put_strike = short_put_strike - put_width

        # Ensure proper structure: LP < SP < SC < LC
        if long_put_strike >= short_put_strike:
            long_put_strike = short_put_strike - put_width
        if short_put_strike >= short_call_strike:
            # Adjust to prevent overlap
            midpoint = underlying_price / 5 * 5
            short_put_strike = midpoint - 5
            short_call_strike = midpoint + 5
            long_put_strike = short_put_strike - put_width
            long_call_strike = short_call_strike + call_width

        # Build legs
        legs = [
            # Long Put (lower strike, protection)
            LegSpec(
                right=OptionRight.PUT,
                strike=long_put_strike,
                quantity=1,
                action=LegAction.BUY,
                expiration=expiration
            ),
            # Short Put (middle strike, credit)
            LegSpec(
                right=OptionRight.PUT,
                strike=short_put_strike,
                quantity=1,
                action=LegAction.SELL,
                expiration=expiration
            ),
            # Short Call (middle strike, credit)
            LegSpec(
                right=OptionRight.CALL,
                strike=short_call_strike,
                quantity=1,
                action=LegAction.SELL,
                expiration=expiration
            ),
            # Long Call (higher strike, protection)
            LegSpec(
                right=OptionRight.CALL,
                strike=long_call_strike,
                quantity=1,
                action=LegAction.BUY,
                expiration=expiration
            ),
        ]

        # Create strategy
        strategy = Strategy(
            strategy_id=f"IC_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            symbol=symbol,
            strategy_type=StrategyType.IRON_CONDOR,
            legs=legs,
            entry_time=datetime.now(),
            status="OPEN",
            metadata={
                "put_width": put_width,
                "call_width": call_width,
                "dte": dte,
                "delta_target": delta_target,
                "underlying_price": underlying_price,
            }
        )

        logger.info(
            f"Built Iron Condor for {symbol}: "
            f"LP=${long_put_strike}, SP=${short_put_strike}, "
            f"SC=${short_call_strike}, LC=${long_call_strike}"
        )

        return strategy

    def validate(self, strategy: Strategy) -> bool:
        """
        Validate an iron condor strategy.

        Checks:
        - Has exactly 4 legs
        - Strikes are in correct order (LP < SP < SC < LC)
        - Put spread width matches call spread width (optional warning)
        - All legs have same expiration

        Args:
            strategy: Strategy to validate

        Returns:
            True if valid, False otherwise
        """
        # Check leg count
        if len(strategy.legs) != 4:
            logger.error(f"Iron Condor must have 4 legs, got {len(strategy.legs)}")
            return False

        # Extract legs by action and right
        legs_by_type = {}
        for leg in strategy.legs:
            key = f"{leg.action.value}_{leg.right.value}"
            legs_by_type[key] = leg

        # Verify all required legs exist
        required = ["BUY_PUT", "SELL_PUT", "SELL_CALL", "BUY_CALL"]
        for req in required:
            if req not in legs_by_type:
                logger.error(f"Iron Condor missing leg type: {req}")
                return False

        # Get strikes
        lp_strike = legs_by_type["BUY_PUT"].strike
        sp_strike = legs_by_type["SELL_PUT"].strike
        sc_strike = legs_by_type["SELL_CALL"].strike
        lc_strike = legs_by_type["BUY_CALL"].strike

        # Verify strike order: LP < SP < SC < LC
        if not (lp_strike < sp_strike < sc_strike < lc_strike):
            logger.error(
                f"Iron Condor strikes out of order: "
                f"LP={lp_strike}, SP={sp_strike}, SC={sc_strike}, LC={lc_strike}"
            )
            return False

        # Verify same expiration
        expirations = {leg.expiration for leg in strategy.legs}
        if len(expirations) != 1:
            logger.error(f"Iron Condor legs must have same expiration, got {expirations}")
            return False

        # Check widths are positive
        put_width = sp_strike - lp_strike
        call_width = lc_strike - sc_strike
        if put_width <= 0 or call_width <= 0:
            logger.error(f"Iron Condor widths must be positive: put={put_width}, call={call_width}")
            return False

        logger.info(f"✓ Iron Condor validation passed for {strategy.symbol}")
        return True


@dataclass(slots=True)
class VerticalSpreadBuilder:
    """
    Vertical spread strategy builder.

    Builds a 2-leg vertical spread: buy ITM option, sell OTM option (same expiration).

    Supports:
        - Bullish: Buy lower strike call, sell higher strike call (debit call spread)
        - Bearish: Buy higher strike put, sell lower strike put (debit put spread)

    Parameters:
        - direction: "BULL" or "BEAR"
        - width: Width between strikes (default: 10)
        - dte: Days to expiration (default: 45)
        - delta_target: Target delta for short strike (default: 0.30)
    """

    priority: int = 11
    name: str = "VerticalSpreadBuilder"

    def build(
        self,
        symbol: str,
        underlying_price: float,
        params: dict
    ) -> Strategy:
        """
        Build a vertical spread strategy.

        Args:
            symbol: Underlying symbol
            underlying_price: Current underlying price
            params: Strategy parameters (direction, width, dte, delta_target)

        Returns:
            Strategy with 2 leg specifications

        Raises:
            ValueError: If parameters are invalid
        """
        # Extract parameters with defaults
        direction = params.get("direction", "BULL").upper()
        width = params.get("width", 10)
        dte = params.get("dte", 45)
        delta_target = params.get("delta_target", 0.30)

        # Validate parameters
        if direction not in ("BULL", "BEAR"):
            raise ValueError(f"direction must be BULL or BEAR, got {direction}")
        if width <= 0:
            raise ValueError(f"width must be positive, got {width}")
        if dte <= 0:
            raise ValueError(f"dte must be positive, got {dte}")
        if not (0 < delta_target < 1):
            raise ValueError(f"delta_target must be between 0 and 1, got {delta_target}")

        # Calculate expiration date
        expiration = date.today() + timedelta(days=dte)

        # Build based on direction
        if direction == "BULL":
            # Bull call spread: buy lower strike call, sell higher strike call
            long_strike = round(underlying_price / 5) * 5  # ATM
            short_strike = long_strike + width

            legs = [
                # Long Call (ITM or ATM)
                LegSpec(
                    right=OptionRight.CALL,
                    strike=long_strike,
                    quantity=1,
                    action=LegAction.BUY,
                    expiration=expiration
                ),
                # Short Call (OTM)
                LegSpec(
                    right=OptionRight.CALL,
                    strike=short_strike,
                    quantity=1,
                    action=LegAction.SELL,
                    expiration=expiration
                ),
            ]
        else:  # BEAR
            # Bear put spread: buy higher strike put, sell lower strike put
            long_strike = round(underlying_price / 5) * 5  # ATM
            short_strike = long_strike - width

            legs = [
                # Long Put (ITM or ATM)
                LegSpec(
                    right=OptionRight.PUT,
                    strike=long_strike,
                    quantity=1,
                    action=LegAction.BUY,
                    expiration=expiration
                ),
                # Short Put (OTM)
                LegSpec(
                    right=OptionRight.PUT,
                    strike=short_strike,
                    quantity=1,
                    action=LegAction.SELL,
                    expiration=expiration
                ),
            ]

        # Create strategy
        strategy = Strategy(
            strategy_id=f"VS_{direction}_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            symbol=symbol,
            strategy_type=StrategyType.VERTICAL_SPREAD,
            legs=legs,
            entry_time=datetime.now(),
            status="OPEN",
            metadata={
                "direction": direction,
                "width": width,
                "dte": dte,
                "delta_target": delta_target,
                "underlying_price": underlying_price,
            }
        )

        logger.info(
            f"Built {direction}ish Vertical Spread for {symbol}: "
            f"long=${legs[0].strike}, short=${legs[1].strike}"
        )

        return strategy

    def validate(self, strategy: Strategy) -> bool:
        """
        Validate a vertical spread strategy.

        Checks:
        - Has exactly 2 legs
        - Both legs have same right (CALL or PUT)
        - Both legs have same expiration
        - One leg is BUY, one is SELL
        - Strikes are different

        Args:
            strategy: Strategy to validate

        Returns:
            True if valid, False otherwise
        """
        # Check leg count
        if len(strategy.legs) != 2:
            logger.error(f"Vertical Spread must have 2 legs, got {len(strategy.legs)}")
            return False

        leg1, leg2 = strategy.legs[0], strategy.legs[1]

        # Check same right
        if leg1.right != leg2.right:
            logger.error(f"Vertical Spread legs must have same right, got {leg1.right} and {leg2.right}")
            return False

        # Check same expiration
        if leg1.expiration != leg2.expiration:
            logger.error(f"Vertical Spread legs must have same expiration")
            return False

        # Check one BUY, one SELL
        actions = {leg1.action, leg2.action}
        if actions != {LegAction.BUY, LegAction.SELL}:
            logger.error(f"Vertical Spread must have one BUY and one SELL, got {actions}")
            return False

        # Check different strikes
        if leg1.strike == leg2.strike:
            logger.error(f"Vertical Spread legs must have different strikes")
            return False

        logger.info(f"✓ Vertical Spread validation passed for {strategy.symbol}")
        return True


@dataclass(slots=True)
class CustomStrategyBuilder:
    """
    Custom strategy builder.

    Builds a user-defined multi-leg strategy from leg specifications.

    Parameters:
        - legs: List of leg dictionaries with keys: right, strike, quantity, action, expiration
    """

    priority: int = 12
    name: str = "CustomStrategyBuilder"

    def build(
        self,
        symbol: str,
        underlying_price: float,
        params: dict
    ) -> Strategy:
        """
        Build a custom strategy from leg specifications.

        Args:
            symbol: Underlying symbol
            underlying_price: Current underlying price (not used, but kept for interface consistency)
            params: Strategy parameters with 'legs' key containing list of leg dicts

        Returns:
            Strategy with custom leg specifications

        Raises:
            ValueError: If parameters are invalid
        """
        # Extract legs from params
        legs_data = params.get("legs", [])

        if not legs_data:
            raise ValueError("Custom strategy must have at least one leg")

        # Build leg specifications
        legs = []
        for i, leg_data in enumerate(legs_data):
            try:
                right = OptionRight[leg_data["right"].upper()]
                action = LegAction[leg_data["action"].upper()]
            except KeyError as e:
                raise ValueError(f"Invalid leg spec at index {i}: {e}")

            leg = LegSpec(
                right=right,
                strike=float(leg_data["strike"]),
                quantity=int(leg_data["quantity"]),
                action=action,
                expiration=date.fromisoformat(leg_data["expiration"])
            )
            legs.append(leg)

        # Create strategy
        strategy = Strategy(
            strategy_id=f"CUSTOM_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            symbol=symbol,
            strategy_type=StrategyType.CUSTOM,
            legs=legs,
            entry_time=datetime.now(),
            status="OPEN",
            metadata={
                "underlying_price": underlying_price,
                "custom_legs": len(legs),
            }
        )

        logger.info(f"Built Custom strategy for {symbol} with {len(legs)} legs")

        return strategy

    def validate(self, strategy: Strategy) -> bool:
        """
        Validate a custom strategy.

        Checks:
        - Has at least 1 leg
        - All legs have valid strikes and expirations

        Args:
            strategy: Strategy to validate

        Returns:
            True if valid, False otherwise
        """
        # Check leg count
        if len(strategy.legs) < 1:
            logger.error(f"Custom strategy must have at least 1 leg, got {len(strategy.legs)}")
            return False

        # Legs are already validated in LegSpec.__post_init__
        # Just check that we have at least one leg
        logger.info(f"✓ Custom strategy validation passed for {strategy.symbol}")
        return True
