"""
Trading Circuit Breaker for System-Level Fault Tolerance

This module implements a circuit breaker pattern adapted from Azure/Microsoft
distributed systems patterns for automated trading systems.

Key features:
- System-level fault tolerance (NOT market circuit breakers)
- Three-state machine: CLOSED (normal), OPEN (failing), HALF_OPEN (testing)
- Failure tracking with sliding time window
- Recovery testing with configurable success threshold
- Manual reset capability for admin intervention

Pattern source: Azure Circuit Breaker Pattern
https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker

Usage:
    >>> from src.v6.risk import CircuitState, CircuitBreakerConfig, TradingCircuitBreaker
    >>>
    >>> # Configure circuit breaker
    >>> config = CircuitBreakerConfig(
    ...     failure_threshold=5,
    ...     failure_window_secs=60
    ... )
    >>>
    >>> # Create circuit breaker
    >>> cb = TradingCircuitBreaker(config)
    >>>
    >>> # Check if trading is allowed
    >>> allowed, reason = cb.is_trading_allowed()
    >>> if not allowed:
    ...     print(f"Trading blocked: {reason}")
    >>>
    >>> # Record failure (e.g., order rejected)
    >>> cb.record_failure()
    >>>
    >>> # Record success (e.g., order filled)
    >>> cb.record_success()
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """
    Circuit breaker states.

    States:
        CLOSED: Normal operation, trades allowed
        OPEN: Failure detected, trades blocked
        HALF_OPEN: Testing if system recovered, trades allowed with monitoring

    Transitions:
        CLOSED → OPEN: When failure threshold exceeded
        OPEN → HALF_OPEN: After open_timeout_secs elapsed
        HALF_OPEN → CLOSED: After half_open_max_tries successful trades
        HALF_OPEN → OPEN: If failure occurs during testing
    """

    CLOSED = auto()  # Normal operation, trades allowed
    OPEN = auto()  # Failure detected, trades blocked
    HALF_OPEN = auto()  # Testing if system recovered


@dataclass(slots=True)
class CircuitBreakerConfig:
    """
    Circuit breaker configuration.

    Attributes:
        failure_threshold: Number of failures required to open circuit (default: 5)
        failure_window_secs: Time window in seconds for failure counting (default: 60)
        half_open_timeout_secs: Wait time before allowing first test trade (default: 30)
        half_open_max_tries: Successful trades required to close circuit (default: 3)
        open_timeout_secs: Minimum time to stay open before half-open (default: 300)

    Example:
        >>> config = CircuitBreakerConfig(
        ...     failure_threshold=5,
        ...     failure_window_secs=60,
        ...     open_timeout_secs=300
        ... )
    """

    # Failure thresholds
    failure_threshold: int = 5  # N failures before opening
    failure_window_secs: int = 60  # Time window for failures

    # Recovery testing
    half_open_timeout_secs: int = 30  # Wait before testing recovery
    half_open_max_tries: int = 3  # N successful trades before closing

    # Cooldown
    open_timeout_secs: int = 300  # Stay open before half-open (5 minutes)


class CircuitBreakerOpenException(Exception):
    """
    Exception raised when circuit breaker is OPEN and trading is blocked.

    Raised when attempting to place an order while the circuit breaker is in OPEN state.
    This prevents cascading failures during systemic issues.

    Attributes:
        message: Human-readable error message
        state: Current circuit state (should be CircuitState.OPEN)
        failure_count: Number of failures in the current window
        failures_in_window: List of failure timestamps

    Example:
        >>> try:
        ...     # Attempt to place order
        ...     pass
        ... except CircuitBreakerOpenException as e:
        ...     print(f"Circuit breaker OPEN: {e.message}")
        ...     print(f"Failures: {e.failure_count} in window")
    """

    def __init__(
        self,
        message: str,
        *,
        state: CircuitState,
        failure_count: int,
        failures_in_window: list[datetime],
    ):
        """
        Initialize circuit breaker open exception.

        Args:
            message: Human-readable error message
            state: Current circuit state
            failure_count: Number of failures in current window
            failures_in_window: List of failure timestamps
        """
        self.message = message
        self.state = state
        self.failure_count = failure_count
        self.failures_in_window = failures_in_window
        super().__init__(self.message)

    def __repr__(self) -> str:
        """Return string representation of exception."""
        return (
            f"CircuitBreakerOpenException("
            f"state={self.state.name}, "
            f"failure_count={self.failure_count}, "
            f"message='{self.message}')"
        )

    def __str__(self) -> str:
        """Return user-friendly string representation."""
        return self.message


class TradingCircuitBreaker:
    """
    Circuit breaker for automated trading system.

    Prevents cascading failures by halting trading during systemic issues:
    - High order rejection rate
    - Data feed failures
    - Margin exhaustion
    - Excessive slippage
    - Connection issues

    This is a SYSTEM circuit breaker (halts automation), not a MARKET circuit breaker
    (which halts trading venues). Adapted from Azure/Microsoft distributed systems patterns.

    State transitions:
        CLOSED → OPEN: When failure_threshold failures occur within failure_window_secs
        OPEN → HALF_OPEN: After open_timeout_secs have elapsed
        HALF_OPEN → CLOSED: After half_open_max_tries successful trades
        HALF_OPEN → OPEN: If any failure occurs during testing

    Attributes:
        config: Circuit breaker configuration
        state: Current circuit state (CLOSED, OPEN, HALF_OPEN)
        failures: List of failure timestamps in current window
        opened_at: Timestamp when circuit opened (None if CLOSED)
        half_open_tries: Number of successful trades in HALF_OPEN state

    Example:
        >>> from src.v6.risk import CircuitBreakerConfig, TradingCircuitBreaker
        >>>
        >>> # Create circuit breaker with default config
        >>> config = CircuitBreakerConfig(
        ...     failure_threshold=5,
        ...     failure_window_secs=60
        ... )
        >>> cb = TradingCircuitBreaker(config)
        >>>
        >>> # Check if trading is allowed
        >>> allowed, reason = cb.is_trading_allowed()
        >>> if not allowed:
        ...     print(f"Trading blocked: {reason}")
        >>>
        >>> # Record order failure
        >>> cb.record_failure()
        >>>
        >>> # Record order success
        >>> cb.record_success()
        >>>
        >>> # Get current state for monitoring
        >>> state = cb.get_state()
        >>> print(f"Circuit state: {state['state']}")
        >>>
        >>> # Manually reset (admin intervention)
        >>> cb.reset()
    """

    def __init__(self, config: CircuitBreakerConfig):
        """
        Initialize trading circuit breaker.

        Args:
            config: Circuit breaker configuration
        """
        self.config = config
        self.state = CircuitState.CLOSED
        self.failures: list[datetime] = []
        self.opened_at: datetime | None = None
        self.half_open_tries = 0

        logger.info(
            f"TradingCircuitBreaker initialized: "
            f"threshold={config.failure_threshold}, "
            f"window={config.failure_window_secs}s"
        )

    def record_failure(self) -> CircuitState:
        """
        Record a failure and update circuit state if needed.

        Adds the current timestamp to the failures list and checks if the
        failure threshold has been exceeded. If so, transitions to OPEN state.

        Returns:
            Current circuit state after recording failure

        Example:
            >>> state = cb.record_failure()
            >>> if state == CircuitState.OPEN:
            ...     print("Circuit breaker opened due to failures")
        """
        now = datetime.now()

        # Add current failure
        self.failures.append(now)

        # Clean old failures outside the time window
        window_start = now - timedelta(seconds=self.config.failure_window_secs)
        self.failures = [f for f in self.failures if f > window_start]

        # Check if threshold exceeded
        if len(self.failures) >= self.config.failure_threshold:
            if self.state != CircuitState.OPEN:
                # Transition to OPEN
                self.state = CircuitState.OPEN
                self.opened_at = now
                logger.warning(
                    f"Circuit breaker OPENED: {len(self.failures)} failures "
                    f"within {self.config.failure_window_secs}s window"
                )
        else:
            logger.debug(
                f"Circuit breaker: {len(self.failures)}/{self.config.failure_threshold} "
                f"failures in {self.config.failure_window_secs}s window"
            )

        return self.state

    def record_success(self) -> CircuitState:
        """
        Record a success and update circuit state if in HALF_OPEN.

        If the circuit is in HALF_OPEN state, increments the success counter.
        If the success threshold is reached, transitions back to CLOSED state.

        Returns:
            Current circuit state after recording success

        Example:
            >>> state = cb.record_success()
            >>> if state == CircuitState.CLOSED:
            ...     print("Circuit breaker closed: system recovered")
        """
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_tries += 1

            logger.debug(
                f"Circuit breaker HALF_OPEN: {self.half_open_tries}/"
                f"{self.config.half_open_max_tries} successful trades"
            )

            # Check if we've reached the success threshold
            if self.half_open_tries >= self.config.half_open_max_tries:
                # Transition to CLOSED
                self.state = CircuitState.CLOSED
                self.failures = []
                self.opened_at = None
                self.half_open_tries = 0

                logger.info(
                    "Circuit breaker CLOSED: System recovered after "
                    f"{self.config.half_open_max_tries} successful trades"
                )
        elif self.state == CircuitState.OPEN:
            # Success in OPEN state is unexpected but can happen
            # (e.g., forced trade during open state)
            logger.debug("Circuit breaker: Success recorded while OPEN (state unchanged)")

        return self.state

    def is_trading_allowed(self) -> tuple[bool, str | None]:
        """
        Check if trading is currently allowed.

        Returns:
            Tuple of (allowed, reason) where:
                - allowed: True if trading is allowed, False if blocked
                - reason: Human-readable reason if blocked, None if allowed

        Example:
            >>> allowed, reason = cb.is_trading_allowed()
            >>> if not allowed:
            ...     print(f"Trading blocked: {reason}")
            >>> else:
            ...     print("Trading allowed")
        """
        if self.state == CircuitState.CLOSED:
            # Normal operation
            return True, None

        elif self.state == CircuitState.OPEN:
            # Check if ready to transition to HALF_OPEN
            if self.opened_at is not None:
                time_in_open = (datetime.now() - self.opened_at).total_seconds()

                if time_in_open >= self.config.open_timeout_secs:
                    # Transition to HALF_OPEN for recovery testing
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_tries = 0

                    logger.info(
                        f"Circuit breaker HALF_OPEN: Testing recovery after "
                        f"{time_in_open:.0f}s in OPEN state"
                    )

                    return True, "HALF_OPEN: Testing recovery"

            # Still in OPEN state, block trading
            return (
                False,
                f"OPEN: {len(self.failures)} failures in "
                f"{self.config.failure_window_secs}s window",
            )

        elif self.state == CircuitState.HALF_OPEN:
            # Testing recovery, allow trading with monitoring
            return True, "HALF_OPEN: Testing recovery"

        # Should not reach here
        return False, "UNKNOWN_STATE"

    def get_state(self) -> dict:
        """
        Get current circuit state for monitoring.

        Returns:
            Dictionary with current state information:
                - state: Circuit state name (CLOSED, OPEN, HALF_OPEN)
                - failures: Number of failures in current window
                - opened_at: Timestamp when circuit opened (None if CLOSED)
                - half_open_tries: Number of successful trades in HALF_OPEN

        Example:
            >>> state = cb.get_state()
            >>> print(f"State: {state['state']}, Failures: {state['failures']}")
        """
        return {
            "state": self.state.name,
            "failures": len(self.failures),
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "half_open_tries": self.half_open_tries,
        }

    def reset(self) -> None:
        """
        Manually reset circuit to CLOSED state.

        Used for admin intervention when the system has been manually verified
        to be healthy. Resets all state tracking and allows trading immediately.

        Example:
            >>> # Admin has verified system is healthy
            >>> cb.reset()
            >>> logger.info("Circuit breaker manually reset")
        """
        old_state = self.state
        self.state = CircuitState.CLOSED
        self.failures = []
        self.opened_at = None
        self.half_open_tries = 0

        logger.info(
            f"Circuit breaker manually reset: {old_state.name} -> CLOSED "
            f"(admin intervention)"
        )
