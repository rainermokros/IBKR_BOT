"""
Position-Level Trailing Stop Implementation

This module provides trailing stop functionality for individual options positions
with whipsaw protection to avoid premature exits in choppy markets.

Key features:
- Trailing based on OPTIONS PREMIUM (not underlying price)
- Whipsaw protection with activation threshold, trailing distance, and minimum move
- TrailingStopAction enum (HOLD, ACTIVATE, UPDATE, TRIGGER)
- TrailingStopManager for multi-position management

Research-backed defaults:
- Activation threshold: 2% (premium must move 2% before stop activates)
- Trailing distance: 1.5% (stop trails 1.5% from peak premium)
- Minimum move: 0.5% (stop only updates if moved at least 0.5%)

Usage:
    >>> from v6.risk import TrailingStop, TrailingStopConfig
    >>>
    >>> # Create trailing stop
    >>> stop = TrailingStop(entry_premium=100.0)
    >>>
    >>> # Update with current premium
    >>> new_stop, action = stop.update(103.0)
    >>> if action == TrailingStopAction.ACTIVATE:
    ...     print(f"Stop activated at {new_stop}")
    >>>
    >>> # Update with new premium
    >>> new_stop, action = stop.update(105.0)
    >>> if action == TrailingStopAction.UPDATE:
    ...     print(f"Stop updated to {new_stop}")
"""

from dataclasses import dataclass, field
from enum import Enum, auto

from loguru import logger

logger = logger.bind(component="TrailingStop")


class TrailingStopAction(Enum):
    """
    Trailing stop action enum.

    Represents the action taken during a trailing stop update.
    """

    HOLD = auto()  # No change
    ACTIVATE = auto()  # Stop activated (first time)
    UPDATE = auto()  # Stop price updated
    TRIGGER = auto()  # Stop triggered (exit position)


@dataclass(slots=True)
class TrailingStopConfig:
    """
    Trailing stop configuration.

    Defines the parameters for trailing stop behavior.

    Attributes:
        activation_pct: Percentage move before activating trailing stop (default: 2.0)
        trailing_pct: Percentage to trail from peak premium (default: 1.5)
        min_move_pct: Minimum percentage move to update stop (default: 0.5)

    Example:
        >>> config = TrailingStopConfig(
        ...     activation_pct=2.0,
        ...     trailing_pct=1.5,
        ...     min_move_pct=0.5
        ... )
    """

    activation_pct: float = 2.0
    trailing_pct: float = 1.5
    min_move_pct: float = 0.5

    def __post_init__(self):
        """Validate trailing stop configuration."""
        if self.activation_pct <= 0:
            raise ValueError(f"activation_pct must be positive, got {self.activation_pct}")

        if self.trailing_pct <= 0:
            raise ValueError(f"trailing_pct must be positive, got {self.trailing_pct}")

        if self.min_move_pct <= 0:
            raise ValueError(f"min_move_pct must be positive, got {self.min_move_pct}")

        if self.trailing_pct >= self.activation_pct:
            raise ValueError(
                f"trailing_pct ({self.trailing_pct}) must be less than "
                f"activation_pct ({self.activation_pct})"
            )


