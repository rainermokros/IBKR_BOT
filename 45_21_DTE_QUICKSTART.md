# 45-21 DTE Framework - Quick Start Guide

## What is the 45-21 DTE Framework?

A delta-based options entry system that:
- **Enters** positions at 45 DTE (Days to Expiration)
- **Exits** positions at 21 DTE (not implemented yet)
- Uses **delta** as probability proxy for strike selection
- **Adjusts** delta targets based on IV rank (Implied Volatility)

---

## Core Concepts

### Delta as Probability
- 16-20 delta ≈ 68% Probability of OTM (Profit)
- 25-35 delta ≈ 70% Probability of OTM (Credit Spreads)
- 30-40 delta ≈ 60-65% Probability of OTM (Wheel CSPs)

### IV Rank Tiers
| IV Rank | Delta Range (Iron Condor) | Strategy |
|---------|---------------------------|----------|
| 75-100% | 8-12 delta | Very expensive premiums, sell further OTM |
| 50-75% | 16-20 delta | Standard Tastytrade guidelines |
| 25-50% | 25-30 delta | Fairly priced, move closer to ATM |
| 0-25% | Use debit spreads | Cheap premiums, avoid credit spreads |

### Entry Rules
- **Iron Condors**: 2% wing width, delta balanced (≤0.05 difference)
- **Credit Spreads**: 1% spread width, 30 delta standard
- **Wheel CSPs**: 35 delta for higher assignment probability
- **Entry DTE**: 45 days (target), 35-60 days (acceptable range)

---

## Basic Usage

### 1. Calculate IV Rank

```python
from v6.indicators import IVRankCalculator

calculator = IVRankCalculator(lookback_days=60)
ivr = calculator.calculate('SPY')  # Returns 0-100

print(f"SPY IV Rank: {ivr:.1f}%")
```

### 2. Adjust Delta Based on IV

```python
# For Iron Condor
base_delta = 0.18
adjusted_delta = calculator.adjust_delta(
    base_delta=base_delta,
    iv_rank=ivr,
    strategy_type='iron_condor'
)

print(f"Target delta: {adjusted_delta:.2f}")
```

### 3. Build an Iron Condor

```python
from v6.strategies import IronCondorBuilder45_21

builder = IronCondorBuilder45_21()

# Prepare option chain data
option_chain = [
    {'strike': 470, 'right': 'P', 'delta': -0.16, 'gamma': 0.04, 'theta': -0.05},
    {'strike': 480, 'right': 'P', 'delta': -0.18, 'gamma': 0.045, 'theta': -0.055},
    {'strike': 520, 'right': 'C', 'delta': 0.18, 'gamma': 0.045, 'theta': -0.055},
    {'strike': 530, 'right': 'C', 'delta': 0.16, 'gamma': 0.04, 'theta': -0.05},
    # ... more strikes
]

# Build strategy
strategy = builder.build(
    symbol='SPY',
    underlying_price=500.0,
    option_chain=option_chain,
    quantity=1
)

# Access metadata
print(f"PUT delta: {strategy.metadata['short_put_delta']:.3f}")
print(f"CALL delta: {strategy.metadata['short_call_delta']:.3f}")
print(f"Delta balance: {strategy.metadata['delta_balance']:.3f}")
print(f"Wing widths: PUT={strategy.metadata['put_wing_width']:.1f}, "
      f"CALL={strategy.metadata['call_wing_width']:.1f}")
```

### 4. Enter a Position

```python
from v6.execution import EntryExecutor
from v6.utils import IBConnectionManager
from v6.execution.engine import OrderExecutionEngine

# Setup
ib_conn = IBConnectionManager()
engine = OrderExecutionEngine(ib_conn, dry_run=True)
executor = EntryExecutor(ib_conn, engine, dry_run=True)

# Enter Iron Condor
result = await executor.enter_iron_condor(
    symbol='SPY',
    option_chain=option_chain,
    quantity=1,
    framework='45_21'
)

print(f"Status: {result['status']}")
print(f"Message: {result['message']}")
```

---

## Option Chain Data Format

The option chain should be a list of dictionaries with the following keys:

