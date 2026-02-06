# Delta Range Update: 0.25-0.80 → 0.10-0.80 ✅

**Date:** 2026-01-30
**Status:** ✅ COMPLETE - All strategy deltas now covered

---

## What Changed

### Problem
The delta range **0.25-0.80** was too narrow and did not cover all strategy deltas:

| Strategy | Delta Target | Was Covered? |
|----------|-------------|--------------|
| **Iron Condor** (short strikes) | 0.20 | ❌ NO - Below 0.25! |
| **Put Spread** (short leg) | 0.25 | ✓ Barely |
| **Call Spread** (long leg) | 0.30 | ✓ Yes |
| **Wheel/Covered Call** | 0.10-0.20 | ❌ NO - Below 0.25! |

### Solution
Updated delta range from **0.25-0.80** to **0.10-0.80** to cover all strategies:

| Strategy | Delta Target | Now Covered? |
|----------|-------------|--------------|
| **Iron Condor** (short strikes) | 0.20 | ✅ YES |
| **Put Spread** (short leg) | 0.25 | ✅ YES |
| **Call Spread** (long leg) | 0.30 | ✅ YES |
| **Wheel/Covered Call** | 0.10-0.20 | ✅ YES |

---

## Files Updated

### 1. `src/v6/core/market_data_fetcher.py`
**Lines 379-386**

**Before:**
```python
# Calls: 0.25 to 0.80 (25-80 delta, includes 70 delta calls)
# Puts: -0.80 to -0.25 (25-80 delta, includes 30 delta puts)
contracts = [c for c in contracts if c.delta is not None and (
    (c.right == 'C' and 0.25 <= c.delta <= 0.80) or  # Calls: 25-80 delta
    (c.right == 'P' and -0.80 <= c.delta <= -0.25)  # Puts: 25-80 delta
)]
```

**After:**
```python
# Calls: 0.10 to 0.80 (10-80 delta, includes all strategy ranges)
# Puts: -0.80 to -0.10 (10-80 delta, includes all strategy ranges)
contracts = [c for c in contracts if c.delta is not None and (
    (c.right == 'C' and 0.10 <= c.delta <= 0.80) or  # Calls: 10-80 delta
    (c.right == 'P' and -0.80 <= c.delta <= -0.10)  # Puts: 10-80 delta
)]
```

### 2. `scripts/collect_option_snapshots_enhanced.py`
**Lines 146-152**

**Before:**
```python
should_include = (
    is_position_strike or
    (contract.delta is not None and 0.25 <= abs(contract.delta) <= 0.80)
)
```

**After:**
```python
should_include = (
    is_position_strike or
    (contract.delta is not None and 0.10 <= abs(contract.delta) <= 0.80)
)
```

### 3. `scripts/filter_option_snapshots_smart.py`
**Smart Filter Logic**

**Before:**
```python
delta_range_filter = (
    (pl.col("delta").is_null()) |
    (
        ((pl.col("right") == "P") & (pl.col("delta") <= -0.25) & (pl.col("delta") >= -0.80)) |
        ((pl.col("right") == "C") & (pl.col("delta") >= 0.25) & (pl.col("delta") <= 0.80))
    )
)
```

**After:**
```python
delta_range_filter = (
    (pl.col("delta").is_null()) |
    (
        ((pl.col("right") == "P") & (pl.col("delta") <= -0.10) & (pl.col("delta") >= -0.80)) |
        ((pl.col("right") == "C") & (pl.col("delta") >= 0.10) & (pl.col("delta") <= 0.80))
    )
)
```

---

## Impact on Data Collection

### Before (0.25-0.80)
- Collected strikes with delta 0.25-0.80
- **Missed:** Iron Condor strikes (delta 0.20)
- **Missed:** Wheel roll candidates (delta 0.10)
- Result: Incomplete strategy data ❌

### After (0.10-0.80)
- Collects strikes with delta 0.10-0.80
- **Includes:** Iron Condor strikes (delta 0.20) ✓
- **Includes:** Wheel roll candidates (delta 0.10) ✓
- **Includes:** All spread strategies ✓
- Result: Complete strategy coverage ✅

---

## Smart Filter Results

### First Run (0.25-0.80 range)
```
Original: 66,265 records (5.7 MB)
Filtered: 64,850 records (4.0 MB)
Reduction: 2.1% records, 29.4% space
```

### Second Run (0.10-0.80 range)
```
Original: 64,850 records (4.0 MB)
Filtered: 64,850 records (4.0 MB)
Reduction: 0.0% records, -0.0% space
```

**Why no reduction?**
- Table was already filtered to 0.25-0.80
- Expanding to 0.10-0.80 means **more** strikes are now valid
- Since all existing data was already within 0.25-0.80 subset, nothing removed

---

## Position Strikes Status

### SPY Iron Condor (635/645/745/755)
| Strike | Delta | In 0.10-0.80 Range? | Status |
|--------|-------|---------------------|--------|
| 635.0 | -0.121 | ✓ Yes (0.121 > 0.10) | ✅ Preserved |
| 645.0 | -0.149 | ✓ Yes (0.149 > 0.10) | ✅ Preserved |
| 745.0 | 0.064 | ❌ No (0.064 < 0.10) | ⚠️ Outside range |
| 755.0 | 0.036 | ❌ No (0.036 < 0.10) | ⚠️ Outside range |

**Important:** Even though strikes 745/755 are outside the 0.10-0.80 range, they are **still preserved** because they're active position strikes! The smart filter **always keeps position strikes regardless of delta**. 🎯

---

## Benefits

### 1. Complete Strategy Coverage
- ✅ Iron Condor (delta 0.20) - Now covered
- ✅ Put Spreads (delta 0.25) - Covered
- ✅ Call Spreads (delta 0.30) - Covered
- ✅ Wheel/Covered Call (delta 0.10-0.20) - Now covered

### 2. Better Strategy Selection
- More strikes available for Iron Condor entry
- More roll candidates for Wheel strategy
- Full range of spread strategies

### 3. Accurate Greeks
- Position strikes always preserved
- No missing data for active positions
- Complete Greeks calculation

---

## Next Steps

### 1. Enhanced Collector Ready
The enhanced collector (`collect_option_snapshots_enhanced.py`) will now:
- Collect delta 0.10-0.80 range (expanded from 0.25-0.80)
- Always collect active position strikes
- Result: Better coverage for all strategies

### 2. Test New Collection Range
```bash
python scripts/collect_option_snapshots_enhanced.py
```

**Expected result:** More strikes collected, including delta 0.10-0.25 range

### 3. Monitor Table Growth
With delta 0.10-0.80, expect ~20-30% more records:
- More strikes in the 0.10-0.25 range
- Better strategy coverage
- Slightly larger table size

---

## Summary

✅ **Delta range updated** - 0.25-0.80 → 0.10-0.80
✅ **All strategies covered** - Iron Condor (0.20), Spreads (0.25-0.30), Wheel (0.10-0.20)
✅ **Data collector updated** - market_data_fetcher.py
✅ **Enhanced collector updated** - collect_option_snapshots_enhanced.py
✅ **Smart filter updated** - filter_option_snapshots_smart.py
✅ **Position strikes preserved** - Always kept regardless of delta
✅ **Table optimized** - 64,850 records, 4.0 MB

**Result:** Complete coverage of all your trading strategies! 🎯
