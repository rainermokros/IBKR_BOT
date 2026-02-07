---
phase: 09-trading-optimization
plan: 04
type: execute
wave: 2
depends_on: [9-02]
files_modified:
  - src/v6/strategy_builder/smart_strike_selector.py
  - src/v6/data/option_snapshots.py
  - src/v6/strategy_builder/strategy_selector.py
autonomous: true
user_setup: []

must_haves:
  truths:
    - "SmartStrikeSelector calculates IV skew ratio from option chain data"
    - "Skew ratio influences strike selection (high put skew -> prefer puts, high call skew -> prefer calls)"
    - "Skew normalized by time to expiration and ATM IV"
    - "Logging shows skew ratio and selected strikes"
    - "StrategySelector uses skew-aware strikes when building strategies"
  artifacts:
    - path: "src/v6/strategy_builder/smart_strike_selector.py"
      provides: "IV skew calculation and skew-aware strike selection"
      contains: "calculate_skew_ratio, select_strike_with_skew"
    - path: "src/v6/data/option_snapshots.py"
      provides: "IV data access for skew calculation"
      exports: ["OptionSnapshotsTable"]
    - path: "src/v6/strategy_builder/strategy_selector.py"
      provides: "Skew-aware strategy building"
      contains: "skew_ratio in metadata"
  key_links:
    - from: "src/v6/strategy_builder/smart_strike_selector.py"
      to: "src/v6/data/option_snapshots.py"
      via: "get_iv_for_strike() reads IV from Delta Lake"
      pattern: "option_snapshots|OptionSnapshotsTable"
    - from: "src/v6/strategy_builder/strategy_selector.py"
      to: "src/v6/strategy_builder/smart_strike_selector.py"
      via: "SmartStrikeSelector used with skew parameter"
      pattern: "SmartStrikeSelector|skew_ratio"
---

<objective>
Add IV skew-aware strike selection to improve strategy credit received.

Current SmartStrikeSelector uses binary search based on delta only, not considering
relative IV between puts and calls. This misses opportunities to sell the expensive
side of the skew.

This plan adds skew calculation (IV ratio: put IV / call IV) and uses it to bias
strike selection toward the higher-IV side, increasing credit received on entry.

Purpose: Improve strategy profitability by selling expensive options (high IV skew).
Output: Skew-aware SmartStrikeSelector with IV ratio calculation.
</objective>

<execution_context>
@/home/bigballs/.claude/get-shit-done/workflows/execute-plan.md
@/home/bigballs/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/09-trading-optimization/9-RESEARCH.md
@.planning/ROADMAP.md
@.planning/STATE.md

@src/v6/strategy_builder/smart_strike_selector.py
@src/v6/data/option_snapshots.py
@src/v6/strategy_builder/strategy_selector.py
</context>

<tasks>

