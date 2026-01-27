"""
Strategy fixtures for testing options strategies.

Provides realistic strategy configurations for iron condors, vertical spreads,
and other strategies with proper leg specifications and Greeks.

Usage:
    @pytest.fixture
    def sample_strategy(sample_iron_condor):
        return sample_strategy

    def test_strategy(sample_strategy):
        assert sample_strategy.strategy_type == StrategyType.IRON_CONDOR
"""

import pytest
from datetime import date, datetime
from typing import Optional

from src.v6.strategies.models import (
    ExecutionStatus,
    LegAction,
    LegSpec,
    LegStatus,
    OptionRight,
    Strategy,
    StrategyType,
)


@pytest.fixture
def sample_iron_condor():
    """
    Create a complete Iron Condor strategy fixture.

    Iron Condor: Sell vertical spread above and below current price.
    - SELL PUT @ 450 (short put spread lower strike)
    - BUY PUT @ 440 (long put spread protection)
    - SELL CALL @ 460 (short call spread lower strike)
    - BUY CALL @ 470 (long call spread protection)

    Returns:
        Strategy: Complete Iron Condor strategy with:
            - strategy_id: Unique identifier
            - symbol: SPY
            - strategy_type: IRON_CONDOR
            - legs: 4 legs (short put vertical + short call vertical)
            - All legs have same expiration
            - Strikes form proper iron condor structure

    Example:
        def test_iron_condor(sample_iron_condor):
            assert len(sample_iron_condor.legs) == 4
            assert sample_iron_condor.strategy_type == StrategyType.IRON_CONDOR
    """
    return Strategy(
        strategy_id="test-ic-spy-001",
        symbol="SPY",
        strategy_type=StrategyType.IRON_CONDOR,
        legs=[
            # Short put spread
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
            # Short call spread
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
    )


@pytest.fixture
def sample_vertical_spread_put():
    """
    Create a vertical put spread (bearish) strategy.

    Vertical Put Spread: Sell higher strike put, buy lower strike put.
    - SELL PUT @ 450 (near ATM)
    - BUY PUT @ 440 (protection)

    Returns:
        Strategy: Vertical put spread with 2 legs

    Example:
        def test_vertical_put(sample_vertical_spread_put):
            assert len(sample_vertical_spread_put.legs) == 2
            assert all(leg.right == OptionRight.PUT for leg in sample_vertical_spread_put.legs)
    """
    return Strategy(
        strategy_id="test-vp-spy-001",
        symbol="SPY",
        strategy_type=StrategyType.VERTICAL_SPREAD,
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
        ],
    )


@pytest.fixture
def sample_vertical_spread_call():
    """
    Create a vertical call spread (bullish) strategy.

    Vertical Call Spread: Buy lower strike call, sell higher strike call.
    - BUY CALL @ 460 (near ATM)
    - SELL CALL @ 470 (target)

    Returns:
        Strategy: Vertical call spread with 2 legs

    Example:
        def test_vertical_call(sample_vertical_spread_call):
            assert len(sample_vertical_spread_call.legs) == 2
            assert all(leg.right == OptionRight.CALL for leg in sample_vertical_spread_call.legs)
    """
    return Strategy(
        strategy_id="test-vc-spy-001",
        symbol="SPY",
        strategy_type=StrategyType.VERTICAL_SPREAD,
        legs=[
            LegSpec(
                right=OptionRight.CALL,
                strike=460.0,
                quantity=1,
                action=LegAction.BUY,
                expiration=date(2026, 3, 20),
            ),
            LegSpec(
                right=OptionRight.CALL,
                strike=470.0,
                quantity=1,
                action=LegAction.SELL,
                expiration=date(2026, 3, 20),
            ),
        ],
    )


@pytest.fixture
def sample_vertical_spread():
    """
    Create a vertical spread (defaults to put spread).

    Returns:
        Strategy: Vertical put spread (duplicate of sample_vertical_spread_put)

    Example:
        def test_vertical(sample_vertical_spread):
            assert sample_vertical_spread.strategy_type == StrategyType.VERTICAL_SPREAD
    """
    return Strategy(
        strategy_id="test-vs-spy-001",
        symbol="SPY",
        strategy_type=StrategyType.VERTICAL_SPREAD,
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
        ],
    )


