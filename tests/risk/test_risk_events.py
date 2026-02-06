"""
Tests for Risk Event Logging

Tests the RiskEventLogger and RiskEventsTable to ensure proper
Delta Lake persistence of all risk management activities.
"""

import asyncio
from datetime import datetime
from pathlib import Path

import pytest
from deltalake import DeltaTable

from v6.risk import (
    CircuitBreakerConfig,
    RiskEventLogger,
    RiskEventType,
    RiskEventsTable,
    TradingCircuitBreaker,
    TrailingStop,
    TrailingStopConfig,
    TrailingStopManager,
)
from v6.risk.models import RiskLimitsConfig
from v6.decisions.portfolio_risk import PortfolioRiskCalculator, Greeks, PortfolioRisk


# Test table path
TEST_TABLE_PATH = "tests/data/lake/test_risk_events"


@pytest.fixture
async def event_logger():
    """Create event logger for testing."""
    # Clean up any existing test table
    import shutil

    if Path(TEST_TABLE_PATH).exists():
        shutil.rmtree(TEST_TABLE_PATH)

    # Create table
    table = RiskEventsTable(table_path=TEST_TABLE_PATH)

    # Create logger
    logger = RiskEventLogger(table=table)
    await logger.initialize()

    yield logger

    # Cleanup
    await logger.flush()
    if Path(TEST_TABLE_PATH).exists():
        shutil.rmtree(TEST_TABLE_PATH)


@pytest.fixture
def mock_risk_calculator():
    """Create mock portfolio risk calculator."""
    # Mock portfolio risk
    greeks = Greeks(
        delta=10.0,
        gamma=2.0,
        theta=-5.0,
        vega=-10.0,
        delta_per_symbol={"SPY": 5.0, "QQQ": 3.0},
    )

    exposure = type("Exposure", (), {})()
    exposure.total_exposure = 50000.0
    exposure.max_single_position = 0.02
    exposure.correlated_exposure = {"SPY": 0.03}

    risk = PortfolioRisk(
        greeks=greeks,
        exposure=exposure,
        total_value=100000.0,
        total_premium=5000.0,
    )

    # Mock calculator
    calculator = pytest.create_autospec(PortfolioRiskCalculator)
    calculator.calculate_portfolio_risk = pytest.AsyncMock(return_value=risk)

    return calculator


class TestRiskEventsTable:
    """Tests for RiskEventsTable."""

    def test_create_table(self):
        """Test that Delta Lake table is created with correct schema."""
        table = RiskEventsTable(table_path=TEST_TABLE_PATH)

        # Verify table exists
        assert Path(TEST_TABLE_PATH).exists()

        # Verify schema
        dt = DeltaTable(str(TEST_TABLE_PATH))
        df = dt.to_pyarrow_table()

        expected_columns = {
            "event_id",
            "event_type",
            "component",
            "timestamp",
            "execution_id",
            "old_state",
            "new_state",
            "failure_count",
            "entry_premium",
            "current_premium",
            "highest_premium",
            "stop_premium",
            "action",
            "limit_type",
            "current_value",
            "limit_value",
            "allowed",
            "rejection_reason",
            "metadata",
        }

        assert set(df.column_names) == expected_columns

        # Cleanup
        import shutil

        if Path(TEST_TABLE_PATH).exists():
            shutil.rmtree(TEST_TABLE_PATH)


