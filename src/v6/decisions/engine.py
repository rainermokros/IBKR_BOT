"""
Decision Engine with Priority Queue Execution

This module provides the DecisionEngine class that evaluates decision rules
in priority order (1-12) using first-wins semantics.

Key patterns:
- Priority queue: Rules sorted by priority (1-12), execute in order
- First-wins semantics: Stop at first rule that triggers
- Rule registration: Register rules dynamically (not hardcoded)
- Stats tracking: Track how often each rule triggers
- Async design: Use async/await for consistency with Phase 2

Reference: ../v5/caretaker/decision_engine.py for patterns (priority-based evaluation),
but adapted to v6 architecture (async, protocol-based).
"""

from typing import Optional, Protocol, runtime_checkable

from loguru import logger

from src.v6.decisions.models import Decision, DecisionAction, Urgency


@runtime_checkable
class Rule(Protocol):
    """
    Rule protocol for decision rules.

    Any class that implements this interface can be registered as a rule.
    Uses Protocol for duck-typing (flexible, no inheritance required).

    Attributes:
        priority: Rule priority (1-12, lower = higher priority)
        name: Unique rule name/identifier

    Methods:
        evaluate: Evaluate rule and return decision or None
    """

    priority: int  # 1-12
    name: str

    async def evaluate(self, snapshot, market_data: Optional[dict] = None) -> Optional[Decision]:
        """
        Evaluate rule and return decision if triggered.

        Args:
            snapshot: Position snapshot with live data
            market_data: Optional market data (VIX, IV, underlying, etc.)

        Returns:
            Decision if rule triggers, None otherwise
        """
        ...


class DecisionEngine:
    """
    Evaluate decision rules in priority order.

    **Priority Queue Execution:**
    - Rules sorted by priority (1-12, lower = higher priority)
    - Execute rules in order, return first non-None result
    - If no rules trigger, return HOLD decision

    **First-Wins Semantics:**
    - Stop at first rule that triggers (returns non-None Decision)
    - Priority 1 rules execute before priority 2, etc.

    **Rule Registration:**
    - Rules registered dynamically via register_rule()
    - Rules sorted by priority on registration
    - No hardcoded rules (extensible design)

    **Stats Tracking:**
    - Track how often each rule triggers
    - Useful for analysis and optimization

    Attributes:
        _rules: List of rules sorted by priority
        _stats: Dict tracking rule trigger counts

    Example:
        ```python
        engine = DecisionEngine()

        # Register rules dynamically
        engine.register_rule(CatastropheRule())
        engine.register_rule(TakeProfitRule())
        engine.register_rule(StopLossRule())

        # Evaluate position
        decision = await engine.evaluate(snapshot, market_data)
        ```
    """

    def __init__(self, rules: Optional[list[Rule]] = None):
        """
        Initialize decision engine.

        Args:
            rules: Optional list of rules to register immediately
        """
        self._rules: list[Rule] = []
        self._stats: dict[str, int] = {}

        # Register initial rules if provided
        if rules:
            for rule in rules:
                self.register_rule(rule)

        logger.debug("DecisionEngine initialized")

    def register_rule(self, rule: Rule) -> None:
        """
        Register a rule with the engine.

        Rules are sorted by priority after registration.
        If rule with same name exists, it will be replaced.

        Args:
            rule: Rule instance implementing Rule protocol

        Raises:
            ValueError: If rule priority is not 1-12
        """
        # Validate priority
        if rule.priority < 1 or rule.priority > 12:
            raise ValueError(f"Rule priority must be 1-12, got {rule.priority}")

        # Remove existing rule with same name (if any)
        self._rules = [r for r in self._rules if r.name != rule.name]

        # Add new rule
        self._rules.append(rule)

        # Sort by priority (lower = higher priority)
        self._rules.sort(key=lambda r: r.priority)

        # Initialize stats for new rule
        if rule.name not in self._stats:
            self._stats[rule.name] = 0

        logger.debug(
            f"Registered rule: {rule.name} (priority {rule.priority}, "
            f"{len(self._rules)} total rules)"
        )

    async def evaluate(
        self,
        snapshot,
        market_data: Optional[dict] = None
    ) -> Decision:
        """
        Evaluate all rules in priority order.

        First rule to trigger wins. Returns HOLD if no rules trigger.

        Args:
            snapshot: Position snapshot with live Greeks and P&L
            market_data: Optional market data (VIX, IV, underlying change, etc.)

        Returns:
            Decision with action, reason, rule, and urgency
        """
        # Evaluate rules in priority order
        for rule in self._rules:
            try:
                # Call rule.evaluate()
                decision = await rule.evaluate(snapshot, market_data)

                # First-wins: return first non-None result
                if decision is not None:
                    # Update stats
                    self._stats[rule.name] = self._stats.get(rule.name, 0) + 1

                    logger.info(
                        f"Rule triggered: {rule.name} (priority {rule.priority}) "
                        f"→ {decision.action.value}: {decision.reason}"
                    )

                    return decision

            except Exception as e:
                # Log error but continue to next rule
                logger.error(f"Error evaluating rule {rule.name}: {e}")
                continue

        # No rules triggered - return HOLD
        return Decision(
            action=DecisionAction.HOLD,
            reason="No rule triggered",
            rule="none",
            urgency=Urgency.NORMAL,
            metadata={"rules_evaluated": len(self._rules)}
        )

    def get_rule_stats(self) -> dict[str, int]:
        """
        Get rule trigger statistics.

        Returns:
            Dict mapping rule name to trigger count
        """
        return self._stats.copy()

    def clear_stats(self) -> None:
        """Clear all rule statistics."""
        self._stats.clear()
        logger.debug("Rule statistics cleared")

    @property
    def rule_count(self) -> int:
        """Get number of registered rules."""
        return len(self._rules)

    def get_rules(self) -> list[str]:
        """
        Get list of registered rule names in priority order.

        Returns:
            List of rule names sorted by priority
        """
        return [rule.name for rule in self._rules]
