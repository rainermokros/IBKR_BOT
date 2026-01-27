"""
Integration tests for decision rules.

Tests the complete decision rules system with all 12 rules registered.
Tests priority ordering, first-wins semantics, and rule-specific logic.

Usage:
    conda run -n ib pytest src/v6/decisions/test_rules.py -v
"""

from datetime import date, datetime, timedelta

import pytest

from src.v6.decisions.engine import DecisionEngine
from src.v6.decisions.models import DecisionAction, Urgency
from src.v6.decisions.rules import register_all_rules


class MockPosition:
    """Mock position snapshot for testing."""

    def __init__(
        self,
        strategy_id: str = "test_strategy",
        strategy_type: str = "iron_condor",
        symbol: str = "SPY",
        unrealized_pnl: float = 100.0,
        entry_price: float = 200.0,
        expiry: date = None,
        delta: float = 0.05,
        gamma: float = 0.01,
    ):
        """Initialize mock position."""
        self.strategy_id = strategy_id
        self.strategy_type = strategy_type
        self.symbol = symbol
        self.unrealized_pnl = unrealized_pnl
        self.entry_price = entry_price
        self.expiry = expiry or (date.today() + timedelta(days=30))
        self.delta = delta
        self.gamma = gamma

    def __getitem__(self, key):
        """Support dictionary-style access for Polars Row compatibility."""
        return getattr(self, key)


@pytest.mark.asyncio
async def test_all_rules_registered():
    """Test that all 12 rules are registered with the engine."""
    engine = DecisionEngine()
    register_all_rules(engine)

    assert engine.rule_count == 12, f"Expected 12 rules, got {engine.rule_count}"


@pytest.mark.asyncio
async def test_priority_order():
    """Test that rules are sorted by priority (1 → 8)."""
    engine = DecisionEngine()
    register_all_rules(engine)

    rule_names = engine.get_rules()

    # Expected priority order (by name)
    # Priority 1: catastrophe_protection
    # Priority 1.3: single_leg_exit
    # Priority 1.4: trailing_stop_loss
    # Priority 1.5: vix_exit
    # Priority 2: take_profit
    # Priority 3: stop_loss
    # Priority 4: delta_risk
    # Priority 5: iv_crush
    # Priority 5.5: iv_percentile_exit
    # Priority 6: dte_roll
    # Priority 7: gamma_risk
    # Priority 8: time_exit

    expected_order = [
        "catastrophe_protection",  # Priority 1
        "single_leg_exit",  # Priority 1.3
        "trailing_stop_loss",  # Priority 1.4
        "vix_exit",  # Priority 1.5
        "take_profit",  # Priority 2
        "stop_loss",  # Priority 3
        "delta_risk",  # Priority 4
        "iv_crush",  # Priority 5
        "iv_percentile_exit",  # Priority 5.5
        "dte_roll",  # Priority 6
        "gamma_risk",  # Priority 7
        "time_exit",  # Priority 8
    ]

    assert rule_names == expected_order, f"Rule order mismatch: {rule_names}"


@pytest.mark.asyncio
async def test_catastrophe_triggers_first():
    """Test that catastrophe rule triggers before take profit (priority test)."""
    engine = DecisionEngine()
    register_all_rules(engine)

    # Create position with catastrophe condition + take profit condition
    # Both should trigger, but catastrophe (priority 1) should win
    position = MockPosition(
        unrealized_pnl=200.0,  # 100% profit (triggers TP)
        entry_price=200.0,
    )

    market_data = {
        "1h_change": -0.05,  # -5% (triggers catastrophe)
        "iv_change_percent": 0.0,
    }

    decision = await engine.evaluate(position, market_data)

    assert decision.action == DecisionAction.CLOSE
    assert decision.rule == "catastrophe_3pct_drop"
    assert decision.urgency == Urgency.IMMEDIATE
    assert "Market crash" in decision.reason


@pytest.mark.asyncio
async def test_take_profit_triggers():
    """Test that take profit rule triggers at 80% profit."""
    engine = DecisionEngine()
    register_all_rules(engine)

    # Create position with 85% profit
    position = MockPosition(
        unrealized_pnl=170.0,  # 85% profit
        entry_price=200.0,
    )

    decision = await engine.evaluate(position)

    assert decision.action == DecisionAction.CLOSE
    assert decision.rule == "take_profit_full"
    assert decision.urgency == Urgency.NORMAL
    assert "Take profit" in decision.reason


