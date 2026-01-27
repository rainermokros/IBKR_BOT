"""
Unit Tests for Strategy Builders and Repository

Tests strategy builders, validation, and Delta Lake persistence.
Run with: pytest src/v6/strategies/test_builders.py -v
"""

import asyncio
from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest

from v6.strategies.builders import (
    IronCondorBuilder,
    VerticalSpreadBuilder,
    CustomStrategyBuilder,
)
from v6.strategies.models import (
    Strategy,
    StrategyType,
    LegSpec,
    StrategyExecution,
    LegExecution,
    ExecutionStatus,
    LegStatus,
    OptionRight,
    LegAction,
)
from v6.strategies.repository import StrategyRepository


class TestIronCondorBuilder:
    """Tests for IronCondorBuilder."""

    def test_iron_condor_builder(self):
        """Test building iron condor with valid params."""
        builder = IronCondorBuilder()
        symbol = "SPY"
        underlying_price = 450.0
        params = {
            "put_width": 10,
            "call_width": 10,
            "dte": 45,
            "delta_target": 0.16,
        }

        strategy = builder.build(symbol, underlying_price, params)

        # Verify strategy type
        assert strategy.strategy_type == StrategyType.IRON_CONDOR
        assert strategy.symbol == symbol

        # Verify 4 legs
        assert len(strategy.legs) == 4

        # Verify leg order: BUY PUT, SELL PUT, SELL CALL, BUY CALL
        assert strategy.legs[0].action == LegAction.BUY
        assert strategy.legs[0].right == OptionRight.PUT
        assert strategy.legs[1].action == LegAction.SELL
        assert strategy.legs[1].right == OptionRight.PUT
        assert strategy.legs[2].action == LegAction.SELL
        assert strategy.legs[2].right == OptionRight.CALL
        assert strategy.legs[3].action == LegAction.BUY
        assert strategy.legs[3].right == OptionRight.CALL

        # Verify strike order: LP < SP < SC < LC
        lp = strategy.legs[0].strike
        sp = strategy.legs[1].strike
        sc = strategy.legs[2].strike
        lc = strategy.legs[3].strike
        assert lp < sp < sc < lc

        # Verify widths
        put_width = sp - lp
        call_width = lc - sc
        assert put_width == 10
        assert call_width == 10

        # Verify same expiration
        expirations = {leg.expiration for leg in strategy.legs}
        assert len(expirations) == 1

    def test_iron_condor_validation(self):
        """Test iron condor validation with valid and invalid params."""
        builder = IronCondorBuilder()
        symbol = "SPY"
        underlying_price = 450.0

        # Test valid strategy
        valid_params = {"put_width": 10, "call_width": 10, "dte": 45}
        valid_strategy = builder.build(symbol, underlying_price, valid_params)
        assert builder.validate(valid_strategy) is True

        # Test invalid: negative width (should raise during build)
        with pytest.raises(ValueError, match="put_width must be positive"):
            builder.build(symbol, underlying_price, {"put_width": -10, "call_width": 10, "dte": 45})

        # Test invalid: zero width (should raise during build)
        with pytest.raises(ValueError, match="call_width must be positive"):
            builder.build(symbol, underlying_price, {"put_width": 10, "call_width": 0, "dte": 45})

        # Test invalid: negative DTE (should raise during build)
        with pytest.raises(ValueError, match="dte must be positive"):
            builder.build(symbol, underlying_price, {"put_width": 10, "call_width": 10, "dte": -5})

        # Test invalid: delta_target out of range (should raise during build)
        with pytest.raises(ValueError, match="delta_target must be between 0 and 1"):
            builder.build(symbol, underlying_price, {"put_width": 10, "call_width": 10, "dte": 45, "delta_target": 1.5})

    def test_iron_condor_custom_widths(self):
        """Test building iron condor with custom wing widths."""
        builder = IronCondorBuilder()
        symbol = "SPY"
        underlying_price = 450.0
        params = {
            "put_width": 5,
            "call_width": 15,
            "dte": 30,
            "delta_target": 0.20,
        }

        strategy = builder.build(symbol, underlying_price, params)

        # Verify custom widths
        lp = strategy.legs[0].strike
        sp = strategy.legs[1].strike
        sc = strategy.legs[2].strike
        lc = strategy.legs[3].strike

        put_width = sp - lp
        call_width = lc - sc

        assert put_width == 5
        assert call_width == 15


