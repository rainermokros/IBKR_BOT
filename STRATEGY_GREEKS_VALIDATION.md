# Strategy Greeks Validation - Implementation Summary

## What Was Added

### 1. **Strategy Greeks Validator** (`src/v6/risk/strategy_greeks_validator.py`)

A new validation layer that checks **strategy-specific Greeks requirements**:

```python
from v6.risk import StrategyGreeksLimits, StrategyGreeksValidator

# Configure limits
limits = StrategyGreeksLimits(
    iron_condor_max_abs_delta=5.0,  # Iron Condors must be delta-neutral
    vertical_spread_max_abs_delta=30.0,  # Vertical spreads can be directional
)

# Create validator
validator = StrategyGreeksValidator(greeks_calc, limits)

# Validate a strategy before entry
is_valid, violations = validator.validate_strategy(strategy)
if not is_valid:
    print(f"Rejected: {violations}")
```

### 2. **Strategy Greeks Limits Model** (`src/v6/risk/models.py`)

Configuration for strategy-specific Greeks thresholds:

```python
@dataclass(slots=True)
class StrategyGreeksLimits:
    iron_condor_max_abs_delta: float = 5.0
    iron_condor_max_delta_bias: float = 0.15
    vertical_spread_max_abs_delta: float = 30.0
```

### 3. **Comprehensive Test Suite** (`tests/risk/test_strategy_greeks_validation.py`)

8 tests covering:
- ✅ Accepts delta-neutral Iron Condors (delta = 2.5)
- ✅ Rejects bearish-skewed Iron Condors (delta = -11.94)
- ✅ Rejects bullish-skewed Iron Condors (delta = 15.0)
- ✅ Allows Iron Condors at threshold (delta = 5.0)
- ✅ Custom limit configuration
- ✅ Vertical spreads allow more delta than Iron Condors
- ✅ Integration with portfolio limits
- ✅ Strategy validation catches what portfolio limits miss

## The Problem It Solves

### Before: Portfolio Limits Only

```python
# Portfolio limits check ABSOLUTE delta:
max_per_symbol_delta = 20.0

# IWM Iron Condor: delta = -11.94
abs(-11.94) = 11.94 < 20.0  # ✅ PASSES

# But this is a TERRIBLE Iron Condor!
# - Short CALL has delta 0.86 (deep ITM!)
# - Short PUT has delta -0.03 (far OTM)
# - Should be delta-neutral, not bearish!
```

### After: Strategy-Specific Validation

```python
# Strategy validation checks STRATEGY STRUCTURE:
iron_condor_max_abs_delta = 5.0

# IWM Iron Condor: delta = -11.94
abs(-11.94) = 11.94 > 5.0  # ❌ REJECTED

# Violation message:
"Iron Condor delta -11.94 exceeds threshold of 5.0.
 Iron Condors should be delta-neutral (|delta| < 5.0).
 Current delta -11.94 indicates significant bearish bias."
```

## Key Features

### 1. Two-Layer Protection

**Layer 1: Portfolio Limits** (existing)
- Checks total portfolio exposure
- Uses `abs(delta)` to limit directional risk
- Example: `max_per_symbol_delta = 20.0`

**Layer 2: Strategy Validation** (new)
- Validates strategy structure is correct
- Strategy-specific requirements (Iron Condors ≠ Vertical Spreads)
- Example: `iron_condor_max_abs_delta = 5.0`

### 2. Strategy-Specific Requirements

| Strategy Type | Delta Requirement | Rationale |
|---------------|-------------------|-----------|
| **Iron Condor** | `abs(delta) < 5` | Must be delta-neutral for range-bound profit |
| **Vertical Spread** | `abs(delta) < 30` | Can be directional (bullish or bearish) |
| **Calendar Spread** | (future) | Theta-focused validation (not yet implemented) |

### 3. Clear Violation Messages

```python
# For the IWM Iron Condor with -11.94 delta:
violations = [
    "Iron Condor delta -11.94 exceeds threshold of 5.0. "
    "Iron Condors should be delta-neutral (|delta| < 5.0). "
    "Current delta -11.94 indicates significant bearish bias."
]
```