<task type="auto">
  <name>Add IV skew calculation to SmartStrikeSelector</name>
  <files>src/v6/strategy_builder/smart_strike_selector.py</files>
  <action>
    Add skew calculation methods to SmartStrikeSelector class.

    Add after _round_to_interval() method:

    ```python
    def calculate_skew_ratio(
        self,
        symbol: str,
        underlying_price: float,
        target_dte: int,
        get_iv_func: callable,
    ) -> float:
        """
        Calculate IV skew ratio (put IV / call IV).

        Returns:
            float: Skew ratio (>1.0 = put skew elevated, <1.0 = call skew elevated)

        Interpretation:
            > 1.2: High put skew - market fears downside, favor selling puts
            < 0.8: High call skew - market fears upside, favor selling calls
            ~1.0: Balanced skew
        """
        # Get IV for symmetric OTM puts and calls
        std_dev = self.calculate_std_deviation(underlying_price)
        put_strike = self._round_to_interval(underlying_price - std_dev)
        call_strike = self._round_to_interval(underlying_price + std_dev)

        try:
            put_iv = get_iv_func(put_strike, "PUT")
            call_iv = get_iv_func(call_strike, "CALL")

            if call_iv <= 0 or put_iv <= 0:
                logger.warning(f"Invalid IV values: put_iv={put_iv}, call_iv={call_iv}")
                return 1.0  # Neutral skew

            skew_ratio = put_iv / call_iv
            logger.info(
                f"Skew ratio: {skew_ratio:.2f} "
                f"(put IV: {put_iv:.2%} @ ${put_strike:.0f}, "
                f"call IV: {call_iv:.2%} @ ${call_strike:.0f})"
            )
            return skew_ratio

        except Exception as e:
            logger.warning(f"Failed to calculate skew ratio: {e}")
            return 1.0  # Default to neutral

    def adjust_target_delta_for_skew(
        self,
        target_delta: float,
        skew_ratio: float,
        option_right: str,
    ) -> float:
        """
        Adjust target delta based on skew ratio.

        When skew is elevated, we can accept higher delta (closer to ATM)
        on the expensive side to receive more credit.

        Args:
            target_delta: Base target delta (e.g., 0.20)
            skew_ratio: IV put/call ratio
            option_right: "PUT" or "CALL"

        Returns:
            Adjusted target delta
        """
        # No adjustment for balanced skew
        if 0.8 <= skew_ratio <= 1.2:
            return target_delta

        # High put skew (>1.2): puts expensive, accept higher delta on puts
        if skew_ratio > 1.2 and option_right == "PUT":
            adjusted = target_delta * 1.2  # Accept 20% higher delta
            logger.debug(f"Skew adjustment: put delta {target_delta:.2f} -> {adjusted:.2f} (high put skew)")
            return min(adjusted, 0.30)  # Cap at 0.30

        # High call skew (<0.8): calls expensive, accept higher delta on calls
        if skew_ratio < 0.8 and option_right == "CALL":
            adjusted = target_delta * 1.2  # Accept 20% higher delta
            logger.debug(f"Skew adjustment: call delta {target_delta:.2f} -> {adjusted:.2f} (high call skew)")
            return min(adjusted, 0.30)  # Cap at 0.30

        return target_delta
    ```

    These methods enable skew-aware strike selection.
  </action>
  <verify>
    1. calculate_skew_ratio() method exists
    2. Returns put_iv / call_iv ratio
    3. Handles invalid IV values gracefully
    4. adjust_target_delta_for_skew() method exists
    5. Adjusts delta based on skew direction
  </verify>
  <done>
    SmartStrikeSelector has skew calculation methods, returns put/call IV ratio,
    adjusts target delta based on skew direction.
  </done>
</task>

<task type="auto">
  <name>Add IV data retrieval to SmartStrikeSelector</name>
  <files>src/v6/data/option_snapshots.py</files>
  <action>
    Add method to get IV for specific strike from option_snapshots Delta Lake table.

    If option_snapshots.py exists, add:

    ```python
    def get_iv_for_strike(self, symbol: str, strike: float, right: str, expiry: date) -> Optional[float]:
        """
        Get IV for specific strike from latest option snapshot.

        Args:
            symbol: Underlying symbol
            strike: Strike price
            right: "PUT" or "CALL"
            expiry: Expiration date

        Returns:
            IV as decimal (0.20 = 20%) or None if not found
        """
        import polars as pl

        # Read latest snapshot for this strike
        df = pl.scan_delta(self.table_path)
            .filter(pl.col("symbol") == symbol)
            .filter(pl.col("strike") == strike)
            .filter(pl.col("right") == right)
            .filter(pl.col("expiry") == expiry.strftime("%Y-%m-%d"))
            .filter(pl.col("timestamp") > (datetime.now() - timedelta(hours=1)))
            .select(["iv"])
            .sort("timestamp", descending=True)
            .limit(1)
            .collect()

        if len(df) > 0:
            return df.row(0)[0] / 100.0  # Convert to decimal
        return None
    ```

    If option_snapshots.py doesn't have this structure, adapt to existing pattern.
    The goal is to provide IV lookup for skew calculation.
  </action>
  <verify>
    1. get_iv_for_strike() method exists in option_snapshots module
    2. Reads from Delta Lake with partition filtering
    3. Returns IV as decimal (0.20 = 20%)
    4. Returns None if data not found
  </verify>
  <done>
    OptionSnapshotsTable provides IV lookup by strike/right/expiry, uses Delta
    Lake lazy loading for efficient queries.
  </done>
</task>

