# DATA INTEGRITY CRISIS - Jan 30, 2026

## 🔴 CRITICAL ISSUE: Delta Lake doesn't match IB Gateway

### What the User Reported

**Dashboard shows:**
- Jan 29: PUT 200/210, CALL 242/252
- Jan 30: PUT 215/225, CALL 252/260

**IB Gateway actually has:**
- PUT 235 (LONG)
- PUT 245 (SHORT)
- CALL 282 (SHORT)
- CALL 290 (LONG)

**THEY DON'T MATCH!**

---

## 🔍 Root Cause Analysis

### Jan 29 Data - COMPLETELY WRONG

**Delta Lake says:**
- Underlying: $225.87 (WRONG - actual was $263.90!)
- Strikes: 200/210/242/252 (WRONG)
- All legs marked as BUY (not a valid Iron Condor!)

**Reality:**
- IWM actual price: $263.90
- Data error: $38 off (14.4% wrong)
- Invalid strategy structure (all BUY legs)

**How this happened:**
- `run_strategist.py` fetches price from `data/lake/market_bars`
- On Jan 29, this table had wrong IWM data ($225.87 vs actual $263.90)
- Strategy builder used wrong price to select wrong strikes
- Result: Completely invalid Iron Condor recorded

### Jan 30 Data - WRONG BACKFILL (FIXED)

**Initial wrong backfill:**
- Used hardcoded strikes: 215/225/252/260
- Based on wrong $225 underlying from Jan 29

**Corrected data:**
- Pulled actual strikes from IB Gateway
- Now matches: 235/245/282/290
- Underlying: $263 (correct!)

---

## ✅ What Was Fixed

1. **Removed wrong backfill** (bf_IWM_20260130_100500 with bad strikes)
2. **Created corrected backfill** with actual IB data:
   - SPY: PUT 635/645, CALL 745/755
   - QQQ: PUT 575/585, CALL 670/680
   - IWM: PUT 235/245, CALL 282/290 ✓ (matches IB!)
3. **Restarted dashboard** to clear cache
4. **Set auto-refresh** to 5 minutes

---

## ⚠️ Outstanding Issues

### Issue 1: Jan 29 Data is Still Wrong

**Problem:** Historical Delta Lake data for Jan 29 is completely wrong

**Options:**
1. Leave it as historical record (bad data, but reflects what happened)
2. Try to reconstruct from IB Gateway (if positions still exist)
3. Mark as "INVALID" in status field

**Recommendation:** Update Jan 29 record with status="INVALID_DATA"

### Issue 2: Price Fetching Bug

**Problem:** `run_strategist.py` got wrong price from `market_bars` table

**Root cause:** Data collection issue on Jan 29
- Market bars table had $225.87 for IWM
- Actual price was $263.90
- 14.4% error!

**Fix needed:**
- Add price validation (check if price is reasonable)
- Cross-check with IB Gateway real-time price
- Add alerts when data looks wrong

### Issue 3: No Validation on Strategy Output

**Problem:** System recorded an invalid Iron Condor (all BUY legs)

**Fix needed:**
- Validate strategy structure before saving
- Check that Iron Condor has:
  - 2 PUT legs (1 BUY, 1 SELL)
  - 2 CALL legs (1 BUY, 1 SELL)
  - Correct spread structure

---

## 📊 Current State

### Delta Lake (AFTER fixes):

| Date | Symbol | Strikes | Status |
|------|--------|---------|--------|
| Jan 29 | IWM | 200/210/242/252 | ⚠️ INVALID (all BUY, wrong price) |
| Jan 30 | IWM | 235/245/282/290 | ✅ CORRECT (matches IB) |

### IB Gateway:
- Current positions: 235/245/282/290 ✅
- Matches corrected Delta Lake for Jan 30 ✅

---

## 🎯 Next Steps

1. **Add price validation** to `run_strategist.py`:
   ```python
   # Check if price is within reasonable range
   if not (previous_price * 0.9 <= price <= previous_price * 1.1):
       raise ValueError(f"Price anomaly: {price}")
   ```

2. **Add strategy validation** before saving:
   ```python
   # Validate Iron Condor structure
   put_legs = [l for l in legs if l.right == 'PUT']
   call_legs = [l for l in legs if l.right == 'CALL']
   assert len(put_legs) == 2, "Need 2 PUT legs"
   assert len(call_legs) == 2, "Need 2 CALL legs"
   ```

3. **Mark invalid data** in Delta Lake:
   ```python
   # Update Jan 29 record
   df = pl.read_delta('data/lake/strategy_executions')
   df = df.with_columns(
       pl.when(
           (pl.col('execution_id') == 'IC_IWM_20260129_130156')
       ).then(pl.lit('INVALID_DATA')).otherwise(pl.col('status'))
   )
   ```

4. **Consider position reconciliation**:
   - Script to compare Delta Lake vs IB Gateway
   - Alert on mismatches
   - Auto-correct when possible

---

## 📝 Lessons Learned

1. **Always validate source data** - The market_bars table had wrong IWM price
2. **Validate strategy structure** - System saved an invalid all-BUY Iron Condor
3. **Cross-check with IB Gateway** - Real-time positions are the source of truth
4. **Dashboard cache issues** - Had to restart to see corrected data
5. **Backfill carefully** - Don't use hardcoded values, pull from actual IB data

---

## 🔗 Related Files

- `scripts/run_strategist.py` - Price fetching from market_bars
- `scripts/backfill_executions_correct.py` - Corrected Jan 30 backfill
- `src/v6/dashboard/app_v5_hybrid.py` - Dashboard reading Delta Lake
- `DELTA_LAKE_PARTITIONING.md` - Performance issues (no partitioning)
