---
phase: 09-trading-optimization
plan: 03
type: execute
wave: 1
depends_on: [9-02]
files_modified:
  - src/v6/risk_manager/trading_workflows/entry.py
  - src/v6/risk_manager/portfolio_limits.py
  - src/v6/strategy_builder/decision_engine/portfolio_risk.py
autonomous: true
user_setup: []

must_haves:
  truths:
    - "EntryWorkflow.check_portfolio_limits() calls PortfolioRiskCalculator before entry"
    - "Portfolio delta calculated from IB positions + greeks aggregation"
    - "Entry rejected when delta capacity exceeded"
    - "Position value estimated for concentration limit checking"
    - "Logging shows portfolio state at entry evaluation"
  artifacts:
    - path: "src/v6/risk_manager/trading_workflows/entry.py"
      provides: "Portfolio-aware entry validation"
      contains: "check_portfolio_limits() method"
    - path: "src/v6/risk_manager/portfolio_limits.py"
      provides: "Portfolio limit checking integration"
      exports: ["PortfolioLimitsChecker"]
    - path: "src/v6/strategy_builder/decision_engine/portfolio_risk.py"
      provides: "Portfolio risk calculation for entry decisions"
      exports: ["PortfolioRiskCalculator"]
  key_links:
    - from: "src/v6/risk_manager/trading_workflows/entry.py"
      to: "src/v6/strategy_builder/decision_engine/portfolio_risk.py"
      via: "EntryWorkflow instantiates PortfolioRiskCalculator"
      pattern: "PortfolioRiskCalculator|calculate_portfolio_risk"
    - from: "src/v6/risk_manager/trading_workflows/entry.py"
      to: "src/v6/risk_manager/portfolio_limits.py"
      via: "EntryWorkflow uses PortfolioLimitsChecker for validation"
      pattern: "PortfolioLimitsChecker|check_entry_allowed"
---

<objective>
Integrate portfolio risk calculation into the entry workflow to prevent entering
positions when portfolio limits are exceeded.

Current EntryWorkflow evaluates entry signals based on basic portfolio checks
(portfolio_delta, position_count) but doesn't use the sophisticated PortfolioRiskCalculator
that already exists for Greek-based risk assessment.

This plan wires the existing PortfolioRiskCalculator into EntryWorkflow, enabling
portfolio-level delta, gamma, and concentration limit checking before entry.

Purpose: Prevent over-concentration and excessive Greek exposure at entry time.
Output: EntryWorkflow with integrated portfolio limit checking using PortfolioRiskCalculator.
</objective>

<execution_context>
@/home/bigballs/.claude/get-shit-done/workflows/execute-plan.md
@/home/bigballs/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/09-trading-optimization/9-RESEARCH.md
@.planning/ROADMAP.md
@.planning/STATE.md

@src/v6/risk_manager/trading_workflows/entry.py
@src/v6/risk_manager/portfolio_limits.py
@src/v6/strategy_builder/decision_engine/portfolio_risk.py
@src/v6/strategy_builder/decision_engine/models.py
</context>

<tasks>

<task type="auto">
  <name>Review PortfolioRiskCalculator interface</name>
  <files>src/v6/strategy_builder/decision_engine/portfolio_risk.py</files>
  <action>
    Read and understand the PortfolioRiskCalculator interface.

    Verify:
    1. calculate_portfolio_risk() method signature
    2. PortfolioRisk result structure (greeks, exposure)
    3. How it gets position data (IB connection or repository)
    4. Dependencies required for instantiation

    Document any missing methods needed for entry workflow integration.
    If calculate_portfolio_risk() doesn't exist, note what needs to be added.

    This is a discovery task - read the file and report findings.
  </action>
  <verify>
    1. PortfolioRiskCalculator class exists
    2. calculate_portfolio_risk() method signature documented
    3. PortfolioRisk result structure understood
    4. Dependencies for instantiation identified
  </verify>
  <done>
    PortfolioRiskCalculator interface understood, integration points identified.
  </done>
</task>

