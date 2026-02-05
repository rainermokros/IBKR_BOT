"""
Entry Workflow for Automated Strategy Execution

This module provides the EntryWorkflow class that evaluates entry signals,
builds strategies, and executes entry orders.

Key features:
- Market condition evaluation (IV Rank, VIX, underlying trend)
- Portfolio constraint checking (delta limits, exposure limits)
- Strategy building via StrategyBuilder
- Order execution via OrderExecutionEngine
- Strategy persistence via StrategyRepository

Usage:
    from v6.workflows import EntryWorkflow
    from v6.strategy_builder.builders import IronCondorBuilder

    # Initialize
    entry_workflow = EntryWorkflow(
        decision_engine=decision_engine,
        execution_engine=execution_engine,
        strategy_builder=IronCondorBuilder(),
        strategy_repo=strategy_repo,
    )

    # Check if we should enter
    should_enter = await entry_workflow.evaluate_entry_signal(
        symbol="SPY",
        market_data={"iv_rank": 60, "vix": 18, "underlying_trend": "neutral"}
    )

    # Execute entry
    if should_enter:
        execution = await entry_workflow.execute_entry(
            symbol="SPY",
            strategy_type=StrategyType.IRON_CONDOR,
            params={"dte": 45, "put_width": 10, "call_width": 10}
        )
"""

from datetime import datetime
from uuid import uuid4

from loguru import logger