```python
[
    {
        'strike': 470.0,      # Strike price
        'right': 'P',         # 'P' for PUT, 'C' for CALL
        'delta': -0.16,       # Delta value (negative for puts)
        'gamma': 0.04,        # Gamma
        'theta': -0.05,       # Theta
        'vega': 0.25,         # Vega
    },
    # ... more strikes
]
```

**Minimum required:** `strike`, `right`, `delta`
**Optional:** `gamma`, `theta`, `vega` (for advanced features)

---

## Strategy Builders

### Iron Condor (45-21)

```python
from v6.strategies import IronCondorBuilder45_21

builder = IronCondorBuilder45_21()
strategy = builder.build(
    symbol='SPY',
    underlying_price=500.0,
    option_chain=option_chain,
    quantity=1
)
```

**Result:** 4-leg Iron Condor with:
- Long Put (lower strike, protection)
- Short Put (16-20 delta, IV-adjusted)
- Short Call (16-20 delta, IV-adjusted)
- Long Call (higher strike, protection)

---

### Bull Put Spread

```python
from v6.strategies import CreditSpreadBuilder45_21

builder = CreditSpreadBuilder45_21()
strategy = builder.build_bull_put_spread(
    symbol='SPY',
    underlying_price=500.0,
    option_chain=option_chain,
    quantity=1
)
```

**Result:** 2-leg Bull Put Spread with:
- Long Put (protection)
- Short Put (25-35 delta, IV-adjusted)

---

### Bear Call Spread

```python
builder = CreditSpreadBuilder45_21()
strategy = builder.build_bear_call_spread(
    symbol='SPY',
    underlying_price=500.0,
    option_chain=option_chain,
    quantity=1
)
```

**Result:** 2-leg Bear Call Spread with:
- Short Call (25-35 delta, IV-adjusted)
- Long Call (protection)

---

### Cash-Secured Put (Wheel Stage 1)

```python
from v6.strategies import WheelStrategyBuilder

builder = WheelStrategyBuilder()
strategy = builder.build_cash_secured_put(
    symbol='SPY',
    underlying_price=500.0,
    option_chain=option_chain,
    quantity=1,
    target_delta=0.35  # Optional, defaults to 0.35
)
```

**Result:** 1-leg Cash-Secured Put with:
- Short Put (30-40 delta for assignment)

---

## Validation

### Check Delta Balance

```python
# After building strategy
delta_balance = strategy.metadata.get('delta_balance', 1.0)

if delta_balance <= 0.05:
    print(f"✓ Delta balanced: {delta_balance:.3f}")
else:
    print(f"✗ Delta imbalance: {delta_balance:.3f} > 0.05")
```

### Check Wing Widths

```python
put_wing = strategy.metadata['put_wing_width']
call_wing = strategy.metadata['call_wing_width']
target_wing = strategy.metadata['target_wing_width']

put_diff = abs(put_wing - target_wing)
call_diff = abs(call_wing - target_wing)

if put_diff <= 2.0 and call_diff <= 2.0:
    print(f"✓ Wing widths acceptable")
else:
    print(f"✗ Wing widths too far from target")
```

### Validate Strategy

```python
from v6.strategies import IronCondorBuilder45_21

builder = IronCondorBuilder45_21()
strategy = builder.build(...)

# Validate
if builder.validate(strategy):
    print("✓ Strategy valid")
else:
    print("✗ Strategy invalid")
```

---

## Configuration

The framework is configured in `v6/config/strategy_deltas.yaml`:

```yaml
# IV Rank Adjustments
iv_rank_adjustments:
  very_high_iv:
    ivr_min: 75
    ivr_max: 100
    iron_condor_short_delta_min: 0.08
    iron_condor_short_delta_max: 0.12

  high_iv:
    ivr_min: 50
    ivr_max: 75
    iron_condor_short_delta_min: 0.16
    iron_condor_short_delta_max: 0.20

  # ... more tiers

# Entry DTE Target
entry_dte:
  target: 45
  min: 35
  max: 60
```

**To adjust parameters:** Edit this file and restart your application.

---

## Testing

### Run Unit Tests

