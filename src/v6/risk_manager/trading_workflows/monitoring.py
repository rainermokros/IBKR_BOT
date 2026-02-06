"""
Position Monitoring Workflow for Automated Strategy Execution

This module provides the PositionMonitoringWorkflow class that monitors
open positions, evaluates decision rules, and generates alerts.

Key features:
- Fetch all open positions from StrategyRepository
- Evaluate each position with DecisionEngine
- Generate alerts via AlertManager for non-HOLD decisions
- Run every 30 seconds (configurable)
- Return decision results for all positions

Usage:
    from v6.workflows import PositionMonitoringWorkflow

    # Initialize
    monitoring = PositionMonitoringWorkflow(
        decision_engine=decision_engine,
        alert_manager=alert_manager,
        strategy_repo=strategy_repo,
    )

    # Monitor all open positions
    decisions = await monitoring.monitor_positions()

    # Monitor single position
    decision = await monitoring.monitor_position(execution_id="123")
"""

import asyncio

from loguru import logger

from v6.system_monitor.alert_system import AlertManager
from v6.strategy_builder.decision_engine.engine import DecisionEngine
from v6.strategy_builder.decision_engine.models import Decision, DecisionAction, Urgency
from v6.risk_manager.trailing_stop import TrailingStopConfig, TrailingStopManager, TrailingStopAction
from v6.strategy_builder.models import StrategyExecution
from v6.strategy_builder.repository import StrategyRepository
from v6.strategy_builder.performance_tracker import StrategyPerformanceTracker
from v6.system_monitor.data.performance_metrics_persistence import PerformanceMetricsTable, PerformanceWriter

logger = logger.bind(component="PositionMonitoringWorkflow")


