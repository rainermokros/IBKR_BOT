# Percentage-Based Wing Widths - IMPLEMENTATION ✅

**Date:** 2026-01-30
**Status:** ✅ Configuration updated, implementation pending

---

## The Problem: Fixed Point Widths

### Current Implementation (WRONG)
All Iron Condors use **fixed 10-point wings**:
- SPY at $695: 10 points = **1.4%** of price ✗ Too narrow
- QQQ at $625: 10 points = **1.6%** of price ✗ Too narrow
- IWM at $250: 10 points = **4.0%** of price ✗✗ **TOO WIDE!**

**Why This is Bad:**
1. **Inconsistent risk** across different assets
2. **Over-paying for protection** on lower-priced assets (IWM)
3. **Under-protected** on higher-priced assets (SPY, QQQ)
4. **Poor risk/reward ratios**

---

## The Solution: Percentage-Based Widths

### New Configuration (CORRECT)
```yaml
wing_width:
  min_width_pct: 1.0   # Minimum 1% of underlying price
  max_width_pct: 3.0   # Maximum 3% of underlying price
  target_width_pct: 2.0  # Standard 2% wings
  min_width_points: 3.0  # Minimum 3 points (for lower-priced assets)
  max_width_points: 25.0 # Maximum 25 points (for higher-priced assets)
```

### How It Works
```python
# Calculate wing width
wing_width = atm_price * (target_width_pct / 100)

# Apply safety limits
wing_width = max(min_width_points, min(wing_width, max_width_points))
```

### Examples

| Asset | ATM Price | 2% Width | Min (1%) | Max (3%) | Actual Current |
|-------|-----------|----------|----------|----------|----------------|
| SPY | $695 | **13.9** | 6.0 | 18.0 | 10.0 ✗ |
| QQQ | $625 | **12.5** | 6.0 | 18.0 | 10.0 ✗ |
| IWM | $250 | **5.0** | 3.0 | 6.0 | 10.0 ✗✗ |

---

## Current Iron Condors Analysis

### SPY Iron Condors (Jan 29, 30)
```
ATM Price: $695
Target: 13.9 points (2%)
Actual: 10.0 points
Status: ✗ TOO NARROW (paying less for protection than target)
Impact: Under-protected, slightly higher risk
```

### QQQ Iron Condors
```
Jan 30: ATM $625, Target 12.5, Actual 10.0 ✗
Jan 29: ATM $715, Target 14.3, Actual 10.0 ✗
Status: TOO NARROW
```

### IWM Iron Condors (CRITICAL!)
```
Jan 30: ATM $263, Target 5.3, Actual 10.0 ✗✗
Jan 29: ATM $226, Target 4.5, Actual 10.0 ✗✗
Status: ALMOST DOUBLE THE TARGET WIDTH!
Impact:
- Paying too much for long wings
- Reducing potential profit
- Poor risk/reward ratio
```

---

## Benefits of Percentage-Based Widths

### 1. Consistent Risk Across Assets
- All Iron Condors have same risk percentage (2%)
- Risk scales with asset price automatically
- No more over-paying on IWM

### 2. Better Risk/Reward
- IWM: 10-point wings = 4% of price → **2x target!**
- SPY: 10-point wings = 1.4% of price → **30% below target!**

### 3. Automatic Scaling
- High-priced assets (SPY $700): 14-point wings
- Mid-priced assets (QQQ $600): 12-point wings
- Low-priced assets (IWM $200): 4-point wings
- **All maintain 2% risk profile!**

### 4. Safety Limits
- Minimum: 3 points (prevents extreme narrow widths)
- Maximum: 25 points (prevents extreme wide widths)
- Example: TSLA at $180 → 3.6 points (hits minimum)

---

## Implementation

### Step 1: Load Configuration
```python
import yaml

with open('config/strategy_deltas.yaml') as f:
    config = yaml.safe_load(f)

wing_config = config['iron_condor']['wing_width']
target_pct = wing_config['target_width_pct']  # 2.0
```

### Step 2: Calculate Wing Width
```python
def calculate_wing_width(atm_price: float, config: dict) -> float:
    """Calculate wing width as percentage of ATM price."""
    target_pct = config['target_width_pct']
    min_pct = config['min_width_pct']
    max_pct = config['max_width_pct']
    min_points = config['min_width_points']
    max_points = config['max_width_points']

    # Calculate target width
    wing_width = atm_price * (target_pct / 100)

    # Apply percentage limits
    wing_width = max(atm_price * (min_pct / 100),
                    min(wing_width, atm_price * (max_pct / 100)))

    # Apply point limits (safety)
    wing_width = max(min_points, min(wing_width, max_points))

    return round(wing_width, 1)

# Example
spy_price = 695
spy_wing = calculate_wing_width(spy_price, wing_config)
# Returns: 13.9 points
```

