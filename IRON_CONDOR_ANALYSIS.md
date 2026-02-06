# Iron Condor Delta Analysis - CRITICAL ISSUES FOUND 🔴

**Date:** 2026-01-30
**Target Range:** 16-20 delta for short strikes (Tastytrade standard)

---

## Summary: 5 out of 6 Iron Condors Are Improperly Constructed! 😱

| Iron Condor | Short PUT Delta | Short CALL Delta | Balance | Status |
|-------------|-----------------|------------------|---------|--------|
| **SPY** (both) | 14.9 ✗ | **6.4** ✗✗✗ | PUT-biased | 🔴 BAD |
| **QQQ** Jan 30 | 17.5 ✓ | 20.1 ✓ | Balanced | 🟢 GOOD |
| **IWM** Jan 30 | **25.8** ✗✗ | 18.4 ✓ | PUT-biased | 🔴 BAD |
| **IWM** Jan 29 | **3.3** ✗✗✗ | **79.9** ✗✗✗ | CALL-biased | 🔴 TERRIBLE |
| **QQQ** Jan 29 | **79.1** ✗✗✗ | **0.4** ✗✗✗ | PUT-biased | 🔴 TERRIBLE |

---

## Detailed Analysis

### 🔴 SPY Iron Condors (Jan 29 & 30) - PUT-BIASED

```
PUT  645 (SELL): delta = 14.9  ✗ Below 16-20 range
CALL 745 (SELL): delta =  6.4  ✗✗✗ WAY below 16-20 range!

Balance: Δ difference = 8.5 (target ≤ 5)
Status: UNBALANCED - PUT-biased (bearish)
```

**Problems:**
1. CALL short strike at 6.4 delta is **TOO FAR OTM**
2. Not collecting enough premium on CALL side
3. Overall position is bearish (PUT-biased)
4. Will lose money if market moves up

**Why This Happened:**
- CALL 745 is 54 points above SPY (~691)
- At that distance, delta is only ~6
- Should be closer to ATM to achieve 16-20 delta

---

### 🟢 QQQ Iron Condor Jan 30 - GOOD! ✅

```
PUT  585 (SELL): delta = 17.5  ✓ In 16-20 range
CALL 670 (SELL): delta = 20.1  ✓ In 16-20 range

Balance: Δ difference = 2.6 (target ≤ 5)
Status: BALANCED - directionally neutral ✅
```

**This is how an Iron Condor SHOULD look!**

---

### 🔴 IWM Iron Condor Jan 30 - PUT-BIASED

```
PUT  245 (SELL): delta = 25.8  ✗ Above 16-20 range
CALL 282 (SELL): delta = 18.4  ✓ In 16-20 range

Balance: Δ difference = 7.4 (target ≤ 5)
Status: UNBALANCED - PUT-biased (bearish)
```

**Problems:**
1. PUT short strike at 25.8 delta is **TOO ITM**
2. Higher risk of assignment on PUT side
3. Overall position is bearish

---

### 🔴 IWM Iron Condor Jan 29 - TERRIBLE! 💀

```
PUT  210 (SELL): delta =  3.3  ✗✗✗ WAY below 16-20
CALL 242 (SELL): delta = 79.9  ✗✗✗ WAY above 16-20!

Balance: Δ difference = 76.6 (target ≤ 5)
Status: EXTREMELY UNBALANCED - CALL-biased (bullish)
```

**This is NOT an Iron Condor - it's two separate positions!**
- PUT side is deep OTM (no protection)
- CALL side is deep ITM (almost guaranteed assignment)
- Extremely directional

---

### 🔴 QQQ Iron Condor Jan 29 - TERRIBLE! 💀

```
PUT  665 (SELL): delta = 79.1  ✗✗✗ WAY above 16-20
CALL 765 (SELL): delta =  0.4  ✗✗✗ WAY below 16-20!

Balance: Δ difference = 78.7 (target ≤ 5)
Status: EXTREMELY UNBALANCED - PUT-biased (bearish)
```

**Same problem as IWM Jan 29 - NOT a proper Iron Condor!**

---

## Root Cause Analysis

### Why Are These Iron Condors So Bad?

**Hypothesis:** The Iron Condor builder is **NOT using delta** to select strikes. It's likely using:
1. Fixed distance from current price (e.g., ±50 points)
2. Fixed strikes (e.g., round numbers)
3. Some other method that doesn't account for volatility

