"""
Order Execution Engine

This module provides the OrderExecutionEngine for placing orders through IB API.
Supports basic orders, bracket orders, OCA groups, and position management.

Key features:
- IB API integration via IBConnectionManager
- OCA groups for One-Cancels-All orders
- Bracket orders (parent + take profit + stop loss)
- Position close and roll functionality
- Dry run mode for testing
- Error handling with ExecutionResult

Usage:
    from src.v6.execution import OrderExecutionEngine
    from src.v6.utils import IBConnectionManager

    ib_conn = IBConnectionManager()
    engine = OrderExecutionEngine(ib_conn, dry_run=False)

    result = await engine.place_order(contract, order)
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

import ib_async
from ib_async import LimitOrder, MarketOrder, Order, StopOrder

from src.v6.execution.models import (
    BracketOrder,
    ExecutionResult,
    Order as OrderModel,
    OrderAction,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from src.v6.strategies.models import (
    LegExecution,
    LegStatus,
    LegSpec,
    Strategy,
    StrategyExecution,
    StrategyType,
)
from src.v6.utils.ib_connection import IBConnectionManager

logger = logging.getLogger(__name__)


class OrderExecutionEngine:
    """
    Execute orders through IB API.

    Handles order placement, cancellation, bracket orders, and position management.

    Attributes:
        ib_conn: IB connection manager
        dry_run: If True, simulate orders without placing them
        logger: Logger instance
    """

    def __init__(
        self,
        ib_conn: IBConnectionManager,
        dry_run: bool = False,
    ):
        """
        Initialize order execution engine.

        Args:
            ib_conn: IB connection manager
            dry_run: If True, simulate orders without placing them
        """
        self.ib_conn = ib_conn
        self.ib = ib_conn.ib
        self.dry_run = dry_run
        self.logger = logger

        if dry_run:
            self.logger.warning("DRY RUN MODE - No actual orders will be placed")

    async def place_order(
        self,
        contract: ib_async.Contract,
        order: OrderModel,
    ) -> OrderModel:
        """
        Place an order through IB API.

        Args:
            contract: IB contract object
            order: Order model to place

        Returns:
            Updated Order model with IB order ID

        Raises:
            ValueError: If order validation fails
            ConnectionError: If IB connection fails
        """
        if order.status != OrderStatus.PENDING_SUBMIT:
            raise ValueError(
                f"Order must be PENDING_SUBMIT to place, got {order.status.value}"
            )

        self.logger.info(
            f"Placing order: {order.action.value} {order.quantity}x "
            f"{order.order_type.value} {contract.symbol}"
        )

        if self.dry_run:
            # Simulate order placement
            mock_order_id = f"DRY_{order.order_id}_{datetime.now().timestamp()}"
            self.logger.info(f"[DRY RUN] Simulated order placement: {mock_order_id}")

            # Update order status (simulate successful fill)
            order.status = OrderStatus.FILLED
            order.filled_quantity = order.quantity
            order.filled_at = datetime.now()
            return order

        # Ensure IB connection
        await self.ib_conn.ensure_connected()

        # Convert OrderModel to IB Order
        ib_order = self._create_ib_order(order)

        # Place order
        try:
            trade = self.ib.placeOrder(contract, ib_order)
            order.order_ref = ib_order
            order.status = OrderStatus.SUBMITTED
            order.conid = contract.conId

            self.logger.info(f"Order placed successfully: {trade.order.orderId}")
            return order

        except Exception as e:
            self.logger.error(f"Failed to place order: {e}")
            order.status = OrderStatus.REJECTED
            raise

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancellation succeeded, False otherwise
        """
        self.logger.info(f"Cancelling order: {order_id}")

        if self.dry_run:
            self.logger.info(f"[DRY RUN] Simulated order cancellation: {order_id}")
            return True

        await self.ib_conn.ensure_connected()

        try:
            # Note: order_id should be IB's orderId, not our UUID
            # In production, we'd need to track the mapping
            self.ib.cancelOrder(int(order_id))
            self.logger.info(f"Order cancelled successfully: {order_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def place_bracket_order(
        self,
        bracket: BracketOrder,
        entry_contract: ib_async.Contract,
        tp_contract: Optional[ib_async.Contract] = None,
        sl_contract: Optional[ib_async.Contract] = None,
    ) -> ExecutionResult:
        """
        Place a bracket order (entry + take profit + stop loss).

        Args:
            bracket: BracketOrder model with parent, TP, SL orders
            entry_contract: IB contract for entry order
            tp_contract: IB contract for take profit order (same as entry if None)
            sl_contract: IB contract for stop loss order (same as entry if None)

        Returns:
            ExecutionResult with order IDs
        """
        self.logger.info(
            f"Placing bracket order: OCA group={bracket.oca_group}, "
            f"parent={bracket.parent_order.order_id}"
        )

        if self.dry_run:
            # Simulate bracket order placement
            mock_ids = [
                f"DRY_{bracket.parent_order.order_id}_{datetime.now().timestamp()}",
            ]
            if bracket.take_profit:
                mock_ids.append(f"DRY_TP_{bracket.take_profit.order_id}")
            if bracket.stop_loss:
                mock_ids.append(f"DRY_SL_{bracket.stop_loss.order_id}")

            self.logger.info(f"[DRY RUN] Simulated bracket order placement: {mock_ids}")
            return ExecutionResult(
                success=True,
                action_taken="DRY_RUN",
                order_ids=mock_ids,
                error_message=None,
            )

        await self.ib_conn.ensure_connected()

        order_ids = []

        try:
            # Create IB orders
            parent_ib_order = self._create_ib_order(bracket.parent_order)
            tp_ib_order = None
            sl_ib_order = None

            if bracket.take_profit:
                tp_ib_order = self._create_ib_order(bracket.take_profit)
                tp_ib_order.parentId = parent_ib_order.orderId
                tp_ib_order.transmit = False  # Don't transmit yet
                tp_ib_order.ocaGroup = bracket.oca_group

            if bracket.stop_loss:
                sl_ib_order = self._create_ib_order(bracket.stop_loss)
                sl_ib_order.parentId = parent_ib_order.orderId
                sl_ib_order.transmit = False  # Don't transmit yet
                sl_ib_order.ocaGroup = bracket.oca_group

            # Set parent OCA group
            parent_ib_order.ocaGroup = bracket.oca_group

            # Place child orders first (transmit=False)
            if tp_ib_order and tp_contract:
                tp_trade = self.ib.placeOrder(
                    tp_contract or entry_contract,
                    tp_ib_order,
                )
                order_ids.append(str(tp_trade.order.orderId))
                self.logger.info(f"TP order placed: {tp_trade.order.orderId}")

            if sl_ib_order and sl_contract:
                sl_trade = self.ib.placeOrder(
                    sl_contract or entry_contract,
                    sl_ib_order,
                )
                order_ids.append(str(sl_trade.order.orderId))
                self.logger.info(f"SL order placed: {sl_trade.order.orderId}")

            # Place parent order last (transmit=True, triggers child orders)
            parent_trade = self.ib.placeOrder(entry_contract, parent_ib_order)
            order_ids.append(str(parent_trade.order.orderId))
            self.logger.info(f"Parent order placed: {parent_trade.order.orderId}")

            return ExecutionResult(
                success=True,
                action_taken="BRACKET_PLACED",
                order_ids=order_ids,
                error_message=None,
            )

        except Exception as e:
            self.logger.error(f"Failed to place bracket order: {e}")
            return ExecutionResult(
                success=False,
                action_taken="FAILED",
                order_ids=order_ids,
                error_message=str(e),
            )

    async def close_position(
        self,
        strategy: Strategy,
    ) -> ExecutionResult:
        """
        Close a position by placing opposite orders for all legs.

        Args:
            strategy: Strategy model with legs to close

        Returns:
            ExecutionResult with order IDs
        """
        self.logger.info(
            f"Closing position: {strategy.strategy_id} "
            f"({strategy.symbol} {strategy.strategy_type.value})"
        )

        if not strategy.legs:
            return ExecutionResult(
                success=False,
                action_taken="FAILED",
                order_ids=[],
                error_message="Strategy has no legs to close",
            )

        order_ids = []

        for leg in strategy.legs:
            try:
                # Opposite action to close
                close_action = (
                    OrderAction.SELL if leg.action == OrderAction.BUY else OrderAction.BUY
                )

                if self.dry_run:
                    # Simulate close order in dry run mode
                    mock_id = f"DRY_{close_action.value}_{leg.right.value}_{leg.strike}_{datetime.now().timestamp()}"
                    order_ids.append(mock_id)
                    self.logger.info(
                        f"[DRY RUN] Would close: {close_action.value} {leg.quantity}x "
                        f"{leg.right.value} ${leg.strike}"
                    )
                    continue

                # Create IB contract for leg
                from ib_async import Option

                contract = Option(
                    symbol=strategy.symbol,
                    right=leg.right.value,
                    strike=leg.strike,
                    lastTradeDateOrContractMonth=leg.expiration.strftime("%Y%m%d"),
                    exchange="SMART",
                    currency="USD",
                )

                await self.ib_conn.ensure_connected()
                await self.ib.qualifyContractsAsync(contract)

                # Create market order for immediate close
                close_order = OrderModel(
                    order_id=str(uuid4()),
                    conid=contract.conId,
                    action=close_action,
                    quantity=leg.quantity,
                    order_type=OrderType.MARKET,
                    limit_price=None,
                    stop_price=None,
                    tif=TimeInForce.DAY,
                    status=OrderStatus.PENDING_SUBMIT,
                    filled_quantity=0,
                    avg_fill_price=None,
                    order_ref=None,
                    parent_order_id=None,
                    oca_group=f"CLOSE_{strategy.strategy_id}",
                    created_at=datetime.now(),
                    filled_at=None,
                )

                # Place order
                updated_order = await self.place_order(contract, close_order)
                order_ids.append(updated_order.order_id)

                self.logger.info(
                    f"Closed leg: {close_action.value} {leg.quantity}x "
                    f"{leg.right.value} ${leg.strike}"
                )

            except Exception as e:
                self.logger.error(f"Failed to close leg: {e}")
                # Continue with other legs

        # Return result with error message if no orders succeeded
        if len(order_ids) == 0:
            return ExecutionResult(
                success=False,
                action_taken="FAILED",
                order_ids=[],
                error_message="Failed to close any legs",
            )

        return ExecutionResult(
            success=True,
            action_taken="CLOSED",
            order_ids=order_ids,
            error_message=None,
        )

    async def roll_position(
        self,
        strategy: Strategy,
        new_dte: int,
    ) -> ExecutionResult:
        """
        Roll a position to new expiration (close old, open new).

        Args:
            strategy: Strategy to roll
            new_dte: New days to expiration

        Returns:
            ExecutionResult with order IDs
        """
        self.logger.info(
            f"Rolling position: {strategy.strategy_id} to DTE={new_dte}"
        )

        # Step 1: Close existing position
        close_result = await self.close_position(strategy)

        if not close_result.success and close_result.order_ids:
            self.logger.warning(f"Partial close during roll: {close_result}")

        # Step 2: Build new strategy with same parameters, new DTE
        # Note: This is a simplified roll. In production, you'd use the
        # StrategyBuilder to construct the new strategy based on current prices.

        order_ids = close_result.order_ids

        if self.dry_run:
            mock_id = f"DRY_ROLL_{strategy.strategy_id}_{datetime.now().timestamp()}"
            order_ids.append(mock_id)
            self.logger.info(f"[DRY RUN] Would roll to new DTE={new_dte}")
        else:
            # In production, you would:
            # 1. Fetch current underlying price
            # 2. Use StrategyBuilder to build new strategy with new_dte
            # 3. Place orders for new legs
            # For now, just log that this needs implementation
            self.logger.warning(
                "Roll position: new strategy entry not yet implemented. "
                "Old position closed, new entry requires manual StrategyBuilder call."
            )

        return ExecutionResult(
            success=len(order_ids) > 0,
            action_taken="ROLLED",
            order_ids=order_ids,
            error_message=None,
        )

    def _create_ib_order(self, order: OrderModel) -> Order:
        """
        Convert OrderModel to IB Order object.

        Args:
            order: OrderModel instance

        Returns:
            IB Order object
        """
        # Create IB order based on order type
        if order.order_type == OrderType.MARKET:
            ib_order = MarketOrder(order.action.value, order.quantity)
        elif order.order_type == OrderType.LIMIT:
            ib_order = LimitOrder(order.action.value, order.quantity, order.limit_price)
        elif order.order_type == OrderType.STOP:
            ib_order = StopOrder(order.action.value, order.quantity, order.stop_price)
        elif order.order_type == OrderType.STOP_LIMIT:
            ib_order = Order()
            ib_order.action = order.action.value
            ib_order.totalQuantity = order.quantity
            ib_order.orderType = "STP LMT"
            ib_order.lmtPrice = order.limit_price
            ib_order.auxPrice = order.stop_price
        else:
            # Default to limit order for unsupported types
            ib_order = LimitOrder(order.action.value, order.quantity, order.limit_price or 0.0)

        # Set time in force
        ib_order.tif = order.tif.value

        # Set OCA group if specified
        if order.oca_group:
            ib_order.ocaGroup = order.oca_group

        # Set transmit flag (True for normal orders, False for bracket children)
        if order.parent_order_id is not None:
            ib_order.transmit = False
        else:
            ib_order.transmit = True

        # Store reference to original order
        ib_order.orderRef = order.order_id

        return ib_order
