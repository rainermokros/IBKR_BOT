"""
Unit Tests for DecisionEngine

Test cases:
- test_empty_engine_returns_hold: Engine with 0 rules returns HOLD decision
- test_priority_order: Create 3 mock rules (priorities 1, 2, 3), verify rule 1 executes first
- test_first_wins_semantics: If rule 1 triggers, rules 2-3 never execute
- test_rule_registration: Register rules dynamically, verify sorted by priority
- test_stats_tracking: Call evaluate multiple times, verify stats track counts
- test_no_trigger_returns_hold: Create rule that returns None, verify HOLD decision
- test_market_data_passing: Verify market_data dict passed to rule.evaluate()
"""

import pytest
from datetime import datetime

from v6.decisions.engine import DecisionEngine
from v6.decisions.models import Decision, DecisionAction, Urgency


# =============================================================================
# Mock Rule for Testing
# =============================================================================


class MockRule:
    """
    Mock rule for testing DecisionEngine.

    Attributes:
        priority: Rule priority (1-12)
        name: Rule name
        should_trigger: Whether this rule should trigger
        decision_to_return: Decision to return when triggered
        call_count: Number of times evaluate() was called
        last_market_data: Last market_data received
    """

    def __init__(
        self,
        priority: int,
        name: str,
        should_trigger: bool = False,
        decision_to_return: Decision = None
    ):
        self.priority = priority
        self.name = name
        self.should_trigger = should_trigger
        self.decision_to_return = decision_to_return
        self.call_count = 0
        self.last_market_data = None

        # Create default decision if none provided
        if self.should_trigger and self.decision_to_return is None:
            self.decision_to_return = Decision(
                action=DecisionAction.CLOSE,
                reason=f"Triggered {self.name}",
                rule=self.name,
                urgency=Urgency.IMMEDIATE
            )

    async def evaluate(self, snapshot, market_data=None):
        """Evaluate rule and return decision if should_trigger."""
        self.call_count += 1
        self.last_market_data = market_data

        if self.should_trigger:
            return self.decision_to_return
        return None


# =============================================================================
# Mock Snapshot for Testing
# =============================================================================


class MockSnapshot:
    """Mock position snapshot for testing."""

    def __init__(self):
        self.symbol = "SPY"
        self.strategy_type = "iron_condor"
        self.upl_percent = 10.0
        self.dte_current = 30
        self.net_delta = 0.15


# =============================================================================
# Test Cases
# =============================================================================


@pytest.mark.asyncio
async def test_empty_engine_returns_hold():
    """Engine with 0 rules returns HOLD decision."""
    engine = DecisionEngine()
    snapshot = MockSnapshot()

    decision = await engine.evaluate(snapshot)

    assert decision.action == DecisionAction.HOLD
    assert decision.reason == "No rule triggered"
    assert decision.rule == "none"
    assert decision.urgency == Urgency.NORMAL
    assert decision.metadata["rules_evaluated"] == 0


@pytest.mark.asyncio
async def test_priority_order():
    """
    Create 3 mock rules (priorities 1, 2, 3), verify rule 1 executes first.

    Even if rule 2 and 3 would trigger, rule 1 should execute first.
    """
    engine = DecisionEngine()

    # Create rules with different priorities (registered out of order)
    rule2 = MockRule(priority=2, name="rule2", should_trigger=True)
    rule1 = MockRule(priority=1, name="rule1", should_trigger=True)
    rule3 = MockRule(priority=3, name="rule3", should_trigger=True)

    # Register out of order
    engine.register_rule(rule2)
    engine.register_rule(rule1)
    engine.register_rule(rule3)

    snapshot = MockSnapshot()
    decision = await engine.evaluate(snapshot)

    # Rule 1 should have triggered (lowest priority number)
    assert decision.rule == "rule1"
    assert rule1.call_count == 1  # Executed
    assert rule2.call_count == 0  # Skipped (first-wins)
    assert rule3.call_count == 0  # Skipped (first-wins)

    # Verify rules are sorted internally
    assert engine.get_rules() == ["rule1", "rule2", "rule3"]


@pytest.mark.asyncio
async def test_first_wins_semantics():
    """
    If rule 1 triggers, rules 2-3 never execute.

    First-wins: stop at first rule that triggers.
    """
    engine = DecisionEngine()

    # Rule 1 triggers
    rule1 = MockRule(priority=1, name="rule1", should_trigger=True)
    # Rule 2 would trigger but shouldn't execute
    rule2 = MockRule(priority=2, name="rule2", should_trigger=True)
    # Rule 3 would trigger but shouldn't execute
    rule3 = MockRule(priority=3, name="rule3", should_trigger=True)

    engine.register_rule(rule1)
    engine.register_rule(rule2)
    engine.register_rule(rule3)

    snapshot = MockSnapshot()
    decision = await engine.evaluate(snapshot)

    # Only rule 1 should have executed
    assert decision.rule == "rule1"
    assert rule1.call_count == 1
    assert rule2.call_count == 0
    assert rule3.call_count == 0