class TestVerticalSpreadBuilder:
    """Tests for VerticalSpreadBuilder."""

    def test_vertical_spread_bull(self):
        """Test building bull vertical spread (call spread)."""
        builder = VerticalSpreadBuilder()
        symbol = "SPY"
        underlying_price = 450.0
        params = {
            "direction": "BULL",
            "width": 10,
            "dte": 45,
            "delta_target": 0.30,
        }

        strategy = builder.build(symbol, underlying_price, params)

        # Verify strategy type
        assert strategy.strategy_type == StrategyType.VERTICAL_SPREAD
        assert strategy.symbol == symbol

        # Verify 2 legs
        assert len(strategy.legs) == 2

        # Verify both are CALLs
        assert strategy.legs[0].right == OptionRight.CALL
        assert strategy.legs[1].right == OptionRight.CALL

        # Verify one BUY, one SELL
        actions = {leg.action for leg in strategy.legs}
        assert actions == {LegAction.BUY, LegAction.SELL}

        # Verify long strike is lower (for bull call spread)
        long_leg = next(leg for leg in strategy.legs if leg.action == LegAction.BUY)
        short_leg = next(leg for leg in strategy.legs if leg.action == LegAction.SELL)
        assert long_leg.strike < short_leg.strike

        # Verify width
        assert short_leg.strike - long_leg.strike == 10

        # Verify same expiration
        assert strategy.legs[0].expiration == strategy.legs[1].expiration

    def test_vertical_spread_bear(self):
        """Test building bear vertical spread (put spread)."""
        builder = VerticalSpreadBuilder()
        symbol = "SPY"
        underlying_price = 450.0
        params = {
            "direction": "BEAR",
            "width": 10,
            "dte": 45,
            "delta_target": 0.30,
        }

        strategy = builder.build(symbol, underlying_price, params)

        # Verify both are PUTs
        assert strategy.legs[0].right == OptionRight.PUT
        assert strategy.legs[1].right == OptionRight.PUT

        # Verify one BUY, one SELL
        actions = {leg.action for leg in strategy.legs}
        assert actions == {LegAction.BUY, LegAction.SELL}

        # Verify long strike is higher (for bear put spread)
        long_leg = next(leg for leg in strategy.legs if leg.action == LegAction.BUY)
        short_leg = next(leg for leg in strategy.legs if leg.action == LegAction.SELL)
        assert long_leg.strike > short_leg.strike

        # Verify width
        assert long_leg.strike - short_leg.strike == 10

    def test_vertical_spread_validation(self):
        """Test vertical spread validation."""
        builder = VerticalSpreadBuilder()
        symbol = "SPY"
        underlying_price = 450.0

        # Test valid bull spread
        valid_params = {"direction": "BULL", "width": 10, "dte": 45}
        valid_strategy = builder.build(symbol, underlying_price, valid_params)
        assert builder.validate(valid_strategy) is True

        # Test valid bear spread
        bear_params = {"direction": "BEAR", "width": 10, "dte": 45}
        bear_strategy = builder.build(symbol, underlying_price, bear_params)
        assert builder.validate(bear_strategy) is True

        # Test invalid: unknown direction
        with pytest.raises(ValueError, match="direction must be BULL or BEAR"):
            builder.build(symbol, underlying_price, {"direction": "UNKNOWN", "width": 10, "dte": 45})


