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
from v6.risk_manager.models import PortfolioLimitExceededError, RiskLimitsConfig
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
from v6.risk_manager.trading_workflows.regime_sizing import RegimeAwarePositionSizer
from v6.strategy_builder.decision_engine.enhanced_market_regime import EnhancedMarketRegimeDetector
from v6.strategy_builder.decision_engine.portfolio_risk import PortfolioRiskCalculator, PortfolioRisk
from v6.risk_manager.portfolio_limits import PortfolioLimitsChecker

# Alias for backward compatibility
PortfolioLimitExceeded = PortfolioLimitExceededError

logger = logger.bind(component="EntryWorkflow")


class EntryWorkflow:
    """
    Automated entry workflow for options strategies.

    Evaluates entry conditions, builds strategies, and executes entry orders.

    **Entry Signal Criteria:**
    - Portfolio has capacity (delta limits not exceeded)
    - Position count not exceeded per symbol
    - Underlying price is valid

    **NOTE:** IV Rank and VIX filters REMOVED - let StrategySelector
    scoring decide which strategy is appropriate for current conditions.

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
        portfolio_risk_calc: PortfolioRiskCalculator = None,  # NEW - portfolio risk integration
        regime_sizer: RegimeAwarePositionSizer = None,  # Optional - regime-based sizing
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
            portfolio_risk_calc: Optional PortfolioRiskCalculator for portfolio state at entry
            regime_sizer: Optional RegimeAwarePositionSizer for regime-based sizing
        """
        self.decision_engine = decision_engine
        self.execution_engine = execution_engine
        self.strategy_builder = strategy_builder  # Kept for backward compatibility
        self.strategy_repo = strategy_repo
        self.max_portfolio_delta = max_portfolio_delta
        self.max_positions_per_symbol = max_positions_per_symbol
        self.portfolio_limits = portfolio_limits
        self.portfolio_risk_calc = portfolio_risk_calc
        self.regime_sizer = regime_sizer
        self.logger = logger

    async def evaluate_entry_signal(
        self,
        symbol: str,
        market_data: dict,
    ) -> bool:
        """
        Evaluate if entry signal is valid.

        **Portfolio Constraints Only:**
        - Portfolio has delta capacity
        - Position count not exceeded
        - Underlying price is valid

        **NOTE:** IV Rank and VIX filtering REMOVED - let StrategySelector
        scoring decide which strategy is appropriate for current conditions.

        Args:
            symbol: Underlying symbol (e.g., "SPY")
            market_data: Market data dict with keys:
                - iv_rank: IV rank percentile (0-100) - logged only
                - vix: Current VIX value - logged only
                - underlying_price: Current underlying price
                - portfolio_delta: Current net portfolio delta (optional, overridden by calculator)
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

        # Log IV Rank and VIX for context (not filtered)
        self.logger.info(f"  Market context: IV Rank={iv_rank:.1f}, VIX={vix:.1f}")

        # NEW: Get portfolio risk if calculator available
        if self.portfolio_risk_calc:
            try:
                portfolio_risk: PortfolioRisk = await self.portfolio_risk_calc.calculate_portfolio_risk()
                portfolio_delta = portfolio_risk.greeks.delta
                market_data["portfolio_delta"] = portfolio_delta

                # Update position count from portfolio risk if available
                if position_count == 0 and portfolio_risk.position_count > 0:
                    # Get count for this specific symbol if available
                    symbol_delta = portfolio_risk.greeks.delta_per_symbol.get(symbol, 0.0)
                    # If symbol has delta, it has at least one position
                    if symbol_delta != 0.0:
                        position_count = 1  # Conservative estimate
                        market_data["position_count"] = position_count

                self.logger.info(
                    f"  Portfolio state: delta={portfolio_delta:.2f}, "
                    f"gamma={portfolio_risk.greeks.gamma:.2f}, "
                    f"positions={portfolio_risk.position_count}, "
                    f"symbols={portfolio_risk.symbol_count}"
                )
            except Exception as e:
                self.logger.warning(f"Failed to calculate portfolio risk: {e}, using provided portfolio_delta")
        else:
            self.logger.debug("No PortfolioRiskCalculator - using provided portfolio_delta")

        # Check 1: Portfolio has delta capacity
        if abs(portfolio_delta) < self.max_portfolio_delta:
            self.logger.debug(f"✓ Portfolio delta check passed: {portfolio_delta}")
        else:
            self.logger.info(
                f"✗ Portfolio delta check failed: {portfolio_delta} "
                f"(exceeds limit {self.max_portfolio_delta})"
            )
            return False

        # Check 2: Position count per symbol
        if position_count < self.max_positions_per_symbol:
            self.logger.debug(f"✓ Position count check passed: {position_count}")
        else:
            self.logger.info(
                f"✗ Position count check failed: {position_count} "
                f"(exceeds limit {self.max_positions_per_symbol})"
            )
            return False

        # Check 3: Underlying price is valid
        if underlying_price > 0:
            self.logger.debug(f"✓ Underlying price check passed: ${underlying_price}")
        else:
            self.logger.warning(f"✗ Underlying price invalid: ${underlying_price}")
            return False

        # All checks passed
        self.logger.info(f"✓ Entry signal validated for {symbol}")
        return True

    async def verify_strike_freshness(
        self,
        symbol: str,
        stored_price: float,
        ib_conn
    ) -> bool:
        """
        Verify underlying price against live IBKR data.

        Rejects order if stored price differs from live price by more than 0.5%.
        This prevents execution errors from stale Delta Lake snapshots.

        Args:
            symbol: Underlying symbol
            stored_price: Price from Delta Lake snapshot
            ib_conn: IBConnectionManager instance for live price fetch

        Returns:
            True if price is fresh (within 0.5%), False if stale

        Raises:
            ValueError: If live price cannot be fetched
        """
        try:
            live_price = await ib_conn.get_live_underlying_price(symbol)
        except ValueError as e:
            self.logger.error(f"Cannot verify strike freshness: {e}")
            # Fail closed - reject order if we can't verify
            raise ValueError(f"Cannot verify live price for {symbol}: {e}")

        # Calculate percentage difference
        if stored_price <= 0:
            raise ValueError(f"Invalid stored price for {symbol}: {stored_price}")

        pct_diff = abs(live_price - stored_price) / stored_price
        threshold = 0.005  # 0.5%

        if pct_diff > threshold:
            self.logger.warning(
                f"STALE DATA for {symbol}: "
                f"stored=${stored_price:.2f}, live=${live_price:.2f}, "
                f"difference={pct_diff*100:.2f}% > {threshold*100:.1f}%"
            )
            return False

        self.logger.info(
            f"✓ Price freshness verified for {symbol}: "
            f"${live_price:.2f} (diff={pct_diff*100:.2f}%)"
        )
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

        # Step 1.25: Apply regime-aware position sizing if configured
        if self.regime_sizer:
            original_quantity = params.get("quantity", 1)

            # Get market context for regime detection
            iv_rank = params.get("iv_rank", 50.0)
            vix = params.get("vix", 18.0)
            underlying_price = params.get("underlying_price", strategy.legs[0].underlying_price if strategy.legs else 0.0)

            adjusted_quantity = await self.regime_sizer.adjust_position_size(
                symbol=symbol,
                base_quantity=original_quantity,
                current_iv_rank=iv_rank,
                current_vix=vix,
                underlying_price=underlying_price,
            )

            if adjusted_quantity != original_quantity:
                self.logger.info(
                    f"Regime-aware sizing applied: {symbol} "
                    f"{original_quantity} -> {adjusted_quantity}"
                )

                # Rebuild strategy with adjusted quantity
                params["quantity"] = adjusted_quantity
                strategy = await builder.build(symbol, underlying_price, params)

                # Validate again with new quantity
                if not builder.validate(strategy):
                    raise ValueError(f"Strategy validation failed after regime adjustment: {strategy}")

        # Step 1.5: Check portfolio limits (if checker provided)
        if self.portfolio_limits:
            # Calculate position delta using Greeks if available
            position_delta = 0.0
            used_greeks = False

            # Try to use actual Greeks from strategy metadata
            if hasattr(strategy, 'metadata') and strategy.metadata:
                for leg in strategy.legs:
                    # Look for delta in metadata: leg_PUT_delta, leg_CALL_delta
                    leg_key = f"leg_{leg.right.value}_delta"
                    leg_delta = strategy.metadata.get(leg_key, 0.0)

                    if leg_delta != 0.0:
                        # Use actual Greek delta
                        used_greeks = True
                        if leg.action == LegAction.SELL:
                            # Short options: positive delta for calls, negative for puts
                            # SELLing a call gives us negative delta (we're short)
                            # SELLing a put gives us positive delta (we're short)
                            if leg.right.value == "CALL":
                                position_delta -= abs(leg_delta) * leg.quantity
                            else:  # PUT
                                position_delta += abs(leg_delta) * leg.quantity
                        else:  # BUY
                            # BUYing a call gives us positive delta
                            # BUYing a put gives us negative delta
                            if leg.right.value == "CALL":
                                position_delta += abs(leg_delta) * leg.quantity
                            else:  # PUT
                                position_delta -= abs(leg_delta) * leg.quantity

            # Fallback to quantity-based if no Greeks available
            if not used_greeks or position_delta == 0.0:
                # Simplified calculation: use quantity as delta proxy
                # SELL legs contribute positively to net delta (for credit spreads)
                # BUY legs contribute negatively
                position_delta = sum(
                    leg.quantity if leg.action == LegAction.SELL else -leg.quantity
                    for leg in strategy.legs
                )

            # Calculate position value (max risk estimation)
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
                self.logger.warning(
                    f"Entry REJECTED by portfolio limits: {reason}\n"
                    f"  Position delta: {position_delta:.2f} ({'using Greeks' if used_greeks else 'quantity-based'})\n"
                    f"  Position value: ${position_value:,.0f}\n"
                    f"  Symbol: {strategy.symbol}"
                )
                raise PortfolioLimitExceededError(
                    message=f"Portfolio limit exceeded: {reason}",
                    limit_type="portfolio_limits",
                    current_value=position_delta,
                    limit_value=0.0,
                    symbol=strategy.symbol,
                )

            self.logger.info(
                f"✓ Entry allowed by portfolio limits: "
                f"delta={position_delta:.2f}, value=${position_value:,.0f}"
            )

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

    @classmethod
    def from_config(
        cls,
        decision_engine: DecisionEngine,
        execution_engine: OrderExecutionEngine,
        strategy_repo: StrategyRepository,
        trading_config=None,
    ) -> "EntryWorkflow":
        """
        Create EntryWorkflow with portfolio integration from config.

        Factory method that creates a fully-wired EntryWorkflow with all
        portfolio components (risk calculator, limits checker) configured.

        Args:
            decision_engine: DecisionEngine for signal evaluation
            execution_engine: OrderExecutionEngine for order placement
            strategy_repo: StrategyRepository for persistence
            trading_config: Optional trading config dict with keys:
                - max_portfolio_delta: Maximum portfolio delta (default: 50.0)
                - max_per_symbol_delta: Max delta per symbol (default: 25.0)
                - max_portfolio_gamma: Maximum portfolio gamma (default: 2.0)
                - max_single_position_pct: Max position as % (default: 0.02)
                - max_correlated_pct: Max correlated exposure % (default: 0.05)
                - max_positions_per_symbol: Max positions per symbol (default: 5)

        Returns:
            EntryWorkflow with portfolio risk calculator and limits checker wired

        Example:
            >>> workflow = EntryWorkflow.from_config(
            ...     decision_engine=decision_engine,
            ...     execution_engine=execution_engine,
            ...     strategy_repo=strategy_repo
            ... )
        """
        # Set default limits if not provided
        if trading_config is None:
            trading_config = {}

        # Extract limits with defaults
        max_portfolio_delta = trading_config.get("max_portfolio_delta", 50.0)
        max_per_symbol_delta = trading_config.get("max_per_symbol_delta", max_portfolio_delta * 0.5)
        max_portfolio_gamma = trading_config.get("max_portfolio_gamma", 2.0)
        max_single_position_pct = trading_config.get("max_single_position_pct", 0.02)
        max_correlated_pct = trading_config.get("max_correlated_pct", 0.05)
        max_positions_per_symbol = trading_config.get("max_positions_per_symbol", 5)

        # Create portfolio risk calculator
        portfolio_risk_calc = PortfolioRiskCalculator()

        # Create portfolio limits checker
        limits = RiskLimitsConfig(
            max_portfolio_delta=max_portfolio_delta,
            max_per_symbol_delta=max_per_symbol_delta,
            max_portfolio_gamma=max_portfolio_gamma,
            max_single_position_pct=max_single_position_pct,
            max_correlated_pct=max_correlated_pct,
            total_exposure_cap=None,  # No cap by default
        )

        portfolio_limits = PortfolioLimitsChecker(
            risk_calculator=portfolio_risk_calc,
            limits=limits,
        )

        return cls(
            decision_engine=decision_engine,
            execution_engine=execution_engine,
            strategy_repo=strategy_repo,
            portfolio_risk_calc=portfolio_risk_calc,
            portfolio_limits=portfolio_limits,
            max_portfolio_delta=max_portfolio_delta,
            max_positions_per_symbol=max_positions_per_symbol,
        )
