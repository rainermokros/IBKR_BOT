"""
OCA (One-Cancels-All) Order Manager

Manages OCA order groups for conditional execution.
When one order in an OCA group fills, IB automatically cancels all remaining orders.

Key features:
- OCA group creation with same-symbol validation
- IB order submission with oca_group parameter
- Status tracking and cancellation
- Fill handling with callbacks

Usage:
    from v6.system_monitor.execution_system import OCAOrderManager
    from v6.utils import IBConnectionManager

    ib_conn = IBConnectionManager()
    oca_manager = OCAOrderManager(ib_conn)

    # Create OCA group
    orders = [order1, order2, order3]
    oca_group_id = await oca_manager.create_oca_group(orders)

    # Check status
    status = await oca_manager.get_oca_status(oca_group_id)
"""

import logging
from datetime import datetime
from typing import Any, Callable, Optional
from uuid import uuid4

from ib_async import Contract

from v6.system_monitor.execution_engine.models import Order, OrderStatus
from v6.utils.ib_connection import IBConnectionManager

logger = logging.getLogger(__name__)


class OCAOrderManager:
    """
    Manage OCA (One-Cancels-All) order groups.

    OCA groups allow conditional execution where filling one order
    automatically cancels all remaining orders in the group.

    Attributes:
        ib_conn: IB connection manager
        active_oca_groups: Dict of active OCA groups
        order_to_oca_map: Mapping from order_id to oca_group_id
        fill_callbacks: Callbacks triggered on order fills
    """

    def __init__(
        self,
        ib_conn: IBConnectionManager,
        order_writer: Optional[Any] = None,
    ):
        """
        Initialize OCA order manager.

        Args:
            ib_conn: IB connection manager
            order_writer: Optional order writer for persistence
        """
        self.ib_conn = ib_conn
        self.ib = ib_conn.ib
        self.order_writer = order_writer

        # Active OCA groups tracking
        self.active_oca_groups: dict[str, dict[str, Any]] = {}

        # Order to OCA group mapping
        self.order_to_oca_map: dict[str, str] = {}

        # Fill callbacks: {oca_group_id: [callback1, callback2, ...]}
        self.fill_callbacks: dict[str, list[Callable]] = {}

        logger.info("OCAOrderManager initialized")

    async def create_oca_group(
        self,
        orders: list[Order],
        contracts: list[Contract],
        oca_type: int = 1,
    ) -> str:
        """
        Create an OCA group with multiple orders.

        Args:
            orders: List of Order objects to include in OCA group
            contracts: List of IB Contract objects (same length as orders)
            oca_type: OCA type (1 = cancel all remaining when one fills)

        Returns:
            oca_group_id: Unique identifier for the OCA group

        Raises:
            ValueError: If validation fails (different symbols, mismatched lengths)
            ConnectionError: If IB connection fails
        """
        if len(orders) != len(contracts):
            raise ValueError(
                f"Orders and contracts must have same length: "
                f"{len(orders)} != {len(contracts)}"
            )

        if len(orders) == 0:
            raise ValueError("Cannot create OCA group with no orders")

        # Validate all orders have same symbol
        symbols = {contract.symbol for contract in contracts}
        if len(symbols) > 1:
            raise ValueError(
                f"All orders in OCA group must have same symbol, got: {symbols}"
            )

        # Generate unique OCA group ID
        oca_group_id = str(uuid4())

        logger.info(
            f"Creating OCA group {oca_group_id} with {len(orders)} orders "
            f"for symbol: {symbols.pop()}"
        )

        # Assign oca_group to all orders and submit
        order_ids = []
        await self.ib_conn.ensure_connected()

        for order, contract in zip(orders, contracts):
            # Assign OCA group
            order.oca_group = oca_group_id

            # Submit order to IB
            try:
                trade = self.ib.placeOrder(contract, order.order_ref)
                order_ids.append(str(trade.order.orderId))

                # Map order to OCA group
                self.order_to_oca_map[str(trade.order.orderId)] = oca_group_id

                logger.info(
                    f"Order {trade.order.orderId} submitted to OCA group {oca_group_id}"
                )

            except Exception as e:
                logger.error(f"Failed to submit order to OCA group: {e}")
                # Clean up: cancel submitted orders
                await self.cancel_oca_group(oca_group_id)
                raise

        # Store OCA group tracking
        self.active_oca_groups[oca_group_id] = {
            "order_ids": order_ids,
            "status": "pending",
            "created_at": datetime.now(),
            "symbol": contracts[0].symbol,
            "oca_type": oca_type,
        }

        logger.info(f"OCA group {oca_group_id} created with {len(order_ids)} orders")

        return oca_group_id

    async def cancel_oca_group(self, oca_group_id: str) -> bool:
        """
        Cancel all active orders in an OCA group.

        Args:
            oca_group_id: OCA group ID to cancel

        Returns:
            True if all cancellations succeeded, False otherwise
        """
        if oca_group_id not in self.active_oca_groups:
            logger.warning(f"OCA group {oca_group_id} not found for cancellation")
            return False

        group = self.active_oca_groups[oca_group_id]

        if group["status"] in ("complete", "cancelled"):
            logger.info(
                f"OCA group {oca_group_id} already {group['status']}, skipping cancellation"
            )
            return True

        logger.info(f"Cancelling OCA group {oca_group_id}")

        all_succeeded = True
        await self.ib_conn.ensure_connected()

        for order_id in group["order_ids"]:
            try:
                self.ib.cancelOrder(int(order_id))
                logger.info(f"Order {order_id} cancelled")
            except Exception as e:
                logger.error(f"Failed to cancel order {order_id}: {e}")
                all_succeeded = False

        # Update status
        group["status"] = "cancelled"

        return all_succeeded

    async def get_oca_status(self, oca_group_id: str) -> dict[str, Any]:
        """
        Query status of all orders in an OCA group.

        Args:
            oca_group_id: OCA group ID to query

        Returns:
            Dict with keys:
                - oca_group_id: str
                - order_count: int
                - filled_count: int
                - status: str ('pending', 'partial', 'complete', 'cancelled')
                - orders: list of {order_id, status, fill_price}
        """
        if oca_group_id not in self.active_oca_groups:
            raise ValueError(f"OCA group {oca_group_id} not found")

        group = self.active_oca_groups[oca_group_id]

        # Query IB for order status
        orders_info = []
        filled_count = 0

        await self.ib_conn.ensure_connected()

        for order_id in group["order_ids"]:
            try:
                # Get order status from IB
                trade = self.ib.tradesByOrderId.get(int(order_id))

                if trade:
                    order_status = trade.orderStatus.status
                    fill_price = trade.orderStatus.avgFillPrice or 0.0

                    if order_status == "Filled":
                        filled_count += 1

                    orders_info.append({
                        "order_id": order_id,
                        "status": order_status,
                        "fill_price": fill_price,
                    })
                else:
                    # Trade not found, assume pending
                    orders_info.append({
                        "order_id": order_id,
                        "status": "Pending",
                        "fill_price": 0.0,
                    })

            except Exception as e:
                logger.error(f"Error querying order {order_id}: {e}")
                orders_info.append({
                    "order_id": order_id,
                    "status": "Unknown",
                    "fill_price": 0.0,
                })

        # Determine overall status
        if group["status"] == "cancelled":
            overall_status = "cancelled"
        elif filled_count == 0:
            overall_status = "pending"
        elif filled_count == len(group["order_ids"]):
            overall_status = "complete"
        else:
            overall_status = "partial"

        return {
            "oca_group_id": oca_group_id,
            "order_count": len(group["order_ids"]),
            "filled_count": filled_count,
            "status": overall_status,
            "orders": orders_info,
            "symbol": group.get("symbol"),
        }

    def list_active_oca_groups(self) -> list[dict[str, Any]]:
        """
        List all active OCA groups.

        Returns:
            List of dicts with oca_group_id, status, order_count, symbol
        """
        active_groups = []

        for oca_group_id, group in self.active_oca_groups.items():
            if group["status"] in ("pending", "partial"):
                active_groups.append({
                    "oca_group_id": oca_group_id,
                    "status": group["status"],
                    "order_count": len(group["order_ids"]),
                    "symbol": group.get("symbol"),
                    "created_at": group.get("created_at"),
                })

        return active_groups

    async def handle_oca_fill(
        self,
        oca_group_id: str,
        filled_order_id: str,
        fill_price: float = 0.0,
    ) -> None:
        """
        Handle an order fill in an OCA group.

        When an order fills, IB automatically cancels remaining orders (OCA type 1).
        This method updates internal tracking and triggers callbacks.

        Args:
            oca_group_id: OCA group ID
            filled_order_id: Order ID that filled
            fill_price: Fill price
        """
        if oca_group_id not in self.active_oca_groups:
            logger.warning(
                f"OCA group {oca_group_id} not found for fill handling "
                f"(order {filled_order_id})"
            )
            return

        group = self.active_oca_groups[oca_group_id]

        # Update status to complete
        previous_status = group["status"]
        group["status"] = "complete"

        logger.info(
            f"OCA group {oca_group_id} filled by order {filled_order_id} "
            f"@ ${fill_price:.2f}, remaining orders cancelled "
            f"(previous status: {previous_status})"
        )

        # Trigger fill callbacks
        if oca_group_id in self.fill_callbacks:
            for callback in self.fill_callbacks[oca_group_id]:
                try:
                    await callback(oca_group_id, filled_order_id, fill_price)
                except Exception as e:
                    logger.error(f"Fill callback error: {e}")

    def register_fill_callback(
        self,
        oca_group_id: str,
        callback: Callable,
    ) -> None:
        """
        Register a callback to be triggered when an OCA group order fills.

        Args:
            oca_group_id: OCA group ID
            callback: Async callback function with signature:
                      callback(oca_group_id, filled_order_id, fill_price)
        """
        if oca_group_id not in self.fill_callbacks:
            self.fill_callbacks[oca_group_id] = []

        self.fill_callbacks[oca_group_id].append(callback)
        logger.info(f"Registered fill callback for OCA group {oca_group_id}")

    async def submit_strategy_oca_orders(
        self,
        strategy: Any,
        contracts: list[Contract],
    ) -> str:
        """
        Submit all strategy legs as an OCA group.

        Extracts orders from strategy legs and creates OCA group.
        Links strategy execution to OCA lifecycle.

        Args:
            strategy: Strategy object with legs
            contracts: List of IB Contract objects for each leg

        Returns:
            oca_group_id: OCA group ID for tracking
        """
        if not hasattr(strategy, "legs"):
            raise ValueError("Strategy must have 'legs' attribute")

        if len(strategy.legs) != len(contracts):
            raise ValueError(
                f"Strategy legs ({len(strategy.legs)}) must match "
                f"contracts ({len(contracts)})"
            )

        # Convert legs to Order objects
        orders = []
        for leg in strategy.legs:
            order = Order(
                order_id=str(uuid4()),
                conid=contracts[0].conId,  # Will be updated after placement
                action=leg.action,
                quantity=leg.quantity,
                order_type="LIMIT",  # Default to limit orders
                limit_price=leg.price,
                stop_price=None,
                tif="DAY",
                good_till_date=None,
                status=OrderStatus.PENDING_SUBMIT,
                filled_quantity=0,
                avg_fill_price=None,
                order_ref=None,
                parent_order_id=None,
                oca_group=None,  # Will be assigned by create_oca_group
                created_at=datetime.now(),
                filled_at=None,
            )
            orders.append(order)

        # Create OCA group
        oca_group_id = await self.create_oca_group(orders, contracts)

        logger.info(
            f"Submitted strategy {strategy.strategy_id} as OCA group {oca_group_id}"
        )

        return oca_group_id