@dataclass(slots=True)
class TrailingStop:
    """
    Position-level trailing stop with whipsaw protection.

    Tracks a trailing stop for a single options position based on OPTIONS PREMIUM
    (not underlying price). This is critical for options trading where premium
    can fluctuate independently of the underlying.

    **Whipsaw Protection:**
    1. Activation threshold: Stop only activates after premium moves X% from entry
    2. Trailing distance: Stop trails Y% below peak premium
    3. Minimum move: Stop only updates if moved at least Z% (prevents excessive updates)

    **Lifecycle:**
    1. Entry: Stop is inactive, no stop price set
    2. Activate: Premium moves activation_pct above entry → stop activates
    3. Update: Premium reaches new peak → stop updates if min_move_pct threshold met
    4. Trigger: Premium drops to/below stop price → stop triggers (exit position)

    Attributes:
        entry_premium: Entry price (premium received/paid for position)
        highest_premium: Highest premium observed (peak)
        stop_premium: Current stop level (None = not activated)
        is_active: Whether trailing stop is activated
        config: Trailing stop configuration

    Example:
        >>> stop = TrailingStop(entry_premium=100.0)
        >>>
        >>> # Premium moves to 103 (3% gain, above 2% activation)
        >>> new_stop, action = stop.update(103.0)
        >>> assert action == TrailingStopAction.ACTIVATE
        >>> assert new_stop == 101.455  # 103 * (1 - 1.5/100)
        >>>
        >>> # Premium rises to 105 (new peak)
        >>> new_stop, action = stop.update(105.0)
        >>> assert action == TrailingStopAction.UPDATE
        >>> assert new_stop == 103.425  # 105 * (1 - 1.5/100)
        >>>
        >>> # Premium drops to 103.5 (below stop)
        >>> new_stop, action = stop.update(103.5)
        >>> assert action == TrailingStopAction.TRIGGER
    """

    entry_premium: float
    highest_premium: float | None = None
    stop_premium: float | None = None
    is_active: bool = False
    config: TrailingStopConfig = field(default_factory=TrailingStopConfig)

    def __post_init__(self):
        """Validate trailing stop initialization."""
        if self.entry_premium <= 0:
            raise ValueError(f"entry_premium must be positive, got {self.entry_premium}")

        # Initialize highest_premium to entry_premium if not set
        if self.highest_premium is None or self.highest_premium <= 0:
            self.highest_premium = self.entry_premium

    def update(
        self, current_premium: float
    ) -> tuple[float | None, TrailingStopAction]:
        """
        Update trailing stop based on current premium.

        This is the main method called during position monitoring. It updates
        the trailing stop based on the current mark-to-market premium and
        returns the action taken.

        **Update Logic:**
        1. Update peak premium if current is higher
        2. Check if stop should activate (if not already active)
        3. Check if stop should update (if active and moved enough)
        4. Check if stop triggered (premium at/below stop)
        5. Default to HOLD if no action needed

        Args:
            current_premium: Current mark-to-market premium for the position

        Returns:
            Tuple of (new_stop_premium, action)
            - new_stop_premium: Updated stop level (None if not activated)
            - action: TrailingStopAction (HOLD, ACTIVATE, UPDATE, TRIGGER)

        Example:
            >>> stop = TrailingStop(entry_premium=100.0)
            >>>
            >>> # First update: Premium at 102 (not enough to activate)
            >>> new_stop, action = stop.update(102.0)
            >>> assert action == TrailingStopAction.HOLD
            >>> assert new_stop is None
            >>>
            >>> # Second update: Premium at 103 (activates stop)
            >>> new_stop, action = stop.update(103.0)
            >>> assert action == TrailingStopAction.ACTIVATE
            >>> assert new_stop == pytest.approx(101.455, rel=0.001)
        """
        # Validate input
        if current_premium <= 0:
            raise ValueError(f"current_premium must be positive, got {current_premium}")

        # Update peak premium
        if current_premium > self.highest_premium:
            self.highest_premium = current_premium

        # Check activation threshold (if not active)
        if not self.is_active:
            move_pct = (
                (self.highest_premium - self.entry_premium) / self.entry_premium * 100
            )

            if move_pct >= self.config.activation_pct:
                # Activate trailing stop
                self.is_active = True
                self.stop_premium = self.highest_premium * (
                    1 - self.config.trailing_pct / 100
                )

                logger.info(
                    f"Trailing stop ACTIVATED: entry={self.entry_premium:.2f}, "
                    f"peak={self.highest_premium:.2f}, "
                    f"stop={self.stop_premium:.2f} "
                    f"(moved {move_pct:.2f}% >= {self.config.activation_pct}%)"
                )

                return self.stop_premium, TrailingStopAction.ACTIVATE

            # Not enough movement to activate
            return None, TrailingStopAction.HOLD

        # Stop is active, check if triggered
        if current_premium <= self.stop_premium:
            logger.warning(
                f"Trailing stop TRIGGERED: current={current_premium:.2f}, "
                f"stop={self.stop_premium:.2f}, "
                f"peak={self.highest_premium:.2f}"
            )

            return self.stop_premium, TrailingStopAction.TRIGGER

        # Check if stop should update (premium moved enough)
        new_stop = self.highest_premium * (1 - self.config.trailing_pct / 100)

        if self.stop_premium:
            move_from_current = (
                abs(new_stop - self.stop_premium) / self.stop_premium * 100
            )
        else:
            move_from_current = 0.0

        if move_from_current >= self.config.min_move_pct:
            old_stop = self.stop_premium
            self.stop_premium = new_stop

            logger.debug(
                f"Trailing stop UPDATED: {old_stop:.2f} → {self.stop_premium:.2f}, "
                f"peak={self.highest_premium:.2f} "
                f"(moved {move_from_current:.2f}% >= {self.config.min_move_pct}%)"
            )

            return self.stop_premium, TrailingStopAction.UPDATE

        # No action needed
        return self.stop_premium, TrailingStopAction.HOLD

    def reset(self) -> None:
        """
        Reset trailing stop to inactive state.

        Used for manual override or when re-enabling trailing stop after
        it was disabled.

        Example:
            >>> stop = TrailingStop(entry_premium=100.0)
            >>> _, _ = stop.update(103.0)  # Activate
            >>> assert stop.is_active
            >>>
            >>> stop.reset()  # Reset to inactive
            >>> assert not stop.is_active
            >>> assert stop.stop_premium is None
        """
        self.is_active = False
        self.stop_premium = None
        self.highest_premium = self.entry_premium

        logger.debug("Trailing stop RESET to inactive state")

    def __repr__(self) -> str:
        """Return string representation of trailing stop."""
        status = "ACTIVE" if self.is_active else "INACTIVE"
        stop_str = f"{self.stop_premium:.2f}" if self.stop_premium else "None"
        return (
            f"TrailingStop(entry={self.entry_premium:.2f}, "
            f"peak={self.highest_premium:.2f}, "
            f"stop={stop_str}, "
            f"status={status})"
        )


