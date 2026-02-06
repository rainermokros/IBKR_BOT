# 45-21 DTE Delta-Based Options ENTRY Framework - Implementation Summary

## Overview

Implemented **ENTRY-ONLY** components for the 45-21 DTE delta-based options trading framework as specified in the implementation plan.

**Date:** 2026-01-30
**Framework:** 45-21 DTE (Enter at 45 DTE, Exit at 21 DTE)
**Focus:** Delta-based strike selection with IV rank adjustment

---

## Implementation Status: ✅ COMPLETE

All phases of the ENTRY framework have been successfully implemented.

---

## Phase 1: Configuration Enhancement ✅

### File: `v6/config/strategy_deltas.yaml`

Added IV rank-based delta adjustments to the existing configuration:

```yaml
# IV Rank Adjustments for Entry
iv_rank_adjustments:
  very_high_iv:  # IVR 75-100%
    ivr_min: 75
    ivr_max: 100
    iron_condor_short_delta_min: 0.08
    iron_condor_short_delta_max: 0.12
    credit_spread_short_delta_min: 0.15
    credit_spread_short_delta_max: 0.20
    description: "Very expensive premiums, sell further OTM (8-12 delta)"

  high_iv:  # IVR 50-75%
    ivr_min: 50
    ivr_max: 75
    iron_condor_short_delta_min: 0.16
    iron_condor_short_delta_max: 0.20
    credit_spread_short_delta_min: 0.25
    credit_spread_short_delta_max: 0.35
    description: "Standard Tastytrade guidelines (16-20 delta)"

  moderate_iv:  # IVR 25-50%
    ivr_min: 25
    ivr_max: 50
    iron_condor_short_delta_min: 0.25
    iron_condor_short_delta_max: 0.30
    credit_spread_short_delta_min: 0.30
    credit_spread_short_delta_max: 0.40
    description: "Fairly priced, move closer to ATM (25-30 delta)"

  low_iv:  # IVR 0-25%
    ivr_min: 0
    ivr_max: 25
    use_debit_spreads: true
    description: "Cheap premiums, use debit spreads instead of credit"

# Entry DTE Target
entry_dte:
  target: 45
  min: 35
  max: 60

# Exit DTE Target
exit_dte:
  target: 21
  min: 14
  max: 28
```

---

## Phase 2: IV Rank Calculator ✅

### File: `v6/src/v6/indicators/iv_rank.py`

**Class:** `IVRankCalculator`

**Features:**
- Calculates IV rank from historical market data (60-day lookback)
- Formula: `IVR = (Current IV - 52-week Low IV) / (52-week High IV - 52-week Low IV) × 100`
- Adjusts delta targets based on IV rank tiers
- Determines when to use debit vs credit spreads

**Key Methods:**
- `calculate(symbol)`: Calculate IV rank for a symbol
- `adjust_delta(base_delta, iv_rank, strategy_type)`: Adjust delta target based on IV
- `get_iv_tier(iv_rank)`: Get IV tier configuration
- `should_use_debit_spreads(iv_rank)`: Check if debit spreads preferred

**Usage:**
```python
from v6.indicators import IVRankCalculator

calculator = IVRankCalculator(lookback_days=60)
ivr = calculator.calculate('SPY')  # Returns 0-100
adjusted_delta = calculator.adjust_delta(0.18, ivr, 'iron_condor')
```

---

## Phase 3: Delta-Based Strategy Builders ✅

### File: `v6/src/v6/strategies/iron_condor_builder_45_21.py`

**Class:** `IronCondorBuilder45_21`

**Features:**
- Builds Iron Condors at 45 DTE using delta-based strike selection
- Percentage-based wing widths (2% of ATM price)
- Delta balance validation (≤0.05 difference between PUT/CALL shorts)
- IV rank adjustment for delta targets

**Entry Process:**
1. Calculate IV rank
2. Adjust delta target based on IV rank
3. Select short PUT at target delta
4. Select short CALL at target delta
5. Calculate wings (2% of ATM price)
6. Validate delta balance (≤0.05)
7. Return strategy specification

**Metadata Generated:**
```python
{
    'framework': '45_21',
    'iv_rank': 60.0,
    'target_delta': 0.18,
    'short_put_delta': -0.18,
    'short_call_delta': 0.18,
    'delta_balance': 0.01,  # Difference between PUT and CALL deltas
    'put_wing_width': 10.0,
    'call_wing_width': 10.0,
    'target_wing_width': 10.0,
    'entry_dte': 45,
}
```

---

### File: `v6/src/v6/strategies/credit_spread_builder_45_21.py`

**Class:** `CreditSpreadBuilder45_21`

**Features:**
- Builds bull put spreads and bear call spreads
- Delta-based strike selection (25-35 delta, IV-adjusted)
- Percentage-based spread width (1% of ATM price)
- 30-delta standard for directional premium selling