```bash
cd v6
python -m pytest tests/test_iv_rank_calculator.py -v
python -m pytest tests/test_delta_adjustment.py -v
python -m pytest tests/test_iron_condor_entry.py -v
```

### Run All Tests

```bash
python -m pytest tests/ -v
```

---

## Common Tasks

### Check if Debit Spreads Preferred

```python
from v6.indicators import IVRankCalculator

calculator = IVRankCalculator()
ivr = calculator.calculate('SPY')

if calculator.should_use_debit_spreads(ivr):
    print("IV rank too low, use debit spreads")
else:
    print("IV rank acceptable, use credit spreads")
```

### Get IV Tier Information

```python
calculator = IVRankCalculator()
tier = calculator.get_iv_tier(ivr)

print(f"IV Tier: {tier['description']}")
print(f"IV Range: {tier['ivr_min']}-{tier['ivr_max']}%")
```

### Build Multiple Strategies

```python
from v6.execution import EntryExecutor

executor = EntryExecutor(ib_conn, engine, dry_run=True)

# Build Iron Condor
ic_result = await executor.enter_iron_condor('SPY', option_chain, 1)

# Build Bull Put Spread
bps_result = await executor.enter_bull_put_spread('SPY', option_chain, 1)

# Build Bear Call Spread
bcs_result = await executor.enter_bear_call_spread('SPY', option_chain, 1)
```

---

## Troubleshooting

### Error: "No strikes available"

**Cause:** Option chain doesn't have strikes for the target delta.

**Solution:**
- Check your option chain data includes both puts and calls
- Verify strikes are on both sides of the underlying price
- Ensure delta values are present in the data

### Error: "Iron Condor not balanced"

**Cause:** Delta difference between PUT and CALL shorts exceeds 0.05.

**Solution:**
- Check your option chain has sufficient strikes
- Verify delta values are accurate
- Try adjusting the underlying price slightly

### Warning: "Wing width differs from target"

**Cause:** Calculated wing width doesn't match available strikes.

**Solution:**
- This is usually a warning, not an error
- The builder selects the closest available strikes
- Wing widths within ±2.0 points are acceptable

### IV Rank Returns 50 (Default)

**Cause:** No historical IV data available or calculation failed.

**Solution:**
- Check that `data/lake/market_bars` table exists and has data
- Verify the table has `iv` column with implied volatility data
- Check logs for specific error messages

---

## Best Practices

1. **Always validate strategies before entering**
   ```python
   if builder.validate(strategy):
       # Enter position
   ```

2. **Check delta balance for Iron Condors**
   ```python
   delta_balance = strategy.metadata['delta_balance']
   assert delta_balance <= 0.05
   ```

3. **Use dry run mode for testing**
   ```python
   executor = EntryExecutor(ib_conn, engine, dry_run=True)
   ```

4. **Monitor IV rank before entry**
   ```python
   ivr = calculator.calculate(symbol)
   if ivr < 25:
       logger.warning(f"Low IV rank ({ivr:.1f}%), consider debit spreads")
   ```

5. **Validate option chain data**
   ```python
   required_keys = ['strike', 'right', 'delta']
   for strike in option_chain:
       assert all(k in strike for k in required_keys)
   ```

---

## Next Steps

1. **Integration Testing**: Test with real IB API data
2. **Backtesting**: Compare with current entry approach
3. **Paper Trading**: Test in paper trading environment
4. **Production Deployment**: Gradual rollout with monitoring

---

## Support

- **Documentation**: `v6/45_21_DTE_IMPLEMENTATION_SUMMARY.md`
- **Tests**: `v6/tests/`
- **Configuration**: `v6/config/strategy_deltas.yaml`
- **Source Code**: `v6/src/v6/indicators/`, `v6/src/v6/strategies/`, `v6/src/v6/execution/`

---

## Summary

✅ **45-21 DTE Framework Entry System Ready!**

- IV rank calculation and delta adjustment
- Delta-based strike selection
- Strategy builders (IC, Credit Spreads, Wheel)
- Entry executor with validation
- Comprehensive unit tests

**Ready for:** Integration testing, backtesting, and paper trading.