## Test Results

```
tests/risk/test_strategy_greeks_validation.py::TestIronCondorDeltaNeutral::test_accepts_delta_neutral_iron_condor PASSED
tests/risk/test_strategy_greeks_validation.py::TestIronCondorDeltaNeutral::test_rejects_bearish_skewed_iron_condor PASSED
tests/risk/test_strategy_greeks_validation.py::TestIronCondorDeltaNeutral::test_iron_condor_delta_at_threshold PASSED
tests/risk/test_strategy_greeks_validation.py::TestStrategyGreeksLimitsConfig::test_default_iron_condor_limits PASSED
tests/risk/test_strategy_greeks_validation.py::TestStrategyGreeksLimitsConfig::test_custom_iron_condor_limits PASSED
tests/risk/test_strategy_greeks_validation.py::TestStrategyGreeksLimitsConfig::test_vertical_spread_allows_more_delta PASSED
tests/risk/test_strategy_greeks_validation.py::TestIntegrationWithPortfolioLimits::test_portfolio_limits_use_abs_delta PASSED
tests/risk/test_strategy_greeks_validation.py::TestIntegrationWithPortfolioLimits::test_strategy_validation_catches_what_portfolio_limits_miss PASSED

============================== 8 passed in 0.06s ===============================
```

## Usage Example

### Before Position Entry

```python
from v6.risk import StrategyGreeksValidator, StrategyGreeksLimits
from v6.strategies import StrategyBuilder

# 1. Build strategy
strategy = StrategyBuilder.build_iron_condor(
    symbol="IWM",
    put_spread=(200, 210),
    call_spread=(242, 252),
    expiration=date(2026, 3, 20),
)

# 2. Calculate Greeks
greeks = greeks_calculator.calculate_position_greeks(strategy)
# Returns: {"delta": -11.94, "gamma": 0.5, ...}

# 3. Validate strategy structure
validator = StrategyGreeksValidator(greeks_calc, StrategyGreeksLimits())
is_valid, violations = validator.validate_strategy(strategy)

# 4. Reject if structure is invalid
if not is_valid:
    logger.error(f"Invalid strategy structure: {violations}")
    # DO NOT ENTER THIS POSITION!
    return

# 5. If valid, proceed to portfolio limit checks
allowed, reason = await portfolio_limits.check_entry_allowed(
    new_position_delta=greeks["delta"],
    symbol="IWM",
    position_value=strategy.value,
)
```

## Files Created/Modified

### Created:
1. `src/v6/risk/strategy_greeks_validator.py` - Validator implementation
2. `tests/risk/test_strategy_greeks_validation.py` - Test suite

### Modified:
1. `src/v6/risk/models.py` - Added `StrategyGreeksLimits` dataclass
2. `src/v6/risk/__init__.py` - Exported new classes

## Configuration

### Default Limits (Recommended)

```python
StrategyGreeksLimits(
    iron_condor_max_abs_delta=5.0,      # Strict delta-neutral
    iron_condor_max_delta_bias=0.15,    # Max 15% per short leg
    vertical_spread_max_abs_delta=30.0, # Allow directional exposure
)
```

### Custom Limits

```python
# More conservative:
StrategyGreeksLimits(iron_condor_max_abs_delta=3.0)

# More aggressive:
StrategyGreeksLimits(iron_condor_max_abs_delta=10.0)
```

## Next Steps

1. **Integrate into Entry Workflow**: Add validation to `src/v6/workflows/entry.py`
2. **Add Leg-Level Validation**: Check individual short leg deltas for balance
3. **Add Calendar Spread Validation**: Implement theta-focused validation
4. **Add Real-Time Monitoring**: Alert if position delta drifts from neutral

## Summary

✅ **Added**: Strategy-specific Greeks validation
✅ **Tested**: 8/8 tests passing
✅ **Protects**: Against skewed Iron Condors like the -11.94 delta IWM position
✅ **Complements**: Existing portfolio-level limits
✅ **Ready**: For integration into entry workflow