class TestRiskEventLogger:
    """Tests for RiskEventLogger."""

    @pytest.mark.asyncio
    async def test_initialize_logger(self, event_logger):
        """Test logger initialization."""
        assert event_logger is not None
        assert event_logger.table is not None

    @pytest.mark.asyncio
    async def test_log_circuit_breaker_state_change(self, event_logger):
        """Test logging circuit breaker state change."""
        await event_logger.log_circuit_breaker_state_change(
            old_state="CLOSED",
            new_state="OPEN",
            failure_count=5,
        )

        await event_logger.flush()

        # Verify event was written
        dt = DeltaTable(str(TEST_TABLE_PATH))
        df = dt.to_pyarrow_table()

        assert df.num_rows == 1
        assert df["event_type"][0].as_py() == "circuit_breaker_state_change"
        assert df["component"][0].as_py() == "circuit_breaker"
        assert df["old_state"][0].as_py() == "CLOSED"
        assert df["new_state"][0].as_py() == "OPEN"
        assert df["failure_count"][0].as_py() == 5

    @pytest.mark.asyncio
    async def test_log_trailing_stop_activate(self, event_logger):
        """Test logging trailing stop activation."""
        await event_logger.log_trailing_stop_activate(
            execution_id="test_123",
            entry_premium=100.0,
            current_premium=103.0,
            highest_premium=103.0,
            stop_premium=101.45,
        )

        await event_logger.flush()

        # Verify event was written
        dt = DeltaTable(str(TEST_TABLE_PATH))
        df = dt.to_pyarrow_table()

        assert df.num_rows == 1
        assert df["event_type"][0].as_py() == "trailing_stop_activate"
        assert df["component"][0].as_py() == "trailing_stop"
        assert df["execution_id"][0].as_py() == "test_123"
        assert df["entry_premium"][0].as_py() == pytest.approx(100.0)
        assert df["stop_premium"][0].as_py() == pytest.approx(101.45)

    @pytest.mark.asyncio
    async def test_log_portfolio_limit_rejection(self, event_logger):
        """Test logging portfolio limit rejection."""
        await event_logger.log_portfolio_limit_rejection(
            limit_type="portfolio_delta",
            current_value=55.0,
            limit_value=50.0,
            rejection_reason="Portfolio delta would exceed limit: 55.0 > 50.0",
            execution_id="test_456",
        )

        await event_logger.flush()

        # Verify event was written
        dt = DeltaTable(str(TEST_TABLE_PATH))
        df = dt.to_pyarrow_table()

        assert df.num_rows == 1
        assert df["event_type"][0].as_py() == "portfolio_limit_rejection"
        assert df["component"][0].as_py() == "portfolio_limits"
        assert df["limit_type"][0].as_py() == "portfolio_delta"
        assert df["allowed"][0].as_py() is False

    @pytest.mark.asyncio
    async def test_batch_writing(self, event_logger):
        """Test that events are batched properly."""
        # Log multiple events
        for i in range(10):
            await event_logger.log_circuit_breaker_failure(failure_count=i + 1)

        # Flush to ensure all written
        await event_logger.flush()

        # Verify all events were written
        dt = DeltaTable(str(TEST_TABLE_PATH))
        df = dt.to_pyarrow_table()

        assert df.num_rows == 10

        # Verify failure counts
        failure_counts = df["failure_count"].to_pylist()
        assert failure_counts == list(range(1, 11))


