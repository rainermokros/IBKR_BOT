# 45-21 DTE Framework - Files Created/Modified

## Implementation Date
2026-01-30

---

## Configuration Files

### Modified: `v6/config/strategy_deltas.yaml`
- **What was added:** IV rank adjustments and DTE configuration
- **New sections:**
  - `iv_rank_adjustments`: 4 tiers (very_high, high, moderate, low)
  - `entry_dte`: Entry DTE target (45 days)
  - `exit_dte`: Exit DTE target (21 days)

---

## New Source Files

### Created: `v6/src/v6/indicators/__init__.py`
- **Purpose:** Indicators package initialization
- **Exports:** `IVRankCalculator`

### Created: `v6/src/v6/indicators/iv_rank.py`
- **Purpose:** IV rank calculation and delta adjustment
- **Classes:** `IVRankCalculator`
- **Key Methods:**
  - `calculate(symbol)`: Calculate IV rank (0-100)
  - `adjust_delta(base_delta, iv_rank, strategy_type)`: Adjust delta targets
  - `get_iv_tier(iv_rank)`: Get IV tier configuration
  - `should_use_debit_spreads(iv_rank)`: Check debit spread preference

### Created: `v6/src/v6/strategies/iron_condor_builder_45_21.py`
- **Purpose:** Build Iron Condors using 45-21 DTE framework
- **Classes:** `IronCondorBuilder45_21`
- **Key Methods:**
  - `build(symbol, underlying_price, option_chain, quantity)`: Build IC
  - `validate(strategy)`: Validate Iron Condor
  - `_find_strike_with_delta(...)`: Find strike at target delta
  - `_get_delta(strike, option_chain)`: Get delta for strike

### Created: `v6/src/v6/strategies/credit_spread_builder_45_21.py`
- **Purpose:** Build credit spreads using 45-21 DTE framework
- **Classes:** `CreditSpreadBuilder45_21`
- **Key Methods:**
  - `build_bull_put_spread(...)`: Build bullish put spread
  - `build_bear_call_spread(...)`: Build bearish call spread
  - `validate(strategy)`: Validate credit spread

### Created: `v6/src/v6/strategies/wheel_builder_45_21.py`
- **Purpose:** Build wheel strategy components
- **Classes:** `WheelStrategyBuilder`
- **Key Methods:**
  - `build_cash_secured_put(...)`: Build CSP (Stage 1)
  - `build_covered_call(...)`: Build covered call (Stage 2)
  - `validate(strategy)`: Validate wheel component

### Created: `v6/src/v6/execution/entry_executor.py`
- **Purpose:** Execute strategy entries with validation
- **Classes:** `EntryExecutor`
- **Key Methods:**
  - `enter_iron_condor(...)`: Enter Iron Condor position
  - `enter_bull_put_spread(...)`: Enter bull put spread
  - `enter_bear_call_spread(...)`: Enter bear call spread
  - `enter_cash_secured_put(...)`: Enter cash-secured put
  - `_validate_entry(strategy)`: Validate before entry
  - `_get_underlying_price(symbol)`: Get current price

---

## Modified Source Files

### Modified: `v6/src/v6/strategies/__init__.py`
- **What was added:** Exports for new 45-21 builders
- **New exports:**
  - `IronCondorBuilder45_21`
  - `CreditSpreadBuilder45_21`
  - `WheelStrategyBuilder`

### Modified: `v6/src/v6/execution/__init__.py`
- **What was added:** Export for entry executor
- **New exports:**
  - `EntryExecutor`

---

## Test Files

### Created: `v6/tests/test_iv_rank_calculator.py`
- **Purpose:** Test IV rank calculator
- **Test classes:**
  - `TestIVRankCalculation`: IV rank calculation tests
  - `TestDeltaAdjustment`: Delta adjustment tests
  - `TestIVTierDetermination`: IV tier tests
  - `TestDebitSpreadDecision`: Debit spread preference tests

### Created: `v6/tests/test_delta_adjustment.py`
- **Purpose:** Test delta-based builders
- **Test classes:**
  - `TestIronCondorDeltaAdjustment`: Iron Condor delta tests
  - `TestCreditSpreadDeltaAdjustment`: Credit spread delta tests
  - `TestWingWidthCalculations`: Wing width tests

### Created: `v6/tests/test_iron_condor_entry.py`
- **Purpose:** Test entry executor
- **Test classes:**
  - `TestEntryExecutor`: Entry executor tests
  - `TestEntryValidation`: Entry validation tests
  - `TestIntegration`: Integration tests

---

## Documentation Files

### Created: `v6/45_21_DTE_IMPLEMENTATION_SUMMARY.md`
- **Purpose:** Complete implementation summary
- **Contents:**
  - Implementation status
  - Phase-by-phase details
  - Key design decisions
  - Usage examples
  - Success metrics

### Created: `v6/45_21_DTE_QUICKSTART.md`
- **Purpose:** Quick start guide for developers
- **Contents:**
  - Core concepts
  - Basic usage
  - Option chain format
  - Strategy builders
  - Validation
  - Configuration
  - Testing
  - Troubleshooting
  - Best practices

