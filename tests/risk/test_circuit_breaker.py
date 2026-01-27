"""
Unit tests for TradingCircuitBreaker.

Tests the circuit breaker state machine, failure tracking, recovery testing,
and manual reset functionality.
"""

import pytest
from datetime import datetime, timedelta

from src.v6.risk.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerOpenException,
    CircuitState,
    TradingCircuitBreaker,
)


class TestCircuitBreakerConfig:
    """Test CircuitBreakerConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = CircuitBreakerConfig()

        assert config.failure_threshold == 5
        assert config.failure_window_secs == 60
        assert config.half_open_timeout_secs == 30
        assert config.half_open_max_tries == 3
        assert config.open_timeout_secs == 300

    def test_custom_config(self):
        """Test custom configuration values."""
        config = CircuitBreakerConfig(
            failure_threshold=10,
            failure_window_secs=120,
            half_open_timeout_secs=60,
            half_open_max_tries=5,
            open_timeout_secs=600,
        )

        assert config.failure_threshold == 10
        assert config.failure_window_secs == 120
        assert config.half_open_timeout_secs == 60
        assert config.half_open_max_tries == 5
        assert config.open_timeout_secs == 600


class TestTradingCircuitBreakerInit:
    """Test TradingCircuitBreaker initialization."""

    def test_initial_state(self):
        """Test circuit breaker starts in CLOSED state."""
        config = CircuitBreakerConfig()
        cb = TradingCircuitBreaker(config)

        assert cb.state == CircuitState.CLOSED
        assert len(cb.failures) == 0
        assert cb.opened_at is None
        assert cb.half_open_tries == 0

    def test_custom_config(self):
        """Test circuit breaker with custom config."""
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = TradingCircuitBreaker(config)

        assert cb.config.failure_threshold == 3
        assert cb.state == CircuitState.CLOSED


class TestRecordFailure:
    """Test record_failure method."""

    def test_record_failure_in_closed_state(self):
        """Test recording failures in CLOSED state."""
        config = CircuitBreakerConfig(failure_threshold=5, failure_window_secs=60)
        cb = TradingCircuitBreaker(config)

        # Record 4 failures (below threshold)
        for _ in range(4):
            state = cb.record_failure()

        assert state == CircuitState.CLOSED
        assert len(cb.failures) == 4

    def test_record_failure_opens_circuit(self):
        """Test that exceeding threshold opens circuit."""
        config = CircuitBreakerConfig(failure_threshold=5, failure_window_secs=60)
        cb = TradingCircuitBreaker(config)

        # Record 5 failures (at threshold)
        for i in range(5):
            state = cb.record_failure()

        assert state == CircuitState.OPEN
        assert cb.opened_at is not None
        assert len(cb.failures) == 5

    def test_record_failure_in_open_state(self):
        """Test recording failures while already OPEN."""
        config = CircuitBreakerConfig(failure_threshold=5, failure_window_secs=60)
        cb = TradingCircuitBreaker(config)

        # Open the circuit
        for _ in range(5):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

        # Record more failures while OPEN
        cb.record_failure()
        cb.record_failure()

        # Should stay OPEN
        assert cb.state == CircuitState.OPEN
        assert len(cb.failures) == 7

    def test_failure_window_cleanup(self):
        """Test that old failures are cleaned up outside window."""
        config = CircuitBreakerConfig(failure_threshold=5, failure_window_secs=60)
        cb = TradingCircuitBreaker(config)

        # Record 5 failures, but manually age them
        old_time = datetime.now() - timedelta(seconds=120)
        cb.failures = [old_time] * 5

        # Record a new failure (should clean old ones)
        state = cb.record_failure()

        # Should only have the new failure
        assert len(cb.failures) == 1
        assert state == CircuitState.CLOSED  # Not enough failures

    def test_failures_within_window_count(self):
        """Test that only failures within window are counted."""
        config = CircuitBreakerConfig(failure_threshold=5, failure_window_secs=60)
        cb = TradingCircuitBreaker(config)

        # Add 3 old failures (outside window)
        old_time = datetime.now() - timedelta(seconds=120)
        cb.failures.extend([old_time] * 3)

        # Add 5 new failures (within window)
        for _ in range(5):
            cb.record_failure()

        # Should have 5 failures (old ones cleaned up)
        assert len(cb.failures) == 5
        assert cb.state == CircuitState.OPEN


class TestRecordSuccess:
    """Test record_success method."""

    def test_record_success_in_closed_state(self):
        """Test recording success in CLOSED state."""
        config = CircuitBreakerConfig()
        cb = TradingCircuitBreaker(config)

        state = cb.record_success()

        # Should stay CLOSED
        assert state == CircuitState.CLOSED
        assert len(cb.failures) == 0

    def test_record_success_in_open_state(self):
        """Test recording success in OPEN state."""
        config = CircuitBreakerConfig()
        cb = TradingCircuitBreaker(config)

        # Open the circuit
        for _ in range(5):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

        # Record success (should not change state)
        state = cb.record_success()

        assert state == CircuitState.OPEN
        assert cb.half_open_tries == 0

    def test_record_success_in_half_open_state(self):
        """Test recording success in HALF_OPEN state."""
        config = CircuitBreakerConfig(
            half_open_max_tries=3, open_timeout_secs=0  # Immediate half-open
        )
        cb = TradingCircuitBreaker(config)

        # Open the circuit
        for _ in range(5):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

        # Transition to HALF_OPEN by checking if allowed
        cb.is_trading_allowed()

        # Record 3 successful trades
        for i in range(3):
            state = cb.record_success()
            # half_open_tries increments until circuit closes
            if i < 2:  # Before closing
                assert cb.half_open_tries == i + 1

        # Should close after 3 successes
        assert state == CircuitState.CLOSED
        assert len(cb.failures) == 0
        assert cb.half_open_tries == 0  # Reset after closing
        assert cb.opened_at is None

    def test_half_open_requires_full_success_count(self):
        """Test that HALF_OPEN requires all successes to close."""
        config = CircuitBreakerConfig(
            half_open_max_tries=3, open_timeout_secs=0
        )
        cb = TradingCircuitBreaker(config)

        # Open circuit
        for _ in range(5):
            cb.record_failure()

        # Transition to HALF_OPEN
        cb.is_trading_allowed()

        # Only 2 successes (not enough)
        cb.record_success()
        cb.record_success()

        # Should still be HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.half_open_tries == 2


class TestIsTradingAllowed:
    """Test is_trading_allowed method."""

    def test_trading_allowed_in_closed_state(self):
        """Test that trading is allowed in CLOSED state."""
        config = CircuitBreakerConfig()
        cb = TradingCircuitBreaker(config)

        allowed, reason = cb.is_trading_allowed()

        assert allowed is True
        assert reason is None

    def test_trading_blocked_in_open_state(self):
        """Test that trading is blocked in OPEN state."""
        config = CircuitBreakerConfig()
        cb = TradingCircuitBreaker(config)

        # Open the circuit
        for _ in range(5):
            cb.record_failure()

        allowed, reason = cb.is_trading_allowed()

        assert allowed is False
        assert reason is not None
        assert "OPEN" in reason
        assert "5 failures" in reason

    def test_trading_allowed_in_half_open_state(self):
        """Test that trading is allowed in HALF_OPEN state."""
        config = CircuitBreakerConfig(open_timeout_secs=0)
        cb = TradingCircuitBreaker(config)

        # Open the circuit
        for _ in range(5):
            cb.record_failure()

        # Check if allowed (should transition to HALF_OPEN)
        allowed, reason = cb.is_trading_allowed()

        assert allowed is True
        assert cb.state == CircuitState.HALF_OPEN
        assert "HALF_OPEN" in reason

    def test_open_to_half_open_transition(self):
        """Test transition from OPEN to HALF_OPEN after timeout."""
        config = CircuitBreakerConfig(open_timeout_secs=1)
        cb = TradingCircuitBreaker(config)

        # Open the circuit
        for _ in range(5):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

        # Should still be OPEN immediately
        allowed, _ = cb.is_trading_allowed()
        assert allowed is False
        assert cb.state == CircuitState.OPEN

        # Wait for timeout
        import time

        time.sleep(1.1)

        # Should transition to HALF_OPEN
        allowed, reason = cb.is_trading_allowed()
        assert allowed is True
        assert cb.state == CircuitState.HALF_OPEN
        assert "HALF_OPEN" in reason


class TestGetState:
    """Test get_state method."""

    def test_get_state_in_closed(self):
        """Test get_state in CLOSED state."""
        config = CircuitBreakerConfig()
        cb = TradingCircuitBreaker(config)

        state = cb.get_state()

        assert state["state"] == "CLOSED"
        assert state["failures"] == 0
        assert state["opened_at"] is None
        assert state["half_open_tries"] == 0

    def test_get_state_in_open(self):
        """Test get_state in OPEN state."""
        config = CircuitBreakerConfig()
        cb = TradingCircuitBreaker(config)

        # Open the circuit
        for _ in range(5):
            cb.record_failure()

        state = cb.get_state()

        assert state["state"] == "OPEN"
        assert state["failures"] == 5
        assert state["opened_at"] is not None
        assert state["half_open_tries"] == 0

    def test_get_state_in_half_open(self):
        """Test get_state in HALF_OPEN state."""
        config = CircuitBreakerConfig(open_timeout_secs=0)
        cb = TradingCircuitBreaker(config)

        # Open and transition to HALF_OPEN
        for _ in range(5):
            cb.record_failure()
        cb.is_trading_allowed()

        # Record some successes
        cb.record_success()
        cb.record_success()

        state = cb.get_state()

        assert state["state"] == "HALF_OPEN"
        assert state["failures"] == 5
        assert state["opened_at"] is not None
        assert state["half_open_tries"] == 2


class TestReset:
    """Test reset method."""

    def test_reset_from_open(self):
        """Test manual reset from OPEN state."""
        config = CircuitBreakerConfig()
        cb = TradingCircuitBreaker(config)

        # Open the circuit
        for _ in range(5):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN
        assert len(cb.failures) == 5

        # Reset
        cb.reset()

        assert cb.state == CircuitState.CLOSED
        assert len(cb.failures) == 0
        assert cb.opened_at is None
        assert cb.half_open_tries == 0

    def test_reset_from_half_open(self):
        """Test manual reset from HALF_OPEN state."""
        config = CircuitBreakerConfig(open_timeout_secs=0)
        cb = TradingCircuitBreaker(config)

        # Open and transition to HALF_OPEN
        for _ in range(5):
            cb.record_failure()
        cb.is_trading_allowed()
        cb.record_success()

        assert cb.state == CircuitState.HALF_OPEN
        assert cb.half_open_tries == 1

        # Reset
        cb.reset()

        assert cb.state == CircuitState.CLOSED
        assert len(cb.failures) == 0
        assert cb.opened_at is None
        assert cb.half_open_tries == 0

    def test_reset_from_closed(self):
        """Test manual reset from CLOSED state (no-op)."""
        config = CircuitBreakerConfig()
        cb = TradingCircuitBreaker(config)

        # Add some failures (but not enough to open)
        cb.record_failure()
        cb.record_failure()

        assert cb.state == CircuitState.CLOSED
        assert len(cb.failures) == 2

        # Reset
        cb.reset()

        assert cb.state == CircuitState.CLOSED
        assert len(cb.failures) == 0
        assert cb.opened_at is None


class TestFullStateTransitions:
    """Test complete state transition cycles."""

    def test_closed_to_open_transition(self):
        """Test CLOSED → OPEN transition."""
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = TradingCircuitBreaker(config)

        # Start CLOSED
        assert cb.state == CircuitState.CLOSED

        # Trigger failures
        cb.record_failure()
        cb.record_failure()
        state = cb.record_failure()

        # Should be OPEN now
        assert state == CircuitState.OPEN
        assert cb.state == CircuitState.OPEN

    def test_open_to_half_open_transition(self):
        """Test OPEN → HALF_OPEN transition after timeout."""
        config = CircuitBreakerConfig(
            failure_threshold=3, open_timeout_secs=0  # Immediate
        )
        cb = TradingCircuitBreaker(config)

        # Open the circuit
        for _ in range(3):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

        # Check if allowed (should transition to HALF_OPEN)
        cb.is_trading_allowed()

        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_to_closed_transition(self):
        """Test HALF_OPEN → CLOSED transition after successes."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            open_timeout_secs=0,
            half_open_max_tries=2,
        )
        cb = TradingCircuitBreaker(config)

        # Open and transition to HALF_OPEN
        for _ in range(3):
            cb.record_failure()
        cb.is_trading_allowed()

        assert cb.state == CircuitState.HALF_OPEN

        # Record successes
        cb.record_success()
        state = cb.record_success()

        # Should be CLOSED now
        assert state == CircuitState.CLOSED
        assert cb.state == CircuitState.CLOSED
        assert len(cb.failures) == 0

    def test_full_cycle_closed_to_closed(self):
        """Test full cycle: CLOSED → OPEN → HALF_OPEN → CLOSED."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            open_timeout_secs=0,
            half_open_max_tries=2,
        )
        cb = TradingCircuitBreaker(config)

        # Start CLOSED
        assert cb.state == CircuitState.CLOSED

        # CLOSED → OPEN
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # OPEN → HALF_OPEN
        cb.is_trading_allowed()
        assert cb.state == CircuitState.HALF_OPEN

        # HALF_OPEN → CLOSED
        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert len(cb.failures) == 0

    def test_half_open_failure_reopens(self):
        """Test that failure in HALF_OPEN reopens circuit."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            open_timeout_secs=0,
            half_open_max_tries=3,
        )
        cb = TradingCircuitBreaker(config)

        # Open and transition to HALF_OPEN
        for _ in range(3):
            cb.record_failure()
        cb.is_trading_allowed()

        assert cb.state == CircuitState.HALF_OPEN

        # Record 2 successes
        cb.record_success()
        cb.record_success()
        assert cb.half_open_tries == 2

        # Record a failure - this should trigger circuit to OPEN again
        # because the failure threshold is exceeded within the window
        state = cb.record_failure()

        # Circuit should transition back to OPEN
        assert state == CircuitState.OPEN
        assert cb.state == CircuitState.OPEN
        assert cb.opened_at is not None


class TestCircuitBreakerOpenException:
    """Test CircuitBreakerOpenException."""

    def test_exception_creation(self):
        """Test creating exception with all attributes."""
        exc = CircuitBreakerOpenException(
            "Circuit is open",
            state=CircuitState.OPEN,
            failure_count=5,
            failures_in_window=[datetime.now()] * 5,
        )

        assert exc.message == "Circuit is open"
        assert exc.state == CircuitState.OPEN
        assert exc.failure_count == 5
        assert len(exc.failures_in_window) == 5

    def test_exception_repr(self):
        """Test exception string representation."""
        exc = CircuitBreakerOpenException(
            "Circuit is open",
            state=CircuitState.OPEN,
            failure_count=5,
            failures_in_window=[],
        )

        repr_str = repr(exc)
        assert "CircuitBreakerOpenException" in repr_str
        assert "OPEN" in repr_str
        assert "5" in repr_str

    def test_exception_str(self):
        """Test exception message."""
        exc = CircuitBreakerOpenException(
            "Circuit is open",
            state=CircuitState.OPEN,
            failure_count=5,
            failures_in_window=[],
        )

        assert str(exc) == "Circuit is open"