<task type="auto">
  <name>Add portfolio limit checking to EntryWorkflow.evaluate_entry_signal</name>
  <files>src/v6/risk_manager/trading_workflows/entry.py</files>
  <action>
    Update EntryWorkflow.evaluate_entry_signal() to call PortfolioRiskCalculator.

    Changes to evaluate_entry_signal():
    1. Add import for PortfolioRiskCalculator
    2. Before existing checks, call portfolio_risk_calc.calculate_portfolio_risk()
    3. Extract portfolio_delta from result
    4. Pass portfolio_delta in market_data dict to existing checks
    5. Add log showing portfolio state

    Pattern:
    ```python
    from v6.strategy_builder.decision_engine.portfolio_risk import PortfolioRiskCalculator

    class EntryWorkflow:
        def __init__(
            self,
            decision_engine,
            execution_engine,
            strategy_repo,
            portfolio_risk_calc: PortfolioRiskCalculator = None,  # NEW
            # ... existing params
        ):
            # ... existing initialization
            self.portfolio_risk_calc = portfolio_risk_calc

        async def evaluate_entry_signal(self, symbol, market_data):
            # NEW: Get portfolio risk if calculator available
            if self.portfolio_risk_calc:
                portfolio_risk = await self.portfolio_risk_calc.calculate_portfolio_risk()
                portfolio_delta = portfolio_risk.greeks.delta
                market_data["portfolio_delta"] = portfolio_delta

                self.logger.info(
                    f"Portfolio state: delta={portfolio_delta:.2f}, "
                    f"gamma={portfolio_risk.greeks.gamma:.2f}"
                )
            else:
                self.logger.warning("No PortfolioRiskCalculator - using provided portfolio_delta")

            # ... existing checks use portfolio_delta from market_data
    ```

    Keep backward compatibility: work without PortfolioRiskCalculator if not provided.
  </action>
  <verify>
    1. EntryWorkflow imports PortfolioRiskCalculator
    2. __init__ accepts portfolio_risk_calc parameter
    3. evaluate_entry_signal() calls calculate_portfolio_risk()
    4. portfolio_delta added to market_data dict
    5. Logging shows portfolio state
    6. Backward compatible (works without calculator)
  </verify>
  <done>
    EntryWorkflow integrates PortfolioRiskCalculator, portfolio delta used in
    entry evaluation, logging shows portfolio state.
  </done>
</task>

<task type="auto">
  <name>Add PortfolioLimitsChecker to EntryWorkflow.execute_entry</name>
  <files>src/v6/risk_manager/trading_workflows/entry.py</files>
  <action>
    Update EntryWorkflow.execute_entry() to use PortfolioLimitsChecker for validation.

    EntryWorkflow already has portfolio_limits parameter but it's not fully wired.
    Enhance the existing check (around line 336-368):

    1. Ensure position_delta calculated correctly (sum of SELL legs delta)
    2. Ensure position_value calculated (strike * quantity * 100)
    3. Add more detailed logging for limit checking
    4. Handle PortfolioLimitExceededError with clearer messaging

    The check_entry_allowed call exists but needs:
    - Better delta calculation (use actual Greeks, not quantity)
    - Better position value estimation
    - Detailed rejection logging

    Enhancement:
    ```python
    # Step 1.5: Check portfolio limits
    if self.portfolio_limits:
        # Calculate position delta using Greeks if available
        position_delta = 0.0
        for leg in strategy.legs:
            # For SELL legs, delta contributes positively to position delta
            # Use actual leg delta if available in strategy.metadata
            leg_delta = strategy.metadata.get(f"leg_{leg.right.value}_delta", 0.0)
            if leg.action == LegAction.SELL:
                position_delta += abs(leg_delta) * leg.quantity
            else:
                position_delta -= abs(leg_delta) * leg.quantity

        # Fallback to quantity-based if no Greeks
        if position_delta == 0.0:
            position_delta = sum(
                leg.quantity if leg.action == LegAction.SELL else -leg.quantity
                for leg in strategy.legs
            )

        # Calculate position value (max risk estimation)
        position_value = sum(
            abs(leg.quantity) * leg.strike * 100
            for leg in strategy.legs
        )

        allowed, reason = await self.portfolio_limits.check_entry_allowed(
            new_position_delta=position_delta,
            symbol=strategy.symbol,
            position_value=position_value,
        )

        if not allowed:
            self.logger.warning(
                f"Entry REJECTED by portfolio limits: {reason}\n"
                f"  Position delta: {position_delta:.2f}\n"
                f"  Position value: ${position_value:,.0f}"
            )
            raise PortfolioLimitExceededError(...)
    ```

    Don't change the overall structure, just enhance the calculation accuracy.
  </action>
  <verify>
    1. Position delta uses Greek values when available
    2. Position value calculated correctly
    3. Detailed logging shows delta and value at rejection
    4. PortfolioLimitExceededError includes clear reason
    5. Existing check_entry_allowed call preserved
  </verify>
  <done>
    Portfolio limit checking uses accurate delta/value calculations, detailed
    logging shows rejection reasons, PortfolioLimitExceededError clear.
  </done>
