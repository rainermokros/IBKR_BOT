"""
Decision Data Models and Enums

This module provides data models for the decision engine.
Uses dataclasses with slots=True for performance (internal data, validated on entry).

Key patterns:
- dataclass(slots=True) for performance
- __post_init__ validation for data integrity
- Type hints for all fields
- Immutable where possible

Decision tree:
    Is this data internal to my process?
    ├─ Yes → Use dataclass (performance matters) ← WE ARE HERE
    └─ No → Use Pydantic (validation critical)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class DecisionAction(str, Enum):
    """
    Decision action enum.

    Actions the decision engine can recommend for a position.
    """

    HOLD = "hold"  # No action required
    CLOSE = "close"  # Close entire position
    ROLL = "roll"  # Roll to new expiration/strikes
    ADJUST = "adjust"  # Adjust position (hedge, add legs)
    HEDGE = "hedge"  # Add hedge protection
    REDUCE = "reduce"  # Reduce position size


class Urgency(str, Enum):
    """
    Decision urgency enum.

    Indicates how quickly action should be taken.
    """

    IMMEDIATE = "immediate"  # Act immediately (market crash, stop loss)
    HIGH = "high"  # Act soon (delta risk, gamma risk)
    NORMAL = "normal"  # Act on next cycle (take profit, DTE roll)
    LOW = "low"  # Consider action (informational)


@dataclass(slots=True)
class Decision:
    """
    Decision data model.

    Represents a trading decision for a position with metadata.

    Attributes:
        action: Action to take (CLOSE, ROLL, etc.)
        reason: Human-readable reason for the decision
        rule: Rule name/identifier that triggered
        urgency: How urgent this decision is
        metadata: Optional rule-specific data (e.g., close_ratio, iv_change_percent)
        timestamp: When this decision was made

    Raises:
        ValueError: If action or urgency validation fails
    """

    action: DecisionAction
    reason: str
    rule: str
    urgency: Urgency
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """
        Validate decision fields after initialization.

        Ensures data integrity before decision is used.
        """
        # Validate reason is not empty
        if not self.reason or not self.reason.strip():
            raise ValueError("Decision reason cannot be empty")

        # Validate rule is not empty
        if not self.rule or not self.rule.strip():
            raise ValueError("Decision rule cannot be empty")

        # Validate urgency is valid enum
        if not isinstance(self.urgency, Urgency):
            raise ValueError(f"Invalid urgency: {self.urgency}")

        # Validate action is valid enum
        if not isinstance(self.action, DecisionAction):
            raise ValueError(f"Invalid action: {self.action}")

        # Ensure metadata is a dict
        if not isinstance(self.metadata, dict):
            raise ValueError("Metadata must be a dictionary")

    def __repr__(self) -> str:
        """Return string representation of decision."""
        return (
            f"Decision(action={self.action.value}, reason={self.reason}, "
            f"rule={self.rule}, urgency={self.urgency.value})"
        )


@dataclass(slots=True)
class RuleResult:
    """
    Rule evaluation result data model.

    Represents the result of evaluating a single decision rule.

    Attributes:
        triggered: Whether the rule triggered (True = rule recommends action)
        decision: Optional decision (if triggered)
        priority: Rule priority (1-12, lower = higher priority)

    Raises:
        ValueError: If validation fails (triggered=True but decision=None)
    """

    triggered: bool
    decision: Optional[Decision] = None
    priority: int = 12  # Default to lowest priority

    def __post_init__(self):
        """
        Validate rule result after initialization.

        Ensures data integrity before result is used.
        """
        # Validate priority range
        if self.priority < 1 or self.priority > 12:
            raise ValueError(f"Priority must be 1-12, got {self.priority}")

        # If triggered=True, must have a decision
        if self.triggered and self.decision is None:
            raise ValueError("Triggered rule must have a decision")

        # If triggered=False, should not have a decision
        if not self.triggered and self.decision is not None:
            raise ValueError("Non-triggered rule should not have a decision")

    def __repr__(self) -> str:
        """Return string representation of rule result."""
        if self.triggered:
            return (
                f"RuleResult(triggered=True, priority={self.priority}, "
                f"decision={self.decision})"
            )
        return f"RuleResult(triggered=False, priority={self.priority})"