class TrailingStopManager:
    """
    Manager for multiple trailing stops across positions.

    Manages trailing stops for all open positions in the portfolio.
    Provides methods to add, update, remove, and query trailing stops.

    **Usage:**
    1. Add trailing stop for new position: add_trailing_stop()
    2. Update all stops with current premiums: update_stops()
    3. Check for triggered stops and create CLOSE decisions
    4. Remove stop when position closed: remove_stop()

    Attributes:
        stops: Dictionary mapping execution_id to TrailingStop
        config: Default configuration for new trailing stops

    Example:
        >>> manager = TrailingStopManager()
        >>>
        >>> # Add trailing stop for position
        >>> manager.add_trailing_stop(
        ...     execution_id="abc123",
        ...     entry_premium=100.0
        ... )
        >>>
        >>> # Update all stops with current premiums
        >>> results = await manager.update_stops({
        ...     "abc123": 103.0,
        ...     "def456": 98.0
        ... })
        >>>
        >>> # Check for triggered stops
        >>> for exec_id, (stop_price, action) in results.items():
        ...     if action == TrailingStopAction.TRIGGER:
        ...         print(f"Stop triggered for {exec_id}: {stop_price}")
    """

    def __init__(self, default_config: TrailingStopConfig | None = None):
        """
        Initialize trailing stop manager.

        Args:
            default_config: Default configuration for new trailing stops
                           (uses TrailingStopConfig() defaults if None)
        """
        self.stops: dict[str, TrailingStop] = {}
        self.config = default_config or TrailingStopConfig()
        self.logger = logger

    def add_trailing_stop(
        self,
        execution_id: str,
        entry_premium: float,
        config: TrailingStopConfig | None = None,
    ) -> TrailingStop:
        """
        Add trailing stop for a position.

        Creates a new TrailingStop instance and stores it in the manager.

        Args:
            execution_id: Strategy execution ID
            entry_premium: Entry premium for the position
            config: Optional configuration (uses default if None)

        Returns:
            TrailingStop instance

        Raises:
            ValueError: If execution_id already has a trailing stop

        Example:
            >>> manager = TrailingStopManager()
            >>> stop = manager.add_trailing_stop(
            ...     execution_id="abc123",
            ...     entry_premium=100.0
            ... )
            >>> assert stop.entry_premium == 100.0
        """
        if execution_id in self.stops:
            raise ValueError(f"Trailing stop already exists for {execution_id}")

        stop_config = config or self.config
        stop = TrailingStop(
            entry_premium=entry_premium,
            highest_premium=entry_premium,
            stop_premium=None,
            is_active=False,
            config=stop_config,
        )

        self.stops[execution_id] = stop

        self.logger.info(
            f"Added trailing stop for {execution_id[:8]}...: "
            f"entry={entry_premium:.2f}"
        )

        return stop

    async def update_stops(
        self, current_premiums: dict[str, float]
    ) -> dict[str, tuple[float | None, TrailingStopAction]]:
        """
        Update all trailing stops based on current premiums.

        Called during position monitoring to update all trailing stops
        with current mark-to-market premiums.

        Args:
            current_premiums: Dictionary mapping execution_id to current premium

        Returns:
            Dictionary mapping execution_id to (stop_premium, action)

        Example:
            >>> manager = TrailingStopManager()
            >>> manager.add_trailing_stop("abc123", 100.0)
            >>>
            >>> # Update with current premiums
            >>> results = await manager.update_stops({
            ...     "abc123": 103.0,
            ...     "def456": 98.0  # Ignored (no stop)
            ... })
            >>>
            >>> # Check action for abc123
            >>> stop_price, action = results["abc123"]
            >>> if action == TrailingStopAction.ACTIVATE:
            ...     print(f"Stop activated at {stop_price}")
        """
        results = {}

        for execution_id, stop in self.stops.items():
            current_premium = current_premiums.get(execution_id)

            if current_premium is None:
                # No premium data for this position, skip
                continue

            try:
                new_stop, action = stop.update(current_premium)
                results[execution_id] = (new_stop, action)

                if action == TrailingStopAction.TRIGGER:
                    self.logger.warning(
                        f"Trailing stop TRIGGERED for {execution_id[:8]}...: "
                        f"stop={new_stop:.2f}"
                    )
                elif action == TrailingStopAction.ACTIVATE:
                    self.logger.info(
                        f"Trailing stop ACTIVATED for {execution_id[:8]}...: "
                        f"stop={new_stop:.2f}"
                    )
                elif action == TrailingStopAction.UPDATE:
                    self.logger.debug(
                        f"Trailing stop UPDATED for {execution_id[:8]}...: "
                        f"stop={new_stop:.2f}"
                    )

            except Exception as e:
                self.logger.error(
                    f"Failed to update trailing stop for {execution_id[:8]}...: {e}"
                )
                # Continue with next stop

        return results

    def get_stop(self, execution_id: str) -> TrailingStop | None:
        """
        Get trailing stop for a position.

        Args:
            execution_id: Strategy execution ID

        Returns:
            TrailingStop instance or None if not found

        Example:
            >>> stop = manager.get_stop("abc123")
            >>> if stop:
            ...     print(f"Stop at {stop.stop_premium}, active={stop.is_active}")
        """
        return self.stops.get(execution_id)

    def remove_stop(self, execution_id: str) -> None:
        """
        Remove trailing stop for a position.

        Called when position is closed to clean up trailing stop.

        Args:
            execution_id: Strategy execution ID

        Example:
            >>> manager.remove_stop("abc123")
            >>> assert manager.get_stop("abc123") is None
        """
        if execution_id in self.stops:
            del self.stops[execution_id]
            self.logger.debug(
                f"Removed trailing stop for {execution_id[:8]}..."
            )

    def get_all_stops(self) -> dict[str, TrailingStop]:
        """
        Get all trailing stops.

        Returns:
            Dictionary mapping execution_id to TrailingStop

        Example:
            >>> all_stops = manager.get_all_stops()
            >>> for exec_id, stop in all_stops.items():
            ...     print(f"{exec_id}: {stop}")
        """
        return self.stops.copy()

    def reset_stop(self, execution_id: str) -> None:
        """
        Reset trailing stop to inactive state.

        Used for manual override or when re-enabling trailing stop.

        Args:
            execution_id: Strategy execution ID

        Example:
            >>> manager.reset_stop("abc123")
            >>> stop = manager.get_stop("abc123")
            >>> assert not stop.is_active
        """
        stop = self.stops.get(execution_id)
        if stop:
            stop.reset()
            self.logger.debug(f"Reset trailing stop for {execution_id[:8]}...")

    def __repr__(self) -> str:
        """Return string representation of manager."""
        active_count = sum(1 for s in self.stops.values() if s.is_active)
        return (
            f"TrailingStopManager(stops={len(self.stops)}, "
            f"active={active_count})"
        )