</task>

<task type="auto">
  <name>Add factory method for creating EntryWorkflow with portfolio integration</name>
  <files>src/v6/risk_manager/trading_workflows/entry.py</files>
  <action>
    Add EntryWorkflow.from_config() factory method for easy instantiation with
    portfolio components.

    Pattern:
    ```python
    @classmethod
    def from_config(
        cls,
        decision_engine,
        execution_engine,
        strategy_repo,
        trading_config=None,
    ) -> "EntryWorkflow":
        """Create EntryWorkflow with portfolio integration from config."""
        from v6.config.trading_config import load_trading_config
        from v6.strategy_builder.decision_engine.portfolio_risk import PortfolioRiskCalculator
        from v6.risk_manager.portfolio_limits import PortfolioLimitsChecker
        from v6.risk_manager.models import RiskLimitsConfig

        # Load config if not provided
        if trading_config is None:
            trading_config = load_trading_config()

        # Create portfolio components
        portfolio_risk_calc = PortfolioRiskCalculator(...)  # Add required params
        portfolio_limits = PortfolioLimitsChecker(
            risk_calculator=portfolio_risk_calc,
            limits=RiskLimitsConfig(
                max_portfolio_delta=trading_config.trading_limits.max_portfolio_delta,
                max_per_symbol_delta=trading_config.trading_limits.max_portfolio_delta * 0.5,
                max_portfolio_gamma=2.0,
                max_single_position_pct=trading_config.trading_limits.max_single_position_pct,
                max_correlated_pct=trading_config.trading_limits.max_correlated_pct,
            )
        )

        return cls(
            decision_engine=decision_engine,
            execution_engine=execution_engine,
            strategy_repo=strategy_repo,
            portfolio_risk_calc=portfolio_risk_calc,
            portfolio_limits=portfolio_limits,
            max_portfolio_delta=trading_config.trading_limits.max_portfolio_delta,
            max_positions_per_symbol=trading_config.trading_limits.max_positions_per_symbol,
        )
    ```

    This makes it easy to create EntryWorkflow with all portfolio components wired.
  </action>
  <verify>
    1. from_config() classmethod exists
    2. Creates PortfolioRiskCalculator with required params
    3. Creates PortfolioLimitsChecker with config limits
    4. Returns EntryWorkflow with all components wired
    5. Imports added for all required classes
  </verify>
  <done>
    EntryWorkflow.from_config() factory method creates fully integrated instance
    with portfolio risk calculator and limits checker.
  </done>
</task>

</tasks>

<verification>
Overall phase checks:
1. Python syntax check: python -m py_compile src/v6/risk_manager/trading_workflows/entry.py
2. Import test: python -c "from v6.risk_manager.trading_workflows.entry import EntryWorkflow"
3. Verify PortfolioRiskCalculator import works
4. Verify PortfolioLimitsChecker import works
5. Check from_config() method exists and callable
</verification>

<success_criteria>
1. EntryWorkflow uses PortfolioRiskCalculator for portfolio state at entry
2. Portfolio delta calculated and used in entry decision
3. PortfolioLimitsChecker validates entry against all limits
4. Rejection logging shows clear reason (delta, concentration, etc.)
5. from_config() creates fully wired EntryWorkflow
6. Backward compatible (works without portfolio components)
</success_criteria>

<output>
After completion, create `.planning/phases/09-trading-optimization/9-03-SUMMARY.md`
</output>
