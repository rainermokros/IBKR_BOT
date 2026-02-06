"""
Strategy Selection Documentation

Complete matrix of option strategies based on market outlook and IV level.

## Strategy Matrix

| Market Outlook | High IV (IV Rank > 50) | Low IV (IV Rank < 50) |
|----------------|-------------------------|------------------------|
| **Bullish** | • Long Call (Debit) | • Bull Put Spread (Credit) |
| | • Bull Call Spread (Debit) | • Cash-Secured Put (Credit) |
| | • Call Backspread (Debit) | |
| **Bearish** | • Long Put (Debit) | • Bear Call Spread (Credit) |
| | • Bear Put Spread (Debit) | |
| | • Put Backspread (Debit) | |
| **Neutral** | • Short Straddle (Credit) | • Long Butterfly (Debit) |
| | • Short Strangle (Credit) | • Iron Condor (Credit) |

## Key Concepts

### IV Context

**High IV (IV Rank > 50):**
- Options are expensive (large premiums)
- Good for **selling premium** (credit strategies)
- Often precedes events (earnings, FDA decisions)
- IV decrease after events ("IV crush") helps credit strategies
- Buying options is costly but benefits from volatility expansion

**Low IV (IV Rank < 50):**
- Options are cheap (small premiums)
- Good for **buying premium** (debit strategies)
- Suggests market expects calm
- Buying options is affordable, IV increase helps long options
- Selling premium collects less but still benefits from time decay

### Debit vs Credit Strategies

**Debit Strategies (Pay money upfront):**
- You want the stock to MOVE
- Often have long option legs
- Long options benefit from IV INCREASE
- Examples: Long calls, long puts, bull/bear spreads (debit), backspreads

**Credit Strategies (Receive money upfront):**
- You want the stock to NOT MOVE (stay in range)
- Involve selling options (naked or spread)
- Higher risk (unlimited/margin intensive) but defined in spreads
- Short options benefit from IV DECREASE ("IV crush")
- Examples: Bull/bear put/call spreads (credit), straddles, strangles, condors, butterflies

### Volatility's Impact

**Buying Options (Long Calls/Puts):**
- Prefer LOW IV when entering (cheaper premium)
- IV increase after entry HELPS your position (vega positive)
- Long options have positive vega

**Selling Options (Short Calls/Puts/Spreads):**
- Prefer HIGH IV when entering (more premium to collect)
- IV decrease after entry HELPS your position (vega negative)
- Short options have negative vega

### Sideways Strategies (Crucial Distinction!)

**High IV + Sideways:**
- Sell premium AGGRESSIVELY
- Strategies: Short Straddle, Short Strangle
- Goal: Maximize premium collection, profit from IV crush
- Risk: Unlimited (straddles/strangles), high margin requirement

**Low IV + Sideways:**
- Use defined-range, lower-cost strategies
- Strategies: Long Butterfly, Iron Condor
- Goal: Avoid paying high premiums, benefit from time decay
- Risk: Limited (butterflies), defined range (condors)

## Strategy Descriptions

### Bullish Strategies

**Long Call (Debit):**
- **Setup:** Buy call option
- **Outlook:** Bullish (price will rise)
- **IV Preference:** Low IV (cheaper) or Rising IV
- **Max Gain:** Unlimited (price can rise indefinitely)
- **Max Loss:** Premium paid (if option expires worthless)
- **Breakeven:** Strike + premium paid
- **Best when:** IV low, expect sharp price increase

**Bull Call Spread (Debit):**
- **Setup:** Buy ITM call, sell OTM call
- **Outlook:** Moderately bullish (price will rise somewhat)
- **IV Preference:** Any (debit strategy, but vol helps)
- **Max Gain:** Width of spread - premium paid
- **Max Loss:** Premium paid (defined risk)
- **Breakeven:** Long strike + premium paid
- **Best when:** Directional bullish view with defined risk

**Bull Put Spread (Credit):**
- **Setup:** Sell OTM put, buy further OTM put
- **Outlook:** Bullish/Neutral (price will stay same or rise)
- **IV Preference:** Low IV or Falling IV (IV crush helps)
- **Max Gain:** Premium received
- **Max Loss:** Width of spread - premium received (defined risk)
- **Breakeven:** Short strike - premium received
- **Best when:** Mildly bullish, want to collect premium

**Cash-Secured Put (Credit):**
- **Setup:** Sell put, hold cash equal to strike price
- **Outlook:** Bullish (want to own stock at lower price)
- **IV Preference:** Low IV (premium is small)
- **Max Gain:** Premium received (if stock above strike at expiration)
- **Max Loss:** Strike price - premium received (if stock goes to zero)
- **Breakeven:** Strike price - premium received
- **Best when:** Very bullish, willing to own stock

**Call Backspread (2:1):**
- **Setup:** Buy 2 OTM calls, sell 1 ATM call
- **Outlook:** Very bullish + volatility expansion
- **IV Preference:** High IV and Rising
- **Max Gain:** Unlimited (if large price increase)
- **Max Loss:** Net debit paid (if price stays same or falls)
- **Breakeven:** Complex (depends on strikes)
- **Best when:** Expect volatility surge, very bullish

### Bearish Strategies

**Long Put (Debit):**
- **Setup:** Buy put option
- **Outlook:** Bearish (price will fall)
- **IV Preference:** Low IV (cheaper) or Rising IV
- **Max Gain:** Strike price - premium paid (if price goes to zero)
- **Max Loss:** Premium paid (if option expires worthless)
- **Breakeven:** Strike price - premium paid
- **Best when:** IV low, expect sharp price decrease

**Bear Put Spread (Debit):**
- **Setup:** Buy ITM put, sell OTM put
- **Outlook:** Moderately bearish (price will fall somewhat)
- **IV Preference:** Any (debit strategy, but vol helps)
- **Max Gain:** Width of spread - premium paid
- **Max Loss:** Premium paid (defined risk)
- **Breakeven:** Short strike + width - premium paid
- **Best when:** Directional bearish view with defined risk

**Bear Call Spread (Credit):**
- **Setup:** Sell OTM call, buy further OTM call
- **Outlook:** Bearish/Neutral (price will stay below short strike)
- **IV Preference:** Low IV (time decay helps, no IV crush needed)
- **Max Gain:** Premium received
- **Max Loss:** Width of spread - premium received (defined risk)
- **Breakeven:** Short strike + premium received
- **Best when:** Mildly bearish, want to collect premium

**Put Backspread (1:2):**
- **Setup:** Buy 2 OTM puts, sell 1 ITM put
- **Outlook:** Very bearish + volatility expansion
- **IV Preference:** High IV and Rising
- **Max Gain:** Net credit received (if sharp price drop)
- **Max Loss:** Large (if price rises)
- **Breakeven:** Complex (depends on strikes)
- **Best when:** Expect volatility surge, very bearish

### Neutral/Sideways Strategies

**Short Straddle (Credit):**
- **Setup:** Sell ATM call + ATM put (same strike and expiration)
- **Outlook:** Neutral/Sideways (price will stay in range)
- **IV Preference:** HIGH IV (large premiums)
- **Max Gain:** Premium received (if price stays near strike at expiration)
- **Max Loss:** UNLIMITED (if price moves significantly in either direction)
- **Breakeven:** Strike ± premium received
- **Best when:** High IV, expect price stability, IV crush
- **RISK:** Unlimited risk, high margin requirement

**Short Strangle (Credit):**
- **Setup:** Sell OTM call + OTM put (different strikes, same expiration)
- **Outlook:** Neutral/Sideways (price will stay between strikes)
- **IV Preference:** HIGH IV (large premiums)
- **Max Gain:** Premium received (if price stays between strikes at expiration)
- **Max Loss:** UNLIMITED (if price moves outside range)
- **Breakeven:** Put strike - premium, Call strike + premium
- **Best when:** High IV, expect price stability in wider range
- **RISK:** Unlimited risk, lower margin than straddle

**Long Butterfly (Debit):**
- **Setup:** Buy 1 ITM call, sell 2 ATM calls, buy 1 OTM call (all same expiration)
- **Outlook:** Neutral/Sideways (price will stay near center)
- **IV Preference:** LOW IV (cheap to enter)
- **Max Gain:** Width of body - debit paid
- **Max Loss:** Debit paid (defined risk, limited)
- **Breakeven:** Lower break-even, Upper break-even (complex)
- **Best when:** Low IV, expect very tight range, defined risk wanted

**Iron Condor (Credit):**
- **Setup:** Sell OTM put spread + Sell OTM call spread (different strikes)
- **Outlook:** Neutral/Sideways (price will stay between wings)
- **IV Preference:** Any (works in both high and low IV)
- **Max Gain:** Premium received (from both spreads)
- **Max Loss:** Width of one spread - premium received (defined risk)
- **Breakeven:** Put spread breakeven, Call spread breakeven
- **Best when:** Neutral/sideways, want defined risk, premium collection

## Decision Tree for Strategy Selection

```
1. Detect Market Outlook (Bullish/Bearish/Neutral)
   ├─ Technical analysis (trend, moving averages)
   ├─ Price momentum
   └─ Support/resistance levels

2. Classify IV Level (High/Low)
   └─ IV Rank > 50 = HIGH
   └─ IV Rank < 50 = LOW

3. Determine Strategy
   ├─ Bullish + High IV → Bull Call Spread, Call Backspread, Long Call
   ├─ Bullish + Low IV → Bull Put Spread, Cash-Secured Put, Long Call
   ├─ Bearish + High IV → Bear Put Spread, Put Backspread, Long Put
   ├─ Bearish + Low IV → Bear Call Spread, Long Put
   ├─ Neutral + High IV → Short Straddle, Short Strangle
   └─ Neutral + Low IV → Long Butterfly, Iron Condor
```

## Risk Considerations

**Credit Strategies (Higher Risk):**
- Short straddles/strangles: Unlimited risk
- Naked options: Unlimited risk
- Require significant margin
- Best for experienced traders

**Debit Strategies (Limited Risk):**
- Vertical spreads: Defined risk
- Butterflies/Condors: Defined risk
- Long options: Limited to premium paid

**High IV Strategies:**
- Benefits: Large premiums available
- Risks: Increased option prices, potential for large moves
- Best: Credit strategies to sell premium

**Low IV Strategies:**
- Benefits: Cheap options to buy
- Risks: Small premiums collected
- Best: Debit strategies or defined-range credit strategies

## Entry Signal Generation

This system now has COMPLETE entry signal logic:

1. **Detect Market Regime** (market_regime.py)
   - Analyze price trend → Bullish/Bearish/Neutral
   - Classify IV level → High/Low
   - Detect vol trend → Rising/Falling/Stable

2. **Select Strategy** (entry_rules.py)
   - Match regime to optimal strategy from matrix
   - Generate entry decision with strategy type
   - Include rationale for strategy selection

3. **Execute Entry** (entry.py)
   - Build selected strategy
   - Place orders
   - Track position

---

**End of Documentation**