class TestCustomStrategyBuilder:
    """Tests for CustomStrategyBuilder."""

    def test_custom_strategy_builder(self):
        """Test building custom 3-leg strategy."""
        builder = CustomStrategyBuilder()
        symbol = "SPY"
        underlying_price = 450.0

        # Define custom legs
        future_date = (date.today() + timedelta(days=45)).isoformat()
        legs_data = [
            {
                "right": "CALL",
                "strike": 445.0,
                "quantity": 1,
                "action": "BUY",
                "expiration": future_date,
            },
            {
                "right": "CALL",
                "strike": 450.0,
                "quantity": 2,
                "action": "SELL",
                "expiration": future_date,
            },
            {
                "right": "CALL",
                "strike": 455.0,
                "quantity": 1,
                "action": "BUY",
                "expiration": future_date,
            },
        ]

        params = {"legs": legs_data}
        strategy = builder.build(symbol, underlying_price, params)

        # Verify strategy type
        assert strategy.strategy_type == StrategyType.CUSTOM
        assert strategy.symbol == symbol

        # Verify 3 legs
        assert len(strategy.legs) == 3

        # Verify legs match input
        assert strategy.legs[0].strike == 445.0
        assert strategy.legs[0].action == LegAction.BUY
        assert strategy.legs[0].quantity == 1

        assert strategy.legs[1].strike == 450.0
        assert strategy.legs[1].action == LegAction.SELL
        assert strategy.legs[1].quantity == 2

        assert strategy.legs[2].strike == 455.0
        assert strategy.legs[2].action == LegAction.BUY
        assert strategy.legs[2].quantity == 1

        # Verify validation passes
        assert builder.validate(strategy) is True

    def test_custom_strategy_validation(self):
        """Test custom strategy validation."""
        builder = CustomStrategyBuilder()
        symbol = "SPY"
        underlying_price = 450.0

        # Test empty legs list
        with pytest.raises(ValueError, match="Custom strategy must have at least one leg"):
            builder.build(symbol, underlying_price, {"legs": []})

        # Test invalid right
        future_date = (date.today() + timedelta(days=45)).isoformat()
        with pytest.raises(ValueError, match="Invalid leg spec"):
            builder.build(symbol, underlying_price, {
                "legs": [{
                    "right": "INVALID",
                    "strike": 450.0,
                    "quantity": 1,
                    "action": "BUY",
                    "expiration": future_date,
                }]
            })

        # Test invalid action
        with pytest.raises(ValueError, match="Invalid leg spec"):
            builder.build(symbol, underlying_price, {
                "legs": [{
                    "right": "CALL",
                    "strike": 450.0,
                    "quantity": 1,
                    "action": "INVALID",
                    "expiration": future_date,
                }]
            })


