"""
Tests for BracketOrderManager.

Tests bracket order creation, max SL enforcement, SL/TP adjustment, and trailing stops.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from src.v6.execution.bracket_order_manager import BracketOrderManager
from src.v6.execution.models import Order, OrderAction, OrderStatus, OrderType, TimeInForce
from src.v6.utils.ib_connection import IBConnectionManager


@pytest.fixture
def mock_ib_conn_with_place_order(mock_ib_conn):
    """Create mock IB connection with placeOrder mocked."""
    mock_trade = MagicMock()
    mock_trade.order.orderId = 1001
    mock_ib_conn.ib.placeOrder.return_value = mock_trade
    return mock_ib_conn


@pytest.fixture
def mock_ib_conn():
    """Create mock IB connection manager."""
    ib_conn = MagicMock(spec=IBConnectionManager)
    ib_conn.ib = MagicMock()
    ib_conn.ensure_connected = AsyncMock()
    ib_conn.ib.placeOrder = MagicMock()
    ib_conn.ib.cancelOrder = MagicMock()
    return ib_conn


@pytest.fixture
def sample_entry_order():
    """Create sample entry order with net_premium."""
    order = Order(
        order_id="entry-order-1",
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
    )
    # Add metadata attribute
    order.metadata = {"net_premium": 2.50}
    return order


@pytest.fixture
def sample_contract():
    """Create sample IB contract."""
    contract = MagicMock()
    contract.conId = 123456
    contract.symbol = "SPY"
    return contract


class TestBracketOrderManager:
    """Test bracket order manager functionality."""

    def test_init(self, mock_ib_conn):
        """Test bracket manager initialization."""
        manager = BracketOrderManager(mock_ib_conn)

        assert manager.ib_conn == mock_ib_conn
        assert manager.active_brackets == {}
        assert manager.order_to_bracket_map == {}

    @pytest.mark.asyncio
    async def test_create_bracket_success(
        self, mock_ib_conn, sample_entry_order, sample_contract
    ):
        """Test successful bracket creation."""
        # Mock placeOrder for bracket placement
        mock_trade = MagicMock()
        mock_trade.order.orderId = 1001
        mock_ib_conn.ib.placeOrder.return_value = mock_trade

        manager = BracketOrderManager(mock_ib_conn)

        # Create bracket
        bracket_id = await manager.create_bracket(
            entry_order=sample_entry_order,
            stop_loss_price=5.00,  # Within 2x net_premium
            take_profit_price=3.75,
            entry_contract=sample_contract,
        )

        # Verify bracket created
        assert bracket_id is not None
        assert bracket_id in manager.active_brackets

        bracket = manager.active_brackets[bracket_id]
        assert bracket["status"] == "pending"
        assert bracket["stop_loss_price"] == 5.00
        assert bracket["take_profit_price"] == 3.75
        assert bracket["net_premium"] == 2.50

    @pytest.mark.asyncio
    async def test_create_bracket_exceeds_max_sl(
        self, mock_ib_conn, sample_entry_order
    ):
        """Test that SL exceeding max is rejected."""
        # Mock placeOrder for bracket placement
        mock_trade = MagicMock()
        mock_trade.order.orderId = 1001
        mock_ib_conn.ib.placeOrder.return_value = mock_trade

        manager = BracketOrderManager(mock_ib_conn)

        # SL of 6.00 exceeds 2x net_premium (2.50 * 2 = 5.00)
        with pytest.raises(ValueError, match="exceeds max"):
            await manager.create_bracket(
                entry_order=sample_entry_order,
                stop_loss_price=6.00,  # Too high
                take_profit_price=3.75,
            )

    @pytest.mark.asyncio
    async def test_create_bracket_no_net_premium(self, mock_ib_conn):
        """Test that order without net_premium raises error."""
        manager = BracketOrderManager(mock_ib_conn)

        order = Order(
            order_id="entry-order-1",
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
        )
        # No metadata attribute

        with pytest.raises(ValueError, match="net_premium"):
            await manager.create_bracket(
                entry_order=order,
                stop_loss_price=5.00,
            )

    @pytest.mark.asyncio
    async def test_create_bracket_auto_calculate_tp(
        self, mock_ib_conn, sample_entry_order
    ):
        """Test automatic TP calculation when not provided."""
        # Mock placeOrder
        mock_trade = MagicMock()
        mock_trade.order.orderId = 1001
        mock_ib_conn.ib.placeOrder.return_value = mock_trade

        manager = BracketOrderManager(mock_ib_conn)

        # Don't provide take_profit_price
        bracket_id = await manager.create_bracket(
            entry_order=sample_entry_order,
            stop_loss_price=5.00,
            take_profit_price=None,  # Auto-calculate
        )

        bracket = manager.active_brackets[bracket_id]
        # TP should be net_premium * 0.5 = 2.50 * 0.5 = 1.25
        assert bracket["take_profit_price"] == 1.25

    @pytest.mark.asyncio
    async def test_cancel_bracket_success(
        self, mock_ib_conn, sample_entry_order, sample_contract
    ):
        """Test successful bracket cancellation."""
        # Mock placeOrder
        mock_trade = MagicMock()
        mock_trade.order.orderId = 1001
        mock_ib_conn.ib.placeOrder.return_value = mock_trade

        manager = BracketOrderManager(mock_ib_conn)

        # Create bracket
        bracket_id = await manager.create_bracket(
            entry_order=sample_entry_order,
            stop_loss_price=5.00,
            take_profit_price=3.75,
            entry_contract=sample_contract,
        )

        # Cancel bracket
        result = await manager.cancel_bracket(bracket_id)

        assert result is True
        assert manager.active_brackets[bracket_id]["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_bracket_not_found(self, mock_ib_conn):
        """Test cancelling non-existent bracket."""
        manager = BracketOrderManager(mock_ib_conn)

        result = await manager.cancel_bracket("non-existent")

        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_bracket_already_stopped_out(
        self, mock_ib_conn, sample_entry_order, sample_contract
    ):
        """Test cancelling already-stopped-out bracket."""
        # Mock placeOrder
        mock_trade = MagicMock()
        mock_trade.order.orderId = 1001
        mock_ib_conn.ib.placeOrder.return_value = mock_trade

        manager = BracketOrderManager(mock_ib_conn)

        # Create bracket
        bracket_id = await manager.create_bracket(
            entry_order=sample_entry_order,
            stop_loss_price=5.00,
            take_profit_price=3.75,
            entry_contract=sample_contract,
        )

        # Mark as stopped_out
        manager.active_brackets[bracket_id]["status"] = "stopped_out"

        # Should succeed without calling cancelOrder
        result = await manager.cancel_bracket(bracket_id)

        assert result is True
        mock_ib_conn.ib.cancelOrder.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_bracket_status(
        self, mock_ib_conn, sample_entry_order, sample_contract
    ):
        """Test getting bracket status."""
        # Mock placeOrder
        mock_trade = MagicMock()
        mock_trade.order.orderId = 1001
        mock_ib_conn.ib.placeOrder.return_value = mock_trade

        manager = BracketOrderManager(mock_ib_conn)

        # Create bracket
        bracket_id = await manager.create_bracket(
            entry_order=sample_entry_order,
            stop_loss_price=5.00,
            take_profit_price=3.75,
            entry_contract=sample_contract,
        )

        # Get status
        status = await manager.get_bracket_status(bracket_id)

        assert status["bracket_id"] == bracket_id
        assert status["overall_status"] in ("pending", "active")
        assert "entry_status" in status
        assert "stop_loss_status" in status
        assert "take_profit_status" in status

    @pytest.mark.asyncio
    async def test_get_bracket_status_not_found(self, mock_ib_conn):
        """Test getting status of non-existent bracket."""
        manager = BracketOrderManager(mock_ib_conn)

        with pytest.raises(ValueError, match="not found"):
            await manager.get_bracket_status("non-existent")

    @pytest.mark.asyncio
    async def test_adjust_stop_loss_success(
        self, mock_ib_conn_with_place_order, sample_entry_order, sample_contract
    ):
bracket_id = await manager.create_bracket(
            entry_order=sample_entry_order,
            stop_loss_price=5.00,
            take_profit_price=3.75,
            entry_contract=None,  # Skip IB submission for adjustment test
        )

        # Adjust stop loss
        result = await manager.adjust_stop_loss(bracket_id, 4.50)

        assert result is True
        assert manager.active_brackets[bracket_id]["stop_loss_price"] == 4.50

    @pytest.mark.asyncio
    async def test_adjust_stop_loss_exceeds_max(
        self, mock_ib_conn, sample_entry_order, sample_contract
    ):
        """Test that SL adjustment exceeding max is rejected."""
        manager = BracketOrderManager(mock_ib_conn)

        # Create bracket
        bracket_id = await manager.create_bracket(
            entry_order=sample_entry_order,
            stop_loss_price=5.00,
            take_profit_price=3.75,
            entry_contract=sample_contract,
        )

        # Try to adjust SL beyond max
        with pytest.raises(ValueError, match="exceeds max"):
            await manager.adjust_stop_loss(bracket_id, 6.00)

    @pytest.mark.asyncio
    async def test_adjust_stop_loss_not_active(
        self, mock_ib_conn, sample_entry_order, sample_contract
    ):
        """Test that SL adjustment fails for inactive brackets."""
        manager = BracketOrderManager(mock_ib_conn)

        # Create bracket
        bracket_id = await manager.create_bracket(
            entry_order=sample_entry_order,
            stop_loss_price=5.00,
            take_profit_price=3.75,
            entry_contract=sample_contract,
        )

        # Mark as cancelled
        manager.active_brackets[bracket_id]["status"] = "cancelled"

        # Should fail
        with pytest.raises(ValueError, match="cannot adjust"):
            await manager.adjust_stop_loss(bracket_id, 4.50)

    @pytest.mark.asyncio
    async def test_adjust_take_profit_success(
        self, mock_ib_conn, sample_entry_order, sample_contract
    ):
        """Test successful take profit adjustment."""
        manager = BracketOrderManager(mock_ib_conn)

        # Create bracket
        bracket_id = await manager.create_bracket(
            entry_order=sample_entry_order,
            stop_loss_price=5.00,
            take_profit_price=3.75,
            entry_contract=sample_contract,
        )

        # Adjust take profit
        result = await manager.adjust_take_profit(bracket_id, 4.00)

        assert result is True
        assert manager.active_brackets[bracket_id]["take_profit_price"] == 4.00

    @pytest.mark.asyncio
    async def test_trail_stop_loss_long_favorable(
        self, mock_ib_conn, sample_entry_order, sample_contract
    ):
        """Test trailing stop for long position with favorable price movement."""
        manager = BracketOrderManager(mock_ib_conn)

        # Create bracket
        bracket_id = await manager.create_bracket(
            entry_order=sample_entry_order,
            stop_loss_price=5.00,
            take_profit_price=3.75,
            entry_contract=sample_contract,
        )

        # Price moved up from 450 to 455 (favorable for long)
        # Trail amount = 0.50
        # New stop = 455 - 0.50 = 454.50 (higher than current 5.00 stop)
        result = await manager.trail_stop_loss(
            bracket_id=bracket_id,
            trail_amount=0.50,
            current_price=455.0,
            direction="long",
        )

        assert result is True
        assert manager.active_brackets[bracket_id]["stop_loss_price"] == 454.50

    @pytest.mark.asyncio
    async def test_trail_stop_loss_long_unfavorable(
        self, mock_ib_conn, sample_entry_order, sample_contract
    ):
        """Test trailing stop for long position with unfavorable price movement."""
        manager = BracketOrderManager(mock_ib_conn)

        # Create bracket
        bracket_id = await manager.create_bracket(
            entry_order=sample_entry_order,
            stop_loss_price=5.00,
            take_profit_price=3.75,
            entry_contract=sample_contract,
        )

        # Price moved down (unfavorable for long)
        # New stop would be lower, so should not trail
        result = await manager.trail_stop_loss(
            bracket_id=bracket_id,
            trail_amount=0.50,
            current_price=445.0,
            direction="long",
        )

        assert result is False  # Should not trail
        assert manager.active_brackets[bracket_id]["stop_loss_price"] == 5.00  # Unchanged

    @pytest.mark.asyncio
    async def test_trail_stop_loss_short_favorable(
        self, mock_ib_conn, sample_entry_order, sample_contract
    ):
        """Test trailing stop for short position with favorable price movement."""
        manager = BracketOrderManager(mock_ib_conn)

        # Create bracket
        bracket_id = await manager.create_bracket(
            entry_order=sample_entry_order,
            stop_loss_price=5.00,
            take_profit_price=3.75,
            entry_contract=sample_contract,
        )

        # Price moved down (favorable for short)
        # Trail amount = 0.50
        # New stop = 445 + 0.50 = 445.50 (lower than current 5.00 stop)
        result = await manager.trail_stop_loss(
            bracket_id=bracket_id,
            trail_amount=0.50,
            current_price=445.0,
            direction="short",
        )

        assert result is True
        assert manager.active_brackets[bracket_id]["stop_loss_price"] == 445.50

    @pytest.mark.asyncio
    async def test_create_strategy_bracket_iron_condor(
        self, mock_ib_conn, sample_iron_condor
    ):
        """Test creating bracket for iron condor strategy."""
        # Add net_premium to metadata
        sample_iron_condor.metadata = {"net_premium": 1.50, "wing_width": 10.0}

        manager = BracketOrderManager(mock_ib_conn)

        # Create bracket for strategy
        bracket_id = await manager.create_strategy_bracket(sample_iron_condor)

        # Verify bracket created
        assert bracket_id is not None
        assert bracket_id in manager.active_brackets

        bracket = manager.active_brackets[bracket_id]
        # Iron Condor: SL at wing_width (10.0), TP at 0.5 * premium (0.75)
        assert bracket["stop_loss_price"] == 10.0
        assert bracket["take_profit_price"] == 0.75

    @pytest.mark.asyncio
    async def test_create_strategy_bracket_credit_spread(
        self, mock_ib_conn, sample_vertical_spread
    ):
        """Test creating bracket for credit spread strategy."""
        # Add metadata for credit spread
        sample_vertical_spread.metadata = {
            "net_premium": 1.00,
            "spread_width": 5.0,
        }

        manager = BracketOrderManager(mock_ib_conn)

        # Create bracket for strategy
        bracket_id = await manager.create_strategy_bracket(sample_vertical_spread)

        bracket = manager.active_brackets[bracket_id]
        # Credit spread: SL at spread_width (5.0), TP at 0.8 * premium (0.80)
        assert bracket["stop_loss_price"] == 5.0
        assert bracket["take_profit_price"] == 0.80

    @pytest.mark.asyncio
    async def test_monitor_strategy_brackets(
        self, mock_ib_conn, sample_iron_condor
    ):
        """Test monitoring brackets for a strategy."""
        # Add net_premium to metadata
        sample_iron_condor.metadata = {"net_premium": 1.50, "wing_width": 10.0}

        manager = BracketOrderManager(mock_ib_conn)

        # Create multiple brackets
        bracket_id_1 = await manager.create_strategy_bracket(sample_iron_condor)
        bracket_id_2 = await manager.create_strategy_bracket(sample_iron_condor)

        # Mark one as complete
        manager.active_brackets[bracket_id_2]["status"] = "profit_taken"

        # Monitor active brackets
        active_brackets = await manager.monitor_strategy_brackets(
            strategy_id=sample_iron_condor.strategy_id
        )

        # Should only return active brackets
        assert len(active_brackets) == 1
        assert active_brackets[0]["bracket_id"] == bracket_id_1
