# USER DECISION REQUIRED: Streaming Slots Architecture

## Summary

Phase 2 (Position Synchronization) is complete but has a **critical architectural flaw** that affects scalability.

## The Problem

**What was implemented:**
- Used `updatePortfolioEvent` to stream ALL position changes in real-time
- Thought the constraint was "100 connections" → solved with singleton pattern
- **Reality:** IB has **100 streaming SLOTS** (not connections)

**Why this matters:**
- `updatePortfolioEvent` consumes a streaming slot for EVERY position
- Inactive positions don't need real-time streaming (wastes slots)
- VIX/SPY/QQQ/IWM should be polled, not streamed
- Will run out of slots at ~100 contracts

## Numbers Example

**Current approach (streaming everything):**
- 50 inactive positions = 50 slots
- 10 active strategy positions = 10 slots
- 4 market data contracts (VIX, SPY, QQQ, IWM) = 4 slots
- **Total: 64 slots** (grows with portfolio size)
- **Problem:** Hits 100-slot limit at ~100 contracts

**Correct approach (poll + selective stream):**
- 50 inactive positions = **0 slots** (poll every 30-60s)
- 10 active strategy positions = 10 slots (stream these)
- 4 market data contracts = **0 slots** (poll these)
- **Total: 10 slots** (fixed, regardless of portfolio size)
- **Benefit:** Scales to thousands of contracts

## Your Options

### Option A: Fix Position Streaming (RECOMMENDED ✅)
**What:** Rewrite 2-01 to use `reqPositions()` polling instead of `updatePortfolioEvent` streaming

**Changes:**
1. Rewrite `IBPositionStreamer` to poll positions every 30-60 seconds
2. Keep handler registration pattern (still works with polling)
3. Only stream market data for active strategy contracts
4. Poll VIX/SPY/QQQ/IWM instead of streaming

**Effort:** Moderate (1-2 days)

**Benefits:**
- ✅ Scales properly (conserves streaming slots)
- ✅ v6 is "clean slate" - fix now before it's too late
- ✅ 30-60s polling is acceptable for position updates
- ✅ Simpler than hybrid approach

**Impact:**
- 2-01 needs rewrite
- 2-02 no changes (handler pattern still works)
- 2-03 minor changes (already uses `reqPositionsAsync` for reconciliation)

---

### Option B: Live With It (RISKY ⚠️)
**What:** Do nothing, keep current streaming approach

**Changes:** None

**Risks:**
- ❌ Will run out of streaming slots at ~100 contracts
- ❌ Need to manually manage streaming (not automated)
- ❌ Doesn't scale for growing portfolio

**Mitigation:**
- Manually unsubscribe from inactive positions
- Accept that portfolio size is limited by slot count

---

### Option C: Hybrid Approach (COMPLEX 🔧)
**What:** Stream active positions, poll inactive positions

**Changes:**
1. Stream only positions in active strategies
2. Poll all other positions
3. Dynamic slot management (add/remove streams as strategies activate/deactivate)

**Effort:** High (3-5 days, complex logic)

**Benefits:**
- ✅ Optimal slot usage
- ✅ Real-time updates for active strategies
- ✅ Scales well

**Drawbacks:**
- ❌ Complex implementation
- ❌ More moving parts = more bugs
- ❌ Harder to test and maintain

## My Recommendation

**Go with Option A: Fix Position Streaming**

**Rationale:**
1. v6 is supposed to be "clean slate" - fix architectural mistakes now
2. Polling 30-60s is perfectly acceptable for position updates (we're not high-frequency trading)
3. Slot conservation is critical for long-term scalability
4. Simpler than Option C (hybrid approach)
5. Better than Option B (living with it) because it will break eventually

**What happens next:**
1. You approve Option A, B, or C (or suggest alternative)
2. I create urgent plan "2.1-POSITION-POLLING.md" if Option A
3. Rewrite position streaming to use polling
4. Update all dependent code
5. Re-test integration
6. Phase 2 becomes truly complete

## Question for You

**Which option do you prefer?**

- **Option A** (fix with polling) - Recommended ✅
- **Option B** (live with it) - Risky ⚠️
- **Option C** (hybrid) - Complex 🔧
- **Something else** (please describe)

---

**Created:** 2026-01-26
**Status:** Awaiting your decision
**Priority:** CRITICAL (blocks Phase 3 start)
