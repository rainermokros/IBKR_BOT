"""
Integration tests for OCA and bracket managers with strategy execution.

Tests submitting multi-leg strategies via OCA, bracket creation for all template types,
and multi-position monitoring.
"""

import pytest
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

from src.v6.execution.oca_order_manager import OCAOrderManager
from src.v6.execution.bracket_order_manager import BracketOrderManager
from src.v6.strategies.models import LegAction, LegSpec, OptionRight, Strategy, StrategyType
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
def sample_iron_condor_strategy():
    """Create sample iron condor strategy."""
    return Strategy(
        strategy_id="test-ic-001",
        symbol="SPY",
        strategy_type=StrategyType.IRON_CONDOR,
        legs=[
            LegSpec(
                right=OptionRight.PUT,
                strike=450.0,
                quantity=1,
                action=LegAction.SELL,
                expiration=date(2026, 3, 20),
            ),
            LegSpec(
                right=OptionRight.PUT,
                strike=440.0,
                quantity=1,
                action=LegAction.BUY,
                expiration=date(2026, 3, 20),
            ),
            LegSpec(
                right=OptionRight.CALL,
                strike=460.0,
                quantity=1,
                action=LegAction.SELL,
                expiration=date(2026, 3, 20),
            ),
            LegSpec(
                right=OptionRight.CALL,
                strike=470.0,
                quantity=1,
                action=LegAction.BUY,
                expiration=date(2026, 3, 20),
            ),
        ],
        metadata={"net_premium": 1.50, "wing_width": 10.0},
    )


@pytest.fixture
def sample_call_spread_strategy():
    """Create sample call spread strategy."""
    return Strategy(
        strategy_id="test-cs-001",
        symbol="QQQ",
        strategy_type=StrategyType.VERTICAL_SPREAD,
        legs=[
            LegSpec(
                right=OptionRight.CALL,
                strike=450.0,
                quantity=1,
                action=LegAction.BUY,
                expiration=date(2026, 3, 20),
            ),
            LegSpec(
                right=OptionRight.CALL,
                strike=460.0,
                quantity=1,
                action=LegAction.SELL,
                expiration=date(2026, 3, 20),
            ),
        ],
        metadata={"net_premium": -2.00, "spread_width": 10.0},
    )


@pytest.fixture
def sample_put_spread_strategy():
    """Create sample put spread strategy."""
    return Strategy(
        strategy_id="test-ps-001",
        symbol="IWM",
        strategy_type=StrategyType.VERTICAL_SPREAD,
        legs=[
            LegSpec(
                right=OptionRight.PUT,
                strike=200.0,
                quantity=1,
                action=LegAction.SELL,
                expiration=date(2026, 3, 20),
            ),
            LegSpec(
                right=OptionRight.PUT,
                strike=195.0,
                quantity=1,
                action=LegAction.BUY,
                expiration=date(2026, 3, 20),
            ),
        ],
        metadata={"net_premium": 1.25, "spread_width": 5.0},
    )


@pytest.fixture
def sample_wheel_strategy():
    """Create sample wheel strategy."""
    return Strategy(
        strategy_id="test-wheel-001",
        symbol="SPY",
        strategy_type=StrategyType.CUSTOM,
        legs=[
            LegSpec(
                right=OptionRight.PUT,
                strike=440.0,
                quantity=100,
                action=LegAction.SELL,
                expiration=date(2026, 3, 20),
            ),
        ],
        metadata={"net_premium": 1.75, "roll_threshold": 0.10},
    )


class TestStrategyOCAIntegration:
    """Test OCA manager integration with strategies."""

    @pytest.mark.asyncio
    async def test_submit_multi_leg_strategy_via_oca(
        self, mock_ib_conn, sample_iron_condor_strategy
    ):
        """Test submitting multi-leg iron condor via OCA group."""
        # Mock placeOrder
        mock_trade = MagicMock()
        mock_trade.order.orderId = 1001
        mock_ib_conn.ib.placeOrder.return_value = mock_trade

        oca_manager = OCAOrderManager(mock_ib_conn)

        # Create contracts for each leg
        contracts = []
        for leg in sample_iron_condor_strategy.legs:
            contract = MagicMock()
            contract.conId = 123456
            contract.symbol = "SPY"
            contracts.append(contract)

        # Submit strategy as OCA
        oca_group_id = await oca_manager.submit_strategy_oca_orders(
            sample_iron_condor_strategy,
            contracts,
        )

        # Verify OCA group created
        assert oca_group_id is not None
        assert oca_group_id in oca_manager.active_oca_groups

        group = oca_manager.active_oca_groups[oca_group_id]
        assert len(group["order_ids"]) == 4  # 4 legs
        assert group["symbol"] == "SPY"
        assert group["status"] == "pending"

    @pytest.mark.asyncio
    async def test_oca_fill_cancels_remaining_orders(
        self, mock_ib_conn, sample_iron_condor_strategy
    ):
        """Test that OCA fill cancels remaining orders."""
        # Mock placeOrder
        mock_trade = MagicMock()
        mock_trade.order.orderId = 1001
        mock_ib_conn.ib.placeOrder.return_value = mock_trade

        oca_manager = OCAOrderManager(mock_ib_conn)

        # Create contracts
        contracts = []
        for _ in sample_iron_condor_strategy.legs:
            contract = MagicMock()
            contract.conId = 123456
            contract.symbol = "SPY"
            contracts.append(contract)

        # Submit strategy
        oca_group_id = await oca_manager.submit_strategy_oca_orders(
            sample_iron_condor_strategy,
            contracts,
        )

        # Simulate fill of first order
        order_ids = oca_manager.active_oca_groups[oca_group_id]["order_ids"]
        filled_order_id = order_ids[0]

        await oca_manager.handle_oca_fill(oca_group_id, filled_order_id, 1.50)

        # Verify status updated to complete
        status = await oca_manager.get_oca_status(oca_group_id)
        assert status["status"] == "complete"


