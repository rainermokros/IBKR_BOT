"""
Tests for Trailing Stop Module

Tests the TrailingStop, TrailingStopConfig, and TrailingStopManager classes.
"""

import pytest

from src.v6.risk.trailing_stop import (
    TrailingStop,
    TrailingStopAction,
    TrailingStopConfig,
    TrailingStopManager,
)


class TestTrailingStopConfig:
    """Tests for TrailingStopConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = TrailingStopConfig()

        assert config.activation_pct == 2.0
        assert config.trailing_pct == 1.5
        assert config.min_move_pct == 0.5

    def test_custom_config(self):
        """Test custom configuration values."""
        config = TrailingStopConfig(
            activation_pct=3.0, trailing_pct=2.0, min_move_pct=0.75
        )

        assert config.activation_pct == 3.0
        assert config.trailing_pct == 2.0
        assert config.min_move_pct == 0.75

    def test_invalid_activation_pct(self):
        """Test that activation_pct must be positive."""
        with pytest.raises(ValueError, match="activation_pct must be positive"):
            TrailingStopConfig(activation_pct=0.0)

        with pytest.raises(ValueError, match="activation_pct must be positive"):
            TrailingStopConfig(activation_pct=-1.0)

    def test_invalid_trailing_pct(self):
        """Test that trailing_pct must be positive."""
        with pytest.raises(ValueError, match="trailing_pct must be positive"):
            TrailingStopConfig(trailing_pct=0.0)

        with pytest.raises(ValueError, match="trailing_pct must be positive"):
            TrailingStopConfig(trailing_pct=-1.0)

    def test_invalid_min_move_pct(self):
        """Test that min_move_pct must be positive."""
        with pytest.raises(ValueError, match="min_move_pct must be positive"):
            TrailingStopConfig(min_move_pct=0.0)

        with pytest.raises(ValueError, match="min_move_pct must be positive"):
            TrailingStopConfig(min_move_pct=-1.0)

    def test_trailing_pct_greater_than_activation(self):
        """Test that trailing_pct must be less than activation_pct."""
        with pytest.raises(ValueError, match="trailing_pct.*must be less than"):
            TrailingStopConfig(activation_pct=1.5, trailing_pct=2.0)

        with pytest.raises(ValueError, match="trailing_pct.*must be less than"):
            TrailingStopConfig(activation_pct=2.0, trailing_pct=2.0)


class TestTrailingStop:
    """Tests for TrailingStop class."""

    def test_initialization(self):
        """Test trailing stop initialization."""
        stop = TrailingStop(entry_premium=100.0)

        assert stop.entry_premium == 100.0
        assert stop.highest_premium == 100.0
        assert stop.stop_premium is None
        assert stop.is_active is False
        assert isinstance(stop.config, TrailingStopConfig)

    def test_custom_config(self):
        """Test trailing stop with custom configuration."""
        config = TrailingStopConfig(activation_pct=3.0, trailing_pct=2.0)
        stop = TrailingStop(entry_premium=100.0, config=config)

        assert stop.config.activation_pct == 3.0
        assert stop.config.trailing_pct == 2.0

    def test_invalid_entry_premium(self):
        """Test that entry_premium must be positive."""
        with pytest.raises(ValueError, match="entry_premium must be positive"):
            TrailingStop(entry_premium=0.0)

        with pytest.raises(ValueError, match="entry_premium must be positive"):
            TrailingStop(entry_premium=-100.0)

    def test_update_before_activation(self):
        """Test update before activation threshold is reached."""
        stop = TrailingStop(entry_premium=100.0)

        # Premium moves to 101 (1% gain, below 2% activation)
        new_stop, action = stop.update(101.0)

        assert action == TrailingStopAction.HOLD
        assert new_stop is None
        assert stop.is_active is False
        assert stop.stop_premium is None

    def test_update_activation(self):
        """Test trailing stop activation."""
        stop = TrailingStop(entry_premium=100.0)

        # Premium moves to 103 (3% gain, above 2% activation)
        new_stop, action = stop.update(103.0)

        assert action == TrailingStopAction.ACTIVATE
        assert new_stop == pytest.approx(101.455, rel=0.001)  # 103 * (1 - 1.5/100)
        assert stop.is_active is True
        assert stop.stop_premium == pytest.approx(101.455, rel=0.001)
        assert stop.highest_premium == 103.0

    def test_update_after_activation_no_new_peak(self):
        """Test update after activation but no new peak."""
        stop = TrailingStop(entry_premium=100.0)

        # Activate
        _, _ = stop.update(103.0)

        # Premium stays at 102 (no new peak)
        new_stop, action = stop.update(102.0)

        assert action == TrailingStopAction.HOLD
        assert new_stop == pytest.approx(101.455, rel=0.001)
        assert stop.highest_premium == 103.0  # Peak unchanged

    def test_update_new_peak(self):
        """Test update with new peak premium."""
        stop = TrailingStop(entry_premium=100.0)

        # Activate
        _, _ = stop.update(103.0)

        # Premium rises to 105 (new peak)
        new_stop, action = stop.update(105.0)

        assert action == TrailingStopAction.UPDATE
        assert new_stop == pytest.approx(103.425, rel=0.001)  # 105 * (1 - 1.5/100)
        assert stop.highest_premium == 105.0
        assert stop.stop_premium == pytest.approx(103.425, rel=0.001)

    def test_update_minimum_move_threshold(self):
        """Test that stop only updates if minimum move threshold is met."""
        stop = TrailingStop(entry_premium=100.0)

        # Activate
        _, _ = stop.update(103.0)

        # Premium rises to 103.5 (new peak but small move)
        new_stop, action = stop.update(103.5)

        # Calculate expected move percentage
        # Old stop: 101.455
        # New stop: 103.5 * (1 - 1.5/100) = 101.9475
        # Move: (101.9475 - 101.455) / 101.455 * 100 = 0.485%
        # This is less than min_move_pct (0.5%), so should HOLD

        assert action == TrailingStopAction.HOLD
        assert stop.stop_premium == pytest.approx(101.455, rel=0.001)

    def test_update_trigger(self):
        """Test trailing stop trigger."""
        stop = TrailingStop(entry_premium=100.0)

        # Activate
        _, _ = stop.update(103.0)

        # Premium drops to 101 (below stop at 101.455)
        new_stop, action = stop.update(101.0)

        assert action == TrailingStopAction.TRIGGER
        assert new_stop == pytest.approx(101.455, rel=0.001)
        assert stop.stop_premium == pytest.approx(101.455, rel=0.001)

    def test_update_exactly_at_stop(self):
        """Test update exactly at stop price (should trigger)."""
        stop = TrailingStop(entry_premium=100.0)

        # Activate
        _, _ = stop.update(103.0)
        stop_price = stop.stop_premium

        # Premium drops exactly to stop price
        new_stop, action = stop.update(stop_price)

        assert action == TrailingStopAction.TRIGGER
        assert new_stop == stop_price

    def test_reset(self):
        """Test trailing stop reset."""
        stop = TrailingStop(entry_premium=100.0)

        # Activate
        _, _ = stop.update(103.0)
        assert stop.is_active is True

        # Reset
        stop.reset()

        assert stop.is_active is False
        assert stop.stop_premium is None
        assert stop.highest_premium == 100.0

    def test_reactivate_after_reset(self):
        """Test that stop can be reactivated after reset."""
        stop = TrailingStop(entry_premium=100.0)

        # Activate
        _, _ = stop.update(103.0)
        assert stop.is_active is True

        # Reset
        stop.reset()
        assert stop.is_active is False

        # Reactivate with higher premium
        new_stop, action = stop.update(105.0)

        assert action == TrailingStopAction.ACTIVATE
        assert stop.is_active is True
        assert new_stop == pytest.approx(103.425, rel=0.001)

    def test_invalid_current_premium(self):
        """Test that current_premium must be positive."""
        stop = TrailingStop(entry_premium=100.0)

        with pytest.raises(ValueError, match="current_premium must be positive"):
            stop.update(0.0)

        with pytest.raises(ValueError, match="current_premium must be positive"):
            stop.update(-100.0)

    def test_repr(self):
        """Test string representation."""
        stop = TrailingStop(entry_premium=100.0)

        repr_str = repr(stop)
        assert "TrailingStop" in repr_str
        assert "100.00" in repr_str
        assert "INACTIVE" in repr_str

        # Activate
        _, _ = stop.update(103.0)

        repr_str = repr(stop)
        assert "ACTIVE" in repr_str


class TestTrailingStopManager:
    """Tests for TrailingStopManager class."""

    def test_initialization(self):
        """Test manager initialization."""
        manager = TrailingStopManager()

        assert manager.stops == {}
        assert isinstance(manager.config, TrailingStopConfig)

    def test_initialization_with_custom_config(self):
        """Test manager with custom default configuration."""
        config = TrailingStopConfig(activation_pct=3.0, trailing_pct=2.0)
        manager = TrailingStopManager(default_config=config)

        assert manager.config.activation_pct == 3.0
        assert manager.config.trailing_pct == 2.0

    def test_add_trailing_stop(self):
        """Test adding trailing stop for position."""
        manager = TrailingStopManager()

        stop = manager.add_trailing_stop(
            execution_id="abc123", entry_premium=100.0
        )

        assert isinstance(stop, TrailingStop)
        assert stop.entry_premium == 100.0
        assert "abc123" in manager.stops
        assert manager.stops["abc123"] is stop

    def test_add_trailing_stop_with_custom_config(self):
        """Test adding trailing stop with custom configuration."""
        manager = TrailingStopManager()

        config = TrailingStopConfig(activation_pct=3.0, trailing_pct=2.0)
        stop = manager.add_trailing_stop(
            execution_id="abc123", entry_premium=100.0, config=config
        )

        assert stop.config.activation_pct == 3.0
        assert stop.config.trailing_pct == 2.0

    def test_add_duplicate_trailing_stop(self):
        """Test that duplicate trailing stop raises error."""
        manager = TrailingStopManager()

        manager.add_trailing_stop(execution_id="abc123", entry_premium=100.0)

        with pytest.raises(ValueError, match="already exists"):
            manager.add_trailing_stop(execution_id="abc123", entry_premium=100.0)

    def test_get_stop(self):
        """Test getting trailing stop for position."""
        manager = TrailingStopManager()

        stop = manager.add_trailing_stop(
            execution_id="abc123", entry_premium=100.0
        )

        retrieved = manager.get_stop("abc123")

        assert retrieved is stop

    def test_get_nonexistent_stop(self):
        """Test getting nonexistent stop returns None."""
        manager = TrailingStopManager()

        retrieved = manager.get_stop("nonexistent")

        assert retrieved is None

    def test_remove_stop(self):
        """Test removing trailing stop."""
        manager = TrailingStopManager()

        manager.add_trailing_stop(execution_id="abc123", entry_premium=100.0)
        assert "abc123" in manager.stops

        manager.remove_stop("abc123")

        assert "abc123" not in manager.stops
        assert manager.get_stop("abc123") is None

    def test_remove_nonexistent_stop(self):
        """Test removing nonexistent stop doesn't raise error."""
        manager = TrailingStopManager()

        # Should not raise
        manager.remove_stop("nonexistent")

    @pytest.mark.asyncio
    async def test_update_stops_empty(self):
        """Test updating stops when no stops exist."""
        manager = TrailingStopManager()

        results = await manager.update_stops({})

        assert results == {}

    @pytest.mark.asyncio
    async def test_update_stops_single_position(self):
        """Test updating stop for single position."""
        manager = TrailingStopManager()
        manager.add_trailing_stop(execution_id="abc123", entry_premium=100.0)

        # Update with premium that activates stop
        results = await manager.update_stops({"abc123": 103.0})

        assert "abc123" in results
        stop_price, action = results["abc123"]

        assert action == TrailingStopAction.ACTIVATE
        assert stop_price == pytest.approx(101.455, rel=0.001)

    @pytest.mark.asyncio
    async def test_update_stops_multiple_positions(self):
        """Test updating stops for multiple positions."""
        manager = TrailingStopManager()
        manager.add_trailing_stop(execution_id="abc123", entry_premium=100.0)
        manager.add_trailing_stop(execution_id="def456", entry_premium=200.0)

        # Update premiums
        results = await manager.update_stops({
            "abc123": 103.0,  # Activates
            "def456": 206.0,  # Activates
        })

        assert len(results) == 2
        assert results["abc123"][1] == TrailingStopAction.ACTIVATE
        assert results["def456"][1] == TrailingStopAction.ACTIVATE

    @pytest.mark.asyncio
    async def test_update_stops_missing_premium(self):
        """Test that positions without premium data are skipped."""
        manager = TrailingStopManager()
        manager.add_trailing_stop(execution_id="abc123", entry_premium=100.0)
        manager.add_trailing_stop(execution_id="def456", entry_premium=200.0)

        # Only provide premium for abc123
        results = await manager.update_stops({"abc123": 103.0})

        assert len(results) == 1
        assert "abc123" in results
        assert "def456" not in results

    @pytest.mark.asyncio
    async def test_update_stops_trigger(self):
        """Test updating stop that triggers."""
        manager = TrailingStopManager()
        manager.add_trailing_stop(execution_id="abc123", entry_premium=100.0)

        # Activate
        await manager.update_stops({"abc123": 103.0})

        # Trigger
        results = await manager.update_stops({"abc123": 101.0})

        assert results["abc123"][1] == TrailingStopAction.TRIGGER

    def test_get_all_stops(self):
        """Test getting all stops."""
        manager = TrailingStopManager()
        manager.add_trailing_stop(execution_id="abc123", entry_premium=100.0)
        manager.add_trailing_stop(execution_id="def456", entry_premium=200.0)

        all_stops = manager.get_all_stops()

        assert len(all_stops) == 2
        assert "abc123" in all_stops
        assert "def456" in all_stops

    def test_reset_stop(self):
        """Test resetting trailing stop."""
        manager = TrailingStopManager()
        manager.add_trailing_stop(execution_id="abc123", entry_premium=100.0)

        # Activate
        stop = manager.get_stop("abc123")
        _, _ = stop.update(103.0)
        assert stop.is_active is True

        # Reset
        manager.reset_stop("abc123")

        stop = manager.get_stop("abc123")
        assert stop.is_active is False
        assert stop.stop_premium is None

    def test_reset_nonexistent_stop(self):
        """Test resetting nonexistent stop doesn't raise error."""
        manager = TrailingStopManager()

        # Should not raise
        manager.reset_stop("nonexistent")

    def test_repr(self):
        """Test string representation."""
        manager = TrailingStopManager()
        manager.add_trailing_stop(execution_id="abc123", entry_premium=100.0)

        # Activate
        stop = manager.get_stop("abc123")
        _, _ = stop.update(103.0)

        repr_str = repr(manager)
        assert "TrailingStopManager" in repr_str
        assert "stops=1" in repr_str
        assert "active=1" in repr_str