class TestStrategyRepository:
    """Tests for StrategyRepository with Delta Lake persistence."""

    @pytest.fixture
    async def repo(self):
        """Create a test repository."""
        # Use a test table path
        import shutil
        test_table_path = "data/lake/test_strategy_executions"

        # Clean up any existing test table
        try:
            shutil.rmtree(test_table_path)
        except FileNotFoundError:
            pass

        test_repo = StrategyRepository(table_path=test_table_path)
        await test_repo.initialize()
        yield test_repo
        # Cleanup happens automatically via test isolation

    @pytest.mark.asyncio
    async def test_strategy_repository_save(self, repo):
        """Test saving execution to Delta Lake."""
        # Create test execution
        execution = self._create_test_execution()

        # Save to repository
        await repo.save_execution(execution)

        # Retrieve and verify
        retrieved = await repo.get_execution(execution.execution_id)

        assert retrieved is not None
        assert retrieved.execution_id == execution.execution_id
        assert retrieved.symbol == "SPY"
        assert retrieved.strategy_type == StrategyType.IRON_CONDOR
        assert retrieved.status == ExecutionStatus.PENDING
        assert len(retrieved.legs) == 4

    @pytest.mark.asyncio
    async def test_strategy_repository_get_open(self, repo):
        """Test retrieving open strategies."""
        # Create test executions
        execution1 = self._create_test_execution(status=ExecutionStatus.PENDING)
        execution2 = self._create_test_execution(status=ExecutionStatus.FILLED)
        execution3 = self._create_test_execution(status=ExecutionStatus.CLOSED)

        # Save to repository
        await repo.save_execution(execution1)
        await repo.save_execution(execution2)
        await repo.save_execution(execution3)

        # Get open strategies
        open_strategies = await repo.get_open_strategies()

        # Should return PENDING and FILLED, not CLOSED
        assert len(open_strategies) == 2
        statuses = {s.status for s in open_strategies}
        assert statuses == {ExecutionStatus.PENDING, ExecutionStatus.FILLED}

    @pytest.mark.asyncio
    async def test_strategy_repository_get_open_by_symbol(self, repo):
        """Test retrieving open strategies filtered by symbol."""
        # Create test executions for different symbols
        spy_execution = self._create_test_execution(symbol="SPY", status=ExecutionStatus.PENDING)
        iwm_execution = self._create_test_execution(symbol="IWM", status=ExecutionStatus.PENDING)

        # Save to repository
        await repo.save_execution(spy_execution)
        await repo.save_execution(iwm_execution)

        # Get SPY strategies only
        spy_strategies = await repo.get_open_strategies(symbol="SPY")

        assert len(spy_strategies) == 1
        assert spy_strategies[0].symbol == "SPY"

        # Get IWM strategies only
        iwm_strategies = await repo.get_open_strategies(symbol="IWM")

        assert len(iwm_strategies) == 1
        assert iwm_strategies[0].symbol == "IWM"

    @pytest.mark.asyncio
    async def test_leg_status_update(self, repo):
        """Test updating leg status."""
        # Create test execution
        execution = self._create_test_execution(status=ExecutionStatus.PENDING)
        await repo.save_execution(execution)

        # Update first leg status to FILLED
        leg_id = execution.legs[0].leg_id
        await repo.update_leg_status(leg_id, LegStatus.FILLED, fill_price=2.50)

        # Retrieve and verify
        retrieved = await repo.get_execution(execution.execution_id)
        assert retrieved.legs[0].status == LegStatus.FILLED
        assert retrieved.legs[0].fill_price == 2.50
        assert retrieved.legs[0].fill_time is not None

    @pytest.mark.asyncio
    async def test_execution_status_update(self, repo):
        """Test updating execution status."""
        # Create test execution
        execution = self._create_test_execution(status=ExecutionStatus.PENDING)
        await repo.save_execution(execution)

        # Update status to FILLED
        await repo.update_execution_status(execution.execution_id, ExecutionStatus.FILLED)

        # Retrieve and verify
        retrieved = await repo.get_execution(execution.execution_id)
        assert retrieved.status == ExecutionStatus.FILLED

    def _create_test_execution(
        self,
        symbol: str = "SPY",
        status: ExecutionStatus = ExecutionStatus.PENDING
    ) -> StrategyExecution:
        """Helper to create a test StrategyExecution."""
        execution_id = str(uuid4())
        future_date = date.today() + timedelta(days=45)

        # Create legs
        legs = [
            LegExecution(
                leg_id=f"{execution_id}_leg_0",
                conid=None,
                right=OptionRight.PUT,
                strike=440.0,
                expiration=future_date,
                quantity=1,
                action=LegAction.BUY,
                status=LegStatus.PENDING,
            ),
            LegExecution(
                leg_id=f"{execution_id}_leg_1",
                conid=None,
                right=OptionRight.PUT,
                strike=450.0,
                expiration=future_date,
                quantity=1,
                action=LegAction.SELL,
                status=LegStatus.PENDING,
            ),
            LegExecution(
                leg_id=f"{execution_id}_leg_2",
                conid=None,
                right=OptionRight.CALL,
                strike=455.0,
                expiration=future_date,
                quantity=1,
                action=LegAction.SELL,
                status=LegStatus.PENDING,
            ),
            LegExecution(
                leg_id=f"{execution_id}_leg_3",
                conid=None,
                right=OptionRight.CALL,
                strike=465.0,
                expiration=future_date,
                quantity=1,
                action=LegAction.BUY,
                status=LegStatus.PENDING,
            ),
        ]

        # Add fill_time and close_time based on status
        fill_time_val = None
        close_time_val = None
        if status == ExecutionStatus.FILLED:
            fill_time_val = datetime.now()
        elif status == ExecutionStatus.CLOSED:
            fill_time_val = datetime.now()
            close_time_val = datetime.now()

        execution = StrategyExecution(
            execution_id=execution_id,
            strategy_id=1,
            symbol=symbol,
            strategy_type=StrategyType.IRON_CONDOR,
            status=status,
            legs=legs,
            entry_params={"put_width": 10, "call_width": 10},
            entry_time=datetime.now(),
            fill_time=fill_time_val,
            close_time=close_time_val,
        )

        return execution


