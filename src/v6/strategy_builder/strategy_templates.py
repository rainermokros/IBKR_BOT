"""
Strategy Templates Library

Provides reusable strategy templates for common options strategies.
Templates reduce code duplication and ensure consistent strategy generation.

Key patterns:
- StrategyTemplate: Abstract base class defining template interface
- StrategyTemplateRegistry: Template registration and creation
- Templates: IronCondor, CallSpread, PutSpread, Wheel
- Integration: Compatible with existing Strategy and LegSpec models
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Type
from uuid import uuid4

from loguru import logger

from v6.strategy_builder.models import (
    LegAction,
    LegSpec,
    OptionRight,
    Strategy,
    StrategyType,
)


@dataclass
class Greeks:
    """Options Greeks data model."""
    delta: float
    gamma: float
    theta: float
    vega: float

    def __add__(self, other: 'Greeks') -> 'Greeks':
        """Add two Greeks objects together."""
        return Greeks(
            delta=self.delta + other.delta,
            gamma=self.gamma + other.gamma,
            theta=self.theta + other.theta,
            vega=self.vega + other.vega
        )

    def __repr__(self) -> str:
        """Return string representation of Greeks."""
        return (
            f"Greeks(Δ={self.delta:.3f}, Γ={self.gamma:.3f}, "
            f"Θ={self.theta:.3f}, ν={self.vega:.3f})"
        )


class StrategyTemplate(ABC):
    """
    Abstract base class for strategy templates.

    Defines the interface that all strategy templates must implement.
    Templates encapsulate the logic for generating common options strategies.
    """

    @abstractmethod
    def generate_legs(
        self,
        symbol: str,
        direction: str,
        params: Dict[str, Any]
    ) -> List[LegSpec]:
        """
        Generate legs for this strategy template.

        Args:
            symbol: Underlying symbol (e.g., "SPY")
            direction: Trade direction ('bullish', 'bearish', 'neutral')
            params: Strategy-specific parameters

        Returns:
            List of LegSpec objects

        Raises:
            ValueError: If parameters are invalid
        """
        pass

    @abstractmethod
    def calculate_greeks(self, legs: List[LegSpec]) -> Greeks:
        """
        Calculate aggregate Greeks for all legs.

        Args:
            legs: List of LegSpec objects

        Returns:
            Greeks object with aggregate greeks
        """
        pass

    @abstractmethod
    def validate_params(self, params: Dict[str, Any]) -> bool:
        """
        Validate strategy parameters.

        Args:
            params: Strategy-specific parameters

        Returns:
            True if valid

        Raises:
            ValueError: If parameters are invalid
        """
        pass

    @abstractmethod
    def get_default_params(self) -> Dict[str, Any]:
        """
        Get default parameters for this strategy.

        Returns:
            Dict of default parameters
        """
        pass

    @abstractmethod
    def estimate_risk_reward(self, params: Dict[str, Any]) -> tuple[float, float]:
        """
        Estimate maximum profit and maximum loss for this strategy.

        Args:
            params: Strategy-specific parameters

        Returns:
            Tuple of (max_profit, max_loss)
        """
        pass

    def create_strategy(
        self,
        symbol: str,
        direction: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Strategy:
        """
        Create a Strategy object from this template.

        Args:
            symbol: Underlying symbol
            direction: Trade direction
            params: Strategy parameters (uses defaults if None)

        Returns:
            Strategy object

        Raises:
            ValueError: If parameters are invalid
        """
        # Use default params if none provided
        if params is None:
            params = self.get_default_params()

        # Validate params
        self.validate_params(params)

        # Generate legs
        legs = self.generate_legs(symbol, direction, params)

        # Create strategy
        strategy = Strategy(
            strategy_id=str(uuid4()),
            symbol=symbol,
            strategy_type=self.get_strategy_type(),
            legs=legs,
            entry_time=datetime.now(),
            metadata={'template': self.__class__.__name__, 'params': params}
        )

        logger.info(
            f"Created {self.__class__.__name__} strategy: "
            f"{symbol} {direction} with {len(legs)} legs"
        )

        return strategy

    @abstractmethod
    def get_strategy_type(self) -> StrategyType:
        """
        Get the StrategyType enum for this template.

        Returns:
            StrategyType enum value
        """
        pass


class StrategyTemplateRegistry:
    """
    Registry for strategy templates.

    Provides template registration, retrieval, and strategy creation.
    """

    def __init__(self):
        """Initialize registry with empty template mapping."""
        self._templates: Dict[str, Type[StrategyTemplate]] = {}

    def register_template(
        self,
        name: str,
        template_class: Type[StrategyTemplate]
    ) -> None:
        """
        Register a strategy template.

        Args:
            name: Template name (e.g., "iron_condor")
            template_class: StrategyTemplate subclass

        Raises:
            ValueError: If template already registered or not a StrategyTemplate
        """
        # Check if already registered
        if name in self._templates:
            raise ValueError(f"Template '{name}' already registered")

        # Check if it's a StrategyTemplate subclass
        if not issubclass(template_class, StrategyTemplate):
            raise ValueError(
                f"Template class must inherit from StrategyTemplate, "
                f"got {template_class}"
            )

        # Register
        self._templates[name] = template_class
        logger.info(f"✓ Registered strategy template: {name}")

    def get_template(self, name: str) -> StrategyTemplate:
        """
        Get a template instance by name.

        Args:
            name: Template name

        Returns:
            StrategyTemplate instance

        Raises:
            ValueError: If template not found
        """
        if name not in self._templates:
            available = ", ".join(self._templates.keys())
            raise ValueError(
                f"Template '{name}' not found. Available: {available}"
            )

        template_class = self._templates[name]
        return template_class()

    def list_templates(self) -> List[str]:
        """
        List all registered template names.

        Returns:
            List of template names
        """
        return list(self._templates.keys())

    def create_strategy(
        self,
        template_name: str,
        symbol: str,
        direction: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Strategy:
        """
        Create a strategy from a registered template.

        Args:
            template_name: Name of registered template
            symbol: Underlying symbol
            direction: Trade direction
            params: Strategy parameters (uses defaults if None)

        Returns:
            Strategy object

        Raises:
            ValueError: If template not found or parameters invalid
        """
        # Get template
        template = self.get_template(template_name)

        # Create strategy
        return template.create_strategy(symbol, direction, params)


# Global registry instance
_registry = StrategyTemplateRegistry()


def get_registry() -> StrategyTemplateRegistry:
    """
    Get the global strategy template registry.

    Returns:
        Global StrategyTemplateRegistry instance
    """
    return _registry


def register_template(name: str, template_class: Type[StrategyTemplate]) -> None:
    """
    Register a template in the global registry.

    Convenience function for registering templates.

    Args:
        name: Template name
        template_class: StrategyTemplate subclass
    """
    _registry.register_template(name, template_class)


class IronCondorTemplate(StrategyTemplate):
    """
    Iron Condor strategy template.

    Generates a 4-leg iron condor: long put, short put, short call, long call.
    Collects premium, profits from range-bound underlying, limited risk.

    Structure:
        - Long put (lower wing): protection
        - Short put (body): income
        - Short call (body): income
        - Long call (upper wing): protection
    """

    def generate_legs(
        self,
        symbol: str,
        direction: str,
        params: Dict[str, Any]
    ) -> List[LegSpec]:
        """
        Generate iron condor legs.

        Args:
            symbol: Underlying symbol
            direction: Trade direction (should be 'neutral' for IC)
            params: {
                'short_put_strike': float,
                'short_call_strike': float,
                'long_put_strike': float,
                'long_call_strike': float,
                'expiry': date,
                'quantity': int,
                'min_wing_width': float (optional, default 5)
            }

        Returns:
            List of 4 LegSpec objects

        Raises:
            ValueError: If parameters invalid or strike relationships wrong
        """
        # Extract parameters
        short_put_strike = params['short_put_strike']
        short_call_strike = params['short_call_strike']
        long_put_strike = params['long_put_strike']
        long_call_strike = params['long_call_strike']
        expiry = params['expiry']
        quantity = params['quantity']
        min_wing_width = params.get('min_wing_width', 5.0)

        # Validate strike relationships: long_put < short_put < short_call < long_call
        if not (long_put_strike < short_put_strike < short_call_strike < long_call_strike):
            raise ValueError(
                f"Invalid strike relationships for iron condor: "
                f"long_put ({long_put_strike}) < short_put ({short_put_strike}) < "
                f"short_call ({short_call_strike}) < long_call ({long_call_strike})"
            )

        # Validate wing widths
        put_wing_width = short_put_strike - long_put_strike
        call_wing_width = long_call_strike - short_call_strike

        if put_wing_width < min_wing_width:
            raise ValueError(
                f"Put wing width {put_wing_width} < min_wing_width {min_wing_width}"
            )

        if call_wing_width < min_wing_width:
            raise ValueError(
                f"Call wing width {call_wing_width} < min_wing_width {min_wing_width}"
            )

        # Generate legs
        legs = [
            # Long put (lower wing) - BUY
            LegSpec(
                right=OptionRight.PUT,
                strike=long_put_strike,
                quantity=quantity,
                action=LegAction.BUY,
                expiration=expiry,
                price=0.0  # Will be filled by market data
            ),
            # Short put (body) - SELL
            LegSpec(
                right=OptionRight.PUT,
                strike=short_put_strike,
                quantity=quantity,
                action=LegAction.SELL,
                expiration=expiry,
                price=0.0
            ),
            # Short call (body) - SELL
            LegSpec(
                right=OptionRight.CALL,
                strike=short_call_strike,
                quantity=quantity,
                action=LegAction.SELL,
                expiration=expiry,
                price=0.0
            ),
            # Long call (upper wing) - BUY
            LegSpec(
                right=OptionRight.CALL,
                strike=long_call_strike,
                quantity=quantity,
                action=LegAction.BUY,
                expiration=expiry,
                price=0.0
            ),
        ]

        logger.info(
            f"Generated iron condor legs: {symbol} "
            f"LP{long_put_strike}/SP{short_put_strike}/ "
            f"SC{short_call_strike}/LC{long_call_strike}"
        )

        return legs

    def calculate_greeks(self, legs: List[LegSpec]) -> Greeks:
        """
        Calculate aggregate greeks for iron condor.

        Iron condor should have:
        - Delta near 0 (balanced)
        - Gamma near 0 (balanced)
        - Theta positive (time decay works in favor)
        - Vega near 0 (balanced volatility exposure)

        Args:
            legs: List of 4 LegSpec objects

        Returns:
            Greeks object with aggregate values
        """
        # For now, return placeholder greeks
        # In production, would calculate from market data
        return Greeks(
            delta=0.0,   # Balanced
            gamma=0.0,   # Low gamma
            theta=0.5,   # Positive theta (time decay)
            vega=0.0     # Balanced vega
        )

    def validate_params(self, params: Dict[str, Any]) -> bool:
        """
        Validate iron condor parameters.

        Args:
            params: Strategy parameters

        Returns:
            True if valid

        Raises:
            ValueError: If parameters invalid
        """
        required = [
            'short_put_strike', 'short_call_strike',
            'long_put_strike', 'long_call_strike',
            'expiry', 'quantity'
        ]

        # Check all required params present
        for key in required:
            if key not in params:
                raise ValueError(f"Missing required parameter: {key}")

        # Validate strikes are positive
        for key in ['short_put_strike', 'short_call_strike', 'long_put_strike', 'long_call_strike']:
            if params[key] <= 0:
                raise ValueError(f"{key} must be positive, got {params[key]}")

        # Validate quantity
        if params['quantity'] <= 0:
            raise ValueError(f"quantity must be positive, got {params['quantity']}")

        # Validate expiry is in future
        if params['expiry'] <= date.today():
            raise ValueError(f"expiry must be in future, got {params['expiry']}")

        # Validate min_wing_width if provided
        if 'min_wing_width' in params:
            if params['min_wing_width'] <= 0:
                raise ValueError(f"min_wing_width must be positive, got {params['min_wing_width']}")

        return True

    def get_default_params(self) -> Dict[str, Any]:
        """
        Get default parameters for iron condor.

        Returns:
            Dict of default parameters
        """
        return {
            'wing_width': 10.0,          # Distance between short and long strikes
            'DTE': 35,                   # Days to expiration (30-45 day range)
            'delta_target': 0.20,        # Target delta for short strikes
            'min_wing_width': 5.0,       # Minimum wing width
            'quantity': 1
        }

    def estimate_risk_reward(self, params: Dict[str, Any]) -> tuple[float, float]:
        """
        Estimate max profit and max loss for iron condor.

        Args:
            params: Strategy parameters (should include 'net_premium')

        Returns:
            Tuple of (max_profit, max_loss)

        Note:
            Max profit: net premium collected (already total for position!)
            Max loss: (wing_width * 100 - net_premium) * quantity
        """
        # Net premium collected (positive = credit, already TOTAL for position)
        net_premium = params.get('net_premium', 0.0)

        # Wing width (assume symmetric)
        wing_width = params.get('wing_width', 10.0)

        # Quantity
        quantity = params.get('quantity', 1)

        # Max profit: premium collected (already total, don't multiply again!)
        max_profit = abs(net_premium)

        # Max loss: (wing_width * 100 - premium) * quantity
        max_loss = (wing_width * 100 * quantity) - abs(net_premium)

        return (max_profit, max_loss)

    def get_strategy_type(self) -> StrategyType:
        """Get strategy type enum."""
        return StrategyType.IRON_CONDOR


class CallSpreadTemplate(StrategyTemplate):
    """
    Call spread (vertical spread) strategy template.

    Generates a 2-leg call spread with bullish or bearish direction.
    Limited risk, limited reward vertical spread strategy.

    Bullish call spread (debit spread):
        - Buy lower strike call
        - Sell higher strike call
        - Profits from upward move

    Bearish call spread (credit spread):
        - Sell lower strike call
        - Buy higher strike call
        - Profits from downward or sideways move
    """

    def generate_legs(
        self,
        symbol: str,
        direction: str,
        params: Dict[str, Any]
    ) -> List[LegSpec]:
        """
        Generate call spread legs.

        Args:
            symbol: Underlying symbol
            direction: 'bullish' (debit) or 'bearish' (credit)
            params: {
                'short_call_strike': float,
                'long_call_strike': float,
                'expiry': date,
                'quantity': int,
                'min_spread': float (optional, default 5)
            }

        Returns:
            List of 2 LegSpec objects

        Raises:
            ValueError: If parameters invalid or strikes wrong
        """
        # Extract parameters
        short_call_strike = params['short_call_strike']
        long_call_strike = params['long_call_strike']
        expiry = params['expiry']
        quantity = params['quantity']
        min_spread = params.get('min_spread', 5.0)

        # Validate strikes
        if short_call_strike >= long_call_strike:
            raise ValueError(
                f"short_call_strike ({short_call_strike}) must be < "
                f"long_call_strike ({long_call_strike})"
            )

        # Validate spread width
        spread_width = long_call_strike - short_call_strike
        if spread_width < min_spread:
            raise ValueError(
                f"Spread width {spread_width} < min_spread {min_spread}"
            )

        # Generate legs based on direction
        if direction == 'bullish':
            # Debit spread: buy lower, sell higher
            legs = [
                LegSpec(
                    right=OptionRight.CALL,
                    strike=short_call_strike,
                    quantity=quantity,
                    action=LegAction.BUY,  # Long lower strike
                    expiration=expiry,
                    price=0.0
                ),
                LegSpec(
                    right=OptionRight.CALL,
                    strike=long_call_strike,
                    quantity=quantity,
                    action=LegAction.SELL,  # Short higher strike
                    expiration=expiry,
                    price=0.0
                ),
            ]
        elif direction == 'bearish':
            # Credit spread: sell lower, buy higher
            legs = [
                LegSpec(
                    right=OptionRight.CALL,
                    strike=short_call_strike,
                    quantity=quantity,
                    action=LegAction.SELL,  # Short lower strike
                    expiration=expiry,
                    price=0.0
                ),
                LegSpec(
                    right=OptionRight.CALL,
                    strike=long_call_strike,
                    quantity=quantity,
                    action=LegAction.BUY,  # Long higher strike
                    expiration=expiry,
                    price=0.0
                ),
            ]
        else:
            raise ValueError(f"Invalid direction: {direction}. Use 'bullish' or 'bearish'")

        logger.info(
            f"Generated {direction} call spread: {symbol} "
            f"{'B' if direction == 'bullish' else 'S'}C{short_call_strike}/"
            f"{'S' if direction == 'bullish' else 'B'}C{long_call_strike}"
        )

        return legs

    def calculate_greeks(self, legs: List[LegSpec]) -> Greeks:
        """
        Calculate aggregate greeks for call spread.

        Bullish (debit): Positive delta, negative theta, negative vega
        Bearish (credit): Negative delta, positive theta, positive vega

        Args:
            legs: List of 2 LegSpec objects

        Returns:
            Greeks object with aggregate values
        """
        # Determine direction from legs
        long_leg = next((leg for leg in legs if leg.action == LegAction.BUY), None)
        short_leg = next((leg for leg in legs if leg.action == LegAction.SELL), None)

        # Check if bullish (buy lower strike)
        if long_leg and short_leg and long_leg.strike < short_leg.strike:
            # Bullish: positive delta
            return Greeks(
                delta=0.30,   # Positive delta
                gamma=0.05,   # Low gamma
                theta=-0.10,  # Negative theta (time decay works against)
                vega=-0.15    # Negative vega
            )
        else:
            # Bearish: negative delta
            return Greeks(
                delta=-0.30,   # Negative delta
                gamma=-0.05,   # Low gamma
                theta=0.10,    # Positive theta (time decay works in favor)
                vega=0.15      # Positive vega
            )

    def validate_params(self, params: Dict[str, Any]) -> bool:
        """
        Validate call spread parameters.

        Args:
            params: Strategy parameters

        Returns:
            True if valid

        Raises:
            ValueError: If parameters invalid
        """
        required = ['short_call_strike', 'long_call_strike', 'expiry', 'quantity']

        for key in required:
            if key not in params:
                raise ValueError(f"Missing required parameter: {key}")

        # Validate strikes
        if params['short_call_strike'] <= 0:
            raise ValueError("short_call_strike must be positive")

        if params['long_call_strike'] <= 0:
            raise ValueError("long_call_strike must be positive")

        # Validate quantity
        if params['quantity'] <= 0:
            raise ValueError("quantity must be positive")

        # Validate expiry
        if params['expiry'] <= date.today():
            raise ValueError("expiry must be in future")

        # Validate min_spread if provided
        if 'min_spread' in params and params['min_spread'] <= 0:
            raise ValueError("min_spread must be positive")

        return True

    def get_default_params(self) -> Dict[str, Any]:
        """
        Get default parameters for call spread.

        Returns:
            Dict of default parameters
        """
        return {
            'spread_width': 5.0,      # Distance between strikes
            'DTE': 35,                # Days to expiration
            'delta_target': 0.30,     # Target delta for long leg
            'min_spread': 5.0,        # Minimum spread width
            'quantity': 1
        }

    def estimate_risk_reward(self, params: Dict[str, Any]) -> tuple[float, float]:
        """
        Estimate max profit and max loss for call spread.

        Args:
            params: Strategy parameters (should include 'net_premium' and 'direction')

        Returns:
            Tuple of (max_profit, max_loss)

        Note:
            Bullish (debit): Max profit = spread - debit paid, Max loss = debit paid
            Bearish (credit): Max profit = credit received, Max loss = spread - credit
            net_premium is already TOTAL for position (don't multiply by 100!)
        """
        net_premium = params.get('net_premium', 0.0)
        spread_width = params.get('spread_width', 5.0)
        quantity = params.get('quantity', 1)
        direction = params.get('direction', 'bullish')

        if direction == 'bullish':
            # Debit spread: paid premium
            max_loss = abs(net_premium)
            max_profit = (spread_width * 100 * quantity) - abs(net_premium)
        else:
            # Credit spread: received premium
            max_profit = abs(net_premium)
            max_loss = (spread_width * 100 * quantity) - abs(net_premium)

        return (max_profit, max_loss)

    def get_strategy_type(self) -> StrategyType:
        """Get strategy type enum."""
        return StrategyType.VERTICAL_SPREAD


class PutSpreadTemplate(StrategyTemplate):
    """
    Put spread (vertical spread) strategy template.

    Generates a 2-leg put spread with bullish or bearish direction.
    Limited risk, limited reward vertical spread strategy.

    Bullish put spread (credit spread):
        - Sell higher strike put
        - Buy lower strike put
        - Profits from upward or sideways move

    Bearish put spread (debit spread):
        - Buy higher strike put
        - Sell lower strike put
        - Profits from downward move
    """

    def generate_legs(
        self,
        symbol: str,
        direction: str,
        params: Dict[str, Any]
    ) -> List[LegSpec]:
        """
        Generate put spread legs.

        Args:
            symbol: Underlying symbol
            direction: 'bullish' (credit) or 'bearish' (debit)
            params: {
                'short_put_strike': float,
                'long_put_strike': float,
                'expiry': date,
                'quantity': int,
                'min_spread': float (optional, default 5)
            }

        Returns:
            List of 2 LegSpec objects

        Raises:
            ValueError: If parameters invalid or strikes wrong
        """
        # Extract parameters
        short_put_strike = params['short_put_strike']
        long_put_strike = params['long_put_strike']
        expiry = params['expiry']
        quantity = params['quantity']
        min_spread = params.get('min_spread', 5.0)

        # Validate strikes
        if short_put_strike <= long_put_strike:
            raise ValueError(
                f"short_put_strike ({short_put_strike}) must be > "
                f"long_put_strike ({long_put_strike})"
            )

        # Validate spread width
        spread_width = short_put_strike - long_put_strike
        if spread_width < min_spread:
            raise ValueError(
                f"Spread width {spread_width} < min_spread {min_spread}"
            )

        # Generate legs based on direction
        if direction == 'bullish':
            # Credit spread: sell higher, buy lower
            legs = [
                LegSpec(
                    right=OptionRight.PUT,
                    strike=short_put_strike,
                    quantity=quantity,
                    action=LegAction.SELL,  # Short higher strike
                    expiration=expiry,
                    price=0.0
                ),
                LegSpec(
                    right=OptionRight.PUT,
                    strike=long_put_strike,
                    quantity=quantity,
                    action=LegAction.BUY,  # Long lower strike
                    expiration=expiry,
                    price=0.0
                ),
            ]
        elif direction == 'bearish':
            # Debit spread: buy higher, sell lower
            legs = [
                LegSpec(
                    right=OptionRight.PUT,
                    strike=short_put_strike,
                    quantity=quantity,
                    action=LegAction.BUY,  # Long higher strike
                    expiration=expiry,
                    price=0.0
                ),
                LegSpec(
                    right=OptionRight.PUT,
                    strike=long_put_strike,
                    quantity=quantity,
                    action=LegAction.SELL,  # Short lower strike
                    expiration=expiry,
                    price=0.0
                ),
            ]
        else:
            raise ValueError(f"Invalid direction: {direction}. Use 'bullish' or 'bearish'")

        logger.info(
            f"Generated {direction} put spread: {symbol} "
            f"{'S' if direction == 'bullish' else 'B'}P{short_put_strike}/"
            f"{'B' if direction == 'bullish' else 'S'}P{long_put_strike}"
        )

        return legs

    def calculate_greeks(self, legs: List[LegSpec]) -> Greeks:
        """
        Calculate aggregate greeks for put spread.

        Bullish (credit): Negative delta, positive theta, negative vega
        Bearish (debit): Negative delta, negative theta, positive vega

        Args:
            legs: List of 2 LegSpec objects

        Returns:
            Greeks object with aggregate values
        """
        # Determine direction from legs
        long_leg = next((leg for leg in legs if leg.action == LegAction.BUY), None)
        short_leg = next((leg for leg in legs if leg.action == LegAction.SELL), None)

        # Check if bullish (sell higher strike)
        if short_leg and long_leg and short_leg.strike > long_leg.strike:
            # Bullish: negative delta
            return Greeks(
                delta=-0.25,   # Negative delta
                gamma=-0.05,   # Low gamma
                theta=0.10,    # Positive theta (time decay works in favor)
                vega=-0.15     # Negative vega
            )
        else:
            # Bearish: negative delta (larger magnitude)
            return Greeks(
                delta=-0.40,   # More negative delta
                gamma=0.05,    # Low gamma
                theta=-0.10,   # Negative theta (time decay works against)
                vega=0.15      # Positive vega
            )

    def validate_params(self, params: Dict[str, Any]) -> bool:
        """
        Validate put spread parameters.

        Args:
            params: Strategy parameters

        Returns:
            True if valid

        Raises:
            ValueError: If parameters invalid
        """
        required = ['short_put_strike', 'long_put_strike', 'expiry', 'quantity']

        for key in required:
            if key not in params:
                raise ValueError(f"Missing required parameter: {key}")

        # Validate strikes
        if params['short_put_strike'] <= 0:
            raise ValueError("short_put_strike must be positive")

        if params['long_put_strike'] <= 0:
            raise ValueError("long_put_strike must be positive")

        # Validate quantity
        if params['quantity'] <= 0:
            raise ValueError("quantity must be positive")

        # Validate expiry
        if params['expiry'] <= date.today():
            raise ValueError("expiry must be in future")

        # Validate min_spread if provided
        if 'min_spread' in params and params['min_spread'] <= 0:
            raise ValueError("min_spread must be positive")

        return True

    def get_default_params(self) -> Dict[str, Any]:
        """
        Get default parameters for put spread.

        Returns:
            Dict of default parameters
        """
        return {
            'spread_width': 5.0,      # Distance between strikes
            'DTE': 35,                # Days to expiration
            'delta_target': 0.25,     # Target delta for short leg
            'min_spread': 5.0,        # Minimum spread width
            'quantity': 1
        }

    def estimate_risk_reward(self, params: Dict[str, Any]) -> tuple[float, float]:
        """
        Estimate max profit and max loss for put spread.

        Args:
            params: Strategy parameters (should include 'net_premium' and 'direction')

        Returns:
            Tuple of (max_profit, max_loss)

        Note:
            Bullish (credit): Max profit = credit received, Max loss = spread - credit
            Bearish (debit): Max profit = spread - debit paid, Max loss = debit paid
            net_premium is already TOTAL for position (don't multiply by 100!)
        """
        net_premium = params.get('net_premium', 0.0)
        spread_width = params.get('spread_width', 5.0)
        quantity = params.get('quantity', 1)
        direction = params.get('direction', 'bullish')

        if direction == 'bullish':
            # Credit spread: received premium
            max_profit = abs(net_premium)
            max_loss = (spread_width * 100 * quantity) - abs(net_premium)
        else:
            # Debit spread: paid premium
            max_loss = abs(net_premium)
            max_profit = (spread_width * 100 * quantity) - abs(net_premium)

        return (max_profit, max_loss)

    def get_strategy_type(self) -> StrategyType:
        """Get strategy type enum."""
        return StrategyType.VERTICAL_SPREAD


class WheelTemplate(StrategyTemplate):
    """
    Wheel strategy template.

    Generates a wheel strategy: cash-secured put -> assignment -> covered call.
    Income-generating strategy that collects premium through option selling.

    Phases:
        - Cash-secured put phase: Sell OTM puts to collect premium
        - Assignment phase: Buy 100 shares per contract if assigned
        - Covered call phase: Sell covered calls while holding shares
    """

    def generate_legs(
        self,
        symbol: str,
        direction: str,
        params: Dict[str, Any]
    ) -> List[LegSpec]:
        """
        Generate wheel strategy legs.

        Args:
            symbol: Underlying symbol
            direction: Trade direction ('bullish' for wheel)
            params: {
                'strike': float,
                'expiry': date,
                'quantity': int,
                'phase': str ('put' or 'covered_call'),
                'share_price': float (optional, for covered call phase)
            }

        Returns:
            List of 1-2 LegSpec objects (1 for put, 2 for covered call)

        Raises:
            ValueError: If parameters invalid or phase not recognized
        """
        # Extract parameters
        strike = params['strike']
        expiry = params['expiry']
        quantity = params['quantity']
        phase = params.get('phase', 'put')

        # Validate phase
        if phase not in ('put', 'covered_call'):
            raise ValueError(
                f"Invalid phase: {phase}. Use 'put' or 'covered_call'"
            )

        if phase == 'put':
            # Cash-secured put phase: sell OTM put
            legs = [
                LegSpec(
                    right=OptionRight.PUT,
                    strike=strike,
                    quantity=quantity,
                    action=LegAction.SELL,  # Sell put for premium
                    expiration=expiry,
                    price=0.0
                ),
            ]

            logger.info(
                f"Generated wheel put leg: {symbol} "
                f"SP{strike} (cash-secured put)"
            )
        else:
            # Covered call phase: sell covered call
            share_price = params.get('share_price')

            # Validate share price provided
            if not share_price or share_price <= 0:
                raise ValueError(
                    f"share_price must be provided and positive for covered call phase, "
                    f"got {share_price}"
                )

            legs = [
                # Long shares (simulated as cash equivalent)
                LegSpec(
                    right=OptionRight.CALL,  # Use CALL to represent shares
                    strike=share_price,
                    quantity=quantity * 100,  # 100 shares per contract
                    action=LegAction.BUY,
                    expiration=expiry,
                    price=0.0
                ),
                # Short covered call
                LegSpec(
                    right=OptionRight.CALL,
                    strike=strike,
                    quantity=quantity,
                    action=LegAction.SELL,
                    expiration=expiry,
                    price=0.0
                ),
            ]

            logger.info(
                f"Generated wheel covered call legs: {symbol} "
                f"long shares + SC{strike}"
            )

        return legs

    def calculate_greeks(self, legs: List[LegSpec]) -> Greeks:
        """
        Calculate aggregate greeks for wheel strategy.

        Short put phase: negative delta, negative theta, positive vega
        Covered call phase: negative delta (reduced), negative theta, negative vega

        Args:
            legs: List of LegSpec objects

        Returns:
            Greeks object with aggregate values
        """
        # Check if put phase (1 leg) or covered call phase (2+ legs)
        if len(legs) == 1 and legs[0].right == OptionRight.PUT:
            # Short put phase
            return Greeks(
                delta=-0.20,   # Negative delta (short put)
                gamma=-0.05,   # Low gamma
                theta=0.10,    # Positive theta (time decay works in favor)
                vega=0.15      # Positive vega (short option)
            )
        else:
            # Covered call phase
            return Greeks(
                delta=-0.10,   # Reduced negative delta (shares + short call)
                gamma=-0.03,   # Low gamma
                theta=0.05,    # Positive theta (time decay)
                vega=-0.10     # Negative vega (short call)
            )

    def validate_params(self, params: Dict[str, Any]) -> bool:
        """
        Validate wheel strategy parameters.

        Args:
            params: Strategy parameters

        Returns:
            True if valid

        Raises:
            ValueError: If parameters invalid
        """
        required = ['strike', 'expiry', 'quantity']

        # Check all required params present
        for key in required:
            if key not in params:
                raise ValueError(f"Missing required parameter: {key}")

        # Validate strike is positive
        if params['strike'] <= 0:
            raise ValueError(f"strike must be positive, got {params['strike']}")

        # Validate quantity is multiple of 100 (standard contract size)
        if params['quantity'] % 100 != 0:
            raise ValueError(
                f"quantity must be in multiples of 100 (standard contract size), "
                f"got {params['quantity']}"
            )

        if params['quantity'] <= 0:
            raise ValueError(f"quantity must be positive, got {params['quantity']}")

        # Validate expiry is in future
        if params['expiry'] <= date.today():
            raise ValueError(f"expiry must be in future, got {params['expiry']}")

        # Validate phase if provided
        phase = params.get('phase')
        if phase and phase not in ('put', 'covered_call'):
            raise ValueError(
                f"Invalid phase: {phase}. Use 'put' or 'covered_call'"
            )

        # Validate share_price if covered call phase
        if phase == 'covered_call':
            share_price = params.get('share_price')
            if not share_price or share_price <= 0:
                raise ValueError(
                    f"share_price must be provided and positive for covered call phase"
                )

        return True

    def get_default_params(self) -> Dict[str, Any]:
        """
        Get default parameters for wheel strategy.

        Returns:
            Dict of default parameters
        """
        return {
            'DTE_target': 30,          # Days to expiration target (20-45 day range)
            'delta_target': 0.20,      # Target delta for short puts/calls
            'roll_threshold': 0.10,    # Delta threshold for rolling
            'capital_allocation': 0.10, # Fraction of capital to allocate
            'quantity': 100,           # 1 contract (100 shares)
            'phase': 'put'             # Start in put phase
        }

    def estimate_risk_reward(self, params: Dict[str, Any]) -> tuple[float, float]:
        """
        Estimate max profit and max loss for wheel strategy.

        Args:
            params: Strategy parameters

        Returns:
            Tuple of (avg_monthly_premium_estimate, max_downside)

        Note:
            Max profit (put phase): premium collected
            Max loss (put phase): strike * 100 * quantity - premium
            Ongoing: sum of premiums collected over cycles
        """
        strike = params.get('strike', 100.0)
        premium = params.get('premium', 2.0)  # Assume $2.00 premium
        quantity = params.get('quantity', 100)
        phase = params.get('phase', 'put')

        if phase == 'put':
            # Cash-secured put phase
            max_profit = premium * quantity  # Premium collected
            max_loss = (strike * quantity) - (premium * quantity)  # Strike cost - premium
        else:
            # Covered call phase - estimate ongoing income
            # Average monthly premium estimate
            avg_monthly_premium = premium * quantity * 12 / 30  # Rough estimate
            max_profit = avg_monthly_premium
            max_loss = (strike * quantity) - (premium * quantity)  # Share downside

        return (max_profit, max_loss)

    def get_strategy_type(self) -> StrategyType:
        """Get strategy type enum."""
        return StrategyType.CUSTOM  # Wheel is a custom strategy type
