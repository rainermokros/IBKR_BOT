# Dashboard Updates - Complete Position Analytics

## ✅ All Features Implemented

### 💰 Position Metrics

1. **Net Credit** (Premium Received)
   - Shows the credit received when opening the position
   - Properly calculated with contract multiplier (×100)
   - Example: $820.00 for IWM Iron Condor

2. **Margin** (IB Requirement)
   - Estimated margin required to hold the position
   - Calculated from spread widths (put spread + call spread)
   - Example: $2,000.00 for IWM Iron Condor

3. **Max Risk** (Maximum Loss)
   - Maximum possible loss if position goes against you
   - For Iron Condor: Spread width - Net Credit
   - Example: $180.00 for IWM Iron Condor

4. **Return / Risk**
   - Maximum return as percentage of max risk
   - Example: 455.6% for IWM Iron Condor

### 📊 Strategy Details

1. **Strikes**
   - All strike prices in the strategy
   - Example: $200, $210, $242, $252

2. **Expiration**
   - Option expiration date
   - Shows Days to Expiration (DTE)
   - Example: 2026-03-20 (50 DTE)

3. **Underlying Price**
   - Price of underlying asset at entry
   - Example: $225.87

4. **Breakevens**
   - Calculate breakeven points at expiration
   - For Iron Condor: Short strikes ± net credit/100
   - Example: $201.67 / $250.33

### 📈 Greeks (Live from option_snapshots)

**Position Greeks** (Total across all legs):
- **Delta**: Net price sensitivity ($ per $1 move in underlying)
  - Example: -11.96 (position profits when underlying drops)
- **Gamma**: Delta sensitivity (delta change per $1 move)
  - Example: 0.503
- **Theta**: Time decay ($ per day)
  - Example: -$0.95 (position earns $0.95/day from time decay)
- **Vega**: Volatility sensitivity ($ per 1% IV change)
  - Example: $6.55 (position gains $6.55 if IV drops 1%)

**Strategy Greeks** (Normalized per leg):
- **Delta/Leg**: Average delta per leg
- **Gamma/Leg**: Average gamma per leg
- **Theta/Leg**: Average theta per leg
- **Vega/Leg**: Average vega per leg

### 🎯 How Greeks Are Calculated

1. **Data Source**: option_snapshots Delta Lake table
2. **Matching**: Legs matched by (symbol, right, strike, expiry)
3. **Format Conversion**:
   - Right: "PUT"/"CALL" → "P"/"C"
   - Expiry: "2026-03-20" → "20260320"
4. **Aggregation**:
   - BUY legs: Add to Greeks
   - SELL legs: Subtract from Greeks
   - Multiply by quantity × 100 (contract multiplier)
5. **Real-Time**: Cached for 5 seconds, auto-refreshes

## 🎨 UI Improvements

- ✅ Smaller font size for Greeks sections (better readability)
- ✅ Clear section headers with emoji icons
- ✅ Helpful tooltips explaining each metric
- ✅ Organized layout with columns

## 📊 How to View All Features

1. Open Dashboard: http://localhost:8501
2. Go to **Positions** page
3. Expand any position card
4. You'll now see:
   - 💰 Position Metrics (Net Credit, Margin, Max Risk, Return/Risk)
   - 📊 Strategy Details (Strikes, Expiration, Underlying, Breakevens)
   - 📈 Position Greeks (Delta, Gamma, Theta, Vega)
   - 🎯 Strategy Greeks (Normalized per leg)
   - 📋 Leg Details (Action, Right, Quantity, Strike, Expiration, Status, Fill Price)

**Refresh the dashboard to see all changes!**

## ✅ Completed Features

- ✅ Position metrics (Net Credit, Margin, Max Risk, Return/Risk)
- ✅ Strategy details (Strikes, Expiration, Underlying, Breakevens)
- ✅ Position Greeks (loaded from option_snapshots)
- ✅ Strategy Greeks (normalized per leg)
- ✅ Smaller font size for better readability
- ✅ Real-time Greeks updates (5-second cache)
- ✅ Status filter fix (OPEN → filled/partial)
- ✅ Page rename (Paper Trading → Trading)

**All requested features have been implemented!**