class PositionMonitoringWorkflow:
    """
    Automated position monitoring workflow.

    Monitors open positions, evaluates decision rules, and generates alerts.

    **Monitoring Process:**
    1. Fetch all open strategies from StrategyRepository
    2. For each strategy:
       - Get latest position snapshot (Greeks, UPL, DTE)
       - Call decision_engine.evaluate(snapshot, market_data)
       - Create alert via alert_manager if not HOLD
       - Return dict mapping strategy_id → Decision

    **Market Data Requirements:**
    - Greeks: delta, gamma, theta, vega
    - P&L: upl, upl_percent
    - Time: dte_current
    - Volatility: iv_rank, vix
    - Portfolio: portfolio_delta, delta_per_symbol

    **Alert Generation:**
    - Alerts created for non-HOLD decisions
    - Alert severity based on decision urgency
    - Alert type based on decision action

    Attributes:
        decision_engine: DecisionEngine for decision evaluation
        alert_manager: AlertManager for alert generation
        strategy_repo: StrategyRepository for position data
        trailing_stops: Optional TrailingStopManager for trailing stop management
        monitoring_interval: Seconds between monitoring cycles (default: 30)
    """

    def __init__(
        self,
        decision_engine: DecisionEngine,
        alert_manager: AlertManager,
        strategy_repo: StrategyRepository,
        trailing_stops: TrailingStopManager | None = None,
        monitoring_interval: int = 30,
    ):
        """
        Initialize position monitoring workflow.

        Args:
            decision_engine: DecisionEngine for decision evaluation
            alert_manager: AlertManager for alert generation
            strategy_repo: StrategyRepository for position data
            trailing_stops: Optional TrailingStopManager for trailing stop management
            monitoring_interval: Seconds between monitoring cycles
        """
        self.decision_engine = decision_engine
        self.alert_manager = alert_manager
        self.strategy_repo = strategy_repo
        self.trailing_stops = trailing_stops
        self.performance_tracker = performance_tracker
        self.monitoring_interval = monitoring_interval
        self.logger = logger

    async def monitor_positions(self) -> dict[str, Decision]:
        """
        Monitor all open positions and evaluate decisions.

        Fetches all open strategies from StrategyRepository, evaluates each
        with DecisionEngine, and generates alerts for non-HOLD decisions.

        Returns:
            Dict mapping strategy_execution_id to Decision

        Example:
            >>> decisions = await monitoring.monitor_positions()
            >>> for exec_id, decision in decisions.items():
            ...     if decision.action != DecisionAction.HOLD:
            ...         print(f"{exec_id}: {decision.action.value}")
        """
        self.logger.info("Starting position monitoring cycle")

        # Fetch all open strategies
        open_strategies = await self.strategy_repo.get_open_strategies()

        if not open_strategies:
            self.logger.info("No open strategies to monitor")
            return {}

        self.logger.info(f"Monitoring {len(open_strategies)} open strategies")

        # Evaluate each strategy
        decisions = {}

        for strategy in open_strategies:
            try:
                decision = await self.monitor_position(strategy.execution_id)
                decisions[strategy.execution_id] = decision

            except Exception as e:
                self.logger.error(
                    f"Failed to monitor position {strategy.execution_id}: {e}"
                )
                # Continue with next position
                continue

        # Log summary
        action_counts = {}
        for decision in decisions.values():
            action = decision.action.value
            action_counts[action] = action_counts.get(action, 0) + 1

        self.logger.info(
            f"Monitoring cycle complete: {len(decisions) positions, "
            f"actions={action_counts}"
        )

        # Write UPL to position_updates for historical tracking
        if self.performance_tracker:
            try:
                # Get current prices (simplified - using entry prices for now)
                # In production, this would fetch real-time market data
                current_prices = {}
                for strategy in open_strategies:
                    if hasattr(strategy, 'entry_params') and strategy.entry_params:
                        # Extract entry price from premium
                        entry_price = strategy.entry_params.get('premium_received', 0)
                        current_prices[strategy.execution_id] = entry_price

                # Calculate UPL
                unrealized_pnl_dict = self.performance_tracker.calculate_unrealized_pnl(current_prices)

                # Write to position_updates
                await self.performance_tracker.write_unrealized_pnl_to_position_updates(
                    unrealized_pnl_dict,
                    current_prices
                )
                self.logger.debug("✓ Wrote UPL to position_updates")
            except Exception as e:
                self.logger.warning(f"Failed to write UPL to position_updates: {e}")

        return decisions

    async def monitor_position(
        self,
        strategy_execution_id: str,
    ) -> Decision:
        """
        Monitor a single position and evaluate decision.

        Fetches position data, evaluates with DecisionEngine, and generates
        alert if decision is not HOLD.

        Args:
            strategy_execution_id: Strategy execution ID to monitor

        Returns:
            Decision with action, reason, rule, and urgency

        Raises:
            ValueError: If strategy not found
        """
        self.logger.debug(f"Monitoring position: {strategy_execution_id[:8]}...")

        # Fetch strategy execution
        execution = await self.strategy_repo.get_execution(strategy_execution_id)

        if execution is None:
            raise ValueError(f"Strategy execution not found: {strategy_execution_id}")

        # Build position snapshot for DecisionEngine
        # Note: In production, this would fetch latest Greeks from Delta Lake
        # For now, we'll create a mock snapshot from execution data
        snapshot = self._create_snapshot(execution)

        # Update trailing stop (if enabled for this position)
        # This happens BEFORE decision engine evaluation so trailing stop
        # triggers take priority over other decision rules
        if self.trailing_stops:
            stop = self.trailing_stops.get_stop(strategy_execution_id)
            if stop:
                # Get current premium from snapshot
                # Note: In production, this would be fetched from Greeks table
                current_premium = snapshot.get("current_premium", execution.entry_params.get("premium_received", 0.0))

                # Update trailing stop
                new_stop, action = stop.update(current_premium)

                if action == TrailingStopAction.TRIGGER:
                    # Trailing stop triggered - create CLOSE decision immediately
                    self.logger.warning(
                        f"Trailing stop TRIGGERED for {strategy_execution_id[:8]}...: "
                        f"stop={new_stop:.2f}, current={current_premium:.2f}"
                    )

                    return Decision(
                        action=DecisionAction.CLOSE,
                        reason=f"Trailing stop triggered at {new_stop:.2f} (current premium: {current_premium:.2f})",
                        rule="TrailingStop",
                        urgency=Urgency.IMMEDIATE,
                        metadata={
                            "stop_premium": new_stop,
                            "current_premium": current_premium,
                            "highest_premium": stop.highest_premium,
                            "entry_premium": stop.entry_premium,
                        },
                    )

                elif action == TrailingStopAction.ACTIVATE:
                    self.logger.info(
                        f"Trailing stop ACTIVATED for {strategy_execution_id[:8]}...: "
                        f"stop={new_stop:.2f}"
                    )

                elif action == TrailingStopAction.UPDATE:
                    self.logger.debug(
                        f"Trailing stop UPDATED for {strategy_execution_id[:8]}...: "
                        f"stop={new_stop:.2f}"
                    )

        # Fetch market data
        # Note: In production, this would fetch from market data feed
        # For now, we'll use placeholder data
        market_data = await self._fetch_market_data(execution.symbol)

        # Evaluate decision
        decision = await self.decision_engine.evaluate(snapshot, market_data)

        self.logger.info(
            f"Decision for {strategy_execution_id[:8]}...: "
            f"{decision.action.value} ({decision.rule}) - {decision.reason}"
        )

        # Generate alert if not HOLD
        # Note: DecisionEngine already creates alert if alert_manager is configured
        # So we don't need to duplicate that here

        return decision

    def enable_trailing_stop(
        self,
        execution_id: str,
        entry_premium: float,
        config: TrailingStopConfig | None = None,
    ) -> None:
        """
        Enable trailing stop for a position.

        Adds a trailing stop for the specified position. The trailing stop will
        be automatically updated during position monitoring.

        Args:
            execution_id: Strategy execution ID
            entry_premium: Entry premium for the position
            config: Optional trailing stop configuration (uses default if None)

        Raises:
            RuntimeError: If TrailingStopManager not configured
            ValueError: If trailing stop already exists for position

        Example:
            >>> monitoring.enable_trailing_stop(
            ...     execution_id="abc123",
            ...     entry_premium=100.0
            ... )
        """
        if self.trailing_stops is None:
            raise RuntimeError("TrailingStopManager not configured")

        self.trailing_stops.add_trailing_stop(execution_id, entry_premium, config)

        self.logger.info(
            f"Enabled trailing stop for {execution_id[:8]}...: "
            f"entry_premium={entry_premium:.2f}"
        )

    async def start_monitoring_loop(self):
        """
        Start continuous monitoring loop.

        Runs monitor_positions() every monitoring_interval seconds.
        Runs until cancelled.

        Usage:
            >>> task = asyncio.create_task(monitoring.start_monitoring_loop())
            >>> # Later: task.cancel()
        """
        self.logger.info(
            f"Starting monitoring loop (interval={self.monitoring_interval}s)"
        )

        while True:
            try:
                await self.monitor_positions()
                await asyncio.sleep(self.monitoring_interval)

            except asyncio.CancelledError:
                self.logger.info("Monitoring loop cancelled")
                break

            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                # Wait before retrying
                await asyncio.sleep(self.monitoring_interval)

    def _create_snapshot(self, execution: StrategyExecution):
        """
        Create position snapshot from StrategyExecution.

        Converts StrategyExecution to a format compatible with DecisionEngine.
        In production, this would fetch latest Greeks from Delta Lake.

        Args:
            execution: StrategyExecution with leg data

        Returns:
            Dict with position data for DecisionEngine
        """
        # Calculate net Greeks from legs
        # Note: This is simplified. In production, fetch from Greeks table.
        net_delta = sum(
            leg.fill_price or 0.0
            for leg in execution.legs
            if leg.status.value == "filled"
        )

        # Calculate DTE from first leg
        dte_current = 0
        if execution.legs and execution.legs[0].expiration:
            from datetime import date

            today = date.today()
            dte_current = (execution.legs[0].expiration - today).days

        # Create snapshot
        snapshot = {
            "strategy_execution_id": execution.execution_id,
            "symbol": execution.symbol,
            "strategy_type": execution.strategy_type.value,
            "entry_date": execution.entry_time.strftime("%Y-%m-%d"),
            "dte_current": dte_current,
            "net_delta": net_delta,
            "net_gamma": 0.0,  # Would fetch from Greeks table
            "net_theta": 0.0,  # Would fetch from Greeks table
            "net_vega": 0.0,  # Would fetch from Greeks table
            "upl": 0.0,  # Would fetch from Greeks table
            "upl_percent": 0.0,  # Would fetch from Greeks table
            "iv_avg": 0.0,  # Would fetch from Greeks table
            "legs": [],  # Would populate from leg Greeks
        }

        return snapshot

    async def _fetch_market_data(self, symbol: str) -> dict:
        """
        Fetch market data for symbol.

        In production, this would fetch from market data feed (VIX, IV, etc.).
        For now, returns placeholder data.

        Args:
            symbol: Underlying symbol

        Returns:
            Dict with market data for DecisionEngine
        """
        # Placeholder market data
        # In production, fetch from:
        # - VIX index
        # - IV rank calculation
        # - Underlying price change
        # - Portfolio delta from PortfolioRiskCalculator

        market_data = {
            "vix": 18.0,  # Would fetch from VIX index
            "iv_rank": 50.0,  # Would calculate from IV history
            "iv_change_percent": 0.0,  # Would calculate from entry IV
            "1h_change": 0.0,  # Would fetch from market data
            "iv_percentile": 0.5,  # Would calculate from IV history
            "portfolio_delta": 0.0,  # Would fetch from PortfolioRiskCalculator
            "delta_per_symbol": {},  # Would fetch from PortfolioRiskCalculator
        }

        return market_data
