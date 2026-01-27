"""
Integration tests for OrderExecutionEngine with circuit breaker.

Tests the interaction between OrderExecutionEngine and TradingCircuitBreaker,
including order blocking during circuit OPEN state and state transitions.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.v6.execution.engine import OrderExecutionEngine
from src.v6.execution.models import Order, OrderAction, OrderStatus, OrderType, TimeInForce
from src.v6.risk import (
    CircuitBreakerConfig,
    CircuitBreakerOpenException,
    CircuitState,
    TradingCircuitBreaker,
)
from src.v6.utils.ib_connection import IBConnectionManager


@pytest.fixture
def mock_ib_conn():
    """Create mock IB connection manager."""
    ib_conn = MagicMock(spec=IBConnectionManager)
    ib_conn.ib = MagicMock()
    ib_conn.ensure_connected = AsyncMock()
    ib_conn.ib.placeOrder = MagicMock()
    return ib_conn


@pytest.fixture
def sample_order():
    """Create sample order for testing."""
    return Order(
        order_id="test-order-123",
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


@pytest.fixture
def mock_contract():
    """Create mock IB contract."""
    contract = MagicMock()
    contract.conId = 123456
    contract.symbol = "SPY"
    return contract


class TestOrderExecutionEngineWithCircuitBreaker:
    """Test OrderExecutionEngine with circuit breaker integration."""

    def test_engine_init_without_circuit_breaker(self, mock_ib_conn):
        """Test engine initialization without circuit breaker (backward compatible)."""
        engine = OrderExecutionEngine(mock_ib_conn, dry_run=False)

        assert engine.circuit_breaker is None
        assert engine.dry_run is False

    def test_engine_init_with_circuit_breaker(self, mock_ib_conn):
        """Test engine initialization with circuit breaker."""
        config = CircuitBreakerConfig(failure_threshold=5)
        cb = TradingCircuitBreaker(config)

        engine = OrderExecutionEngine(mock_ib_conn, circuit_breaker=cb, dry_run=False)

        assert engine.circuit_breaker is cb
        assert engine.dry_run is False

    @pytest.mark.asyncio
    async def test_order_allowed_when_circuit_closed(self, mock_ib_conn, sample_order, mock_contract):
        """Test that order is allowed when circuit is CLOSED."""
        config = CircuitBreakerConfig(failure_threshold=5)
        cb = TradingCircuitBreaker(config)
        engine = OrderExecutionEngine(mock_ib_conn, circuit_breaker=cb, dry_run=True)

        # Circuit should be CLOSED initially
        assert cb.state == CircuitState.CLOSED

        # Order should be allowed
        result = await engine.place_order(mock_contract, sample_order)

        assert result.status == OrderStatus.FILLED  # Dry run fills immediately
        assert cb.state == CircuitState.CLOSED  # Should stay CLOSED

    @pytest.mark.asyncio
    async def test_order_blocked_when_circuit_open(self, mock_ib_conn, sample_order, mock_contract):
        """Test that order is blocked when circuit is OPEN."""
        config = CircuitBreakerConfig(failure_threshold=3, open_timeout_secs=300)
        cb = TradingCircuitBreaker(config)
        engine = OrderExecutionEngine(mock_ib_conn, circuit_breaker=cb, dry_run=True)

        # Open the circuit by recording failures
        for _ in range(3):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

        # Order should be blocked
        with pytest.raises(CircuitBreakerOpenException) as exc_info:
            await engine.place_order(mock_contract, sample_order)

        assert "OPEN" in str(exc_info.value)
        assert sample_order.status == OrderStatus.PENDING_SUBMIT  # Not submitted

    @pytest.mark.asyncio
    async def test_order_allowed_when_circuit_half_open(self, mock_ib_conn, sample_order, mock_contract):
        """Test that order is allowed when circuit is HALF_OPEN with warning."""
        config = CircuitBreakerConfig(failure_threshold=3, open_timeout_secs=0)
        cb = TradingCircuitBreaker(config)
        engine = OrderExecutionEngine(mock_ib_conn, circuit_breaker=cb, dry_run=True)

        # Open the circuit
        for _ in range(3):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

        # Check if allowed (should transition to HALF_OPEN)
        cb.is_trading_allowed()
        assert cb.state == CircuitState.HALF_OPEN

        # Order should be allowed (testing recovery)
        result = await engine.place_order(mock_contract, sample_order)

        assert result.status == OrderStatus.FILLED
        assert cb.half_open_tries == 1  # Success recorded

    @pytest.mark.asyncio
    async def test_success_recording_in_dry_run(self, mock_ib_conn, sample_order, mock_contract):
        """Test that successful orders record success in circuit breaker."""
        config = CircuitBreakerConfig(failure_threshold=3, open_timeout_secs=0, half_open_max_tries=2)
        cb = TradingCircuitBreaker(config)
        engine = OrderExecutionEngine(mock_ib_conn, circuit_breaker=cb, dry_run=True)

        # Open and transition to HALF_OPEN
        for _ in range(3):
            cb.record_failure()
        cb.is_trading_allowed()

        assert cb.state == CircuitState.HALF_OPEN
        assert cb.half_open_tries == 0

        # Helper to create fresh orders
        def create_order(order_id: str) -> Order:
            return Order(
                order_id=order_id,
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

        # Execute first successful order
        await engine.place_order(mock_contract, create_order("order-1"))
        assert cb.half_open_tries == 1
        assert cb.state == CircuitState.HALF_OPEN  # Still HALF_OPEN

        # Execute second successful order (should close circuit since half_open_max_tries=2)
        await engine.place_order(mock_contract, create_order("order-2"))
        assert cb.half_open_tries == 0  # Reset after closing
        assert cb.state == CircuitState.CLOSED  # Circuit closed

        # Execute third order (should stay CLOSED)
        await engine.place_order(mock_contract, create_order("order-3"))
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_failure_recording_on_exception(self, mock_ib_conn, sample_order, mock_contract):
        """Test that failed orders record failure in circuit breaker."""
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = TradingCircuitBreaker(config)

        # Mock placeOrder to raise exception
        mock_ib_conn.ib.placeOrder.side_effect = Exception("IB API error")

        engine = OrderExecutionEngine(mock_ib_conn, circuit_breaker=cb, dry_run=False)

        # Circuit should be CLOSED initially
        assert cb.state == CircuitState.CLOSED
        assert len(cb.failures) == 0

        # Helper to create fresh orders
        def create_order(order_id: str) -> Order:
            return Order(
                order_id=order_id,
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

        # Attempt to place order (should fail)
        with pytest.raises(Exception, match="IB API error"):
            await engine.place_order(mock_contract, create_order("order-1"))

        # Failure should be recorded
        assert len(cb.failures) == 1
        assert cb.state == CircuitState.CLOSED  # Not enough failures yet

        # Record 2 more failures to open circuit
        with pytest.raises(Exception):
            await engine.place_order(mock_contract, create_order("order-2"))

        with pytest.raises(Exception):
            await engine.place_order(mock_contract, create_order("order-3"))

        # Circuit should be OPEN now
        assert len(cb.failures) == 3
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_backward_compatibility_without_circuit_breaker(
        self, mock_ib_conn, sample_order, mock_contract
    ):
        """Test that engine works without circuit breaker (backward compatible)."""
        # Create engine without circuit breaker
        engine = OrderExecutionEngine(mock_ib_conn, circuit_breaker=None, dry_run=True)

        # Order should work normally
        result = await engine.place_order(mock_contract, sample_order)

        assert result.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_full_cycle_closed_to_closed(self, mock_ib_conn, sample_order, mock_contract):
        """Test full cycle: CLOSED → OPEN → HALF_OPEN → CLOSED."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            open_timeout_secs=0,
            half_open_max_tries=2,
        )
        cb = TradingCircuitBreaker(config)
        engine = OrderExecutionEngine(mock_ib_conn, circuit_breaker=cb, dry_run=False)

        # Mock placeOrder to simulate failures then success
        failure_count = [0]

        def mock_place_order(*args, **kwargs):
            if failure_count[0] < 3:
                failure_count[0] += 1
                raise Exception(f"IB API error {failure_count[0]}")
            # Succeed after 3 failures
            trade = MagicMock()
            trade.order.orderId = 12345
            return trade

        mock_ib_conn.ib.placeOrder.side_effect = mock_place_order

        # Helper to create fresh orders
        def create_order(order_id: str) -> Order:
            return Order(
                order_id=order_id,
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

        # Start CLOSED
        assert cb.state == CircuitState.CLOSED

        # Record failures (CLOSED → OPEN)
        for i in range(3):
            try:
                await engine.place_order(mock_contract, create_order(f"fail-order-{i}"))
            except Exception:
                pass

        assert cb.state == CircuitState.OPEN

        # Check if allowed (OPEN → HALF_OPEN)
        cb.is_trading_allowed()
        assert cb.state == CircuitState.HALF_OPEN

        # Record successes (HALF_OPEN → CLOSED)
        for i in range(2):
            await engine.place_order(mock_contract, create_order(f"success-order-{i}"))

        assert cb.state == CircuitState.CLOSED
        assert len(cb.failures) == 0


class TestCircuitBreakerConfigDefaults:
    """Test default circuit breaker configuration for OrderExecutionEngine."""

    def test_recommended_config_for_trading(self):
        """Test recommended configuration for trading systems."""
        # Recommended settings from research:
        # - 5 failures in 60s window
        # - 300s (5 min) cooldown before testing
        # - 3 successful trades before closing
        config = CircuitBreakerConfig(
            failure_threshold=5,
            failure_window_secs=60,
            half_open_timeout_secs=30,
            half_open_max_tries=3,
            open_timeout_secs=300,
        )

        assert config.failure_threshold == 5
        assert config.failure_window_secs == 60
        assert config.open_timeout_secs == 300
        assert config.half_open_max_tries == 3

    def test_aggressive_config_for_testing(self):
        """Test aggressive configuration for testing."""
        # More sensitive settings for testing:
        # - 3 failures in 30s window
        # - 0s cooldown (immediate testing)
        # - 2 successful trades before closing
        config = CircuitBreakerConfig(
            failure_threshold=3,
            failure_window_secs=30,
            half_open_timeout_secs=10,
            half_open_max_tries=2,
            open_timeout_secs=0,  # Immediate HALF_OPEN
        )

        assert config.failure_threshold == 3
        assert config.failure_window_secs == 30
        assert config.open_timeout_secs == 0
        assert config.half_open_max_tries == 2