class TestTrailingStopLifecycle:
    """Integration tests for trailing stop lifecycle."""

    def test_full_lifecycle(self):
        """Test complete trailing stop lifecycle: enable -> activate -> update -> trigger."""
        stop = TrailingStop(entry_premium=100.0)

        # 1. Hold before activation
        new_stop, action = stop.update(101.0)
        assert action == TrailingStopAction.HOLD
        assert new_stop is None

        # 2. Activate
        new_stop, action = stop.update(103.0)
        assert action == TrailingStopAction.ACTIVATE
        assert new_stop == pytest.approx(101.455, rel=0.001)

        # 3. Update with new peak
        new_stop, action = stop.update(105.0)
        assert action == TrailingStopAction.UPDATE
        assert new_stop == pytest.approx(103.425, rel=0.001)

        # 4. Hold while premium stays high
        new_stop, action = stop.update(104.0)
        assert action == TrailingStopAction.HOLD
        assert new_stop == pytest.approx(103.425, rel=0.001)

        # 5. Trigger
        new_stop, action = stop.update(103.0)
        assert action == TrailingStopAction.TRIGGER
        assert new_stop == pytest.approx(103.425, rel=0.001)

    @pytest.mark.asyncio
    async def test_manager_full_lifecycle(self):
        """Test full lifecycle with TrailingStopManager."""
        manager = TrailingStopManager()

        # Enable
        manager.add_trailing_stop(execution_id="abc123", entry_premium=100.0)

        # Activate
        results = await manager.update_stops({"abc123": 103.0})
        assert results["abc123"][1] == TrailingStopAction.ACTIVATE

        # Update
        results = await manager.update_stops({"abc123": 105.0})
        assert results["abc123"][1] == TrailingStopAction.UPDATE

        # Trigger
        results = await manager.update_stops({"abc123": 103.0})
        assert results["abc123"][1] == TrailingStopAction.TRIGGER

        # Remove
        manager.remove_stop("abc123")
        assert manager.get_stop("abc123") is None

    def test_whipsaw_protection(self):
        """Test that whipsaw protection prevents premature triggers."""
        stop = TrailingStop(entry_premium=100.0)

        # Activate at 103
        _, _ = stop.update(103.0)
        assert stop.is_active is True

        # Small drop to 102.5 (above stop at 101.455)
        new_stop, action = stop.update(102.5)
        assert action == TrailingStopAction.HOLD

        # Small rise to 103.2 (not enough to update stop)
        new_stop, action = stop.update(103.2)
        # Move from 101.455 to 101.656 = 0.198% < 0.5% min_move
        assert action == TrailingStopAction.HOLD

        # Verify stop hasn't changed
        assert new_stop == pytest.approx(101.455, rel=0.001)

    def test_custom_whipsaw_thresholds(self):
        """Test custom whipsaw protection thresholds."""
        config = TrailingStopConfig(
            activation_pct=5.0, trailing_pct=3.0, min_move_pct=1.0
        )
        stop = TrailingStop(entry_premium=100.0, config=config)

        # Need 5% move to activate (premium at 105)
        new_stop, action = stop.update(103.0)
        assert action == TrailingStopAction.HOLD

        # Activate at 105
        new_stop, action = stop.update(105.0)
        assert action == TrailingStopAction.ACTIVATE
        assert new_stop == pytest.approx(101.85, rel=0.001)  # 105 * 0.97

        # Need 1% move to update (premium to 107)
        new_stop, action = stop.update(106.0)
        # New stop would be 106 * 0.97 = 102.82
        # Move from 101.85 to 102.82 = 0.95% < 1.0%
        assert action == TrailingStopAction.HOLD

        # Now enough move
        new_stop, action = stop.update(107.0)
        # New stop: 107 * 0.97 = 103.79
        # Move from 101.85 to 103.79 = 1.9% > 1.0%
        assert action == TrailingStopAction.UPDATE
        assert new_stop == pytest.approx(103.79, rel=0.001)