@pytest.mark.asyncio
async def test_rule_registration():
    """Register rules dynamically, verify sorted by priority."""
    engine = DecisionEngine()

    # Register rules in random order
    engine.register_rule(MockRule(priority=3, name="rule3"))
    engine.register_rule(MockRule(priority=1, name="rule1"))
    engine.register_rule(MockRule(priority=2, name="rule2"))

    # Verify sorted by priority
    assert engine.get_rules() == ["rule1", "rule2", "rule3"]
    assert engine.rule_count == 3

    # Test rule replacement (register same name again)
    new_rule1 = MockRule(priority=1, name="rule1", should_trigger=True)
    engine.register_rule(new_rule1)

    # Should still have 3 rules (replaced, not added)
    assert engine.rule_count == 3
    assert engine.get_rules() == ["rule1", "rule2", "rule3"]


@pytest.mark.asyncio
async def test_stats_tracking():
    """Call evaluate multiple times, verify stats track trigger counts."""
    engine = DecisionEngine()

    # Create 3 rules with different triggers
    rule1 = MockRule(priority=1, name="rule1", should_trigger=True)
    rule2 = MockRule(priority=2, name="rule2", should_trigger=False)
    rule3 = MockRule(priority=3, name="rule3", should_trigger=False)

    engine.register_rule(rule1)
    engine.register_rule(rule2)
    engine.register_rule(rule3)

    snapshot = MockSnapshot()

    # Evaluate 5 times (rule1 should trigger each time)
    for _ in range(5):
        await engine.evaluate(snapshot)

    stats = engine.get_rule_stats()

    # Rule1 should have 5 triggers
    assert stats["rule1"] == 5
    # Rules 2 and 3 should have 0 triggers
    assert stats.get("rule2", 0) == 0
    assert stats.get("rule3", 0) == 0

    # Clear stats
    engine.clear_stats()
    assert engine.get_rule_stats() == {}


@pytest.mark.asyncio
async def test_no_trigger_returns_hold():
    """Create rule that returns None, verify HOLD decision."""
    engine = DecisionEngine()

    # Rule that doesn't trigger
    rule1 = MockRule(priority=1, name="rule1", should_trigger=False)
    rule2 = MockRule(priority=2, name="rule2", should_trigger=False)

    engine.register_rule(rule1)
    engine.register_rule(rule2)

    snapshot = MockSnapshot()
    decision = await engine.evaluate(snapshot)

    # Should return HOLD
    assert decision.action == DecisionAction.HOLD
    assert decision.rule == "none"
    assert decision.metadata["rules_evaluated"] == 2


@pytest.mark.asyncio
async def test_market_data_passing():
    """Verify market_data dict passed to rule.evaluate()."""
    engine = DecisionEngine()

    # Create rule that doesn't trigger
    rule1 = MockRule(priority=1, name="rule1", should_trigger=False)
    engine.register_rule(rule1)

    snapshot = MockSnapshot()
    market_data = {
        "vix": 20.5,
        "iv_change_percent": -10.0,
        "underlying_1h_change": -0.02
    }

    # Evaluate with market_data
    await engine.evaluate(snapshot, market_data)

    # Verify rule received market_data
    assert rule1.last_market_data == market_data
    assert rule1.last_market_data["vix"] == 20.5


@pytest.mark.asyncio
async def test_rule_error_handling():
    """Test that errors in rule evaluation don't crash the engine."""
    engine = DecisionEngine()

    # Create a faulty rule that raises an exception
    class FaultyRule:
        priority = 1
        name = "faulty_rule"

        async def evaluate(self, snapshot, market_data=None):
            raise RuntimeError("This rule is broken!")

    # Create a good rule
    good_rule = MockRule(priority=2, name="good_rule", should_trigger=True)

    engine.register_rule(FaultyRule())
    engine.register_rule(good_rule)

    snapshot = MockSnapshot()
    decision = await engine.evaluate(snapshot)

    # Should skip faulty rule and trigger good_rule
    assert decision.rule == "good_rule"
    assert good_rule.call_count == 1


@pytest.mark.asyncio
async def test_priority_validation():
    """Test that priority must be 1-12."""
    engine = DecisionEngine()

    # Valid priorities
    engine.register_rule(MockRule(priority=1, name="rule1"))
    engine.register_rule(MockRule(priority=12, name="rule12"))

    # Invalid priority (should raise ValueError)
    with pytest.raises(ValueError, match="priority must be 1-12"):
        engine.register_rule(MockRule(priority=0, name="rule0"))

    with pytest.raises(ValueError, match="priority must be 1-12"):
        engine.register_rule(MockRule(priority=13, name="rule13"))


@pytest.mark.asyncio
async def test_decision_metadata():
    """Test that decisions preserve metadata."""
    engine = DecisionEngine()

    # Create rule with custom metadata
    decision_with_metadata = Decision(
        action=DecisionAction.CLOSE,
        reason="Test with metadata",
        rule="test_rule",
        urgency=Urgency.NORMAL,
        metadata={
            "close_ratio": 0.5,
            "iv_change_percent": -25.0,
            "profit_percent": 45.0
        }
    )

    rule1 = MockRule(
        priority=1,
        name="rule1",
        should_trigger=True,
        decision_to_return=decision_with_metadata
    )
    engine.register_rule(rule1)

    snapshot = MockSnapshot()
    decision = await engine.evaluate(snapshot)

    # Verify metadata is preserved
    assert decision.metadata["close_ratio"] == 0.5
    assert decision.metadata["iv_change_percent"] == -25.0
    assert decision.metadata["profit_percent"] == 45.0
