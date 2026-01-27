"""
Integration Tests for Entry, Exit, and Monitoring Workflows

Tests the complete end-to-end workflow cycle:
- Entry workflow: Signal evaluation, strategy building, order placement
- Monitoring workflow: Position monitoring, decision evaluation, alerts
- Exit workflow: Execute close/roll/hold decisions

Run with: pytest src/v6/workflows/test_workflows.py -v
"""

import asyncio
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.v6.alerts import AlertManager
from src.v6.decisions.engine import DecisionEngine
from src.v6.decisions.models import Decision, DecisionAction, Urgency
from src.v6.decisions.rules.catastrophe import CatastropheProtection
from src.v6.decisions.rules.protection_rules import TakeProfit
from src.v6.execution.engine import OrderExecutionEngine
from src.v6.strategies.builders import IronCondorBuilder
from src.v6.strategies.models import (
    ExecutionStatus,
    LegAction,
    LegStatus,
    OptionRight,
    StrategyExecution,
    StrategyType,
)
from src.v6.strategies.repository import StrategyRepository
from src.v6.utils.ib_connection import IBConnectionManager
from src.v6.workflows.entry import EntryWorkflow
from src.v6.workflows.exit import ExitWorkflow
from src.v6.workflows.monitoring import PositionMonitoringWorkflow


# Helper functions
def future_date(days=30):
    """Create a date in the future."""
    return date.today() + timedelta(days=days)


class MockPosition:
    """Mock position for DecisionEngine rules."""

    def __init__(self, symbol="SPY", strategy_type="IRON_CONDOR", dte_current=30):
        self.strategy_execution_id = str(uuid4())
        self.symbol = symbol
        self.strategy_type = strategy_type
        self.entry_date = "2024-01-01"
        self.dte_current = dte_current
        self.current_premium_net = 1.50
        self.total_premium_entry = 2.00
        self.upl = 75.0  # 37.5% profit
        self.upl_percent = 37.5
        self.net_delta = 0.15
        self.net_gamma = 0.02
        self.net_theta = 5.0
        self.net_vega = -0.30
        self.iv_avg = 0.18
        self.legs = []

    def __getitem__(self, key):
        """Allow dict-style access for compatibility with rules."""
        return getattr(self, key)


# Fixtures
@pytest.fixture
def ib_conn():
    """Create mock IB connection manager."""
    ib_conn = MagicMock(spec=IBConnectionManager)
    ib_conn.ib = MagicMock()
    ib_conn.ensure_connected = AsyncMock()
    return ib_conn


@pytest.fixture
def execution_engine(ib_conn):
    """Create OrderExecutionEngine in dry run mode."""
    return OrderExecutionEngine(ib_conn, dry_run=True)


@pytest.fixture
def strategy_repo(tmp_path):
    """Create StrategyRepository with temp directory."""
    repo = StrategyRepository(table_path=str(tmp_path / "strategy_executions"))
    asyncio.run(repo.initialize())
    return repo


@pytest.fixture
def alert_manager(tmp_path):
    """Create AlertManager with temp directory."""
    manager = AlertManager(delta_lake_path=str(tmp_path / "alerts"))
    asyncio.run(manager.initialize())
    return manager


@pytest.fixture
def decision_engine(alert_manager):
    """Create DecisionEngine with test rules."""
    engine = DecisionEngine(alert_manager=alert_manager)
    engine.register_rule(CatastropheProtection())
    engine.register_rule(TakeProfit())
    return engine


@pytest.fixture
def strategy_builder():
    """Create IronCondorBuilder."""
    return IronCondorBuilder()


@pytest.fixture
def entry_workflow(execution_engine, decision_engine, strategy_builder, strategy_repo):
    """Create EntryWorkflow."""
    return EntryWorkflow(
        decision_engine=decision_engine,
        execution_engine=execution_engine,
        strategy_builder=strategy_builder,
        strategy_repo=strategy_repo,
    )


@pytest.fixture
def monitoring_workflow(decision_engine, alert_manager, strategy_repo):
    """Create PositionMonitoringWorkflow."""
    return PositionMonitoringWorkflow(
        decision_engine=decision_engine,
        alert_manager=alert_manager,
        strategy_repo=strategy_repo,
    )


