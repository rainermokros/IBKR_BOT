"""
Bracket Order Manager

Manages bracket orders with automatic stop-loss and take-profit.
Enforces max stop-loss of 2x net premium for risk management.

Key features:
- Bracket creation with entry + SL + TP orders
- Max stop-loss enforcement (2x net_premium)
- SL/TP adjustment methods
- Trailing stop functionality

Usage:
    from v6.system_monitor.execution_system import BracketOrderManager
    from v6.utils import IBConnectionManager

    ib_conn = IBConnectionManager()
    bracket_manager = BracketOrderManager(ib_conn)

    # Create bracket
    bracket_id = await bracket_manager.create_bracket(
        entry_order=entry_order,
        stop_loss_price=stop_price,
        take_profit_price=tp_price,
    )
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import uuid4

from ib_async import Contract, LimitOrder, StopOrder

from v6.system_monitor.execution_engine.engine import OrderExecutionEngine
from v6.system_monitor.execution_engine.models import (
    BracketOrder,
    ExecutionResult,
    Order,
    OrderAction,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from v6.utils.ib_connection import IBConnectionManager

logger = logging.getLogger(__name__)


class BracketOrderManager:
    """
    Manage bracket orders with automatic stop-loss and take-profit.

    Bracket orders consist of:
    - Entry order (parent)
    - Stop loss order (child)
    - Take profit order (child)

    When entry fills, SL and TP activate. When SL or TP hits, the other cancels.

    Attributes:
        ib_conn: IB connection manager
        engine: Order execution engine
        active_brackets: Dict of active bracket orders
        order_to_bracket_map: Mapping from order_id to bracket_id
    """

    def __init__(
        self,
        ib_conn: IBConnectionManager,
        order_writer: Optional[Any] = None,
    ):
        """
        Initialize bracket order manager.

        Args:
            ib_conn: IB connection manager
            order_writer: Optional order writer for persistence
        """
        self.ib_conn = ib_conn
        self.order_writer = order_writer

        # Create execution engine
        self.engine = OrderExecutionEngine(ib_conn, dry_run=False)

        # Active brackets tracking
        self.active_brackets: dict[str, dict[str, Any]] = {}

        # Order to bracket mapping
        self.order_to_bracket_map: dict[str, str] = {}

        logger.info("BracketOrderManager initialized")

    async def create_bracket(
        self,
        entry_order: Order,
        stop_loss_price: float,
        take_profit_price: Optional[float] = None,
        max_sl_ratio: float = 1.5,  # Changed from 2.0 to 1.5 per user requirement
        entry_contract: Optional[Contract] = None,
    ) -> str:
        """
        Create a bracket order with entry, stop loss, and take profit.

        Args:
            entry_order: Entry order (must have net_premium in metadata)
            stop_loss_price: Stop loss price
            take_profit_price: Take profit price (optional, calculated if None)
            max_sl_ratio: Max stop loss as ratio of net_premium (default: 1.5 - user requirement)
            entry_contract: IB contract for entry order

        Returns:
            bracket_id: Unique identifier for the bracket

        Raises:
            ValueError: If validation fails or SL exceeds max
            ConnectionError: If IB connection fails
        """
        # Validate entry_order has net_premium
        net_premium = entry_order.metadata.get("net_premium") if hasattr(entry_order, "metadata") else None

        if net_premium is None:
            raise ValueError("entry_order must have 'net_premium' in metadata")

        net_premium = float(net_premium)

        # Calculate max stop loss
        max_stop_loss = net_premium * max_sl_ratio

        # Validate stop loss price
        if abs(stop_loss_price) > max_stop_loss:
            raise ValueError(
                f"Stop loss ${stop_loss_price:.2f} exceeds max "
                f"${max_stop_loss:.2f} (1.5x net_premium ${net_premium:.2f})"
            )

        # Calculate take profit if not provided
        if take_profit_price is None:
            # Default: entry_price + net_premium (for calls) or entry_price - net_premium (for puts)
            # Simplified: use 0.5 * net_premium as TP target
            take_profit_price = net_premium * 0.5
            logger.info(f"Calculated take profit: ${take_profit_price:.2f}")

        # Generate bracket ID
        bracket_id = str(uuid4())

        # Generate OCA group ID for SL/TP linkage
        oca_group = f"BRACKET_{bracket_id}"

        logger.info(
            f"Creating bracket {bracket_id}: "
            f"entry=${net_premium:.2f}, SL=${stop_loss_price:.2f}, "
            f"TP=${take_profit_price:.2f}, max SL=${max_stop_loss:.2f}"
        )

        # Create stop loss order
        stop_loss_order = Order(
            order_id=str(uuid4()),
            conid=entry_order.conid,
            action=(
                OrderAction.SELL if entry_order.action == OrderAction.BUY
                else OrderAction.BUY
            ),
            quantity=entry_order.quantity,
            order_type=OrderType.STOP,
            limit_price=None,
            stop_price=stop_loss_price,
            tif=TimeInForce.GTC,  # Good till cancelled
            good_till_date=None,
            status=OrderStatus.PENDING_SUBMIT,
            filled_quantity=0,
            avg_fill_price=None,
            order_ref=None,
            parent_order_id=entry_order.order_id,
            oca_group=oca_group,
            created_at=datetime.now(),
            filled_at=None,
        )

        # Create take profit order
        take_profit_order = Order(
            order_id=str(uuid4()),
            conid=entry_order.conid,
            action=(
                OrderAction.SELL if entry_order.action == OrderAction.BUY
                else OrderAction.BUY
            ),
            quantity=entry_order.quantity,
            order_type=OrderType.LIMIT,
            limit_price=take_profit_price,
            stop_price=None,
            tif=TimeInForce.GTC,
            good_till_date=None,
            status=OrderStatus.PENDING_SUBMIT,
            filled_quantity=0,
            avg_fill_price=None,
            order_ref=None,
            parent_order_id=entry_order.order_id,
            oca_group=oca_group,
            created_at=datetime.now(),
            filled_at=None,
        )

        # Create bracket order model
        bracket = BracketOrder(
            parent_order=entry_order,
            take_profit=take_profit_order,
            stop_loss=stop_loss_order,
            oca_group=oca_group,
        )

        # Submit bracket via execution engine
        if entry_contract:
            result = await self.engine.place_bracket_order(
                bracket=bracket,
                entry_contract=entry_contract,
                tp_contract=entry_contract,  # Same contract
                sl_contract=entry_contract,  # Same contract
            )

            if not result.success:
                raise ValueError(f"Failed to place bracket order: {result.error_message}")

        # Store bracket tracking
        self.active_brackets[bracket_id] = {
            "entry_order_id": entry_order.order_id,
            "stop_loss_order_id": stop_loss_order.order_id,
            "take_profit_order_id": take_profit_order.order_id,
            "status": "pending",
            "oca_group": oca_group,
            "net_premium": net_premium,
            "stop_loss_price": stop_loss_price,
            "take_profit_price": take_profit_price,
            "max_sl_ratio": max_sl_ratio,
            "created_at": datetime.now(),
        }

        # Map orders to bracket
        self.order_to_bracket_map[entry_order.order_id] = bracket_id
        self.order_to_bracket_map[stop_loss_order.order_id] = bracket_id
        self.order_to_bracket_map[take_profit_order.order_id] = bracket_id

        logger.info(f"Bracket {bracket_id} created successfully")

        return bracket_id

    async def cancel_bracket(self, bracket_id: str) -> bool:
        """
        Cancel all orders in a bracket.

        Args:
            bracket_id: Bracket ID to cancel

        Returns:
            True if all cancellations succeeded, False otherwise
        """
        if bracket_id not in self.active_brackets:
            logger.warning(f"Bracket {bracket_id} not found for cancellation")
            return False

        bracket = self.active_brackets[bracket_id]

        if bracket["status"] in ("stopped_out", "profit_taken", "cancelled"):
            logger.info(
                f"Bracket {bracket_id} already {bracket['status']}, skipping cancellation"
            )
            return True

        logger.info(f"Cancelling bracket {bracket_id}")

        all_succeeded = True

        # Cancel entry order (if not filled)
        entry_order_id = bracket["entry_order_id"]
        try:
            if await self.engine.cancel_order(entry_order_id):
                logger.info(f"Entry order {entry_order_id} cancelled")
            else:
                all_succeeded = False
        except Exception as e:
            logger.error(f"Failed to cancel entry order: {e}")
            all_succeeded = False

        # Cancel stop loss order
        sl_order_id = bracket["stop_loss_order_id"]
        try:
            if await self.engine.cancel_order(sl_order_id):
                logger.info(f"Stop loss order {sl_order_id} cancelled")
            else:
                all_succeeded = False
        except Exception as e:
            logger.error(f"Failed to cancel stop loss order: {e}")
            all_succeeded = False

        # Cancel take profit order
        tp_order_id = bracket["take_profit_order_id"]
        try:
            if await self.engine.cancel_order(tp_order_id):
                logger.info(f"Take profit order {tp_order_id} cancelled")
            else:
                all_succeeded = False
        except Exception as e:
            logger.error(f"Failed to cancel take profit order: {e}")
            all_succeeded = False

        # Update status
        bracket["status"] = "cancelled"

        return all_succeeded

    async def get_bracket_status(self, bracket_id: str) -> dict[str, Any]:
        """
        Query status of all orders in a bracket.

        Args:
            bracket_id: Bracket ID to query

        Returns:
            Dict with keys:
                - bracket_id: str
                - entry_status: str
                - stop_loss_status: str
                - take_profit_status: str
                - overall_status: str ('pending', 'active', 'stopped_out', 'profit_taken', 'cancelled')
        """
        if bracket_id not in self.active_brackets:
            raise ValueError(f"Bracket {bracket_id} not found")

        bracket = self.active_brackets[bracket_id]

        # Query order status from IB (simplified - would use actual IB queries)
        # For now, use cached status
        entry_status = "Submitted"  # Would query IB
        sl_status = "Submitted"
        tp_status = "Submitted"

        # Determine overall status
        if bracket["status"] == "cancelled":
            overall_status = "cancelled"
        elif bracket["status"] == "stopped_out":
            overall_status = "stopped_out"
        elif bracket["status"] == "profit_taken":
            overall_status = "profit_taken"
        elif entry_status == "Filled":
            overall_status = "active"  # Entry filled, SL/TP working
        else:
            overall_status = "pending"  # Entry not filled

        return {
            "bracket_id": bracket_id,
            "entry_status": entry_status,
            "stop_loss_status": sl_status,
            "take_profit_status": tp_status,
            "overall_status": overall_status,
            "oca_group": bracket.get("oca_group"),
        }

    async def adjust_stop_loss(
        self,
        bracket_id: str,
        new_stop_price: float,
    ) -> bool:
        """
        Adjust stop loss price for an active bracket.

        Args:
            bracket_id: Bracket ID
            new_stop_price: New stop loss price

        Returns:
            True if adjustment succeeded, False otherwise

        Raises:
            ValueError: If bracket is not active
        """
        if bracket_id not in self.active_brackets:
            raise ValueError(f"Bracket {bracket_id} not found")

        bracket = self.active_brackets[bracket_id]

        # Only allow adjustment if bracket is active
        if bracket["status"] not in ("pending", "active"):
            raise ValueError(
                f"Cannot adjust stop loss: bracket is {bracket['status']}"
            )

        # Validate new stop price against max
        max_stop_loss = bracket["net_premium"] * bracket["max_sl_ratio"]
        if abs(new_stop_price) > max_stop_loss:
            raise ValueError(
                f"New stop loss ${new_stop_price:.2f} exceeds max "
                f"${max_stop_loss:.2f}"
            )

        logger.info(
            f"Adjusting stop loss for bracket {bracket_id}: "
            f"${bracket['stop_loss_price']:.2f} -> ${new_stop_price:.2f}"
        )

        # Cancel existing stop loss order
        sl_order_id = bracket["stop_loss_order_id"]
        try:
            if not await self.engine.cancel_order(sl_order_id):
                logger.error(f"Failed to cancel old stop loss order")
                return False
        except Exception as e:
            logger.error(f"Error cancelling stop loss: {e}")
            return False

        # Create new stop loss order
        new_sl_order = Order(
            order_id=str(uuid4()),
            conid=None,  # Will be assigned
            action=OrderAction.SELL,  # Simplified
            quantity=1,
            order_type=OrderType.STOP,
            limit_price=None,
            stop_price=new_stop_price,
            tif=TimeInForce.GTC,
            good_till_date=None,
            status=OrderStatus.PENDING_SUBMIT,
            filled_quantity=0,
            avg_fill_price=None,
            order_ref=None,
            parent_order_id=bracket["entry_order_id"],
            oca_group=bracket["oca_group"],
            created_at=datetime.now(),
            filled_at=None,
        )

        # Update bracket tracking
        old_sl_order_id = bracket["stop_loss_order_id"]
        bracket["stop_loss_order_id"] = new_sl_order.order_id
        bracket["stop_loss_price"] = new_stop_price

        # Update mapping
        del self.order_to_bracket_map[old_sl_order_id]
        self.order_to_bracket_map[new_sl_order.order_id] = bracket_id

        logger.info(f"Stop loss adjusted to ${new_stop_price:.2f}")

        return True

    async def adjust_take_profit(
        self,
        bracket_id: str,
        new_tp_price: float,
    ) -> bool:
        """
        Adjust take profit price for an active bracket.

        Args:
            bracket_id: Bracket ID
            new_tp_price: New take profit price

        Returns:
            True if adjustment succeeded, False otherwise

        Raises:
            ValueError: If bracket is not active
        """
        if bracket_id not in self.active_brackets:
            raise ValueError(f"Bracket {bracket_id} not found")

        bracket = self.active_brackets[bracket_id]

        # Only allow adjustment if bracket is active
        if bracket["status"] not in ("pending", "active"):
            raise ValueError(
                f"Cannot adjust take profit: bracket is {bracket['status']}"
            )

        logger.info(
            f"Adjusting take profit for bracket {bracket_id}: "
            f"${bracket['take_profit_price']:.2f} -> ${new_tp_price:.2f}"
        )

        # Cancel existing take profit order
        tp_order_id = bracket["take_profit_order_id"]
        try:
            if not await self.engine.cancel_order(tp_order_id):
                logger.error(f"Failed to cancel old take profit order")
                return False
        except Exception as e:
            logger.error(f"Error cancelling take profit: {e}")
            return False

        # Create new take profit order
        new_tp_order = Order(
            order_id=str(uuid4()),
            conid=None,
            action=OrderAction.SELL,
            quantity=1,
            order_type=OrderType.LIMIT,
            limit_price=new_tp_price,
            stop_price=None,
            tif=TimeInForce.GTC,
            good_till_date=None,
            status=OrderStatus.PENDING_SUBMIT,
            filled_quantity=0,
            avg_fill_price=None,
            order_ref=None,
            parent_order_id=bracket["entry_order_id"],
            oca_group=bracket["oca_group"],
            created_at=datetime.now(),
            filled_at=None,
        )

        # Update bracket tracking
        old_tp_order_id = bracket["take_profit_order_id"]
        bracket["take_profit_order_id"] = new_tp_order.order_id
        bracket["take_profit_price"] = new_tp_price

        # Update mapping
        del self.order_to_bracket_map[old_tp_order_id]
        self.order_to_bracket_map[new_tp_order.order_id] = bracket_id

        logger.info(f"Take profit adjusted to ${new_tp_price:.2f}")

        return True

    async def trail_stop_loss(
        self,
        bracket_id: str,
        trail_amount: float,
        current_price: float,
        direction: str = "long",
    ) -> bool:
        """
        Implement trailing stop: adjust SL as price moves favorably.

        Args:
            bracket_id: Bracket ID
            trail_amount: Amount to trail (e.g., 0.50 for $0.50)
            current_price: Current market price
            direction: 'long' or 'short'

        Returns:
            True if trail succeeded, False otherwise
        """
        if bracket_id not in self.active_brackets:
            raise ValueError(f"Bracket {bracket_id} not found")

        bracket = self.active_brackets[bracket_id]

        current_stop = bracket["stop_loss_price"]

        # Calculate new stop based on direction
        if direction == "long":
            # For long: trail up as price rises
            # New stop = current_price - trail_amount
            new_stop = current_price - trail_amount

            # Only trail if new stop is higher (better) than current stop
            if new_stop <= current_stop:
                logger.info(
                    f"Price ${current_price:.2f} not favorable enough to trail: "
                    f"current SL=${current_stop:.2f}, new SL=${new_stop:.2f}"
                )
                return False

        else:  # short
            # For short: trail down as price falls
            # New stop = current_price + trail_amount
            new_stop = current_price + trail_amount

            # Only trail if new stop is lower (better) than current stop
            if new_stop >= current_stop:
                logger.info(
                    f"Price ${current_price:.2f} not favorable enough to trail: "
                    f"current SL=${current_stop:.2f}, new SL=${new_stop:.2f}"
                )
                return False

        logger.info(
            f"Trailing stop loss for bracket {bracket_id}: "
            f"${current_stop:.2f} -> ${new_stop:.2f} "
            f"(current price: ${current_price:.2f}, trail: ${trail_amount:.2f})"
        )

        # Call adjust_stop_loss
        return await self.adjust_stop_loss(bracket_id, new_stop)

    async def create_strategy_bracket(
        self,
        strategy: Any,
        max_sl_ratio: float = 1.5,  # Changed from 2.0 to 1.5 per user requirement
    ) -> str:
        """
        Create a bracket for a strategy based on its type.

        Calculates stop loss and take profit based on strategy type:
        - Iron Condor: SL at 1.5x net_premium, TP at 0.5x net_premium
        - Credit Spread: SL at 1.5x spread_width, TP at 0.8x net_premium
        - Debit Spread: SL at premium paid, TP at spread_width - premium
        - Wheel: SL at roll_down_threshold, TP at roll_up_threshold

        Args:
            strategy: Strategy object with legs and metadata
            max_sl_ratio: Max stop loss as ratio of net_premium (default: 1.5 - user requirement)

        Returns:
            bracket_id: Bracket ID for monitoring
        """
        if not hasattr(strategy, "legs") or not strategy.legs:
            raise ValueError("Strategy must have legs")

        # Get net premium from strategy
        net_premium = strategy.metadata.get("net_premium", 0.0)
        if not net_premium:
            # Calculate from leg prices
            net_premium = sum(leg.price * leg.quantity for leg in strategy.legs)

        # Get strategy type
        strategy_type = strategy.strategy_type.value if hasattr(strategy.strategy_type, "value") else strategy.strategy_type

        # Calculate SL and TP based on strategy type
        if strategy_type == "iron_condor":
            # Iron Condor: SL at wing_width, TP at 0.5 * premium
            wing_width = strategy.metadata.get("wing_width", 10.0)
            stop_loss_price = wing_width
            take_profit_price = net_premium * 0.5

        elif strategy_type == "vertical_spread":
            # Vertical spread: check if credit or debit
            spread_width = strategy.metadata.get("spread_width", 5.0)

            # Determine if credit spread (selling) or debit spread (buying)
            sell_legs = [leg for leg in strategy.legs if leg.action.value == "SELL"]
            if len(sell_legs) > 0:
                # Credit spread: SL at spread_width, TP at keep full credit
                stop_loss_price = spread_width
                take_profit_price = net_premium * 0.8  # Keep 80% of credit
            else:
                # Debit spread: SL at premium paid, TP at spread_width
                stop_loss_price = net_premium
                take_profit_price = spread_width - net_premium

        elif strategy_type == "custom":
            # Wheel strategy
            roll_threshold = strategy.metadata.get("roll_threshold", 0.10)
            stop_loss_price = roll_threshold * 100  # Convert to price
            take_profit_price = net_premium * 0.5

        else:
            # Default: generic SL/TP
            stop_loss_price = net_premium * 2.0
            take_profit_price = net_premium * 0.5

        # Create entry order from first leg
        first_leg = strategy.legs[0]
        entry_order = Order(
            order_id=str(uuid4()),
            conid=None,
            action=first_leg.action,
            quantity=first_leg.quantity,
            order_type=OrderType.LIMIT,
            limit_price=first_leg.price,
            stop_price=None,
            tif=TimeInForce.DAY,
            good_till_date=None,
            status=OrderStatus.PENDING_SUBMIT,
            filled_quantity=0,
            avg_fill_price=None,
            order_ref=None,
            parent_order_id=None,
            oca_group=None,
            created_at=datetime.now(),
            filled_at=None,
            metadata={"net_premium": net_premium},
        )

        # Create bracket
        bracket_id = await self.create_bracket(
            entry_order=entry_order,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            max_sl_ratio=max_sl_ratio,
            entry_contract=None,  # Will be provided by caller
        )

        logger.info(
            f"Created bracket {bracket_id} for strategy {strategy.strategy_id} "
            f"({strategy_type}): SL=${stop_loss_price:.2f}, TP=${take_profit_price:.2f}"
        )

        return bracket_id

    async def monitor_strategy_brackets(
        self,
        strategy_id: str,
    ) -> list[dict[str, Any]]:
        """
        Query all active brackets for a strategy.

        Args:
            strategy_id: Strategy ID to query

        Returns:
            List of bracket status dicts
        """
        # Find all brackets associated with this strategy
        # (Would need strategy_id -> bracket_id mapping in production)
        active_brackets = []

        for bracket_id, bracket in self.active_brackets.items():
            # Check if bracket is still active
            if bracket["status"] in ("pending", "active"):
                status = await self.get_bracket_status(bracket_id)
                active_brackets.append(status)

        return active_brackets
