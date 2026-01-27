"""
Unit Tests for OrderExecutionEngine

Tests order placement, cancellation, bracket orders, and position management.
Run with: pytest src/v6/execution/test_engine.py -v
"""

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from ib_async import LimitOrder

from src.v6.execution.engine import OrderExecutionEngine
from src.v6.execution.models import (
    BracketOrder,
    ExecutionResult,
    OrderAction,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from src.v6.execution.models import (
    Order as OrderModel,
)
from src.v6.strategies.models import (
    LegAction,
    LegSpec,
    OptionRight,
    Strategy,
    StrategyType,
)
from src.v6.utils.ib_connection import IBConnectionManager


# Helper function to create future dates
def future_date(days=30):
    """Create a date in the future."""
    return date.today() + timedelta(days=days)


class TestOrderExecutionEngine:
    """Tests for OrderExecutionEngine."""

    @pytest.fixture
    def ib_conn(self):
        """Create mock IB connection manager."""
        ib_conn = MagicMock(spec=IBConnectionManager)
        ib_conn.ib = MagicMock()
        ib_conn.ensure_connected = AsyncMock()
        return ib_conn

    @pytest.fixture
    def engine(self, ib_conn):
        """Create OrderExecutionEngine instance."""
        return OrderExecutionEngine(ib_conn, dry_run=False)

    @pytest.fixture
    def dry_run_engine(self, ib_conn):
        """Create OrderExecutionEngine in dry run mode."""
        return OrderExecutionEngine(ib_conn, dry_run=True)

    @pytest.fixture
    def sample_contract(self):
        """Create sample IB contract."""
        contract = MagicMock()
        contract.conId = 123456
        contract.symbol = "SPY"
        return contract

    @pytest.fixture
    def sample_order(self):
        """Create sample order model."""
        return OrderModel(
            order_id=str(uuid4()),
            conid=123456,
            action=OrderAction.BUY,
            quantity=1,
            order_type=OrderType.MARKET,
            limit_price=None,
            stop_price=None,
            tif=TimeInForce.DAY,
            status=OrderStatus.PENDING_SUBMIT,
            filled_quantity=0,
            avg_fill_price=None,
            order_ref=None,
            parent_order_id=None,
            oca_group=None,
            created_at=datetime.now(),
            filled_at=None,
        )

    @pytest.mark.asyncio
    async def test_place_market_order(self, engine, sample_contract, sample_order):
        """Test placing a market order."""
        # Mock IB placeOrder response
        mock_trade = MagicMock()
        mock_trade.order.orderId = 12345
        engine.ib.placeOrder = MagicMock(return_value=mock_trade)

        # Place order
        result = await engine.place_order(sample_contract, sample_order)

        # Verify order was placed
        engine.ib.placeOrder.assert_called_once()
        assert result.status == OrderStatus.SUBMITTED
        assert result.conid == sample_contract.conId

    @pytest.mark.asyncio
    async def test_place_limit_order(self, engine, sample_contract):
        """Test placing a limit order."""
        limit_order = OrderModel(
            order_id=str(uuid4()),
            conid=123456,
            action=OrderAction.BUY,
            quantity=2,
            order_type=OrderType.LIMIT,
            limit_price=100.0,
            stop_price=None,
            tif=TimeInForce.DAY,
            status=OrderStatus.PENDING_SUBMIT,
            filled_quantity=0,
            avg_fill_price=None,
            order_ref=None,
            parent_order_id=None,
            oca_group=None,
            created_at=datetime.now(),
            filled_at=None,
        )

        # Mock IB placeOrder response
        mock_trade = MagicMock()
        mock_trade.order.orderId = 12346
        engine.ib.placeOrder = MagicMock(return_value=mock_trade)

        # Place order
        result = await engine.place_order(sample_contract, limit_order)

        # Verify order was placed with limit price
        engine.ib.placeOrder.assert_called_once()
        placed_order = engine.ib.placeOrder.call_args[0][1]
        assert isinstance(placed_order, LimitOrder)
        assert placed_order.lmtPrice == 100.0
        assert result.status == OrderStatus.SUBMITTED

    @pytest.mark.asyncio
    async def test_cancel_order(self, engine):
        """Test cancelling an order."""
        order_id = "12345"

        # Mock IB cancelOrder
        engine.ib.cancelOrder = MagicMock()

        # Cancel order
        result = await engine.cancel_order(order_id)

        # Verify cancellation
        engine.ib.cancelOrder.assert_called_once_with(12345)
        assert result is True

    @pytest.mark.asyncio
    async def test_bracket_order_placement(self, engine, sample_contract):
        """Test placing a bracket order with TP and SL."""
        # Create parent order
        parent_order = OrderModel(
            order_id=str(uuid4()),
            conid=123456,
            action=OrderAction.BUY,
            quantity=1,
            order_type=OrderType.LIMIT,
            limit_price=100.0,
            stop_price=None,
            tif=TimeInForce.GTC,
            status=OrderStatus.PENDING_SUBMIT,
            filled_quantity=0,
            avg_fill_price=None,
            order_ref=None,
            parent_order_id=None,
            oca_group=None,
            created_at=datetime.now(),
            filled_at=None,
        )

        # Create take profit order
        tp_order = OrderModel(
            order_id=str(uuid4()),
            conid=123456,
            action=OrderAction.SELL,
            quantity=1,
            order_type=OrderType.LIMIT,
            limit_price=110.0,
            stop_price=None,
            tif=TimeInForce.GTC,
            status=OrderStatus.PENDING_SUBMIT,
            filled_quantity=0,
            avg_fill_price=None,
            order_ref=None,
            parent_order_id=parent_order.order_id,
            oca_group="bracket_123",
            created_at=datetime.now(),
            filled_at=None,
        )

        # Create stop loss order
        sl_order = OrderModel(
            order_id=str(uuid4()),
            conid=123456,
            action=OrderAction.SELL,
            quantity=1,
            order_type=OrderType.STOP,
            limit_price=None,
            stop_price=95.0,
            tif=TimeInForce.GTC,
            status=OrderStatus.PENDING_SUBMIT,
            filled_quantity=0,
            avg_fill_price=None,
            order_ref=None,
            parent_order_id=parent_order.order_id,
            oca_group="bracket_123",
            created_at=datetime.now(),
            filled_at=None,
        )

        # Create bracket order
        bracket = BracketOrder(
            parent_order=parent_order,
            take_profit=tp_order,
            stop_loss=sl_order,
            oca_group="bracket_123",
        )

        # Mock IB placeOrder responses
        call_count = [0]

        def mock_place_order(contract, order):
            call_count[0] += 1
            mock_trade = MagicMock()
            mock_trade.order.orderId = 12340 + call_count[0]
            # Store the order for inspection
            mock_trade.order_args = (contract, order)
            return mock_trade

        engine.ib.placeOrder = MagicMock(side_effect=mock_place_order)

        # Place bracket order (entry contract used for all orders)
        result = await engine.place_bracket_order(
            bracket,
            entry_contract=sample_contract,
            tp_contract=sample_contract,
            sl_contract=sample_contract,
        )

        # Verify bracket order placed correctly
        assert result.success is True
        assert result.action_taken == "BRACKET_PLACED"
        assert len(result.order_ids) == 3
        assert engine.ib.placeOrder.call_count == 3

        # Verify orders were placed with correct properties
        # First call should be TP (transmit=False)
        tp_call_order = engine.ib.placeOrder.call_args_list[0][0][1]
        assert tp_call_order.transmit is False
        assert tp_call_order.ocaGroup == "bracket_123"

        # Second call should be SL (transmit=False)
        sl_call_order = engine.ib.placeOrder.call_args_list[1][0][1]
        assert sl_call_order.transmit is False
        assert sl_call_order.ocaGroup == "bracket_123"

        # Third call should be parent (transmit=True)
        parent_call_order = engine.ib.placeOrder.call_args_list[2][0][1]
        assert parent_call_order.transmit is True
        assert parent_call_order.ocaGroup == "bracket_123"

    @pytest.mark.asyncio
    async def test_close_position(self, engine):
        """Test closing a position by placing opposite orders."""
        # Create strategy with legs
        strategy = Strategy(
            strategy_id="test_strategy_123",
            symbol="SPY",
            strategy_type=StrategyType.IRON_CONDOR,
            legs=[
                LegSpec(
                    right=OptionRight.PUT,
                    strike=440.0,
                    quantity=1,
                    action=LegAction.SELL,
                    expiration=future_date(30),
                ),
                LegSpec(
                    right=OptionRight.PUT,
                    strike=435.0,
                    quantity=1,
                    action=LegAction.BUY,
                    expiration=future_date(30),
                ),
            ],
        )

        # Mock IB qualification and placeOrder
        engine.ib.qualifyContractsAsync = AsyncMock()
        mock_trade = MagicMock()
        mock_trade.order.orderId = 12350
        engine.ib.placeOrder = MagicMock(return_value=mock_trade)

        # Close position
        result = await engine.close_position(strategy)

        # Verify close orders placed
        assert result.success is True
        assert result.action_taken == "CLOSED"
        assert len(result.order_ids) == 2
        assert engine.ib.placeOrder.call_count == 2

    @pytest.mark.asyncio
    async def test_roll_position(self, engine):
        """Test rolling a position to new DTE."""
        # Create strategy
        strategy = Strategy(
            strategy_id="test_strategy_123",
            symbol="SPY",
            strategy_type=StrategyType.VERTICAL_SPREAD,
            legs=[
                LegSpec(
                    right=OptionRight.CALL,
                    strike=450.0,
                    quantity=1,
                    action=LegAction.BUY,
                    expiration=future_date(30),
                ),
            ],
        )

        # Mock close_position
        engine.close_position = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                action_taken="CLOSED",
                order_ids=["close_123"],
                error_message=None,
            )
        )

        # Roll position
        result = await engine.roll_position(strategy, new_dte=45)

        # Verify roll completed
        assert result.success is True
        assert result.action_taken == "ROLLED"
        assert "close_123" in result.order_ids
        engine.close_position.assert_called_once_with(strategy)

    @pytest.mark.asyncio
    async def test_error_handling_invalid_order(self, engine, sample_contract):
        """Test error handling for invalid order."""
        # Invalid order (negative quantity) should raise ValueError during creation
        with pytest.raises(ValueError, match="Quantity must be positive"):
            OrderModel(
                order_id=str(uuid4()),
                conid=123456,
                action=OrderAction.BUY,
                quantity=-1,  # Invalid
                order_type=OrderType.MARKET,
                limit_price=None,
                stop_price=None,
                tif=TimeInForce.DAY,
                status=OrderStatus.PENDING_SUBMIT,
                filled_quantity=0,
                avg_fill_price=None,
                order_ref=None,
                parent_order_id=None,
                oca_group=None,
                created_at=datetime.now(),
                filled_at=None,
            )

    @pytest.mark.asyncio
    async def test_dry_run_mode(self, dry_run_engine, sample_contract, sample_order):
        """Test dry run mode simulates orders without IB API calls."""
        # Place order in dry run mode
        result = await dry_run_engine.place_order(sample_contract, sample_order)

        # Verify no IB API calls
        dry_run_engine.ib.placeOrder.assert_not_called()

        # Verify order marked as filled (dry run simulates successful fill)
        assert result.status == OrderStatus.FILLED
        assert result.filled_quantity == sample_order.quantity
        assert result.filled_at is not None

    @pytest.mark.asyncio
    async def test_dry_run_bracket_order(
        self, dry_run_engine, sample_contract
    ):
        """Test dry run mode for bracket orders."""
        # Create bracket order
        parent_order = OrderModel(
            order_id=str(uuid4()),
            conid=123456,
            action=OrderAction.BUY,
            quantity=1,
            order_type=OrderType.LIMIT,
            limit_price=100.0,
            stop_price=None,
            tif=TimeInForce.GTC,
            status=OrderStatus.PENDING_SUBMIT,
            filled_quantity=0,
            avg_fill_price=None,
            order_ref=None,
            parent_order_id=None,
            oca_group=None,
            created_at=datetime.now(),
            filled_at=None,
        )

        tp_order = OrderModel(
            order_id=str(uuid4()),
            conid=123456,
            action=OrderAction.SELL,
            quantity=1,
            order_type=OrderType.LIMIT,
            limit_price=110.0,
            stop_price=None,
            tif=TimeInForce.GTC,
            status=OrderStatus.PENDING_SUBMIT,
            filled_quantity=0,
            avg_fill_price=None,
            order_ref=None,
            parent_order_id=parent_order.order_id,
            oca_group="bracket_123",
            created_at=datetime.now(),
            filled_at=None,
        )

        bracket = BracketOrder(
            parent_order=parent_order,
            take_profit=tp_order,
            stop_loss=None,
            oca_group="bracket_123",
        )

        # Place bracket order in dry run mode
        result = await dry_run_engine.place_bracket_order(bracket, sample_contract)

        # Verify no IB API calls
        dry_run_engine.ib.placeOrder.assert_not_called()

        # Verify result
        assert result.success is True
        assert result.action_taken == "DRY_RUN"
        assert len(result.order_ids) == 2  # parent + TP

    @pytest.mark.asyncio
    async def test_dry_run_close_position(self, dry_run_engine):
        """Test dry run mode for closing position."""
        # Create strategy
        strategy = Strategy(
            strategy_id="test_strategy_123",
            symbol="SPY",
            strategy_type=StrategyType.IRON_CONDOR,
            legs=[
                LegSpec(
                    right=OptionRight.PUT,
                    strike=440.0,
                    quantity=1,
                    action=LegAction.SELL,
                    expiration=future_date(30),
                ),
            ],
        )

        # Close position in dry run mode
        result = await dry_run_engine.close_position(strategy)

        # Verify no IB API calls (dry run doesn't call IB)
        # Note: dry_run creates orders without placing them
        assert result.success is True
        assert result.action_taken == "CLOSED"
        assert len(result.order_ids) == 1
        assert result.order_ids[0].startswith("DRY_")

    @pytest.mark.asyncio
    async def test_place_order_with_wrong_status(self, engine, sample_contract):
        """Test placing order with wrong status raises error."""
        # Create order with FILLED status (can't place)
        filled_order = OrderModel(
            order_id=str(uuid4()),
            conid=123456,
            action=OrderAction.BUY,
            quantity=1,
            order_type=OrderType.MARKET,
            limit_price=None,
            stop_price=None,
            tif=TimeInForce.DAY,
            status=OrderStatus.FILLED,  # Wrong status
            filled_quantity=1,
            avg_fill_price=100.0,
            order_ref=None,
            parent_order_id=None,
            oca_group=None,
            created_at=datetime.now(),
            filled_at=datetime.now(),
        )

        # Should raise ValueError
        with pytest.raises(ValueError, match="must be PENDING_SUBMIT"):
            await engine.place_order(sample_contract, filled_order)

    @pytest.mark.asyncio
    async def test_cancel_order_failure(self, engine):
        """Test cancel order handling on failure."""
        order_id = "12345"

        # Mock IB cancelOrder to raise exception
        engine.ib.cancelOrder = MagicMock(side_effect=Exception("Connection lost"))

        # Cancel order
        result = await engine.cancel_order(order_id)

        # Verify failure handled
        assert result is False

    @pytest.mark.asyncio
    async def test_bracket_order_without_tp_or_sl(self, sample_contract):
        """Test bracket order requires at least TP or SL."""
        # Create parent order
        parent_order = OrderModel(
            order_id=str(uuid4()),
            conid=123456,
            action=OrderAction.BUY,
            quantity=1,
            order_type=OrderType.LIMIT,
            limit_price=100.0,
            stop_price=None,
            tif=TimeInForce.GTC,
            status=OrderStatus.PENDING_SUBMIT,
            filled_quantity=0,
            avg_fill_price=None,
            order_ref=None,
            parent_order_id=None,
            oca_group=None,
            created_at=datetime.now(),
            filled_at=None,
        )

        # Create bracket without TP or SL (should fail validation)
        with pytest.raises(ValueError, match="at least take profit or stop loss"):
            BracketOrder(
                parent_order=parent_order,
                take_profit=None,
                stop_loss=None,
                oca_group="bracket_123",
            )

    @pytest.mark.asyncio
    async def test_close_position_with_leg_close_failure(self, engine):
        """Test closing position when leg close fails partially."""
        # Create strategy with multiple legs
        strategy = Strategy(
            strategy_id="test_strategy_123",
            symbol="SPY",
            strategy_type=StrategyType.IRON_CONDOR,
            legs=[
                LegSpec(
                    right=OptionRight.PUT,
                    strike=440.0,
                    quantity=1,
                    action=LegAction.SELL,
                    expiration=future_date(30),
                ),
                LegSpec(
                    right=OptionRight.CALL,
                    strike=460.0,
                    quantity=1,
                    action=LegAction.SELL,
                    expiration=future_date(30),
                ),
            ],
        )

        # Mock IB to raise exception on second leg
        engine.ib.qualifyContractsAsync = AsyncMock()

        def mock_place_order(contract, order):
            # Simulate failure on second leg
            if "460" in str(contract.strike):
                raise Exception("Order rejected")
            mock_trade = MagicMock()
            mock_trade.order.orderId = 12351
            return mock_trade

        engine.ib.placeOrder = MagicMock(side_effect=mock_place_order)

        # Close position
        result = await engine.close_position(strategy)

        # Verify partial success (one leg closed)
        assert result.success is True  # At least one order succeeded
        assert result.action_taken == "CLOSED"
        assert len(result.order_ids) == 1  # Only first leg succeeded
