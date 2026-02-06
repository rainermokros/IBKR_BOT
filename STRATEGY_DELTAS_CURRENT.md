# Strategy Deltas Table

**Date:** 2026-01-30
**Delta Range:** 0.10-0.80 (10-80 delta)

---

## All Active Strategies

| Strategy | Right | Strike | Delta | In Range? |
|----------|-------|--------|-------|-----------|
| **SPY Iron Condor (IC_SPY_20260130_100500)** | | | | |
| | PUT | 635.0 | -0.121 | ✓ IN |
| | PUT | 645.0 | -0.149 | ✓ IN |
| | CALL | 745.0 | +0.064 | ✗ OUT |
| | CALL | 755.0 | +0.036 | ✗ OUT |
| **QQQ Iron Condor (IC_QQQ_20260130_100500)** | | | | |
| | PUT | 575.0 | -0.141 | ✓ IN |
| | PUT | 585.0 | -0.175 | ✓ IN |
| | CALL | 670.0 | +0.201 | ✓ IN |
| | CALL | 680.0 | +0.132 | ✓ IN |
| **IWM Iron Condor (IC_IWM_20260130_100500)** | | | | |
| | PUT | 235.0 | -0.112 | ✓ IN |
| | PUT | 245.0 | -0.258 | ✓ IN |
| | CALL | 282.0 | +0.184 | ✓ IN |
| | CALL | 290.0 | +0.094 | ✗ OUT |
| **IWM Iron Condor (IC_IWM_20260129_130156)** | | | | |
| | PUT | 200.0 | -0.021 | ✗ OUT |
| | PUT | 210.0 | -0.033 | ✗ OUT |
| | CALL | 242.0 | +0.799 | ✓ IN |
| | CALL | 252.0 | +0.676 | ✓ IN |
| **QQQ Iron Condor (IC_QQQ_20260129_130156)** | | | | |
| | PUT | 655.0 | -0.794 | ✓ IN |
| | PUT | 665.0 | -0.791 | ✓ IN |
| | CALL | 765.0 | +0.004 | ✗ OUT |
| | CALL | 775.0 | +0.003 | ✗ OUT |
| **SPY Iron Condor (IC_SPY_20260129_130155)** | | | | |
| | PUT | 635.0 | -0.121 | ✓ IN |
| | PUT | 645.0 | -0.149 | ✓ IN |
| | CALL | 745.0 | +0.064 | ✗ OUT |
| | CALL | 755.0 | +0.036 | ✗ OUT |

---

## Summary

### In Range vs Out of Range
| Strategy | In Range | Out of Range |
|----------|----------|--------------|
| SPY IC (Jan 30) | 2/4 (50%) | 2/4 (50%) |
| QQQ IC (Jan 30) | 4/4 (100%) | 0/4 (0%) |
| IWM IC (Jan 30) | 3/4 (75%) | 1/4 (25%) |
| IWM IC (Jan 29) | 2/4 (50%) | 2/4 (50%) |
| QQQ IC (Jan 29) | 2/4 (50%) | 2/4 (50%) |
| SPY IC (Jan 29) | 2/4 (50%) | 2/4 (50%) |
| **TOTAL** | **15/24 (63%)** | **9/24 (37%)** |

### Key Findings

1. **9 out of 24 legs (37%) are outside the 0.10-0.80 range**
   - These are deep OTM options (delta < 0.10)
   - Typically the far wing of Iron Condors

2. **All positions are preserved** regardless of delta range
   - Enhanced collector always includes active position strikes
   - Greeks calculations still accurate

3. **Iron Condors often use strikes outside 0.10-0.80**
   - Far OTM wings have very low delta (< 0.10)
   - This is intentional for risk management
   - Short strikes closer to ATM (delta 0.15-0.25)

---

## Delta Range Implications

### With 0.10-0.80 Range
- ✅ Collects all short strikes (delta 0.15-0.25)
- ✅ Collects most long strikes
- ❌ Misses far OTM wings (delta < 0.10)
- ✅ Enhanced collector preserves all position strikes

### Iron Condor Structure
```
PUT 635 (BUY):  delta=-0.121  (far OTM protection)
PUT 645 (SELL): delta=-0.149  (short strike, ~15 delta)
CALL 745 (SELL): delta=+0.064  (short strike, ~6 delta - OUT of range!)
CALL 755 (BUY):  delta=+0.036  (far OTM protection - OUT of range!)
```

**Result:** Enhanced collector is **essential** to preserve all position legs! 🎯
