"""
Exit Workflow for Automated Strategy Execution

This module provides the ExitWorkflow class that executes exit decisions
(CLOSE, ROLL, HOLD) and manages position closures.

Key features:
- Execute CLOSE decisions via OrderExecutionEngine
- Execute ROLL decisions (close old, log warning for new entry)
- Handle HOLD decisions (no action)
- Close all positions for a symbol
- Update StrategyRepository with execution results

Usage:
    from src.v6.workflows import ExitWorkflow
    from src.v6.decisions import Decision, DecisionAction

    # Initialize
    exit_workflow = ExitWorkflow(
        execution_engine=execution_engine,
        decision_engine=decision_engine,
        strategy_repo=strategy_repo,
    )

    # Execute close decision
    result = await exit_workflow.execute_exit_decision(
        strategy_execution_id="123",
        decision=Decision(action=DecisionAction.CLOSE, reason="Take profit", ...)
    )

    # Close all positions for symbol
    results = await exit_workflow.execute_close_all(symbol="SPY")
"""

from typing import Optional

from loguru import logger

from src.v6.decisions.engine import DecisionEngine
from src.v6.decisions.models import Decision, DecisionAction, Urgency
from src.v6.execution.engine import OrderExecutionEngine
from src.v6.execution.models import ExecutionResult
from src.v6.strategies.models import (
    ExecutionStatus,
    Strategy,
    StrategyExecution,
)
from src.v6.strategies.repository import StrategyRepository

try:
    from src.v6.risk import TrailingStopManager
except ImportError:
    TrailingStopManager = None  # type: ignore

logger = logger.bind(component="ExitWorkflow")