**Methods:**
- `build_bull_put_spread()`: Bullish credit spread (sell OTM put, buy further OTM put)
- `build_bear_call_spread()`: Bearish credit spread (sell OTM call, buy further OTM call)

**Metadata Generated:**
```python
{
    'framework': '45_21',
    'direction': 'bullish',  # or 'bearish'
    'spread_type': 'bull_put_spread',  # or 'bear_call_spread'
    'iv_rank': 60.0,
    'target_delta': 0.30,
    'short_put_delta': -0.30,
    'spread_width': 5.0,
    'target_spread_width': 5.0,
    'entry_dte': 45,
}
```

---

### File: `v6/src/v6/strategies/wheel_builder_45_21.py`

**Class:** `WheelStrategyBuilder`

**Features:**
- Stage 1: Cash-secured puts (30-40 delta for assignment)
- Stage 2: Covered calls (15-30 delta for income)
- Delta-based strike selection for both stages

**Methods:**
- `build_cash_secured_put()`: Build CSP to acquire shares at discount
- `build_covered_call()`: Build CC for income while holding shares

**Metadata Generated (CSP):**
```python
{
    'wheel_stage': 'cash_secured_put',
    'target_delta': 0.35,
    'short_put_delta': -0.35,
    'shares_required': 100,
    'description': 'Stage 1: Sell CSP to acquire shares at discount',
}
```

---

## Phase 4: Integration with Execution System ✅

### File: `v6/src/v6/execution/entry_executor.py`

**Class:** `EntryExecutor`

**Features:**
- Orchestrates entry process for 45-21 DTE strategies
- Gets market data (price, IV rank, option chain)
- Builds strategy with delta-based builder
- Validates delta balance and wing widths
- Submits to execution engine (when implemented)

**Methods:**
- `enter_iron_condor()`: Enter Iron Condor position
- `enter_bull_put_spread()`: Enter bull put spread
- `enter_bear_call_spread()`: Enter bear call spread
- `enter_cash_secured_put()`: Enter cash-secured put

**Entry Process:**
1. Get current market data (price, IV rank, option chain)
2. Build strategy with delta-based builder
3. Validate delta balance (≤0.05 difference)
4. Validate wing widths (within 2% of target)
5. Submit to execution engine
6. Return execution result

---

### File: `v6/src/v6/strategies/__init__.py`

**Updated exports to include:**
```python
from v6.strategies.iron_condor_builder_45_21 import IronCondorBuilder45_21
from v6.strategies.credit_spread_builder_45_21 import CreditSpreadBuilder45_21
from v6.strategies.wheel_builder_45_21 import WheelStrategyBuilder
```

### File: `v6/src/v6/execution/__init__.py`

**Updated exports to include:**
```python
from v6.execution.entry_executor import EntryExecutor
```

---

## Phase 5: Testing & Validation ✅

### File: `v6/tests/test_iv_rank_calculator.py`

**Tests:**
- `test_iv_rank_calculation_mid_range`: IV rank calculation
- `test_iv_rank_bounds`: IV rank bounded between 0-100
- `test_iv_rank_no_data`: Returns default value when no data
- `test_delta_adjustment_very_high_iv`: Delta adjusts to 8-12 range
- `test_delta_adjustment_high_iv`: Delta adjusts to 16-20 range
- `test_delta_adjustment_moderate_iv`: Delta adjusts to 25-30 range
- `test_delta_adjustment_low_iv`: Warns about debit spreads
- `test_delta_adjustment_credit_spread`: Credit spread delta adjustment
- `test_delta_adjustment_unknown_strategy`: Returns base delta
- `test_get_iv_tier_*`: IV tier determination tests
- `test_should_use_debit_spreads_*`: Debit spread preference tests

---

### File: `v6/tests/test_delta_adjustment.py`

**Tests:**
- `test_iron_condor_build_with_18_delta`: IC built with correct delta
- `test_iron_condor_delta_balance`: Delta balance ≤0.05
- `test_iron_condor_strike_structure`: Valid strike structure
- `test_iron_condor_wing_widths`: Wing widths within tolerance
- `test_iron_condor_validation`: Validation passes
- `test_bull_put_spread_*`: Bull put spread tests
- `test_bear_call_spread_*`: Bear call spread tests
- `test_wing_width_percentage_spy`: 2% wing width for SPY
- `test_wing_width_min_max_limits`: Min/max limits respected

---

### File: `v6/tests/test_iron_condor_entry.py`

**Tests:**
- `test_enter_iron_condor_dry_run`: Entry in dry run mode
- `test_iron_condor_delta_accuracy`: Deltas within ±0.03 of target
- `test_iron_condor_delta_balance`: Delta balance ≤0.05
- `test_iron_condor_wing_widths`: Wing widths within ±2.0 of target
- `test_iron_condor_strike_structure`: Valid strike structure
- `test_enter_bull_put_spread`: Bull put spread entry
- `test_enter_bear_call_spread`: Bear call spread entry
- `test_entry_validation_passes`: Valid entry passes validation
- `test_entry_validation_invalid_framework`: Invalid framework raises error
- `test_complete_entry_flow`: Complete entry flow test
- `test_multiple_strategies_same_symbol`: Multiple strategies for same symbol