class TestStrategyBracketIntegration:
    """Test bracket manager integration with strategies."""

    @pytest.mark.asyncio
    async def test_bracket_creation_for_iron_condor(
        self, mock_ib_conn, sample_iron_condor_strategy
    ):
        """Test bracket creation for iron condor strategy."""
        bracket_manager = BracketOrderManager(mock_ib_conn)

        # Create bracket for iron condor
        bracket_id = await bracket_manager.create_strategy_bracket(
            sample_iron_condor_strategy,
            max_sl_ratio=2.0,
        )

        # Verify bracket created
        assert bracket_id is not None
        assert bracket_id in bracket_manager.active_brackets

        bracket = bracket_manager.active_brackets[bracket_id]
        # Iron Condor: SL at wing_width, TP at 0.5 * premium
        assert bracket["stop_loss_price"] == 10.0
        assert bracket["take_profit_price"] == 0.75  # 1.50 * 0.5
        assert bracket["net_premium"] == 1.50

    @pytest.mark.asyncio
    async def test_bracket_creation_for_call_spread(
        self, mock_ib_conn, sample_call_spread_strategy
    ):
        """Test bracket creation for call spread strategy."""
        bracket_manager = BracketOrderManager(mock_ib_conn)

        # Create bracket for call spread
        bracket_id = await bracket_manager.create_strategy_bracket(
            sample_call_spread_strategy,
            max_sl_ratio=2.0,
        )

        bracket = bracket_manager.active_brackets[bracket_id]
        # Debit call spread: SL at premium paid, TP at spread_width - premium
        assert bracket["stop_loss_price"] == 2.00  # Premium paid
        assert bracket["take_profit_price"] == 8.00  # 10.0 - 2.0

    @pytest.mark.asyncio
    async def test_bracket_creation_for_put_spread(
        self, mock_ib_conn, sample_put_spread_strategy
    ):
        """Test bracket creation for put spread strategy."""
        bracket_manager = BracketOrderManager(mock_ib_conn)

        # Create bracket for put spread
        bracket_id = await bracket_manager.create_strategy_bracket(
            sample_put_spread_strategy,
            max_sl_ratio=2.0,
        )

        bracket = bracket_manager.active_brackets[bracket_id]
        # Credit put spread: SL at spread_width, TP at 0.8 * premium
        assert bracket["stop_loss_price"] == 5.0  # Spread width
        assert bracket["take_profit_price"] == 1.00  # 1.25 * 0.8

    @pytest.mark.asyncio
    async def test_bracket_creation_for_wheel(
        self, mock_ib_conn, sample_wheel_strategy
    ):
        """Test bracket creation for wheel strategy."""
        bracket_manager = BracketOrderManager(mock_ib_conn)

        # Create bracket for wheel
        bracket_id = await bracket_manager.create_strategy_bracket(
            sample_wheel_strategy,
            max_sl_ratio=2.0,
        )

        bracket = bracket_manager.active_brackets[bracket_id]
        # Wheel: SL at roll_threshold * 100, TP at 0.5 * premium
        assert bracket["stop_loss_price"] == 10.0  # 0.10 * 100
        assert bracket["take_profit_price"] == 0.875  # 1.75 * 0.5

    @pytest.mark.asyncio
    async def test_bracket_max_sl_enforcement_for_all_templates(
        self,
        mock_ib_conn,
        sample_iron_condor_strategy,
        sample_call_spread_strategy,
        sample_put_spread_strategy,
        sample_wheel_strategy,
    ):
        """Test that max SL ratio is enforced for all template types."""
        bracket_manager = BracketOrderManager(mock_ib_conn)

        strategies = [
            ("iron_condor", sample_iron_condor_strategy),
            ("call_spread", sample_call_spread_strategy),
            ("put_spread", sample_put_spread_strategy),
            ("wheel", sample_wheel_strategy),
        ]

        for name, strategy in strategies:
            # Create bracket with aggressive max_sl_ratio
            bracket_id = await bracket_manager.create_strategy_bracket(
                strategy,
                max_sl_ratio=1.5,  # More conservative
            )

            bracket = bracket_manager.active_brackets[bracket_id]
            net_premium = bracket["net_premium"]
            max_allowed_sl = net_premium * 1.5

            # Verify SL doesn't exceed max
            assert abs(bracket["stop_loss_price"]) <= max_allowed_sl + 0.01  # Small tolerance