@pytest.fixture
def sample_strategy_state():
    """
    Create a strategy execution with full state.

    Returns a StrategyExecution with realistic execution state,
    including leg statuses, fill prices, and Greeks.

    Returns:
        dict: Strategy execution state with:
            - execution_id: Unique execution identifier
            - strategy_id: Reference to strategy
            - symbol: Underlying symbol
            - strategy_type: Strategy type
            - status: Execution status (PENDING, FILLED, CLOSED)
            - legs: List of leg execution states
            - entry_price: Net credit/debit at entry
            - current_price: Current market value
            - greeks: Current portfolio Greeks
            - pnl: Unrealized P&L
            - opened_at: Entry timestamp
            - updated_at: Last update timestamp

    Example:
        def test_strategy_state(sample_strategy_state):
            assert sample_strategy_state["status"] == ExecutionStatus.FILLED
            assert len(sample_strategy_state["legs"]) == 4
    """
    from src.v6.execution.models import OrderStatus

    return {
        "execution_id": "test-exec-001",
        "strategy_id": "test-ic-spy-001",
        "symbol": "SPY",
        "strategy_type": StrategyType.IRON_CONDOR,
        "status": ExecutionStatus.FILLED,
        "entry_price": -1.50,  # Net credit received
        "current_price": -1.25,  # Current credit (profit)
        "unrealized_pnl": 25.0,  # $25 profit
        "realized_pnl": 0.0,
        "opened_at": datetime.now(),
        "updated_at": datetime.now(),
        "legs": [
            {
                "leg_id": "leg-001",
                "conid": 123456789,
                "right": "PUT",
                "strike": 450.0,
                "quantity": -1,
                "action": "SELL",
                "status": OrderStatus.FILLED,
                "avg_fill_price": 1.50,
                "filled_at": datetime.now(),
            },
            {
                "leg_id": "leg-002",
                "conid": 234567890,
                "right": "PUT",
                "strike": 440.0,
                "quantity": 1,
                "action": "BUY",
                "status": OrderStatus.FILLED,
                "avg_fill_price": 0.75,
                "filled_at": datetime.now(),
            },
            {
                "leg_id": "leg-003",
                "conid": 345678901,
                "right": "CALL",
                "strike": 460.0,
                "quantity": -1,
                "action": "SELL",
                "status": OrderStatus.FILLED,
                "avg_fill_price": 1.75,
                "filled_at": datetime.now(),
            },
            {
                "leg_id": "leg-004",
                "conid": 456789012,
                "right": "CALL",
                "strike": 470.0,
                "quantity": 1,
                "action": "BUY",
                "status": OrderStatus.FILLED,
                "avg_fill_price": 0.50,
                "filled_at": datetime.now(),
            },
        ],
        "greeks": {
            "delta": -0.30,
            "gamma": -0.02,
            "theta": 8.0,
            "vega": -14.0,
        },
    }


@pytest.fixture
def sample_pending_strategy_state():
    """
    Create a strategy execution in PENDING state.

    Returns a StrategyExecution with PENDING status (orders submitted but not filled).

    Returns:
        dict: Strategy execution state with status=PENDING

    Example:
        def test_pending_state(sample_pending_strategy_state):
            assert sample_pending_strategy_state["status"] == ExecutionStatus.PENDING
    """
    from src.v6.execution.models import OrderStatus

    return {
        "execution_id": "test-exec-pending",
        "strategy_id": "test-ic-spy-002",
        "symbol": "QQQ",
        "strategy_type": StrategyType.IRON_CONDOR,
        "status": ExecutionStatus.PENDING_SUBMIT,
        "entry_price": None,
        "current_price": None,
        "unrealized_pnl": 0.0,
        "realized_pnl": 0.0,
        "opened_at": datetime.now(),
        "updated_at": datetime.now(),
        "legs": [
            {
                "leg_id": "leg-001",
                "conid": 123456789,
                "right": "PUT",
                "strike": 450.0,
                "quantity": -1,
                "action": "SELL",
                "status": OrderStatus.PENDING_SUBMIT,
                "avg_fill_price": None,
                "filled_at": None,
            },
            {
                "leg_id": "leg-002",
                "conid": 234567890,
                "right": "PUT",
                "strike": 440.0,
                "quantity": 1,
                "action": "BUY",
                "status": OrderStatus.PENDING_SUBMIT,
                "avg_fill_price": None,
                "filled_at": None,
            },
            {
                "leg_id": "leg-003",
                "conid": 345678901,
                "right": "CALL",
                "strike": 460.0,
                "quantity": -1,
                "action": "SELL",
                "status": OrderStatus.PENDING_SUBMIT,
                "avg_fill_price": None,
                "filled_at": None,
            },
            {
                "leg_id": "leg-004",
                "conid": 456789012,
                "right": "CALL",
                "strike": 470.0,
                "quantity": 1,
                "action": "BUY",
                "status": OrderStatus.PENDING_SUBMIT,
                "avg_fill_price": None,
                "filled_at": None,
            },
        ],
        "greeks": None,  # Not calculated yet
    }


@pytest.fixture
def sample_custom_strategy():
    """
    Create a custom strategy with arbitrary legs.

    Returns a Strategy with CUSTOM type and user-specified legs.

    Returns:
        Strategy: Custom strategy with 3 legs

    Example:
        def test_custom(sample_custom_strategy):
            assert sample_custom_strategy.strategy_type == StrategyType.CUSTOM
            assert len(sample_custom_strategy.legs) == 3
    """
    return Strategy(
        strategy_id="test-custom-001",
        symbol="IWM",
        strategy_type=StrategyType.CUSTOM,
        legs=[
            LegSpec(
                right=OptionRight.PUT,
                strike=200.0,
                quantity=2,
                action=LegAction.SELL,
                expiration=date(2026, 4, 17),
            ),
            LegSpec(
                right=OptionRight.PUT,
                strike=195.0,
                quantity=2,
                action=LegAction.BUY,
                expiration=date(2026, 4, 17),
            ),
            LegSpec(
                right=OptionRight.CALL,
                strike=210.0,
                quantity=1,
                action=LegAction.SELL,
                expiration=date(2026, 4, 17),
            ),
        ],
    )