<task type="auto">
  <name>Integrate skew into StrategySelector strategy building</name>
  <files>src/v6/strategy_builder/strategy_selector.py</files>
  <action>
    Update StrategySelector to calculate and use skew ratio when building strategies.

    Modify _build_iron_condor, _build_bull_put_spread, _build_bear_call_spread:

    1. Calculate skew ratio before building
    2. Pass skew ratio to SmartStrikeSelector
    3. Store skew_ratio in strategy metadata
    4. Log skew-aware decisions

    Pattern:
    ```python
    async def _build_iron_condor(self, symbol, quantity, target_dte, use_smart_lookup):
        # Get underlying price
        underlying_price = await self._get_underlying_price(symbol)

        # NEW: Calculate skew ratio
        from v6.data.option_snapshots import OptionSnapshotsTable
        snapshots = OptionSnapshotsTable()
        expiry = date.today() + timedelta(days=target_dte)

        def get_iv_for_skew(strike, right):
            return snapshots.get_iv_for_strike(symbol, strike, right, expiry) or 0.20

        skew_ratio = self.ic_builder.strike_selector.calculate_skew_ratio(
            symbol=symbol,
            underlying_price=underlying_price,
            target_dte=target_dte,
            get_iv_func=get_iv_for_skew,
        )

        # Build iron condor with skew-aware deltas
        params = {
            'dte': target_dte,
            'put_width': 10,
            'call_width': 10,
            'quantity': quantity,
            'skew_ratio': skew_ratio,  # NEW
            'underlying_price': underlying_price,
        }

        strategy = await self.ic_builder.build(symbol, underlying_price, params)

        # Add skew ratio to metadata
        strategy.metadata['skew_ratio'] = skew_ratio
        strategy.metadata['skew_interpretation'] = (
            'high_put_skew' if skew_ratio > 1.2 else
            'high_call_skew' if skew_ratio < 0.8 else
            'neutral'
        )

        return strategy
    ```

    Apply similar pattern to _build_bull_put_spread and _build_bear_call_spread.
  </action>
  <verify>
    1. StrategySelector imports OptionSnapshotsTable
    2. _build_iron_condor calculates skew_ratio
    3. skew_ratio passed to builder params
    4. skew_ratio stored in strategy.metadata
    5. skew_interpretation added to metadata
    6. Similar changes in vertical spread builders
  </verify>
  <done>
    StrategySelector calculates skew ratio, uses it for strike selection,
    stores skew metrics in strategy metadata for analysis.
  </done>
</task>

<task type="auto">
  <name>Update SmartStrikeSelector binary search to use skew-adjusted delta</name>
  <files>src/v6/strategy_builder/smart_strike_selector.py</files>
  <action>
    Modify find_strike_with_delta_binary_search to accept and use skew_ratio.

    Update signature and add skew adjustment:

    ```python
    def find_strike_with_delta_binary_search(
        self,
        symbol: str,
        right: str,
        target_delta: float,
        underlying_price: float,
        get_delta_func: callable,
        skew_ratio: float = 1.0,  # NEW parameter
        max_iterations: int = 10,
    ) -> Tuple[float, float]:
        """
        Find strike with target delta using binary search.

        Args:
            skew_ratio: IV put/call ratio, used to adjust target delta

        Returns:
            (strike, delta) tuple
        """
        # NEW: Adjust target delta based on skew
        adjusted_delta = self.adjust_target_delta_for_skew(
            target_delta=target_delta,
            skew_ratio=skew_ratio,
            option_right=right,
        )

        logger.info(
            f"Binary search for {right} strike: target_delta={target_delta:.2f}, "
            f"skew_ratio={skew_ratio:.2f}, adjusted_delta={adjusted_delta:.2f}"
        )

        # Use adjusted_delta for search
        # ... rest of binary search logic using adjusted_delta
    ```

    Ensure the binary search uses the adjusted delta for finding strikes.
  </action>
  <verify>
    1. find_strike_with_delta_binary_search accepts skew_ratio parameter
    2. Calls adjust_target_delta_for_skew() with skew_ratio
    3. Uses adjusted_delta in binary search
    4. Logs show original and adjusted delta
  </verify>
  <done>
    SmartStrikeSelector binary search uses skew-adjusted delta, strikes selected
    based on skew-aware targets.
  </done>
</task>

</tasks>

<verification>
Overall phase checks:
1. Python syntax check: python -m py_compile src/v6/strategy_builder/smart_strike_selector.py
2. Import test: python -c "from v6.strategy_builder.smart_strike_selector import SmartStrikeSelector"
3. Verify skew calculation methods exist
4. Verify get_iv_for_strike in option_snapshots module
5. Check StrategySelector stores skew_ratio in metadata
</verification>

<success_criteria>
1. SmartStrikeSelector calculates put/call IV ratio correctly
2. Skew ratio influences strike selection (higher delta on expensive side)
3. StrategySelector calculates skew before building strategies
4. Strategy metadata includes skew_ratio and skew_interpretation
5. Logging shows skew-aware decisions
6. No errors when IV data unavailable (graceful fallback to neutral)
</success_criteria>

<output>
After completion, create `.planning/phases/09-trading-optimization/9-04-SUMMARY.md`
</output>