@pytest.mark.asyncio
async def test_stop_loss_triggers():
    """Test that stop loss rule triggers at -200% loss."""
    engine = DecisionEngine()
    register_all_rules(engine)

    # Create position with -250% loss
    position = MockPosition(
        unrealized_pnl=-500.0,  # -250% loss
        entry_price=200.0,
    )

    decision = await engine.evaluate(position)

    assert decision.action == DecisionAction.CLOSE
    assert decision.rule == "stop_loss_hard"
    assert decision.urgency == Urgency.IMMEDIATE
    assert "Stop loss" in decision.reason


@pytest.mark.asyncio
async def test_dte_roll_triggers():
    """Test that DTE roll rule triggers at 22 DTE."""
    engine = DecisionEngine()
    register_all_rules(engine)

    # Create position with 22 DTE (should trigger roll)
    # Set unrealized_pnl to 0 to avoid triggering take profit
    position = MockPosition(
        unrealized_pnl=0.0,  # No profit/loss
        entry_price=200.0,
        expiry=date.today() + timedelta(days=22),
    )

    decision = await engine.evaluate(position)

    assert decision.action == DecisionAction.ROLL
    assert decision.rule == "dte_roll"
    # 22 DTE is not force roll (force is <=21), so urgency is NORMAL
    assert decision.urgency == Urgency.NORMAL
    assert "DTE roll" in decision.reason
    assert decision.metadata["current_dte"] == 22
    assert decision.metadata["roll_to_dte"] == 45
    assert decision.metadata["force_roll"] is False


@pytest.mark.asyncio
async def test_gamma_risk_triggers():
    """Test that gamma risk rule triggers with high gamma near expiry."""
    from src.v6.decisions.rules.roll_rules import GammaRisk

    # Test gamma risk rule directly (not through engine)
    # because DTE roll (priority 6) will trigger before gamma risk (priority 7)
    rule = GammaRisk()

    # Create position with high gamma and low DTE
    position = MockPosition(
        unrealized_pnl=0.0,  # No profit/loss
        entry_price=200.0,
        gamma=0.15,  # High gamma
        expiry=date.today() + timedelta(days=10),  # Low DTE
    )

    decision = await rule.evaluate(position)

    assert decision.action == DecisionAction.CLOSE
    assert decision.rule == "gamma_risk"
    assert decision.urgency == Urgency.HIGH
    assert "Gamma risk" in decision.reason


@pytest.mark.asyncio
async def test_no_trigger_returns_hold():
    """Test that healthy position returns HOLD decision."""
    engine = DecisionEngine()
    register_all_rules(engine)

    # Create healthy position (30% profit, 30 DTE, normal Greeks)
    position = MockPosition(
        unrealized_pnl=60.0,  # 30% profit (below TP threshold)
        entry_price=200.0,
        expiry=date.today() + timedelta(days=30),  # Good DTE
        delta=0.05,  # Normal delta
        gamma=0.01,  # Normal gamma
    )

    decision = await engine.evaluate(position)

    assert decision.action == DecisionAction.HOLD
    assert decision.rule == "none"
    assert decision.urgency == Urgency.NORMAL
    assert "No rule triggered" in decision.reason


@pytest.mark.asyncio
async def test_partial_take_profit():
    """Test that partial take profit triggers at 50% profit."""
    engine = DecisionEngine()
    register_all_rules(engine)

    # Create position with 55% profit (triggers partial TP)
    position = MockPosition(
        unrealized_pnl=110.0,  # 55% profit
        entry_price=200.0,
    )

    decision = await engine.evaluate(position)

    assert decision.action == DecisionAction.REDUCE
    assert decision.rule == "take_profit_partial"
    assert decision.urgency == Urgency.NORMAL
    assert "Partial take profit" in decision.reason
    assert decision.metadata["close_ratio"] == 0.50


