"""
Tests for OCAOrderManager.

Tests OCA group creation, status tracking, cancellation, and fill handling.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock

from src.v6.execution.oca_order_manager import OCAOrderManager
from src.v6.execution.models import Order, OrderAction, OrderStatus, OrderType, TimeInForce
from src.v6.utils.ib_connection import IBConnectionManager


@pytest.fixture
def mock_ib_conn():
    """Create mock IB connection manager."""
    ib_conn = MagicMock(spec=IBConnectionManager)
    ib_conn.ib = MagicMock()
    ib_conn.ensure_connected = AsyncMock()
    ib_conn.ib.placeOrder = MagicMock()
    ib_conn.ib.cancelOrder = MagicMock()
    ib_conn.ib.tradesByOrderId = {}
    return ib_conn


@pytest.fixture
def sample_orders():
    """Create sample orders for testing."""
    return [
        Order(
            order_id="order-1",
            conid=123456,
            action=OrderAction.BUY,
            quantity=1,
            order_type=OrderType.LIMIT,
            limit_price=2.50,
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
        ),
        Order(
            order_id="order-2",
            conid=123456,
            action=OrderAction.SELL,
            quantity=1,
            order_type=OrderType.LIMIT,
            limit_price=2.75,
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
        ),
        Order(
            order_id="order-3",
            conid=123456,
            action=OrderAction.SELL,
            quantity=1,
            order_type=OrderType.LIMIT,
            limit_price=3.00,
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
        ),
    ]


@pytest.fixture
def sample_contracts():
    """Create sample IB contracts."""
    contracts = []
    for i in range(3):
        contract = MagicMock()
        contract.conId = 123456
        contract.symbol = "SPY"
        contracts.append(contract)
    return contracts


class TestOCAOrderManager:
    """Test OCA order manager functionality."""

    def test_init(self, mock_ib_conn):
        """Test OCA manager initialization."""
        manager = OCAOrderManager(mock_ib_conn)

        assert manager.ib_conn == mock_ib_conn
        assert manager.ib == mock_ib_conn.ib
        assert manager.active_oca_groups == {}
        assert manager.order_to_oca_map == {}
        assert manager.fill_callbacks == {}

    @pytest.mark.asyncio
    async def test_create_oca_group_success(self, mock_ib_conn, sample_orders, sample_contracts):
        """Test successful OCA group creation."""
        # Mock placeOrder to return trade with orderId
        mock_trade = MagicMock()
        mock_trade.order.orderId = 1001
        mock_ib_conn.ib.placeOrder.return_value = mock_trade

        manager = OCAOrderManager(mock_ib_conn)

        # Create OCA group
        oca_group_id = await manager.create_oca_group(sample_orders, sample_contracts)

        # Verify OCA group created
        assert oca_group_id is not None
        assert oca_group_id in manager.active_oca_groups

        group = manager.active_oca_groups[oca_group_id]
        assert group["status"] == "pending"
        assert len(group["order_ids"]) == 3
        assert group["symbol"] == "SPY"

        # Verify orders have oca_group assigned
        for order in sample_orders:
            assert order.oca_group == oca_group_id

    @pytest.mark.asyncio
    async def test_create_oca_group_same_symbol_validation(
        self, mock_ib_conn, sample_orders
    ):
        """Test that OCA group enforces same-symbol requirement."""
        # Create contracts with different symbols
        contracts = []
        for i, symbol in enumerate(["SPY", "QQQ", "IWM"]):
            contract = MagicMock()
            contract.conId = 123456 + i
            contract.symbol = symbol
            contracts.append(contract)

        manager = OCAOrderManager(mock_ib_conn)

        # Should raise ValueError for different symbols
        with pytest.raises(ValueError, match="same symbol"):
            await manager.create_oca_group(sample_orders, contracts)

    @pytest.mark.asyncio
    async def test_create_oca_group_empty_orders(self, mock_ib_conn):
        """Test that empty orders list raises error."""
        manager = OCAOrderManager(mock_ib_conn)

        with pytest.raises(ValueError, match="no orders"):
            await manager.create_oca_group([], [])

    @pytest.mark.asyncio
    async def test_create_oca_group_mismatched_lengths(self, mock_ib_conn, sample_orders):
        """Test that mismatched orders and contracts raises error."""
        manager = OCAOrderManager(mock_ib_conn)

        contracts = [MagicMock()]  # Only 1 contract for 3 orders

        with pytest.raises(ValueError, match="same length"):
            await manager.create_oca_group(sample_orders, contracts)

    @pytest.mark.asyncio
    async def test_cancel_oca_group_success(self, mock_ib_conn, sample_orders, sample_contracts):
        """Test successful OCA group cancellation."""
        # Mock placeOrder
        mock_trade = MagicMock()
        mock_trade.order.orderId = 1001
        mock_ib_conn.ib.placeOrder.return_value = mock_trade

        manager = OCAOrderManager(mock_ib_conn)

        # Create OCA group
        oca_group_id = await manager.create_oca_group(sample_orders, sample_contracts)

        # Cancel OCA group
        result = await manager.cancel_oca_group(oca_group_id)

        assert result is True
        assert manager.active_oca_groups[oca_group_id]["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_oca_group_not_found(self, mock_ib_conn):
        """Test cancelling non-existent OCA group."""
        manager = OCAOrderManager(mock_ib_conn)

        result = await manager.cancel_oca_group("non-existent")

        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_oca_group_already_complete(self, mock_ib_conn, sample_orders, sample_contracts):
        """Test cancelling already-complete OCA group."""
        # Mock placeOrder
        mock_trade = MagicMock()
        mock_trade.order.orderId = 1001
        mock_ib_conn.ib.placeOrder.return_value = mock_trade

        manager = OCAOrderManager(mock_ib_conn)

        # Create OCA group
        oca_group_id = await manager.create_oca_group(sample_orders, sample_contracts)

        # Mark as complete
        manager.active_oca_groups[oca_group_id]["status"] = "complete"

        # Should succeed without calling cancelOrder
        result = await manager.cancel_oca_group(oca_group_id)

        assert result is True
        mock_ib_conn.ib.cancelOrder.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_oca_status_pending(self, mock_ib_conn, sample_orders, sample_contracts):
        """Test getting status of pending OCA group."""
        # Mock placeOrder
        mock_trade = MagicMock()
        mock_trade.order.orderId = 1001
        mock_ib_conn.ib.placeOrder.return_value = mock_trade

        # Mock tradesByOrderId to return pending trades
        mock_ib_conn.ib.tradesByOrderId = MagicMock()
        mock_ib_conn.ib.tradesByOrderId.get = MagicMock(return_value=None)

        manager = OCAOrderManager(mock_ib_conn)

        # Create OCA group
        oca_group_id = await manager.create_oca_group(sample_orders, sample_contracts)

        # Get status
        status = await manager.get_oca_status(oca_group_id)

        assert status["oca_group_id"] == oca_group_id
        assert status["order_count"] == 3
        assert status["filled_count"] == 0
        assert status["status"] == "pending"
        assert len(status["orders"]) == 3

    @pytest.mark.asyncio
    async def test_get_oca_status_not_found(self, mock_ib_conn):
        """Test getting status of non-existent OCA group."""
        manager = OCAOrderManager(mock_ib_conn)

        with pytest.raises(ValueError, match="not found"):
            await manager.get_oca_status("non-existent")

    def test_list_active_oca_groups(self, mock_ib_conn):
        """Test listing active OCA groups."""
        manager = OCAOrderManager(mock_ib_conn)

        # Add some groups
        manager.active_oca_groups["group-1"] = {
            "order_ids": ["order-1"],
            "status": "pending",
            "symbol": "SPY",
            "created_at": datetime.now(),
        }
        manager.active_oca_groups["group-2"] = {
            "order_ids": ["order-2"],
            "status": "partial",  # Changed from "active" to "partial"
            "symbol": "QQQ",
            "created_at": datetime.now(),
        }
        manager.active_oca_groups["group-3"] = {
            "order_ids": ["order-3"],
            "status": "cancelled",
            "symbol": "IWM",
            "created_at": datetime.now(),
        }

        # List active groups
        active = manager.list_active_oca_groups()

        assert len(active) == 2  # Only pending and partial
        group_ids = [g["oca_group_id"] for g in active]
        assert "group-1" in group_ids
        assert "group-2" in group_ids
        assert "group-3" not in group_ids

    @pytest.mark.asyncio
    async def test_handle_oca_fill(self, mock_ib_conn, sample_orders, sample_contracts):
        """Test handling order fill in OCA group."""
        # Mock placeOrder
        mock_trade = MagicMock()
        mock_trade.order.orderId = 1001
        mock_ib_conn.ib.placeOrder.return_value = mock_trade

        manager = OCAOrderManager(mock_ib_conn)

        # Create OCA group
        oca_group_id = await manager.create_oca_group(sample_orders, sample_contracts)

        # Handle fill
        await manager.handle_oca_fill(oca_group_id, "order-1", 2.50)

        # Verify status updated to complete
        assert manager.active_oca_groups[oca_group_id]["status"] == "complete"

    @pytest.mark.asyncio
    async def test_handle_oca_fill_with_callback(self, mock_ib_conn, sample_orders, sample_contracts):
        """Test fill callback triggered on OCA fill."""
        # Mock placeOrder
        mock_trade = MagicMock()
        mock_trade.order.orderId = 1001
        mock_ib_conn.ib.placeOrder.return_value = mock_trade

        manager = OCAOrderManager(mock_ib_conn)

        # Create OCA group
        oca_group_id = await manager.create_oca_group(sample_orders, sample_contracts)

        # Register callback
        callback_called = []

        async def test_callback(oca_id, order_id, fill_price):
            callback_called.append((oca_id, order_id, fill_price))

        manager.register_fill_callback(oca_group_id, test_callback)

        # Handle fill
        await manager.handle_oca_fill(oca_group_id, "order-1", 2.50)

        # Verify callback called
        assert len(callback_called) == 1
        assert callback_called[0] == (oca_group_id, "order-1", 2.50)

    def test_register_fill_callback(self, mock_ib_conn):
        """Test registering fill callbacks."""
        manager = OCAOrderManager(mock_ib_conn)

        async def test_callback(oca_id, order_id, fill_price):
            pass

        manager.register_fill_callback("group-1", test_callback)

        assert "group-1" in manager.fill_callbacks
        assert len(manager.fill_callbacks["group-1"]) == 1

    @pytest.mark.asyncio
    async def test_submit_strategy_oca_orders(self, mock_ib_conn, sample_iron_condor):
        """Test submitting strategy as OCA group."""
        # Mock placeOrder
        mock_trade = MagicMock()
        mock_trade.order.orderId = 1001
        mock_ib_conn.ib.placeOrder.return_value = mock_trade

        # Create contracts for each leg
        contracts = []
        for _ in sample_iron_condor.legs:
            contract = MagicMock()
            contract.conId = 123456
            contract.symbol = "SPY"
            contracts.append(contract)

        manager = OCAOrderManager(mock_ib_conn)

        # Submit strategy as OCA
        oca_group_id = await manager.submit_strategy_oca_orders(sample_iron_condor, contracts)

        # Verify OCA group created
        assert oca_group_id is not None
        assert oca_group_id in manager.active_oca_groups

        group = manager.active_oca_groups[oca_group_id]
        assert len(group["order_ids"]) == 4  # 4 legs for iron condor