@pytest.fixture
def exit_workflow(execution_engine, decision_engine, strategy_repo):
    """Create ExitWorkflow."""
    return ExitWorkflow(
        execution_engine=execution_engine,
        decision_engine=decision_engine,
        strategy_repo=strategy_repo,
    )


# Tests
class TestEntryWorkflow:
    """Tests for EntryWorkflow."""

    @pytest.mark.asyncio
    async def test_entry_workflow_signal_validation(
        self, entry_workflow, execution_engine
    ):
        """Test entry signal evaluation with valid conditions."""
        # Valid market data
        market_data = {
            "iv_rank": 60,  # >50, good for selling premium
            "vix": 18,  # <35, not extreme
            "underlying_price": 450.0,
            "portfolio_delta": 0.1,  # <0.3 limit
            "position_count": 2,  # <5 limit
        }

        should_enter = await entry_workflow.evaluate_entry_signal("SPY", market_data)

        assert should_enter is True

    @pytest.mark.asyncio
    async def test_entry_workflow_rejects_low_iv_rank(self, entry_workflow):
        """Test entry signal rejects when IV Rank not in entry range."""
        # IV Rank between 25-50 should be rejected
        market_data = {
            "iv_rank": 35,  # Not in entry range
            "vix": 18,
            "underlying_price": 450.0,
            "portfolio_delta": 0.1,
            "position_count": 2,
        }

        should_enter = await entry_workflow.evaluate_entry_signal("SPY", market_data)

        assert should_enter is False

    @pytest.mark.asyncio
    async def test_entry_workflow_rejects_high_vix(self, entry_workflow):
        """Test entry signal rejects when VIX too high."""
        # VIX >35 should be rejected
        market_data = {
            "iv_rank": 60,
            "vix": 40,  # Too high
            "underlying_price": 450.0,
            "portfolio_delta": 0.1,
            "position_count": 2,
        }

        should_enter = await entry_workflow.evaluate_entry_signal("SPY", market_data)

        assert should_enter is False

    @pytest.mark.asyncio
    async def test_entry_workflow_full_execution(
        self, entry_workflow, strategy_repo
    ):
        """Test full entry workflow execution."""
        # Execute entry
        execution = await entry_workflow.execute_entry(
            symbol="SPY",
            strategy_type=StrategyType.IRON_CONDOR,
            params={
                "underlying_price": 450.0,
                "put_width": 10,
                "call_width": 10,
                "dte": 45,
                "delta_target": 0.16,
            },
        )

        # Verify execution created
        assert execution is not None
        assert execution.symbol == "SPY"
        assert execution.strategy_type == StrategyType.IRON_CONDOR
        assert len(execution.legs) == 4  # Iron condor has 4 legs
        assert execution.status in [
            ExecutionStatus.PENDING,
            ExecutionStatus.FILLED,
            ExecutionStatus.PARTIAL,
        ]

        # Verify saved to repository
        retrieved = await strategy_repo.get_execution(execution.execution_id)
        assert retrieved is not None
        assert retrieved.execution_id == execution.execution_id


