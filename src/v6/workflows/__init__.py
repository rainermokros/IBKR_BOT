"""
Entry, Exit, and Monitoring Workflows

This package provides automated workflows for options trading execution:

- EntryWorkflow: Evaluate entry signals, build strategies, execute entry orders
- PositionMonitoringWorkflow: Monitor open positions, evaluate decisions, generate alerts
- ExitWorkflow: Execute exit decisions (CLOSE, ROLL, HOLD), close all positions

Example:
    ```python
    from src.v6.workflows import (
        EntryWorkflow,
        PositionMonitoringWorkflow,
        ExitWorkflow,
    )

    # Initialize workflows
    entry_workflow = EntryWorkflow(...)
    monitoring_workflow = PositionMonitoringWorkflow(...)
    exit_workflow = ExitWorkflow(...)

    # Entry workflow
    should_enter = await entry_workflow.evaluate_entry_signal("SPY", market_data)
    if should_enter:
        execution = await entry_workflow.execute_entry("SPY", StrategyType.IRON_CONDOR, params)

    # Monitoring workflow
    decisions = await monitoring_workflow.monitor_positions()

    # Exit workflow
    result = await exit_workflow.execute_exit_decision(execution_id, decision)
    ```
"""

from src.v6.workflows.entry import EntryWorkflow
from src.v6.workflows.exit import ExitWorkflow
from src.v6.workflows.monitoring import PositionMonitoringWorkflow

__all__ = [
    "EntryWorkflow",
    "PositionMonitoringWorkflow",
    "ExitWorkflow",
]