---

## Key Design Decisions

### 1. IV Rank Lookback Period
**Decision:** 60 days
**Reasoning:** Balances responsiveness with stability

### 2. Delta Tolerance for Strike Selection
**Decision:** ±0.03 delta
**Reasoning:** Allows flexibility while maintaining target range

### 3. Wing Width Percentage
**Decision:** 2% of ATM price (with 1-3% limits)
**Reasoning:** Consistent risk across different asset prices

### 4. Delta Balance Threshold
**Decision:** ≤0.05 delta difference between PUT and CALL shorts
**Reasoning:** Tastytrade standard for directionally neutral Iron Condors

### 5. Entry DTE Target
**Decision:** 45 DTE (with 35-60 day range)
**Reasoning:** Captures theta decay while avoiding gamma spike

---

## File Structure

```
v6/
├── config/
│   └── strategy_deltas.yaml          # Updated with IV rank adjustments
├── src/v6/
│   ├── indicators/
│   │   ├── __init__.py               # New package
│   │   └── iv_rank.py                # IV rank calculator
│   ├── strategies/
│   │   ├── __init__.py               # Updated with new builders
│   │   ├── iron_condor_builder_45_21.py      # New Iron Condor builder
│   │   ├── credit_spread_builder_45_21.py    # New credit spread builder
│   │   └── wheel_builder_45_21.py            # New wheel strategy builder
│   └── execution/
│       ├── __init__.py               # Updated with entry executor
│       └── entry_executor.py         # New entry executor
└── tests/
    ├── test_iv_rank_calculator.py    # IV rank tests
    ├── test_delta_adjustment.py      # Delta adjustment tests
    └── test_iron_condor_entry.py     # Entry flow tests
```

---

## Usage Examples

### Building an Iron Condor

```python
from v6.strategies import IronCondorBuilder45_21

builder = IronCondorBuilder45_21()

strategy = builder.build(
    symbol='SPY',
    underlying_price=500.0,
    option_chain=option_chain_data,  # List of dicts with strike, right, delta, etc.
    quantity=1
)

print(f"Strategy ID: {strategy.strategy_id}")
print(f"PUT delta: {strategy.metadata['short_put_delta']}")
print(f"CALL delta: {strategy.metadata['short_call_delta']}")
print(f"Delta balance: {strategy.metadata['delta_balance']}")
```

### Entering a Position

```python
from v6.execution import EntryExecutor
from v6.utils import IBConnectionManager
from v6.execution.engine import OrderExecutionEngine

ib_conn = IBConnectionManager()
engine = OrderExecutionEngine(ib_conn, dry_run=True)
executor = EntryExecutor(ib_conn, engine, dry_run=True)

result = await executor.enter_iron_condor(
    symbol='SPY',
    option_chain=option_chain_data,
    quantity=1,
    framework='45_21'
)

print(f"Status: {result['status']}")
print(f"Strategy: {result['strategy']}")
```

---

## Success Metrics

### Entry Quality Metrics
- ✅ **Delta Accuracy**: Short strikes within ±0.03 of target delta
- ✅ **Delta Balance**: PUT/CALL delta difference ≤0.05
- ✅ **IV Adjustment**: Correct delta selection for all IV tiers
- ✅ **Wing Width Accuracy**: Within ±2.0 points of 2% target

### Performance Metrics (vs Current)
- 🎯 **Expected Improvement**: Higher win rate (>85%), better risk/reward
- 🎯 **Theta Capture**: More consistent premium collection
- 🎯 **Gamma Risk**: Lower exposure at entry (proper 45 DTE)

---

## What Was NOT Implemented

The following were explicitly **OUT OF SCOPE** for this implementation:

- ❌ Position monitoring (separate work)
- ❌ Rolling logic (separate work)
- ❌ Exit triggers (separate work)
- ❌ Portfolio management (separate work)
- ❌ Real-time IB API integration (uses mock data for now)

---

## Next Steps

1. **Integration Testing**: Test with real IB API data
2. **Backtesting**: Backtest entry strategies vs current approach
3. **Paper Trading**: Paper trade with new entry system
4. **Production Deployment**: Gradual rollout with monitoring

---

## Summary

✅ **Successfully implemented ENTRY-ONLY components for the 45-21 DTE framework:**

- ✅ IV rank calculation and delta adjustment
- ✅ Delta-based Iron Condor builder
- ✅ Delta-based credit spread builders
- ✅ Delta-based wheel strategy builders
- ✅ Entry executor with validation
- ✅ Comprehensive unit tests
- ✅ Configuration integration

**Focus:** Building strategies correctly at 45 DTE with proper delta-based strike selection.

**Result:** Complete entry framework ready for integration testing and paper trading.