class TestMonitoringWorkflow:
    """Tests for PositionMonitoringWorkflow."""

    @pytest.mark.asyncio
    async def test_monitoring_workflow_no_positions(self, monitoring_workflow):
        """Test monitoring workflow with no open positions."""
        decisions = await monitoring_workflow.monitor_positions()

        assert decisions == {}

    @pytest.mark.asyncio
    async def test_monitoring_workflow_with_position(
        self, monitoring_workflow, strategy_repo
    ):
        """Test monitoring workflow evaluates position."""
        # Create sample legs
        from src.v6.strategies.models import LegExecution

        legs = [
            LegExecution(
                leg_id=str(uuid4()),
                conid=123456,
                right=OptionRight.PUT,
                strike=440.0,
                expiration=future_date(30),
                quantity=1,
                action=LegAction.SELL,
                status=LegStatus.FILLED,
                fill_price=1.00,
                order_id="order_1",
                fill_time=datetime.now(),
            ),
            LegExecution(
                leg_id=str(uuid4()),
                conid=123457,
                right=OptionRight.PUT,
                strike=435.0,
                expiration=future_date(30),
                quantity=1,
                action=LegAction.BUY,
                status=LegStatus.FILLED,
                fill_price=0.80,
                order_id="order_2",
                fill_time=datetime.now(),
            ),
        ]

        # Create a sample execution
        execution = StrategyExecution(
            execution_id=str(uuid4()),
            strategy_id=1,
            symbol="SPY",
            strategy_type=StrategyType.IRON_CONDOR,
            legs=legs,
            entry_params={},
            entry_time=datetime.now(),
            fill_time=datetime.now(),
            close_time=None,
            status=ExecutionStatus.FILLED,
        )
        await strategy_repo.save_execution(execution)

        # Monitor positions
        decisions = await monitoring_workflow.monitor_positions()

        # Verify decision returned
        assert execution.execution_id in decisions
        decision = decisions[execution.execution_id]
        assert decision.action in [DecisionAction.HOLD, DecisionAction.CLOSE]

    @pytest.mark.asyncio
    async def test_monitoring_workflow_single_position(
        self, monitoring_workflow, strategy_repo
    ):
        """Test monitoring single position."""
        # Create sample legs
        from src.v6.strategies.models import LegExecution

        legs = [
            LegExecution(
                leg_id=str(uuid4()),
                conid=123456,
                right=OptionRight.CALL,
                strike=460.0,
                expiration=future_date(30),
                quantity=1,
                action=LegAction.SELL,
                status=LegStatus.FILLED,
                fill_price=1.20,
                order_id="order_3",
                fill_time=datetime.now(),
            ),
        ]

        # Create a sample execution
        execution = StrategyExecution(
            execution_id=str(uuid4()),
            strategy_id=1,
            symbol="SPY",
            strategy_type=StrategyType.VERTICAL_SPREAD,
            legs=legs,
            entry_params={},
            entry_time=datetime.now(),
            fill_time=datetime.now(),
            close_time=None,
            status=ExecutionStatus.FILLED,
        )
        await strategy_repo.save_execution(execution)

        # Monitor single position
        decision = await monitoring_workflow.monitor_position(execution.execution_id)

        # Verify decision returned
        assert decision is not None
        assert decision.action in [DecisionAction.HOLD, DecisionAction.CLOSE]