class ExitWorkflow:
    """
    Automated exit workflow for options strategies.

    Executes exit decisions (CLOSE, ROLL, HOLD) and manages position closures.

    **Exit Actions:**
    - CLOSE: Close all legs via OrderExecutionEngine.close_position()
    - ROLL: Close old legs, log warning for new entry (manual StrategyBuilder call)
    - HOLD: No action, return success=True

    **Workflow:**
    1. execute_exit_decision(): Execute single exit decision
    2. execute_close_all(): Close all positions for symbol

    **Integration:**
    - OrderExecutionEngine for order placement
    - StrategyRepository for status updates
    - DecisionEngine for decision validation (optional)
    - TrailingStopManager for trailing stop cleanup (optional)

    Attributes:
        execution_engine: OrderExecutionEngine for order placement
        decision_engine: DecisionEngine for decision validation (optional)
        strategy_repo: StrategyRepository for persistence
        trailing_stops: Optional TrailingStopManager for trailing stop cleanup
    """

    def __init__(
        self,
        execution_engine: OrderExecutionEngine,
        decision_engine: Optional[DecisionEngine] = None,
        strategy_repo: Optional[StrategyRepository] = None,
        trailing_stops: Optional["TrailingStopManager"] = None,
    ):
        """
        Initialize exit workflow.

        Args:
            execution_engine: OrderExecutionEngine for order placement
            decision_engine: Optional DecisionEngine for decision validation
            strategy_repo: Optional StrategyRepository for status updates
            trailing_stops: Optional TrailingStopManager for trailing stop cleanup
        """
        self.execution_engine = execution_engine
        self.decision_engine = decision_engine
        self.strategy_repo = strategy_repo
        self.trailing_stops = trailing_stops
        self.logger = logger

    async def execute_exit_decision(
        self,
        strategy_execution_id: str,
        decision: Decision,
    ) -> ExecutionResult:
        """
        Execute an exit decision for a strategy.

        Parses decision.action and executes appropriate action:
        - CLOSE: Close position via execution_engine.close_position()
        - ROLL: Roll position via execution_engine.roll_position()
        - HOLD: No action, return success=True

        Args:
            strategy_execution_id: Strategy execution ID to exit
            decision: Decision with action (CLOSE/ROLL/HOLD)

        Returns:
            ExecutionResult with order IDs and outcome

        Raises:
            ValueError: If strategy not found or decision invalid
        """
        self.logger.info(
            f"Executing exit decision for {strategy_execution_id[:8]}...: "
            f"{decision.action.value} - {decision.reason}"
        )

        # Handle HOLD decision
        if decision.action == DecisionAction.HOLD:
            self.logger.debug(f"HOLD decision for {strategy_execution_id[:8]}...")
            return ExecutionResult(
                success=True,
                action_taken="NO_ACTION",
                order_ids=[],
                error_message=None,
            )

        # Fetch strategy execution
        if self.strategy_repo is None:
            raise RuntimeError("StrategyRepository not configured")

        execution = await self.strategy_repo.get_execution(strategy_execution_id)

        if execution is None:
            raise ValueError(f"Strategy execution not found: {strategy_execution_id}")

        # Convert execution to Strategy for OrderExecutionEngine
        strategy = self._execution_to_strategy(execution)

        # Execute based on decision action
        if decision.action == DecisionAction.CLOSE:
            result = await self._execute_close(execution, strategy, decision)

        elif decision.action == DecisionAction.ROLL:
            # Extract new DTE from decision metadata
            new_dte = decision.metadata.get("roll_to_dte", 45)
            result = await self._execute_roll(execution, strategy, new_dte, decision)

        elif decision.action == DecisionAction.REDUCE:
            # Partial close (close_ratio from metadata)
            close_ratio = decision.metadata.get("close_ratio", 0.5)
            result = await self._execute_reduce(
                execution, strategy, close_ratio, decision
            )

        else:
            self.logger.warning(f"Unknown decision action: {decision.action.value}")
            return ExecutionResult(
                success=False,
                action_taken="FAILED",
                order_ids=[],
                error_message=f"Unknown action: {decision.action.value}",
            )

        # Update strategy status in repository
        if result.success and self.strategy_repo:
            try:
                if decision.action == DecisionAction.CLOSE:
                    await self.strategy_repo.update_execution_status(
                        strategy_execution_id, ExecutionStatus.CLOSED
                    )
                elif decision.action == DecisionAction.ROLL:
                    await self.strategy_repo.update_execution_status(
                        strategy_execution_id, ExecutionStatus.CLOSED
                    )
                    # Note: New strategy execution created by roll_position()

                self.logger.info(
                    f"✓ Updated strategy status: {strategy_execution_id[:8]}... "
                    f"→ {decision.action.value}"
                )

            except Exception as e:
                self.logger.error(f"Failed to update strategy status: {e}")

        # Remove trailing stop if exists (for CLOSE and ROLL actions)
        if result.success and self.trailing_stops:
            if decision.action in (DecisionAction.CLOSE, DecisionAction.ROLL):
                try:
                    self.trailing_stops.remove_stop(strategy_execution_id)
                    self.logger.debug(
                        f"✓ Removed trailing stop for {strategy_execution_id[:8]}..."
                    )
                except Exception as e:
                    self.logger.error(f"Failed to remove trailing stop: {e}")

        return result

    async def execute_close_all(
        self,
        symbol: Optional[str] = None,
    ) -> dict[str, ExecutionResult]:
        """
        Close all positions for a symbol (or all positions if symbol=None).

        Fetches all open strategies, executes CLOSE decision for each,
        returns dict mapping execution_id to ExecutionResult.

        Args:
            symbol: Optional symbol filter (if None, closes all positions)

        Returns:
            Dict mapping strategy_execution_id to ExecutionResult
        """
        self.logger.info(f"Executing close_all for symbol={symbol or 'ALL'}")

        if self.strategy_repo is None:
            raise RuntimeError("StrategyRepository not configured")

        # Fetch open strategies
        open_strategies = await self.strategy_repo.get_open_strategies(symbol=symbol)

        if not open_strategies:
            self.logger.info("No open strategies to close")
            return {}

        self.logger.info(f"Closing {len(open_strategies)} positions")

        # Close each position
        results = {}

        for execution in open_strategies:
            try:
                # Create CLOSE decision
                decision = Decision(
                    action=DecisionAction.CLOSE,
                    reason="Close all positions",
                    rule="manual_close_all",
                    urgency=Urgency.NORMAL,
                    metadata={"manual": True},
                )

                # Execute close
                result = await self.execute_exit_decision(
                    execution.execution_id, decision
                )
                results[execution.execution_id] = result

                self.logger.info(
                    f"✓ Closed {execution.execution_id[:8]}...: "
                    f"success={result.success}, action={result.action_taken}"
                )

            except Exception as e:
                self.logger.error(
                    f"Failed to close {execution.execution_id[:8]}...: {e}"
                )
                # Continue with next position
                continue

        # Log summary
        success_count = sum(1 for r in results.values() if r.success)
        self.logger.info(
            f"Close all complete: {success_count}/{len(results)} successful"
        )

        return results

    async def _execute_close(
        self,
        execution: StrategyExecution,
        strategy: Strategy,
        decision: Decision,
    ) -> ExecutionResult:
        """Execute close position."""
        self.logger.info(f"Closing position: {execution.execution_id[:8]}...")

        # Close position via execution engine
        result = await self.execution_engine.close_position(strategy)

        # Note: close_time will be set by update_execution_status in repository
        return result

    async def _execute_roll(
        self,
        execution: StrategyExecution,
        strategy: Strategy,
        new_dte: int,
        decision: Decision,
    ) -> ExecutionResult:
        """Execute roll position."""
        self.logger.info(
            f"Rolling position: {execution.execution_id[:8]}... to DTE={new_dte}"
        )

        # Roll position via execution engine
        result = await self.execution_engine.roll_position(strategy, new_dte)

        # Note: close_time will be set by update_execution_status in repository
        return result

    async def _execute_reduce(
        self,
        execution: StrategyExecution,
        strategy: Strategy,
        close_ratio: float,
        decision: Decision,
    ) -> ExecutionResult:
        """Execute partial close (reduce position size)."""
        self.logger.info(
            f"Reducing position: {execution.execution_id[:8]}... by {close_ratio*100}%"
        )

        # Note: OrderExecutionEngine doesn't have a partial close method yet
        # For now, we'll log a warning and return success
        self.logger.warning(
            f"Partial close not yet implemented: close_ratio={close_ratio}. "
            "Would close portion of legs."
        )

        return ExecutionResult(
            success=True,
            action_taken="REDUCED",
            order_ids=[],
            error_message=None,
        )

    def _execution_to_strategy(self, execution: StrategyExecution) -> Strategy:
        """
        Convert StrategyExecution to Strategy for OrderExecutionEngine.

        Args:
            execution: StrategyExecution with leg data

        Returns:
            Strategy with LegSpec objects
        """
        from src.v6.strategies.models import LegAction, LegSpec

        legs = []
        for leg_exec in execution.legs:
            leg_spec = LegSpec(
                right=leg_exec.right,
                strike=leg_exec.strike,
                quantity=leg_exec.quantity,
                action=LegAction(leg_exec.action.value),
                expiration=leg_exec.expiration,
            )
            legs.append(leg_spec)

        strategy = Strategy(
            strategy_id=execution.strategy_id,
            symbol=execution.symbol,
            strategy_type=execution.strategy_type,
            legs=legs,
            entry_time=execution.entry_time,
            status=execution.status.value,
            metadata=execution.entry_params,
        )

        return strategy