from v6.strategy_builder.decision_engine.engine import DecisionEngine
from v6.strategy_builder.builder_factory import StrategyBuilderFactory
from v6.system_monitor.execution_engine.engine import OrderExecutionEngine
from v6.system_monitor.execution_engine.models import Order as OrderModel
from v6.system_monitor.execution_engine.models import (
    OrderAction,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from v6.risk_manager.models import PortfolioLimitExceededError
from v6.strategy_builder.builders import StrategyBuilder
from v6.strategy_builder.models import (
    ExecutionStatus,
    LegAction,
    LegExecution,
    LegStatus,
    StrategyExecution,
    StrategyType,
)
from v6.strategy_builder.repository import StrategyRepository

# Alias for backward compatibility
PortfolioLimitExceeded = PortfolioLimitExceededError

logger = logger.bind(component="EntryWorkflow")


class EntryWorkflow:
    """
    Automated entry workflow for options strategies.

    Evaluates entry conditions, builds strategies, and executes entry orders.

    **Entry Signal Criteria:**
    - IV Rank >50 (sell premium) or <25 (buy premium)
    - VIX not in extreme range (not >35)
    - Portfolio has capacity (delta limits not exceeded)
    - No conflicting positions

    **Workflow:**
    1. evaluate_entry_signal(): Check market and portfolio conditions
    2. execute_entry(): Build strategy, place orders, save execution

    Attributes:
        decision_engine: DecisionEngine for signal evaluation
        execution_engine: OrderExecutionEngine for order placement
        strategy_builder: StrategyBuilder for strategy construction
        strategy_repo: StrategyRepository for persistence
        max_portfolio_delta: Maximum net delta allowed (default: 0.3)
        max_positions_per_symbol: Max positions per symbol (default: 5)
    """

    def __init__(
        self,
        decision_engine: DecisionEngine,
        execution_engine: OrderExecutionEngine,
        strategy_repo: StrategyRepository,
        strategy_builder: StrategyBuilder = None,  # Optional - factory used now
        max_portfolio_delta: float = 0.3,
        max_positions_per_symbol: int = 5,
        portfolio_limits=None,
    ):
        """
        Initialize entry workflow.

        Args:
            decision_engine: DecisionEngine for signal evaluation
            execution_engine: OrderExecutionEngine for order placement
            strategy_repo: StrategyRepository for persistence
            strategy_builder: DEPRECATED - StrategyBuilderFactory used instead
            max_portfolio_delta: Maximum net portfolio delta allowed
            max_positions_per_symbol: Maximum positions per symbol
            portfolio_limits: Optional PortfolioLimitsChecker for risk validation
        """
        self.decision_engine = decision_engine
        self.execution_engine = execution_engine
        self.strategy_builder = strategy_builder  # Kept for backward compatibility
        self.strategy_repo = strategy_repo
        self.max_portfolio_delta = max_portfolio_delta
        self.max_positions_per_symbol = max_positions_per_symbol
        self.portfolio_limits = portfolio_limits
        self.logger = logger

    async def evaluate_entry_signal(
        self,
        symbol: str,
        market_data: dict,
    ) -> bool:
        """
        Evaluate if entry signal is valid.

        Checks market conditions (IV Rank, VIX, underlying trend) and
        portfolio constraints (delta limits, exposure limits, position count).

        Args:
            symbol: Underlying symbol (e.g., "SPY")
            market_data: Market data dict with keys:
                - iv_rank: IV rank percentile (0-100)
                - vix: Current VIX value
                - underlying_price: Current underlying price
                - portfolio_delta: Current net portfolio delta (optional)
                - position_count: Current open positions for symbol (optional)

        Returns:
            True if entry conditions are met, False otherwise
        """
        self.logger.info(f"Evaluating entry signal for {symbol}")

        # Extract market data
        iv_rank = market_data.get("iv_rank", 0)
        vix = market_data.get("vix", 0)
        underlying_price = market_data.get("underlying_price", 0)
        portfolio_delta = market_data.get("portfolio_delta", 0.0)
        position_count = market_data.get("position_count", 0)

        # Check 1: IV Rank conditions
        # - IV Rank >50: Good for selling premium (iron condors, credit spreads)
        # - IV Rank <25: Good for buying premium (debit spreads)
        if iv_rank < 25 or iv_rank > 50:
            self.logger.debug(f"✓ IV Rank check passed: {iv_rank}")
        else:
            self.logger.info(f"✗ IV Rank check failed: {iv_rank} (not in entry range)")
            return False

        # Check 2: VIX not in extreme range
        # - VIX >35 indicates extreme volatility, avoid entries
        if vix < 35:
            self.logger.debug(f"✓ VIX check passed: {vix}")
        else:
            self.logger.info(f"✗ VIX check failed: {vix} (too high)")
            return False

        # Check 3: Portfolio has delta capacity
        if abs(portfolio_delta) < self.max_portfolio_delta:
            self.logger.debug(f"✓ Portfolio delta check passed: {portfolio_delta}")
        else:
            self.logger.info(
                f"✗ Portfolio delta check failed: {portfolio_delta} "
                f"(exceeds limit {self.max_portfolio_delta})"
            )
            return False

        # Check 4: Position count per symbol
        if position_count < self.max_positions_per_symbol:
            self.logger.debug(f"✓ Position count check passed: {position_count}")
        else:
            self.logger.info(
                f"✗ Position count check failed: {position_count} "
                f"(exceeds limit {self.max_positions_per_symbol})"
            )
            return False

        # Check 5: Underlying price is valid
        if underlying_price > 0:
            self.logger.debug(f"✓ Underlying price check passed: ${underlying_price}")
        else:
            self.logger.warning(f"✗ Underlying price invalid: ${underlying_price}")
            return False

        # All checks passed
        self.logger.info(f"✓ Entry signal validated for {symbol}")
        return True

    async def execute_entry(
        self,
        symbol: str,
        strategy_type: StrategyType,
        params: dict,
    ) -> StrategyExecution:
        """
        Execute entry for a strategy.

        Builds strategy using StrategyBuilder, validates it, places entry orders,
        and saves execution to StrategyRepository.

        Args:
            symbol: Underlying symbol
            strategy_type: Type of strategy to enter
            params: Strategy parameters (passed to StrategyBuilder.build())

        Returns:
            StrategyExecution with order IDs and status

        Raises:
            ValueError: If strategy validation fails
            RuntimeError: If order placement fails
        """
        self.logger.info(
            f"Executing entry: {symbol} {strategy_type.value} with params={params}"
        )

        # Step 1: Build strategy
        underlying_price = params.get("underlying_price", 0.0)
        if underlying_price <= 0:
            raise ValueError(f"Invalid underlying price: {underlying_price}")

        # Get the appropriate builder for this strategy type
        builder = StrategyBuilderFactory.get_builder(strategy_type)
        self.logger.debug(f"Using builder: {builder.__class__.__name__} for {strategy_type.value}")

        strategy = await builder.build(symbol, underlying_price, params)

        # Validate strategy
        if not builder.validate(strategy):
            raise ValueError(f"Strategy validation failed: {strategy}")

        self.logger.info(f"✓ Strategy built: {strategy}")

        # Step 1.5: Check portfolio limits (if checker provided)
        if self.portfolio_limits:
            # Calculate position delta (sum of SELL legs)
            # Note: This is a simplified calculation - actual delta depends on Greeks
            position_delta = sum(
                leg.quantity if leg.action == LegAction.SELL else -leg.quantity
                for leg in strategy.legs
            )

            # Calculate position value (rough estimate)
            # Use strike * quantity * 100 multiplier for options
            position_value = sum(
                abs(leg.quantity) * leg.strike * 100
                for leg in strategy.legs
            )

            # Check portfolio limits
            allowed, reason = await self.portfolio_limits.check_entry_allowed(
                new_position_delta=position_delta,
                symbol=strategy.symbol,
                position_value=position_value,
            )

            if not allowed:
                self.logger.warning(f"Entry REJECTED by portfolio limits: {reason}")
                raise PortfolioLimitExceededError(
                    message=f"Portfolio limit exceeded: {reason}",
                    limit_type="portfolio_limits",
                    current_value=0.0,
                    limit_value=0.0,
                    symbol=strategy.symbol,
                )

            self.logger.info("✓ Entry allowed by portfolio limits")

        # Step 2: Create StrategyExecution
        execution_id = str(uuid4())
        legs_execution = []

        for leg_spec in strategy.legs:
            leg_exec = LegExecution(
                leg_id=str(uuid4()),
                conid=None,  # Will be assigned when order is placed
                right=leg_spec.right,
                strike=leg_spec.strike,
                expiration=leg_spec.expiration,
                quantity=leg_spec.quantity,
                action=leg_spec.action,
                status=LegStatus.PENDING,
                fill_price=None,
                order_id=None,
                fill_time=None,
            )
            legs_execution.append(leg_exec)

        # Generate strategy_id as int (hash of strategy_id string or sequential ID)
        # For now, use a simple hash approach
        strategy_id_int = hash(strategy.strategy_id) % (10**10)  # Keep it reasonable

        execution = StrategyExecution(
            execution_id=execution_id,
            strategy_id=strategy_id_int,
            symbol=symbol,
            strategy_type=strategy_type,
            legs=legs_execution,
            entry_params=params,
            entry_time=datetime.now(),
            fill_time=None,
            close_time=None,
            status=ExecutionStatus.PENDING,
        )

        # Step 3: Place orders for each leg
        order_ids = []

        for i, (leg_spec, leg_exec) in enumerate(zip(strategy.legs, execution.legs, strict=True)):
            try:
                # Create IB contract
                import ib_async

                contract = ib_async.Option(
                    symbol=symbol,
                    right=leg_spec.right.value,
                    strike=leg_spec.strike,
                    lastTradeDateOrContractMonth=leg_spec.expiration.strftime("%Y%m%d"),
                    exchange="SMART",
                    currency="USD",
                )

                # Create order
                # Convert LegAction to OrderAction
                order_action = (
                    OrderAction.BUY
                    if leg_spec.action == LegAction.BUY
                    else OrderAction.SELL
                )

                # Use MARKET orders by default (more reliable for entry)
                # If limit_price provided, use LIMIT order
                limit_price = params.get("limit_price")
                order_type = OrderType.LIMIT if limit_price else OrderType.MARKET

                order = OrderModel(
                    order_id=str(uuid4()),
                    conid=contract.conId,
                    action=order_action,
                    quantity=leg_spec.quantity,
                    order_type=order_type,
                    limit_price=limit_price,
                    stop_price=None,
                    tif=TimeInForce.DAY,
                    status=OrderStatus.PENDING_SUBMIT,
                    filled_quantity=0,
                    avg_fill_price=None,
                    order_ref=None,
                    parent_order_id=None,
                    oca_group=f"ENTRY_{execution_id}",
                    created_at=datetime.now(),
                    filled_at=None,
                )

                # Place order
                updated_order = await self.execution_engine.place_order(
                    contract, order
                )

                # Update leg execution with order info
                leg_exec.order_id = updated_order.order_id
                leg_exec.conid = updated_order.conid
                leg_exec.status = (
                    LegStatus.FILLED
                    if updated_order.status == OrderStatus.FILLED
                    else LegStatus.PENDING
                )

                if updated_order.status == OrderStatus.FILLED:
                    leg_exec.fill_price = updated_order.avg_fill_price or 0.0
                    leg_exec.fill_time = updated_order.filled_at

                order_ids.append(updated_order.order_id)
                self.logger.info(
                    f"✓ Order placed for leg {i+1}/{len(strategy.legs)}: "
                    f"{updated_order.order_id[:8]}..."
                )

            except Exception as e:
                self.logger.error(f"Failed to place order for leg {i+1}: {e}")
                leg_exec.status = LegStatus.PENDING  # Keep as pending, will need manual intervention
                # Continue with other legs

        # Step 4: Update execution status
        all_filled = all(leg.status == LegStatus.FILLED for leg in execution.legs)
        any_filled = any(leg.status == LegStatus.FILLED for leg in execution.legs)

        if all_filled:
            execution.status = ExecutionStatus.FILLED
            execution.fill_time = datetime.now()
        elif any_filled:
            execution.status = ExecutionStatus.PARTIAL
        else:
            execution.status = ExecutionStatus.PENDING

        # Step 5: Save execution to repository
        await self.strategy_repo.save_execution(execution)

        self.logger.info(
            f"✓ Entry execution saved: {execution_id[:8]}... "
            f"(status={execution.status.value}, {len(order_ids)} orders)"
        )

        return execution