class TestExitWorkflow:
    """Tests for ExitWorkflow."""

    @pytest.mark.asyncio
    async def test_exit_workflow_hold_decision(self, exit_workflow):
        """Test exit workflow with HOLD decision."""
        decision = Decision(
            action=DecisionAction.HOLD,
            reason="No action needed",
            rule="none",
            urgency=Urgency.NORMAL,
            metadata={},
        )

        result = await exit_workflow.execute_exit_decision("123", decision)

        assert result.success is True
        assert result.action_taken == "NO_ACTION"
        assert result.order_ids == []

    @pytest.mark.asyncio
    async def test_exit_workflow_close_decision(
        self, exit_workflow, execution_engine, strategy_repo
    ):
        """Test exit workflow with CLOSE decision."""
        # Create sample legs
        from src.v6.strategies.models import LegExecution

        legs = [
            LegExecution(
                leg_id=str(uuid4()),
                conid=123456,
                right=OptionRight.PUT,
                strike=440.0,
                expiration=future_date(30),
                quantity=1,
                action=LegAction.SELL,
                status=LegStatus.FILLED,
                fill_price=1.00,
                order_id="order_1",
                fill_time=datetime.now(),
            ),
            LegExecution(
                leg_id=str(uuid4()),
                conid=123457,
                right=OptionRight.PUT,
                strike=435.0,
                expiration=future_date(30),
                quantity=1,
                action=LegAction.BUY,
                status=LegStatus.FILLED,
                fill_price=0.80,
                order_id="order_2",
                fill_time=datetime.now(),
            ),
        ]

        # Create a sample execution
        execution = StrategyExecution(
            execution_id=str(uuid4()),
            strategy_id=1,
            symbol="SPY",
            strategy_type=StrategyType.IRON_CONDOR,
            legs=legs,
            entry_params={},
            entry_time=datetime.now(),
            fill_time=datetime.now(),
            close_time=None,
            status=ExecutionStatus.FILLED,
        )
        await strategy_repo.save_execution(execution)

        # Create CLOSE decision
        decision = Decision(
            action=DecisionAction.CLOSE,
            reason="Take profit",
            rule="take_profit_80pct",
            urgency=Urgency.NORMAL,
            metadata={},
        )

        # Execute close
        result = await exit_workflow.execute_exit_decision(
            execution.execution_id, decision
        )

        # Verify result (dry run mode)
        assert result is not None

    @pytest.mark.asyncio
    async def test_exit_workflow_close_all(
        self, exit_workflow, strategy_repo
    ):
        """Test exit workflow close all positions."""
        # Create sample legs
        from src.v6.strategies.models import LegExecution

        legs1 = [
            LegExecution(
                leg_id=str(uuid4()),
                conid=123456,
                right=OptionRight.PUT,
                strike=440.0,
                expiration=future_date(30),
                quantity=1,
                action=LegAction.SELL,
                status=LegStatus.FILLED,
                fill_price=1.00,
                order_id="order_1",
                fill_time=datetime.now(),
            ),
        ]

        legs2 = [
            LegExecution(
                leg_id=str(uuid4()),
                conid=123457,
                right=OptionRight.CALL,
                strike=460.0,
                expiration=future_date(30),
                quantity=1,
                action=LegAction.SELL,
                status=LegStatus.FILLED,
                fill_price=0.90,
                order_id="order_2",
                fill_time=datetime.now(),
            ),
        ]

        # Create sample executions
        exec1 = StrategyExecution(
            execution_id=str(uuid4()),
            strategy_id=1,
            symbol="SPY",
            strategy_type=StrategyType.IRON_CONDOR,
            legs=legs1,
            entry_params={},
            entry_time=datetime.now(),
            fill_time=datetime.now(),
            close_time=None,
            status=ExecutionStatus.FILLED,
        )

        exec2 = StrategyExecution(
            execution_id=str(uuid4()),
            strategy_id=2,
            symbol="SPY",
            strategy_type=StrategyType.VERTICAL_SPREAD,
            legs=legs2,
            entry_params={},
            entry_time=datetime.now(),
            fill_time=datetime.now(),
            close_time=None,
            status=ExecutionStatus.FILLED,
        )

        await strategy_repo.save_execution(exec1)
        await strategy_repo.save_execution(exec2)

        # Close all SPY positions
        results = await exit_workflow.execute_close_all(symbol="SPY")

        # Verify both positions closed
        assert len(results) == 2


class TestEndToEndWorkflow:
    """Tests for complete end-to-end workflow."""

    @pytest.mark.asyncio
    async def test_end_to_entry_monitor_exit(
        self, entry_workflow, monitoring_workflow, exit_workflow, strategy_repo
    ):
        """Test complete cycle: entry → monitor → exit."""
        # Step 1: Entry
        execution = await entry_workflow.execute_entry(
            symbol="SPY",
            strategy_type=StrategyType.IRON_CONDOR,
            params={
                "underlying_price": 450.0,
                "put_width": 10,
                "call_width": 10,
                "dte": 45,
                "delta_target": 0.16,
            },
        )

        assert execution is not None
        assert execution.status != ExecutionStatus.FAILED

        # Step 2: Monitoring
        decisions = await monitoring_workflow.monitor_positions()

        assert execution.execution_id in decisions
        monitor_decision = decisions[execution.execution_id]

        # Step 3: Exit (simulate CLOSE)
        exit_decision = Decision(
            action=DecisionAction.CLOSE,
            reason="Test close",
            rule="test",
            urgency=Urgency.NORMAL,
            metadata={},
        )

        exit_result = await exit_workflow.execute_exit_decision(
            execution.execution_id, exit_decision
        )

        # Verify complete cycle
        assert execution.execution_id is not None
        assert monitor_decision is not None
        assert exit_result is not None

        # Verify execution updated
        final_execution = await strategy_repo.get_execution(execution.execution_id)
        assert final_execution is not None