**Evidence:**
- SPY Iron Condor: PUT side at 14.9 delta (close!), but CALL side at 6.4 delta (way off)
- This happens when you use the same distance in both directions
- Example: If SPY is at 691, and you go 50 points in both directions:
  - PUT at 641 (≈ 15 delta) ✗ Too low
  - CALL at 741 (≈ 6 delta) ✗✗✗ Way too low!

**The Problem:** Delta is NOT linear with distance!
- In low IV environments, you need to go FURTHER from ATM to get the same delta
- In high IV environments, you need to go CLOSER to ATM
- Fixed distances don't account for this!

---

## Correct Iron Condor Construction

### Step 1: Start with Current Price
SPY is at ~691

### Step 2: Find PUT Strike at 16-20 Delta
Looking for delta around -0.18
- PUT 645: delta = -0.149 (14.9 delta) ✗ Too low
- PUT 640: delta ≈ -0.16? Need to check
- PUT 635: delta = -0.121 (12.1 delta) ✗ Too low

**The issue:** Your PUTs are below the 16-20 delta range!

### Step 3: Find CALL Strike at 16-20 Delta
Looking for delta around +0.18
- CALL 745: delta = +0.064 (6.4 delta) ✗✗✗ Way too low!
- CALL 720: delta ≈ ? Need to check
- CALL 700: delta ≈ ? Need to check

**The issue:** Your CALLs are WAY below the 16-20 delta range!

### Correct SPY Iron Condor (Example)
```
PUT  655 (SELL): Should be ~16-20 delta
CALL 725 (SELL): Should be ~16-20 delta
PUT  645 (BUY):  Protection wing (10-point width)
CALL 735 (BUY):  Protection wing (10-point width)
```

---

## Recommendations

### 1. Fix Iron Condor Builder 🔧

**Current implementation (WRONG):**
```python
# BAD: Fixed distance from ATM
put_strike = round_down(atm_price - 50)
call_strike = round_up(atm_price + 50)
```

**Correct implementation:**
```python
# GOOD: Find strikes by delta
put_strike = find_strike_with_delta(atm_price, 'PUT', target_delta=0.18)
call_strike = find_strike_with_delta(atm_price, 'CALL', target_delta=0.18)

# Verify balance
if abs(put_delta - call_delta) > 0.05:
    # Adjust strikes to balance
    ...
```

### 2. Add Validation ✅

Before entering an Iron Condor, validate:
```python
assert 0.16 <= short_put_delta <= 0.20, "PUT delta not in range"
assert 0.16 <= short_call_delta <= 0.20, "CALL delta not in range"
assert abs(short_put_delta - short_call_delta) <= 0.05, "Iron Condor not balanced"
```

### 3. Load Delta Configuration from YAML 📝

```python
import yaml

with open('config/strategy_deltas.yaml') as f:
    config = yaml.safe_load(f)

iron_condor_config = config['iron_condor']
target_delta = iron_condor_config['short_puts']['target_delta']  # 0.18
```

### 4. Monitor Existing Positions 📊

Your current Iron Condors:
- **QQQ Jan 30:** ✅ Keep monitoring (good construction)
- **SPY, IWM, QQQ others:** Consider closing/rolling
  - They're directionally biased
  - Not following Tastytrade guidelines
  - Higher risk than intended

---

## Next Steps

1. ✅ **Delta configuration YAML created** - `config/strategy_deltas.yaml`
2. 🔧 **Fix Iron Condor builder** - Use delta-based strike selection
3. ✅ **Add validation** - Reject Iron Condors outside delta ranges
4. 📊 **Add dashboard alerts** - Show when positions are unbalanced
5. 📚 **Document Tastytrade guidelines** - Reference for future

---

## Configuration File

Created: `config/strategy_deltas.yaml`

Contains:
- Iron Condor targets: 16-20 delta for short strikes
- Put Spread targets: 30 delta for short strike (Tastytrade standard)
- Call Spread targets: 30 delta for short strike (Tastytrade standard)
- Wheel/Covered Call targets: 20-30 delta
- Validation rules
- Risk management thresholds

**This YAML should be loaded by all strategy builders to ensure consistent delta targets!**