class TestStrategyModels:
    """Tests for strategy data models."""

    def test_leg_spec_validation(self):
        """Test LegSpec validation."""
        future_date = date.today() + timedelta(days=45)

        # Valid leg
        leg = LegSpec(
            right=OptionRight.CALL,
            strike=450.0,
            quantity=1,
            action=LegAction.BUY,
            expiration=future_date,
        )
        assert leg.strike == 450.0

        # Invalid: negative strike
        with pytest.raises(ValueError, match="Strike must be positive"):
            LegSpec(
                right=OptionRight.CALL,
                strike=-10.0,
                quantity=1,
                action=LegAction.BUY,
                expiration=future_date,
            )

        # Invalid: zero quantity
        with pytest.raises(ValueError, match="Quantity must be positive"):
            LegSpec(
                right=OptionRight.CALL,
                strike=450.0,
                quantity=0,
                action=LegAction.BUY,
                expiration=future_date,
            )

        # Invalid: past expiration
        with pytest.raises(ValueError, match="Expiration must be in future"):
            LegSpec(
                right=OptionRight.CALL,
                strike=450.0,
                quantity=1,
                action=LegAction.BUY,
                expiration=date(2020, 1, 1),
            )

    def test_strategy_validation(self):
        """Test Strategy validation."""
        future_date = date.today() + timedelta(days=45)

        legs = [
            LegSpec(
                right=OptionRight.CALL,
                strike=450.0,
                quantity=1,
                action=LegAction.BUY,
                expiration=future_date,
            )
        ]

        # Valid strategy
        strategy = Strategy(
            strategy_id="test_strategy",
            symbol="SPY",
            strategy_type=StrategyType.CUSTOM,
            legs=legs,
        )
        assert strategy.symbol == "SPY"

        # Invalid: empty symbol
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            Strategy(
                strategy_id="test_strategy",
                symbol="",
                strategy_type=StrategyType.CUSTOM,
                legs=legs,
            )

        # Invalid: no legs
        with pytest.raises(ValueError, match="Strategy must have at least one leg"):
            Strategy(
                strategy_id="test_strategy",
                symbol="SPY",
                strategy_type=StrategyType.CUSTOM,
                legs=[],
            )

    def test_leg_execution_validation(self):
        """Test LegExecution validation."""
        future_date = date.today() + timedelta(days=45)

        # Valid pending leg
        leg = LegExecution(
            leg_id="test_leg",
            conid=None,
            right=OptionRight.CALL,
            strike=450.0,
            expiration=future_date,
            quantity=1,
            action=LegAction.BUY,
            status=LegStatus.PENDING,
        )
        assert leg.status == LegStatus.PENDING

        # Valid filled leg
        filled_leg = LegExecution(
            leg_id="test_leg_filled",
            conid=123456,
            right=OptionRight.CALL,
            strike=450.0,
            expiration=future_date,
            quantity=1,
            action=LegAction.BUY,
            status=LegStatus.FILLED,
            fill_price=2.50,
            fill_time=datetime.now(),
        )
        assert filled_leg.fill_price == 2.50

        # Invalid: filled without fill_price
        with pytest.raises(ValueError, match="Filled leg must have fill_price"):
            LegExecution(
                leg_id="test_leg_invalid",
                conid=123456,
                right=OptionRight.CALL,
                strike=450.0,
                expiration=future_date,
                quantity=1,
                action=LegAction.BUY,
                status=LegStatus.FILLED,
                fill_price=None,
            )

    def test_strategy_execution_validation(self):
        """Test StrategyExecution validation."""
        legs = [
            LegExecution(
                leg_id="test_leg",
                conid=None,
                right=OptionRight.CALL,
                strike=450.0,
                expiration=date.today(),
                quantity=1,
                action=LegAction.BUY,
                status=LegStatus.PENDING,
            )
        ]

        # Valid pending execution
        execution = StrategyExecution(
            execution_id="test_execution",
            strategy_id=1,
            symbol="SPY",
            strategy_type=StrategyType.CUSTOM,
            status=ExecutionStatus.PENDING,
            legs=legs,
            entry_params={},
            entry_time=datetime.now(),
        )
        assert execution.status == ExecutionStatus.PENDING

        # Valid filled execution
        filled_execution = StrategyExecution(
            execution_id="test_execution_filled",
            strategy_id=1,
            symbol="SPY",
            strategy_type=StrategyType.CUSTOM,
            status=ExecutionStatus.FILLED,
            legs=legs,
            entry_params={},
            entry_time=datetime.now(),
            fill_time=datetime.now(),
        )
        assert filled_execution.fill_time is not None

        # Invalid: filled without fill_time
        with pytest.raises(ValueError, match="Filled execution must have fill_time"):
            StrategyExecution(
                execution_id="test_execution_invalid",
                strategy_id=1,
                symbol="SPY",
                strategy_type=StrategyType.CUSTOM,
                status=ExecutionStatus.FILLED,
                legs=legs,
                entry_params={},
                entry_time=datetime.now(),
                fill_time=None,
            )

    def test_strategy_execution_properties(self):
        """Test StrategyExecution properties."""
        legs = [
            LegExecution(
                leg_id="test_leg",
                conid=None,
                right=OptionRight.CALL,
                strike=450.0,
                expiration=date.today(),
                quantity=1,
                action=LegAction.BUY,
                status=LegStatus.PENDING,
            )
        ]

        # Pending execution
        pending_execution = StrategyExecution(
            execution_id="test_pending",
            strategy_id=1,
            symbol="SPY",
            strategy_type=StrategyType.CUSTOM,
            status=ExecutionStatus.PENDING,
            legs=legs,
            entry_params={},
            entry_time=datetime.now(),
        )
        assert pending_execution.is_open is True
        assert pending_execution.is_filled is False

        # Filled execution
        filled_execution = StrategyExecution(
            execution_id="test_filled",
            strategy_id=1,
            symbol="SPY",
            strategy_type=StrategyType.CUSTOM,
            status=ExecutionStatus.FILLED,
            legs=legs,
            entry_params={},
            entry_time=datetime.now(),
            fill_time=datetime.now(),
        )
        assert filled_execution.is_open is True
        assert filled_execution.is_filled is True

        # Closed execution
        closed_execution = StrategyExecution(
            execution_id="test_closed",
            strategy_id=1,
            symbol="SPY",
            strategy_type=StrategyType.CUSTOM,
            status=ExecutionStatus.CLOSED,
            legs=legs,
            entry_params={},
            entry_time=datetime.now(),
            fill_time=datetime.now(),
            close_time=datetime.now(),
        )
        assert closed_execution.is_open is False
        assert closed_execution.is_filled is True
