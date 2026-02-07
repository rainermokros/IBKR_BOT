"""
Decision Models for Risk Management

Defines the core decision data structures used throughout the system.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class DecisionAction(str, Enum):
    """Actions that can be taken on a position."""
    HOLD = "HOLD"          # No action needed
    CLOSE = "CLOSE"        # Close entire position
    ROLL = "ROLL"          # Roll to new expiration/strikes
    ADJUST = "ADJUST"      # Adjust position (add/remove legs)
    REDUCE = "REDUCE"      # Reduce position size


class Urgency(str, Enum):
    """Urgency level for decision/action."""
    IMMEDIATE = "IMMEDIATE"  # Act now (within seconds)
    HIGH = "HIGH"           # Act soon (within minutes)
    NORMAL = "NORMAL"       # Normal priority (default for most decisions)
    MEDIUM = "MEDIUM"       # Act this hour
    LOW = "LOW"            # Act today


@dataclass(slots=True)
class Decision:
    """
    Decision result from rule evaluation.

    Attributes:
        action: DecisionAction to take
        reason: Human-readable explanation
        rule: Name of rule that triggered
        urgency: How urgent this decision is
        metadata: Additional context (strike, premium, etc.)
    """
    action: DecisionAction
    reason: str
    rule: str
    urgency: Urgency = Urgency.MEDIUM
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.action.value} ({self.rule}) - {self.reason}"
