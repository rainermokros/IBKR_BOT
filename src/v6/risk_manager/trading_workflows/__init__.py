"""
Entry, Exit, and Monitoring Workflows

This package provides automated workflows for options trading execution:

- EntryWorkflow: Evaluate entry signals, build strategies, execute entry orders
- PositionMonitoringWorkflow: Monitor open positions, evaluate decisions, generate alerts
- ExitWorkflow: Execute exit decisions (CLOSE, ROLL, HOLD), close all positions

Example:
    ```python
    from v6.risk_manager.trading_workflows import (
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

from v6.risk_manager.trading_workflows.entry import EntryWorkflow
from v6.risk_manager.trading_workflows.exit import ExitWorkflow
from v6.risk_manager.trading_workflows.monitoring import PositionMonitoringWorkflow

__all__ = [
    "EntryWorkflow",
    "PositionMonitoringWorkflow",
    "ExitWorkflow",
]