### Step 3: Validate Wing Width
```python
def validate_iron_condor(
    short_put_strike: float,
    short_call_strike: float,
    long_put_strike: float,
    long_call_strike: float,
    atm_price: float,
    config: dict
) -> tuple[bool, str]:
    """Validate Iron Condor wing widths."""

    target_wing = calculate_wing_width(atm_price, config)

    put_wing = short_put_strike - long_put_strike
    call_wing = long_call_strike - short_call_strike

    # Check if wings are close to target
    put_diff = abs(put_wing - target_wing)
    call_diff = abs(call_wing - target_wing)

    tolerance = 2.0  # Allow 2-point tolerance

    if put_diff > tolerance or call_diff > tolerance:
        return False, (
            f"Wing widths not within target range:\n"
            f"  Target: {target_wing:.1f} points (2% of ${atm_price:.0f})\n"
            f"  PUT wing: {put_wing:.1f} points (diff: {put_diff:.1f})\n"
            f"  CALL wing: {call_wing:.1f} points (diff: {call_diff:.1f})\n"
            f"  Tolerance: ±{tolerance:.1f} points"
        )

    return True, "Wing widths valid"

# Example validation
valid, msg = validate_iron_condor(
    short_put_strike=645,
    short_call_strike=745,  # This should be adjusted!
    long_put_strike=635,
    long_call_strike=755,
    atm_price=695,
    config=wing_config
)

if not valid:
    print(f"ERROR: {msg}")
```

### Step 4: Build Iron Condor with Correct Wings
```python
def build_iron_condor(
    symbol: str,
    atm_price: float,
    option_chain: list,
    config: dict
) -> dict:
    """Build Iron Condor with delta-based strikes and percentage wings."""

    delta_config = config['iron_condor']
    wing_config = delta_config['wing_width']

    # Target delta for short strikes
    target_delta = delta_config['short_puts']['target_delta']  # 0.18

    # Find short strikes at target delta
    short_put = find_strike_with_delta(
        option_chain,
        'PUT',
        target_delta=target_delta,
        atm_price=atm_price
    )

    short_call = find_strike_with_delta(
        option_chain,
        'CALL',
        target_delta=target_delta,
        atm_price=atm_price
    )

    # Calculate wing width
    wing_width = calculate_wing_width(atm_price, wing_config)

    # Add wings
    long_put = short_put - wing_width
    long_call = short_call + wing_width

    # Validate
    valid, msg = validate_iron_condor(
        short_put, short_call,
        long_put, long_call,
        atm_price, wing_config
    )

    if not valid:
        raise ValueError(f"Iron Condor validation failed: {msg}")

    return {
        'short_put': short_put,
        'short_call': short_call,
        'long_put': long_put,
        'long_call': long_call,
        'wing_width': wing_width,
        'target_delta': target_delta
    }
```

---

## Spread Widths Also Updated

Same percentage-based approach for credit spreads:

```yaml
put_spread:
  spread_width:
    min_width_pct: 0.8   # 0.8% of underlying price
    max_width_pct: 2.0   # 2% of underlying price
    target_width_pct: 1.0  # Standard 1% spread
    min_width_points: 3.0
    max_width_points: 15.0

call_spread:
  spread_width:
    min_width_pct: 0.8
    max_width_pct: 2.0
    target_width_pct: 1.0
    min_width_points: 3.0
    max_width_points: 15.0
```

### Examples

| Asset | ATM Price | 1% Spread | SPY Example | IWM Example |
|-------|-----------|-----------|-------------|-------------|
| SPY | $695 | **7.0 points** | 695-702 spread | - |
| QQQ | $625 | **6.3 points** | - | - |
| IWM | $250 | **2.5 points** | - | 247-250 spread |

---

## Next Steps

### 1. ✅ Configuration Updated
- `config/strategy_deltas.yaml` now uses percentage-based widths
- All wing and spread configurations updated

### 2. 🔧 Update Strategy Builders
- Modify Iron Condor builder to use percentage widths
- Modify Put/Call Spread builders to use percentage widths
- Add validation to ensure widths are within target range

### 3. 📊 Add Dashboard Indicators
- Show actual vs target wing width
- Alert if wings are outside tolerance (±2 points)
- Show wing width as percentage of price

### 4. ⚠️ Review Existing Positions
- IWM Iron Condors: Wings almost **2x target width**
- Consider closing/rolling for better risk/reward
- SPY/QQQ: Wings slightly narrow, less critical

---

## Configuration File

Updated: `config/strategy_deltas.yaml`

Key sections:
- `iron_condor.wing_width` - Percentage-based wing widths
- `put_spread.spread_width` - Percentage-based spread widths
- `call_spread.spread_width` - Percentage-based spread widths

All include:
- Percentage targets (min/max/actual)
- Point limits (safety boundaries)
- Descriptions

---

## Summary

✅ **Configuration updated** - Percentage-based widths implemented in YAML
✅ **Safety limits** - Min 3 points, max 25 points
✅ **Consistent risk** - 2% wings across all assets
✅ **Better scaling** - Automatically adjusts to asset price

🔧 **Implementation pending** - Strategy builders need updating
⚠️ **IWM positions problematic** - Wings almost 2x target width

**This is a significant improvement in risk management!** 🎯