### Created: `v6/45_21_DTE_FILES_SUMMARY.md` (This file)
- **Purpose:** Summary of all files created/modified
- **Contents:**
  - Configuration files
  - Source files
  - Test files
  - Documentation files

---

## File Tree

```
v6/
├── config/
│   └── strategy_deltas.yaml          # MODIFIED: Added IV rank adjustments
├── src/v6/
│   ├── indicators/
│   │   ├── __init__.py               # NEW: Package init
│   │   └── iv_rank.py                # NEW: IV rank calculator
│   ├── strategies/
│   │   ├── __init__.py               # MODIFIED: Added new builders
│   │   ├── iron_condor_builder_45_21.py      # NEW: IC builder
│   │   ├── credit_spread_builder_45_21.py    # NEW: Credit spread builder
│   │   └── wheel_builder_45_21.py            # NEW: Wheel builder
│   └── execution/
│       ├── __init__.py               # MODIFIED: Added entry executor
│       └── entry_executor.py         # NEW: Entry executor
├── tests/
│   ├── test_iv_rank_calculator.py    # NEW: IV rank tests
│   ├── test_delta_adjustment.py      # NEW: Delta adjustment tests
│   └── test_iron_condor_entry.py     # NEW: Entry flow tests
├── 45_21_DTE_IMPLEMENTATION_SUMMARY.md  # NEW: Implementation summary
├── 45_21_DTE_QUICKSTART.md              # NEW: Quick start guide
└── 45_21_DTE_FILES_SUMMARY.md           # NEW: This file
```

---

## Summary Statistics

- **Configuration files modified:** 1
- **New source files created:** 6
  - 1 indicator module
  - 3 strategy builders
  - 1 execution module
  - 2 package __init__ files
- **Source files modified:** 2
  - 1 strategies __init__
  - 1 execution __init__
- **Test files created:** 3
- **Documentation files created:** 3
- **Total lines of code:** ~2,500+ lines
- **Total lines of tests:** ~800+ lines

---

## Module Dependencies

```
entry_executor.py
    ├── iv_rank.py (IVRankCalculator)
    ├── iron_condor_builder_45_21.py (IronCondorBuilder45_21)
    ├── credit_spread_builder_45_21.py (CreditSpreadBuilder45_21)
    ├── wheel_builder_45_21.py (WheelStrategyBuilder)
    └── engine.py (OrderExecutionEngine)

iron_condor_builder_45_21.py
    ├── iv_rank.py (IVRankCalculator)
    └── models.py (Strategy, LegSpec, etc.)

credit_spread_builder_45_21.py
    ├── iv_rank.py (IVRankCalculator)
    └── models.py (Strategy, LegSpec, etc.)

wheel_builder_45_21.py
    ├── iv_rank.py (IVRankCalculator)
    └── models.py (Strategy, LegSpec, etc.)

iv_rank.py
    ├── strategy_deltas.yaml (config)
    └── market_bars (DeltaTable)
```

---

## Key Features Implemented

### IV Rank Calculator
✅ Calculates IV rank from 60-day historical data
✅ Adjusts delta targets based on IV rank tiers
✅ Determines debit vs credit spread preference
✅ Returns default IV rank (50) when data unavailable

### Iron Condor Builder
✅ Delta-based strike selection (16-20 delta, IV-adjusted)
✅ Percentage-based wing widths (2% of ATM price)
✅ Delta balance validation (≤0.05 difference)
✅ Strike structure validation (LP < SP < SC < LC)

### Credit Spread Builders
✅ Bull put spread builder (30 delta, IV-adjusted)
✅ Bear call spread builder (30 delta, IV-adjusted)
✅ Percentage-based spread width (1% of ATM price)
✅ 2-leg validation

### Wheel Strategy Builder
✅ Cash-secured put builder (35 delta for assignment)
✅ Covered call builder (22 delta for income)
✅ Shares requirement validation
✅ Wheel stage tracking

### Entry Executor
✅ Orchestrates entry flow for all strategies
✅ Delta balance validation
✅ Wing width validation
✅ Strike structure validation
✅ Dry run mode support

---

## Next Steps

1. **Integration Testing:** Test with real IB API data
2. **Option Chain Integration:** Connect to real IB option chain data
3. **Backtesting:** Compare with current entry approach
4. **Paper Trading:** Test in paper trading environment
5. **Exit Logic:** Implement 21 DTE exit framework (separate work)
6. **Position Monitoring:** Implement monitoring and rolling (separate work)

---

## Maintenance Notes

- **Configuration:** Edit `v6/config/strategy_deltas.yaml` to adjust parameters
- **Testing:** Run `pytest v6/tests/test_*` to verify functionality
- **Documentation:** Update `45_21_DTE_QUICKSTART.md` for user-facing changes
- **Logs:** Check logs for IV rank calculation warnings and errors

---

**Implementation Status:** ✅ COMPLETE (ENTRY FRAMEWORK ONLY)

**Scope:** Entry components only (position monitoring, rolling, and exit triggers are separate work)

**Date Completed:** 2026-01-30
