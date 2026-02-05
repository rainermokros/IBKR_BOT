"""
Decision Rules Package

This package contains all decision rules for the trading bot.
Rules are organized by category and follow the Rule protocol.

Key patterns:
- Protocol-based rules (duck-typing, no inheritance required)
- Priority 1-12 (lower = higher priority)
- async evaluate() method
- Return Decision or None

Usage:
    from v6.strategy_builder.decision_engine import register_all_rules
    from v6.strategy_builder.decision_engine.engine import DecisionEngine

    engine = DecisionEngine()
    register_all_rules(engine)
"""

# Export all rule classes and DecisionEngine
from v6.strategy_builder.decision_engine.engine import DecisionEngine
from v6.strategy_builder.decision_engine.catastrophe import (
    CatastropheProtection,
    SingleLegExit,
    TrailingStopLoss,
    VIXExit,
)
from v6.strategy_builder.decision_engine.protection_rules import (
    DeltaRisk,
    IVCrush,
    IVPercentileExit,
    StopLoss,
    TakeProfit,
)
from v6.strategy_builder.decision_engine.roll_rules import DTERoll, GammaRisk, TimeExit

__all__ = [
    "DecisionEngine",
    "register_all_rules",
    "CatastropheProtection",
    "SingleLegExit",
    "TrailingStopLoss",
    "VIXExit",
    "TakeProfit",
    "StopLoss",
    "DeltaRisk",
    "IVCrush",
    "IVPercentileExit",
    "DTERoll",
    "GammaRisk",
    "TimeExit",
]


def register_all_rules(engine) -> None:
    """
    Register all 12 rules with DecisionEngine.

    This function registers all decision rules in priority order.
    Rules are automatically sorted by the engine, so order here doesn't matter.

    Args:
        engine: DecisionEngine instance to register rules with

    Example:
        >>> from v6.strategy_builder.decision_engine.engine import DecisionEngine
        >>> from v6.strategy_builder.decision_engine import register_all_rules
        >>>
        >>> engine = DecisionEngine()
        >>> register_all_rules(engine)
        >>> print(f"Registered {engine.rule_count} rules")
    """
    # Import here to avoid circular imports
    from v6.strategy_builder.decision_engine.catastrophe import (
        CatastropheProtection,
        SingleLegExit,
        TrailingStopLoss,
        VIXExit,
    )
    from v6.strategy_builder.decision_engine.protection_rules import (
        DeltaRisk,
        IVCrush,
        IVPercentileExit,
        StopLoss,
        TakeProfit,
    )
    from v6.strategy_builder.decision_engine.roll_rules import DTERoll, GammaRisk, TimeExit

    # Register all 12 rules (priority 1-8)
    rules = [
        CatastropheProtection(),
        SingleLegExit(),
        TrailingStopLoss(),
        VIXExit(),
        TakeProfit(),
        StopLoss(),
        DeltaRisk(),
        IVCrush(),
        IVPercentileExit(),
        DTERoll(),
        GammaRisk(),
        TimeExit(),
    ]

    for rule in rules:
        engine.register_rule(rule)