@pytest.mark.asyncio
async def test_vix_exit_triggers():
    """Test that VIX exit rule triggers when VIX > 35."""
    engine = DecisionEngine()
    register_all_rules(engine)

    position = MockPosition()

    market_data = {
        "vix": 40.0,  # VIX > 35
    }

    decision = await engine.evaluate(position, market_data)

    assert decision.action == DecisionAction.CLOSE
    assert decision.rule == "vix_level"
    assert decision.urgency == Urgency.HIGH
    assert "VIX exit" in decision.reason


@pytest.mark.asyncio
async def test_time_exit_triggers():
    """Test that time exit rule triggers on last day before expiration."""
    from src.v6.decisions.rules.roll_rules import TimeExit

    # Test time exit rule directly (not through engine)
    # because DTE roll (priority 6) will trigger before time exit (priority 8)
    rule = TimeExit()

    position = MockPosition(
        unrealized_pnl=0.0,  # No profit/loss
        entry_price=200.0,
        expiry=date.today() + timedelta(days=1),
    )

    decision = await rule.evaluate(position)

    assert decision.action == DecisionAction.CLOSE
    assert decision.rule == "time_exit"
    assert decision.urgency == Urgency.IMMEDIATE
    assert "Time exit" in decision.reason


@pytest.mark.asyncio
async def test_iv_crush_triggers():
    """Test that IV crush rule triggers when IV drops >30% with profit."""
    engine = DecisionEngine()
    register_all_rules(engine)

    # Create position with 30% profit and IV drop
    position = MockPosition(
        unrealized_pnl=60.0,  # 30% profit
        entry_price=200.0,
    )

    market_data = {
        "iv_change_percent": -0.40,  # IV dropped 40%
    }

    decision = await engine.evaluate(position, market_data)

    assert decision.action == DecisionAction.CLOSE
    assert decision.rule == "iv_crush"
    assert "IV crush" in decision.reason


@pytest.mark.asyncio
async def test_trailing_stop_activates():
    """Test that trailing stop activates after peak >= 40%."""
    from src.v6.decisions.rules.catastrophe import TrailingStopLoss

    # Create rule instance
    rule = TrailingStopLoss()

    # First call: Position at 50% profit (sets peak)
    position1 = MockPosition(
        strategy_id="test_1",
        unrealized_pnl=100.0,  # 50% profit
        entry_price=200.0,
    )

    decision1 = await rule.evaluate(position1)
    assert decision1 is None, "Trailing stop should not trigger on peak"

    # Second call: Position drops to 15% profit (below 40% of peak = 20%)
    position2 = MockPosition(
        strategy_id="test_1",
        unrealized_pnl=30.0,  # 15% profit
        entry_price=200.0,
    )

    decision2 = await rule.evaluate(position2)
    assert decision2 is not None, "Trailing stop should trigger"
    assert decision2.rule == "trailing_stop"
    assert decision2.action == DecisionAction.CLOSE


@pytest.mark.asyncio
async def test_single_leg_exit_only_for_long_short():
    """Test that single-leg exit only applies to LONG/SHORT strategies."""
    engine = DecisionEngine()
    register_all_rules(engine)

    # Iron condor should NOT trigger single-leg exit
    position = MockPosition(
        strategy_type="iron_condor",
        unrealized_pnl=200.0,  # 100% profit
        entry_price=200.0,
    )

    decision = await engine.evaluate(position)

    # Should not trigger single-leg exit (it's a spread)
    # No other rules should trigger for this position either
    assert decision.action == DecisionAction.HOLD or decision.rule != "single_leg_tp"


@pytest.mark.asyncio
async def test_delta_risk_with_portfolio_data():
    """Test that delta risk rule checks portfolio-level delta."""
    engine = DecisionEngine()
    register_all_rules(engine)

    # Set unrealized_pnl to 0 to avoid triggering take profit
    position = MockPosition(
        unrealized_pnl=0.0,  # No profit/loss
        entry_price=200.0,
        strategy_type="iron_condor",
        symbol="SPY",
    )

    market_data = {
        "portfolio_delta": 0.35,  # Exceeds IC limit of 0.30
    }

    decision = await engine.evaluate(position, market_data)

    assert decision.action == DecisionAction.CLOSE
    assert decision.rule == "delta_risk_portfolio"
    assert "Delta risk" in decision.reason
