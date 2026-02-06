This document provides a technical specification for the initial data collection, feature engineering, and labeling phases of a Market Regime Classification model. The goal is to predict 6 market regimes specifically optimized for 21–45 DTE options trading on **SPY**, **QQQ**, and **IWM**.

---

## Technical Specification: Market Regime Model (Phase 1)

### 1. Objective

Build a multiclass classifier that identifies the current market regime into 6 states:

* **Directional (3):** Bullish, Bearish, Neutral
* **Volatility (2):** High, Low
* **Combined Target:** 

### 2. Data Acquisition (IBKR API)

The developer should implement a robust ingestion script using `ibapi` (or `ib_async`).

#### Core Tickers & Parameters

* **Assets:** `SPY` (STK), `QQQ` (STK), `IWM` (STK)
* **Exogenous Features:** `VIX` (IND), `GLD` (STK)
* **Frequency:** `1 day` bars (Daily).
* **WhatToShow:** `TRADES` (for price) and `OPTION_IMPLIED_VOLATILITY` (where available) and HISTORICAL_VOLATILITY ` (where available).
* **Duration:** Minimum 10 years of history to capture sufficient market cycles (2015–2025).

#### IBKR Request Settings

```python
# Technical Note: Use reqHistoricalData with the following:
endDateTime = "" # Current
durationString = "10 Y"
barSizeSetting = "1 day"
whatToShow = "TRADES" 
useRTH = 1 # Regular Trading Hours only to avoid gap noise

```

---

### 3. Feature Engineering Pipeline

To allow for pooled training (treating SPY, QQQ, and IWM as a single dataset), features must be **ticker-agnostic** (normalized).

| Feature Category | Computation | Purpose |
| --- | --- | --- |
| **Price Momentum** | 21-day RSI, 50/200-day MA distance (Z-scored). | Capture trend strength relative to history. |
| **Relative Vol** | Current 21-day HV / 252-day Median HV. | Measures "Vol Expansion" vs. "Vol Contraction." |
| **Sentiment (VIX)** | VIX level + VIX 5-day Rate of Change (ROC). | Global "Fear" gauge impact on the specific ticker. |
| **Macro/Safe Haven** | Correlation(Ticker, GLD) over 21 days. | Detects "Risk-Off" flight to safety (Gold). |
| **Inter-market** | Ticker Close / SPY Close ratio. | Measures relative strength (e.g., QQQ outperforming SPY). |

---

### 4. Target Labeling (The Ground Truth)

The model's performance depends on the "Forward Look." For options in the 21-45 DTE range, we define the target based on the **next 21 trading days (~1 calendar month)**.

#### Target Function Logic:

Let  be the 21-day forward log return and  be the current 21-day Historical Volatility.

1. **Standardize Returns:** Calculate the rolling 1-year mean () and std dev () of 21-day returns for each ticker.
* **Bullish:** 
* **Bearish:** 
* **Neutral:** Everything in between.


2. **Standardize Volatility:** Use **HV Percentile** (0-100) over a 252-day lookback.
* **High Vol:** Current HV > 70th Percentile.
* **Low Vol:** Current HV  70th Percentile.



#### The 6-Class Map:

| Return Class | Vol Class | Label ID | Interpretation |
| --- | --- | --- | --- |
| Bullish | Low | 0 | "Grind Higher" (Long Delta) |
| Bullish | High | 1 | "Volatile Recovery" (Call Spreads) |
| Neutral | Low | 2 | "Mean Reversion/Quiet" (Iron Condors) |
| Neutral | High | 3 | "Whiplash" (Wide Strangles) |
| Bearish | Low | 4 | "Slow Bleed" (Bear Spreads) |
| Bearish | High | 5 | "Panic" (Long Gamma/Puts) |

---

### 5. Implementation Roadmap for Developer

1. **Normalization Module:** Implement a class that stores rolling  and  for each ticker to prevent **look-ahead bias** during training.
2. **Data Pooling:** Concatenate the processed DataFrames for SPY, QQQ, and IWM into one master training set ( samples).
3. **Baseline Model:** Start with an **XGBoost** or **Random Forest** classifier. These handle non-linear relationships between VIX/GLD and price action well.

---

use this as reference: https://interactivebrokers.github.io/tws-api/historical_bars.html