class TestCircuitBreakerLogging:
    """Tests for circuit breaker logging integration."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_logs_state_changes(self, event_logger):
        """Test that circuit breaker logs state transitions."""
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = TradingCircuitBreaker(config, event_logger=event_logger)

        # Trigger state change from CLOSED to OPEN
        for _ in range(3):
            cb.record_failure()

        # Give time for async logging to complete
        await asyncio.sleep(0.1)
        await event_logger.flush()

        # Verify state change was logged
        dt = DeltaTable(str(TEST_TABLE_PATH))
        df = dt.to_pyarrow_table()

        # Should have 1 state change event + 3 failure events
        state_changes = df.filter(df["event_type"] == "circuit_breaker_state_change")
        failures = df.filter(df["event_type"] == "circuit_breaker_failure")

        assert state_changes.num_rows >= 1
        assert failures.num_rows == 3

    @pytest.mark.asyncio
    async def test_circuit_breaker_logs_manual_reset(self, event_logger):
        """Test that circuit breaker logs manual reset."""
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = TradingCircuitBreaker(config, event_logger=event_logger)

        # Open circuit
        for _ in range(3):
            cb.record_failure()

        # Reset
        cb.reset()

        # Give time for async logging
        await asyncio.sleep(0.1)
        await event_logger.flush()

        # Verify reset was logged
        dt = DeltaTable(str(TEST_TABLE_PATH))
        df = dt.to_pyarrow_table()

        reset_events = df.filter(df["event_type"] == "circuit_breaker_manual_reset")
        assert reset_events.num_rows >= 1


class TestTrailingStopLogging:
    """Tests for trailing stop logging integration."""

    @pytest.mark.asyncio
    async def test_trailing_stop_logs_activate(self, event_logger):
        """Test that trailing stop logs activation."""
        stop = TrailingStop(
            execution_id="test_123",
            entry_premium=100.0,
            event_logger=event_logger,
        )

        # Trigger activation
        new_stop, action = stop.update(103.0)

        assert action == TrailingStopAction.ACTIVATE

        # Give time for async logging
        await asyncio.sleep(0.1)
        await event_logger.flush()

        # Verify activation was logged
        dt = DeltaTable(str(TEST_TABLE_PATH))
        df = dt.to_pyarrow_table()

        activate_events = df.filter(df["event_type"] == "trailing_stop_activate")
        assert activate_events.num_rows >= 1

    @pytest.mark.asyncio
    async def test_trailing_stop_logs_update(self, event_logger):
        """Test that trailing stop logs updates."""
        stop = TrailingStop(
            execution_id="test_123",
            entry_premium=100.0,
            event_logger=event_logger,
        )

        # Activate
        stop.update(103.0)

        # Update to new peak
        new_stop, action = stop.update(105.0)

        assert action == TrailingStopAction.UPDATE

        # Give time for async logging
        await asyncio.sleep(0.1)
        await event_logger.flush()

        # Verify update was logged
        dt = DeltaTable(str(TEST_TABLE_PATH))
        df = dt.to_pyarrow_table()

        update_events = df.filter(df["event_type"] == "trailing_stop_update")
        assert update_events.num_rows >= 1

    @pytest.mark.asyncio
    async def test_trailing_stop_logs_trigger(self, event_logger):
        """Test that trailing stop logs triggers."""
        stop = TrailingStop(
            execution_id="test_123",
            entry_premium=100.0,
            event_logger=event_logger,
        )

        # Activate
        stop.update(103.0)

        # Trigger
        new_stop, action = stop.update(100.0)

        assert action == TrailingStopAction.TRIGGER

        # Give time for async logging
        await asyncio.sleep(0.1)
        await event_logger.flush()

        # Verify trigger was logged
        dt = DeltaTable(str(TEST_TABLE_PATH))
        df = dt.to_pyarrow_table()

        trigger_events = df.filter(df["event_type"] == "trailing_stop_trigger")
        assert trigger_events.num_rows >= 1

    @pytest.mark.asyncio
    async def test_trailing_stop_manager_logs_add_and_remove(self, event_logger):
        """Test that TrailingStopManager logs add/remove events."""
        manager = TrailingStopManager(event_logger=event_logger)

        # Add stop
        manager.add_trailing_stop("test_123", 100.0)

        # Remove stop
        manager.remove_stop("test_123")

        # Give time for async logging
        await asyncio.sleep(0.1)
        await event_logger.flush()

        # Verify events were logged
        dt = DeltaTable(str(TEST_TABLE_PATH))
        df = dt.to_pyarrow_table()

        add_events = df.filter(df["event_type"] == "trailing_stop_add")
        remove_events = df.filter(df["event_type"] == "trailing_stop_remove")

        assert add_events.num_rows >= 1
        assert remove_events.num_rows >= 1


class TestPortfolioLimitsLogging:
    """Tests for portfolio limits logging integration."""

    @pytest.mark.asyncio
    async def test_portfolio_limits_logs_rejection(self, mock_risk_calculator, event_logger):
        """Test that portfolio limits checker logs rejections."""
        from v6.risk.portfolio_limits import PortfolioLimitsChecker

        limits = RiskLimitsConfig(max_portfolio_delta=50.0)
        checker = PortfolioLimitsChecker(
            mock_risk_calculator,
            limits,
            event_logger=event_logger,
        )

        # Try to exceed delta limit
        allowed, reason = await checker.check_entry_allowed(
            new_position_delta=55.0,
            symbol="SPY",
            position_value=10000.0,
        )

        assert not allowed
        assert reason is not None

        # Give time for async logging
        await asyncio.sleep(0.1)
        await event_logger.flush()

        # Verify rejection was logged
        dt = DeltaTable(str(TEST_TABLE_PATH))
        df = dt.to_pyarrow_table()

        rejection_events = df.filter(df["event_type"] == "portfolio_limit_rejection")
        assert rejection_events.num_rows >= 1

    @pytest.mark.asyncio
    async def test_portfolio_limits_logs_allowed(self, mock_risk_calculator, event_logger):
        """Test that portfolio limits checker logs allowed entries."""
        from v6.risk.portfolio_limits import PortfolioLimitsChecker

        limits = RiskLimitsConfig(max_portfolio_delta=50.0)
        checker = PortfolioLimitsChecker(
            mock_risk_calculator,
            limits,
            event_logger=event_logger,
        )

        # Entry within limits
        allowed, reason = await checker.check_entry_allowed(
            new_position_delta=5.0,
            symbol="SPY",
            position_value=10000.0,
        )

        assert allowed
        assert reason is None

        # Give time for async logging
        await asyncio.sleep(0.1)
        await event_logger.flush()

        # Verify check was logged
        dt = DeltaTable(str(TEST_TABLE_PATH))
        df = dt.to_pyarrow_table()

        check_events = df.filter(df["event_type"] == "portfolio_limit_check")
        assert check_events.num_rows >= 1

        # Verify the check event has allowed=True
        allowed_events = df.filter(
            (df["event_type"] == "portfolio_limit_check") & (df["allowed"] == True)
        )
        assert allowed_events.num_rows >= 1

    @pytest.mark.asyncio
    async def test_portfolio_limits_logs_warnings(self, mock_risk_calculator, event_logger):
        """Test that portfolio limits checker logs warnings."""
        from v6.risk.portfolio_limits import PortfolioLimitsChecker

        limits = RiskLimitsConfig(max_portfolio_delta=5.0)  # Very low limit
        checker = PortfolioLimitsChecker(
            mock_risk_calculator,
            limits,
            event_logger=event_logger,
        )

        # Check portfolio health (should generate warnings)
        warnings = await checker.check_portfolio_health()

        assert len(warnings) > 0  # Should have at least one warning

        # Give time for async logging
        await asyncio.sleep(0.1)
        await event_logger.flush()

        # Verify warnings were logged
        dt = DeltaTable(str(TEST_TABLE_PATH))
        df = dt.to_pyarrow_table()

        warning_events = df.filter(df["event_type"] == "portfolio_limit_warning")
        assert warning_events.num_rows >= 1


class TestBackwardCompatibility:
    """Tests for backward compatibility when event_logger is None."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_works_without_logger(self):
        """Test that circuit breaker works without event logger."""
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = TradingCircuitBreaker(config, event_logger=None)

        # Should work normally
        for _ in range(3):
            state = cb.record_failure()

        assert state.name == "OPEN"

    @pytest.mark.asyncio
    async def test_trailing_stop_works_without_logger(self):
        """Test that trailing stop works without event logger."""
        stop = TrailingStop(
            execution_id="test_123",
            entry_premium=100.0,
            event_logger=None,
        )

        # Should work normally
        new_stop, action = stop.update(103.0)

        assert action == TrailingStopAction.ACTIVATE
        assert new_stop == pytest.approx(101.455, rel=0.001)

    @pytest.mark.asyncio
    async def test_trailing_stop_manager_works_without_logger(self):
        """Test that TrailingStopManager works without event logger."""
        manager = TrailingStopManager(event_logger=None)

        # Should work normally
        stop = manager.add_trailing_stop("test_123", 100.0)

        assert stop.entry_premium == 100.0
        assert "test_123" in manager.stops

    @pytest.mark.asyncio
    async def test_portfolio_limits_works_without_logger(self, mock_risk_calculator):
        """Test that portfolio limits checker works without event logger."""
        from v6.risk.portfolio_limits import PortfolioLimitsChecker

        limits = RiskLimitsConfig(max_portfolio_delta=50.0)
        checker = PortfolioLimitsChecker(
            mock_risk_calculator,
            limits,
            event_logger=None,
        )

        # Should work normally
        allowed, reason = await checker.check_entry_allowed(
            new_position_delta=5.0,
            symbol="SPY",
            position_value=10000.0,
        )

        assert allowed
        assert reason is None