class TestMultiPositionMonitoring:
    """Test monitoring multiple brackets for a strategy."""

    @pytest.mark.asyncio
    async def test_multi_bracket_monitoring(
        self, mock_ib_conn, sample_iron_condor_strategy
    ):
        """Test monitoring multiple brackets for same strategy."""
        bracket_manager = BracketOrderManager(mock_ib_conn)

        # Create multiple brackets for same strategy
        bracket_id_1 = await bracket_manager.create_strategy_bracket(
            sample_iron_condor_strategy,
        )
        bracket_id_2 = await bracket_manager.create_strategy_bracket(
            sample_iron_condor_strategy,
        )
        bracket_id_3 = await bracket_manager.create_strategy_bracket(
            sample_iron_condor_strategy,
        )

        # Mark one as complete, one as cancelled
        bracket_manager.active_brackets[bracket_id_2]["status"] = "profit_taken"
        bracket_manager.active_brackets[bracket_id_3]["status"] = "cancelled"

        # Monitor active brackets
        active_brackets = await bracket_manager.monitor_strategy_brackets(
            strategy_id=sample_iron_condor_strategy.strategy_id,
        )

        # Should only return active brackets
        assert len(active_brackets) == 1
        assert active_brackets[0]["bracket_id"] == bracket_id_1

    @pytest.mark.asyncio
    async def test_bracket_status_tracking(
        self, mock_ib_conn, sample_iron_condor_strategy
    ):
        """Test tracking bracket status through lifecycle."""
        bracket_manager = BracketOrderManager(mock_ib_conn)

        # Create bracket
        bracket_id = await bracket_manager.create_strategy_bracket(
            sample_iron_condor_strategy,
        )

        # Initial status: pending
        status = await bracket_manager.get_bracket_status(bracket_id)
        assert status["overall_status"] == "pending"

        # Simulate entry filled -> active
        bracket_manager.active_brackets[bracket_id]["status"] = "active"
        status = await bracket_manager.get_bracket_status(bracket_id)
        assert status["overall_status"] == "active"

        # Simulate stop loss hit -> stopped_out
        bracket_manager.active_brackets[bracket_id]["status"] = "stopped_out"
        status = await bracket_manager.get_bracket_status(bracket_id)
        assert status["overall_status"] == "stopped_out"

    @pytest.mark.asyncio
    async def test_list_active_brackets_for_strategy(
        self, mock_ib_conn, sample_iron_condor_strategy
    ):
        """Test listing all active brackets for a strategy."""
        bracket_manager = BracketOrderManager(mock_ib_conn)

        # Create multiple brackets
        bracket_id_1 = await bracket_manager.create_strategy_bracket(
            sample_iron_condor_strategy,
        )
        bracket_id_2 = await bracket_manager.create_strategy_bracket(
            sample_iron_condor_strategy,
        )

        # Get all active brackets
        active_brackets = await bracket_manager.monitor_strategy_brackets(
            strategy_id=sample_iron_condor_strategy.strategy_id,
        )

        assert len(active_brackets) == 2
        bracket_ids = {b["bracket_id"] for b in active_brackets}
        assert bracket_id_1 in bracket_ids
        assert bracket_id_2 in bracket_ids


class TestOCAAndBracketCollaboration:
    """Test OCA and bracket managers working together."""

    @pytest.mark.asyncio
    async def test_strategy_with_oca_and_bracket(
        self, mock_ib_conn, sample_call_spread_strategy
    ):
        """Test strategy using both OCA and bracket managers."""
        # Mock placeOrder
        mock_trade = MagicMock()
        mock_trade.order.orderId = 1001
        mock_ib_conn.ib.placeOrder.return_value = mock_trade

        oca_manager = OCAOrderManager(mock_ib_conn)
        bracket_manager = BracketOrderManager(mock_ib_conn)

        # Create contracts
        contracts = []
        for _ in sample_call_spread_strategy.legs:
            contract = MagicMock()
            contract.conId = 123456
            contract.symbol = "QQQ"
            contracts.append(contract)

        # Submit strategy legs via OCA
        oca_group_id = await oca_manager.submit_strategy_oca_orders(
            sample_call_spread_strategy,
            contracts,
        )

        # Create bracket for risk management
        bracket_id = await bracket_manager.create_strategy_bracket(
            sample_call_spread_strategy,
        )

        # Both should be active
        assert oca_group_id in oca_manager.active_oca_groups
        assert bracket_id in bracket_manager.active_brackets

        # OCA group should have 2 orders
        oca_status = await oca_manager.get_oca_status(oca_group_id)
        assert oca_status["order_count"] == 2

        # Bracket should have SL and TP
        bracket_status = await bracket_manager.get_bracket_status(bracket_id)
        assert bracket_status["overall_status"] in ("pending", "active")
