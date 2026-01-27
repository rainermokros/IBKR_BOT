# Strategy Requirements Analysis

**Date:** 2026-01-27
**Status:** CRITICAL ISSUE IDENTIFIED

## User Requirements

### Trading Universe
- **Symbols:** SPY, QQQ, IWM

### DTE Range
- **Target:** 21-45 days to expiration

### Margin Constraints
- **CRITICAL:** NO SHORT CALL or SHORT PUT (margin reasons)

## Current Implementation vs Requirements

### Current: Iron Condor Strategy
**Structure:**
```
Long Put  (lower strike)     ← BUY
Short Put (middle strike)    ← SELL ❌ MARGIN REQUIRED
Short Call (middle strike)   ← SELL ❌ MARGIN REQUIRED
Long Call (higher strike)    ← BUY
```

**Issues:**
- ❌ Has 2 short legs (Short Put + Short Call)
- ❌ Requires margin for short options
- ❌ Violates user's "NO SHORT" requirement

### What User Actually Needs

Based on "NO SHORT CALL or SHORT PUT for margin reasons", the system should trade:

**Option 1: Debit Spreads (Buying Premium)**
```
Put Spread (bearish):
  Long Put  (higher strike)   ← BUY
  Short Put (lower strike)    ← SELL ❌ Still has short leg

Call Spread (bullish):
  Long Call  (lower strike)   ← BUY
  Short Call (higher strike)  ← SELL ❌ Still has short leg
```

**Issue:** Even debit spreads have a short leg!

**Option 2: Long Options Only (No Margin)**
```
Long Call (bullish)   ← BUY only, no margin
Long Put (bearish)    ← BUY only, no margin
Long Straddle         ← BUY both sides, no margin
Long Strangle         ← BUY both sides, no margin
```

**Option 3: Calendar Spreads (Same Strike, Different Expiration)**
```
Long Term Option (far expiration)   ← BUY
Short Term Option (near expiration) ← SELL ❌ Still has short leg
```

## The Dilemma

**Problem:** Almost all options strategies involve selling premium (short legs)

**Exceptions:**
1. **Long options only** (no spread, no hedge)
   - Pros: No margin required
   - Cons: Unlimited risk if naked, expensive

2. **Risk reversal**
   - Sell OTM put, buy ITM call (or vice versa)
   - Still has short leg

3. **Covered calls** (requires owning underlying)
   - Short call is covered by stock
   - Still has short leg

## Possible Solutions

### Solution 1: Allow Short Legs With Sufficient Capital
If user has enough margin, short legs are fine:
- Iron condors are standard income strategies
- Credit spreads have defined risk
- Just need to ensure sufficient account equity

**Question for User:** Do you have margin in your paper trading account?

### Solution 2: Long Options Only
Implement simple long call/put strategies:
- Long call (bullish bet)
- Long put (bearish bet)
- Long straddle (volatility bet)
- Long strangle (volatility bet)

**Pros:** No margin required
**Cons:** Expensive (paying full premium), no hedge

### Solution 3: Debit Spreads (Accept Short Leg)
Explain that debit spreads have:
- Defined risk (max loss = debit paid)
- Short leg is protected by long leg
- Lower cost than outright long options

**Example:**
```python
# Bullish Call Debit Spread
Long $700 Call  @ $10.00  ← Pay $1000
Short $720 Call  @ $5.00   ← Receive $500
Net Debit: $5.00           ← Max risk = $500

# Naked Long Call (no spread)
Long $700 Call  @ $10.00  ← Pay $1000 (no protection)
```

Debit spread has lower risk and cost!

## Recommendation

**IMMEDIATE:** Clarify with user:

1. **Do you have margin available?**
   - If yes: Keep iron condors/credit spreads
   - If no: Need long-only strategies

2. **Are you OK with defined-risk debit spreads?**
   - These have a short leg but it's protected
   - Lower cost than naked longs
   - Example: Long $700 Call + Short $720 Call = Max risk $500

3. **What's your market outlook?**
   - Bullish → Long calls or call debit spreads
   - Bearish → Long puts or put debit spreads
   - Neutral → Long straddles/strangles (expensive)
   - Income → Iron condors (requires margin)

## Current Status

❌ **BLOCKER:** Strategy type mismatch
- System builds iron condors (requires margin)
- User wants NO short options
- Cannot proceed with live trading until resolved

## Next Steps

1. **Ask user about margin availability**
2. **Confirm acceptable strategy types**
3. **Implement appropriate strategy builder**
4. **Test with dry_run=false (already verified working)**

## Alternative Interpretation

Perhaps user meant:
- No **NAKED** short calls/puts
- But **COVERED** short legs (in spreads) are OK?

If so, iron condors and credit spreads are fine because:
- Short put is protected by long put (lower strike)
- Short call is protected by long call (higher strike)
- Max loss is defined (width of spreads)

**This is the most likely interpretation** - spreads are standard practice!

## Summary

- Current: Iron condors (short + long legs)
- User requirement: "NO SHORT CALL or SHORT PUT"
- Most likely intent: No **NAKED** shorts (spreads OK)
- Action: Confirm with user, then proceed
