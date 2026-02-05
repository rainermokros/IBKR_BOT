"""
Option Assignment Monitoring

Monitors Interactive Brokers account for option assignment events and triggers
immediate emergency closure of affected strategies.

Critical for preventing:
- Naked positions from broken strategies
- Margin calls from assigned stock positions
- Unlimited loss scenarios

Assignment Detection:
- IB API: openOrder() callback (order status changes)
- IB API: position() callback (position changes)
- Reconciliation: Delta Lake vs IB discrepancies

Assignment Response:
1. IMMEDIATE detection (< 1 second)
2. CRITICAL alert notification
3. EMERGENCY_CLOSE of entire strategy at MARKET
4. Bypass all normal decision rules
5. Accept slippage - priority is speed
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from logging import getLogger
from typing import Optional

from v6.system_monitor.alert_system.manager import AlertManager
from v6.system_monitor.data.repositories import StrategyRepository
from v6.execution.engine import OrderExecutionEngine
from v6.models.decisions import Decision, DecisionAction, Urgency
from v6.models.strategy import Strategy
from v6.workflows.exit import ExitWorkflow

logger = getLogger(__name__)


class AssignmentType(str, Enum):
    """Type of assignment."""

    EARLY = "EARLY"  # Assignment before expiration (dividend plays, etc.)
    EXPIRATION = "EXPIRATION"  # Assignment at expiration


@dataclass(slots=True)
class Assignment:
    """
    Option assignment event.

    Attributes:
        assignment_id: Unique identifier for this assignment event
        conid: IB contract ID of assigned option
        symbol: Underlying symbol
        right: Option type (CALL or PUT)
        strike: Strike price
        quantity: Number of contracts assigned
        assignment_type: EARLY or EXPIRATION
        execution_id: Strategy execution ID
        strategy_id: Strategy ID
        leg_id: Leg execution ID
        timestamp: When assignment was detected
        stock_position: Stock position created (+long or -short)
        metadata: Additional information
    """

    assignment_id: str
    conid: int
    symbol: str
    right: str
    strike: float
    quantity: int
    assignment_type: AssignmentType
    execution_id: str
    strategy_id: str
    leg_id: str
    timestamp: datetime = field(default_factory=datetime.now)
    stock_position: Optional[int] = None  # Positive = long, Negative = short
    metadata: dict = field(default_factory=dict)

    def __str__(self) -> str:
        """String representation for logging."""
        return (
            f"{self.symbol} {self.right} ${self.strike} "
            f"({self.quantity} contracts) - {self.assignment_type.value}"
        )


class AssignmentMonitor:
    """
    Monitor for option assignment events.

    Listens to IB API callbacks and reconciliation events to detect
    when short options are assigned, triggering immediate emergency
    closure of affected strategies.

    Response Strategy:
    1. Detect assignment (< 1 second)
    2. Send CRITICAL alert
    3. Close strategy at MARKET immediately
    4. Bypass all normal rules
    5. Accept slippage (speed > price optimization)

    Usage:
        ```python
        monitor = AssignmentMonitor(
            ib_wrapper=ib_wrapper,
            exit_workflow=exit_workflow,
            strategy_repo=strategy_repo,
            alert_manager=alert_manager,
        )

        # Start monitoring (runs in background)
        await monitor.start()

        # Stop monitoring
        await monitor.stop()
        ```
    """

    def __init__(
        self,
        ib_wrapper: any,  # IB API wrapper (EWrapper implementation)
        exit_workflow: ExitWorkflow,
        strategy_repo: StrategyRepository,
        alert_manager: AlertManager,
        enabled: bool = True,
    ):
        """
        Initialize assignment monitor.

        Args:
            ib_wrapper: IB API wrapper with EWrapper callbacks
            exit_workflow: Exit workflow for emergency closure
            strategy_repo: Strategy repository for marking broken strategies
            alert_manager: Alert manager for critical notifications
            enabled: Whether monitoring is active (default: True)
        """
        self.ib_wrapper = ib_wrapper
        self.exit_workflow = exit_workflow
        self.strategy_repo = strategy_repo
        self.alert_manager = alert_manager
        self.enabled = enabled

        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False

        self.logger = logger

        # Register IB API callbacks if wrapper provided
        if self.ib_wrapper:
            self._register_ib_callbacks()

    def _register_ib_callbacks(self) -> None:
        """
        Register callbacks with IB API wrapper.

        Hooks into openOrder() and position() callbacks to detect
        assignment events in real-time.
        """
        try:
            # Register openOrder callback
            if hasattr(self.ib_wrapper, "openOrder"):
                original_open_order = self.ib_wrapper.openOrder

                def wrapped_open_order(order, order_state):
                    """Wrapped callback that detects assignment."""
                    # Call original
                    if original_open_order:
                        original_open_order(order, order_state)

                    # Check for assignment
                    asyncio.create_task(
                        self._check_order_for_assignment(order, order_state)
                    )

                self.ib_wrapper.openOrder = wrapped_open_order
                self.logger.info("Registered openOrder callback for assignment detection")

            # Register position callback
            if hasattr(self.ib_wrapper, "position"):
                original_position = self.ib_wrapper.position

                def wrapped_position(account, contract, position, avg_cost):
                    """Wrapped callback that detects position changes."""
                    # Call original
                    if original_position:
                        original_position(account, contract, position, avg_cost)

                    # Check for assignment
                    asyncio.create_task(
                        self._check_position_for_assignment(
                            contract, position, account
                        )
                    )

                self.ib_wrapper.position = wrapped_position
                self.logger.info("Registered position callback for assignment detection")

        except Exception as e:
            self.logger.error(f"Failed to register IB callbacks: {e}")

    async def start(self) -> None:
        """
        Start assignment monitoring.

        Starts background task to monitor for assignments.
        """
        if not self.enabled:
            self.logger.info("Assignment monitoring is disabled")
            return

        if self._running:
            self.logger.warning("Assignment monitor already running")
            return

        self._running = True
        self.logger.info("Assignment monitor started")

    async def stop(self) -> None:
        """Stop assignment monitoring."""
        self._running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        self.logger.info("Assignment monitor stopped")

    async def _check_order_for_assignment(
        self, order: any, order_state: any
    ) -> None:
        """
        Check order update for assignment indication.

        IB API indicators:
        - Order status changes to Filled
        - Order was for an option position
        - Position size goes to zero (assigned/exercised)

        Args:
            order: IB order object
            order_state: IB order state object
        """
        try:
            # Check if this is an option order
            if not hasattr(order, "contract") or not hasattr(
                order.contract, "secType"
            ):
                return

            if order.contract.secType != "OPT":
                return  # Not an option

            # Check if order indicates assignment
            # Assignments show as order fills with zero remaining position
            if hasattr(order_state, "remaining") and order_state.remaining == 0:
                # This might be an assignment - verify with position check
                await self._verify_assignment_from_order(order, order_state)

        except Exception as e:
            self.logger.error(f"Error checking order for assignment: {e}")

    async def _verify_assignment_from_order(
        self, order: any, order_state: any
    ) -> None:
        """
        Verify if order fill indicates assignment by checking current positions.

        Args:
            order: IB order object
            order_state: IB order state object
        """
        try:
            # Get current positions from IB
            if not hasattr(self.ib_wrapper, "get_positions"):
                return

            positions = await self.ib_wrapper.get_positions()

            # Look for the option position - if it's gone or changed, might be assignment
            conid = order.contract.conId
            symbol = order.contract.symbol

            # Check if option position exists
            option_position = None
            for pos in positions:
                if hasattr(pos, "contract") and pos.contract.conId == conid:
                    option_position = pos
                    break

            # If option position disappeared or went to zero - possible assignment
            if (
                not option_position
                or (hasattr(option_position, "position") and option_position.position == 0)
            ):
                # Check if stock position appeared (assignment indicator)
                stock_position = None
                for pos in positions:
                    if (
                        hasattr(pos, "contract")
                        and pos.contract.secType == "STK"
                        and pos.contract.symbol == symbol
                    ):
                        stock_position = pos
                        break

                # If stock position appeared, this is likely an assignment
                if stock_position and hasattr(stock_position, "position"):
                    await self._handle_detected_assignment(
                        conid=conid,
                        symbol=symbol,
                        right=order.contract.right,
                        strike=order.contract.strike,
                        quantity=abs(int(order.totalQuantity)),
                        stock_position=int(stock_position.position),
                    )

        except Exception as e:
            self.logger.error(f"Error verifying assignment from order: {e}")

    async def _check_position_for_assignment(
        self, contract: any, position: float, account: str
    ) -> None:
        """
        Check position update for assignment indication.

        Assignment indicators:
        - Option position disappears (was > 0, now 0)
        - Stock position appears (was 0, now != 0)
        - Both happen for same symbol

        Args:
            contract: IB contract object
            position: Current position size
            account: Account ID
        """
        try:
            # Check if this is a stock position (could be from assignment)
            if hasattr(contract, "secType") and contract.secType == "STK":
                # Stock position appeared or changed - check if from assignment
                if abs(position) > 0:
                    await self._check_if_assignment_stock(
                        symbol=contract.symbol,
                        stock_position=int(position),
                        conid=contract.conId,
                    )

        except Exception as e:
            self.logger.error(f"Error checking position for assignment: {e}")

    async def _check_if_assignment_stock(
        self, symbol: str, stock_position: int, conid: int
    ) -> None:
        """
        Check if stock position is from option assignment.

        Looks for:
        - Short options on same symbol that disappeared
        - Correlation with option legs in open strategies

        Args:
            symbol: Underlying symbol
            stock_position: Stock position size (+long or -short)
            conid: IB contract ID for stock
        """
        try:
            # Get open strategies with this symbol
            open_executions = await self.strategy_repo.get_open_executions_by_symbol(
                symbol
            )

            for execution in open_executions:
                # Check if any legs are short options
                for leg in execution.strategy.legs:
                    # Short option that might have been assigned
                    if (
                        leg.action.value == "SELL"
                        and leg.status == "FILLED"
                        and leg.right in ["CALL", "PUT"]
                    ):
                        # Determine if this assignment makes sense
                        is_put = leg.right == "PUT"

                        # PUT assignment → Long stock (positive position)
                        # CALL assignment → Short stock (negative position)
                        expected_stock_positive = is_put

                        if (stock_position > 0 and expected_stock_positive) or (
                            stock_position < 0 and not expected_stock_positive
                        ):
                            # This looks like an assignment
                            await self._handle_detected_assignment(
                                conid=leg.conid or 0,
                                symbol=symbol,
                                right=leg.right,
                                strike=leg.strike,
                                quantity=leg.quantity * 100,  # Contracts to shares
                                stock_position=stock_position,
                                execution_id=execution.execution_id,
                                strategy_id=execution.strategy_id,
                                leg_id=leg.leg_id,
                            )

        except Exception as e:
            self.logger.error(f"Error checking if assignment stock: {e}")

    async def _handle_detected_assignment(
        self,
        conid: int,
        symbol: str,
        right: str,
        strike: float,
        quantity: int,
        stock_position: int,
        execution_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
        leg_id: Optional[str] = None,
    ) -> None:
        """
        Handle detected assignment event.

        CRITICAL RESPONSE:
        1. Log CRITICAL alert
        2. Send notification (email, Slack, etc.)
        3. Mark strategy as BROKEN
        4. Create IMMEDIATE CLOSE decision
        5. Execute emergency close at MARKET

        Args:
            conid: IB contract ID
            symbol: Underlying symbol
            right: Option right (CALL/PUT)
            strike: Strike price
            quantity: Number of shares/ccontracts
            stock_position: Stock position created
            execution_id: Strategy execution ID (if known)
            strategy_id: Strategy ID (if known)
            leg_id: Leg ID (if known)
        """
        try:
            # Determine assignment type
            # If we don't have execution_id, check from repository
            if not execution_id:
                execution_id = await self._find_execution_for_leg(conid)

            if execution_id:
                execution = await self.strategy_repo.get_execution(execution_id)

                if execution:
                    strategy_id = execution.strategy_id
                    strategy = execution.strategy

                    # Determine DTE to classify assignment type
                    dte = (strategy.legs[0].expiration - datetime.now().date()).days
                    assignment_type = (
                        AssignmentType.EXPIRATION if dte <= 1 else AssignmentType.EARLY
                    )

                    # Create assignment event
                    assignment = Assignment(
                        assignment_id=f"asn_{datetime.now().timestamp()}_{conid}",
                        conid=conid,
                        symbol=symbol,
                        right=right,
                        strike=strike,
                        quantity=quantity // 100 if quantity > 100 else quantity,
                        assignment_type=assignment_type,
                        execution_id=execution_id,
                        strategy_id=strategy_id,
                        leg_id=leg_id or "",
                        stock_position=stock_position,
                    )

                    # Log CRITICAL
                    self.logger.critical(
                        f"ASSIGNMENT DETECTED: {assignment} - "
                        f"Execution: {execution_id[:8]}... - "
                        f"Executing EMERGENCY CLOSE at MARKET"
                    )

                    # Send critical alert
                    await self.alert_manager.send_critical_alert(
                        f"ASSIGNMENT DETECTED: {assignment}\n"
                        f"Strategy: {strategy_id}\n"
                        f"Execution: {execution_id}\n"
                        f"Stock Position: {stock_position} shares\n"
                        f"Executing EMERGENCY CLOSE at MARKET immediately\n"
                        f"Time: {assignment.timestamp.isoformat()}"
                    )

                    # Mark strategy as BROKEN
                    await self.strategy_repo.mark_execution_broken(
                        execution_id=execution_id,
                        reason=f"OPTION ASSIGNMENT: {assignment}",
                        metadata={
                            "assignment": assignment.__dict__,
                            "stock_position": stock_position,
                        },
                    )

                    # Execute EMERGENCY CLOSE at MARKET
                    await self._execute_emergency_close(execution, strategy, assignment)

        except Exception as e:
            self.logger.error(f"Error handling detected assignment: {e}", exc_info=True)

    async def _find_execution_for_leg(self, conid: int) -> Optional[str]:
        """
        Find execution ID for a given leg conid.

        Args:
            conid: IB contract ID

        Returns:
            Execution ID if found, None otherwise
        """
        try:
            executions = await self.strategy_repo.get_open_executions()

            for execution in executions:
                for leg in execution.legs:
                    if leg.conid == conid:
                        return execution.execution_id

        except Exception as e:
            self.logger.error(f"Error finding execution for leg {conid}: {e}")

        return None

    async def _execute_emergency_close(
        self, execution: any, strategy: Strategy, assignment: Assignment
    ) -> None:
        """
        Execute emergency close of broken strategy at MARKET.

        IMMEDIATE PRIORITY:
        - Bypass all decision rules
        - Bypass trailing stops
        - Bypass circuit breaker (for this close only)
        - Close ALL remaining legs at MARKET
        - Accept slippage - SPEED is priority

        Args:
            execution: Strategy execution
            strategy: Strategy model
            assignment: Assignment event
        """
        try:
            # Create EMERGENCY CLOSE decision
            decision = Decision(
                action=DecisionAction.CLOSE,
                reason=(
                    f"EMERGENCY CLOSE: Option assignment detected - {assignment}. "
                    f"Closing strategy at MARKET immediately to prevent unlimited loss."
                ),
                rule="AssignmentMonitor_Emergency",
                urgency=Urgency.IMMEDIATE,
                metadata={
                    "assignment": assignment.__dict__,
                    "emergency": True,
                    "close_type": "MARKET",
                    "bypass_rules": True,
                },
            )

            # Execute emergency close via exit workflow
            self.logger.critical(
                f"Executing EMERGENCY CLOSE for {execution.execution_id[:8]}... "
                f"at MARKET (bypassing all rules)"
            )

            result = await self.exit_workflow.execute_exit_decision(
                execution=execution,
                strategy=strategy,
                decision=decision,
            )

            if result.success:
                self.logger.critical(
                    f"EMERGENCY CLOSE completed for {execution.execution_id[:8]}... - "
                    f"Action: {result.action_taken}"
                )

                # Send completion alert
                await self.alert_manager.send_critical_alert(
                    f"EMERGENCY CLOSE COMPLETED: {execution.execution_id}\n"
                    f"Assignment: {assignment}\n"
                    f"Action: {result.action_taken}\n"
                    f"Order IDs: {result.order_ids}"
                )
            else:
                self.logger.critical(
                    f"EMERGENCY CLOSE FAILED for {execution.execution_id[:8]}... - "
                    f"Error: {result.error_message}"
                )

                # Send failure alert
                await self.alert_manager.send_critical_alert(
                    f"EMERGENCY CLOSE FAILED: {execution.execution_id}\n"
                    f"Assignment: {assignment}\n"
                    f"Error: {result.error_message}\n"
                    f"MANUAL INTERVENTION REQUIRED"
                )

        except Exception as e:
            self.logger.critical(
                f"Error executing emergency close: {e}", exc_info=True
            )

            await self.alert_manager.send_critical_alert(
                f"EMERGENCY CLOSE ERROR: {execution.execution_id}\n"
                f"Error: {e}\n"
                f"MANUAL INTERVENTION REQUIRED IMMEDIATELY"
            )
