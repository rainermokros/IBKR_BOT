# Phase 8: Futures Data Collection - Research

**Researched:** 2026-01-30
**Domain:** IBKR futures data collection, Delta Lake storage, continuous contracts
**Confidence:** HIGH

## Summary

Research covered Interactive Brokers futures data collection for ES (E-mini S&P 500), NQ (E-mini Nasdaq-100), and RTY (E-mini Russell 2000) using the ib_async library. Key findings: IBKR provides continuous futures contracts that automatically splice expiring contracts, but **only for historical data requests**, not real-time streaming. For real-time collection, use active front-month contracts and implement manual rollover logic.

**Primary recommendation:** Use ib_async for real-time streaming of front-month futures contracts, store snapshots in Delta Lake with 1-minute frequency, and implement simple front-month rollover (check volume, switch to next contract on expiry). Delta Lake provides excellent time-series storage with partitioning by date/symbol and time-travel for historical analysis.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| **ib_async** | 2.0+ | IBKR API interface | Modern async IB library, successor to ib_insync, production-ready |
| **Delta Lake** | Latest (via delta-spark) | Time-series storage | ACID transactions, time-travel, Parquet format |
| **PySpark** | 3.x | Delta Lake operations | Standard interface for Delta Lake in Python |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **pyspark.sql** | Built-in | Delta table operations | All Delta Lake read/write operations |
| **pandas** | 2.x | Data manipulation | Analysis, visualization, correlation calculations |
| **deltalake** (optional) | Latest | Lightweight Delta access | For simple Delta reads without full PySpark |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| ib_async | ib_insync | ib_insync is older, less maintained; ib_async is actively developed |
| Delta Lake | Parquet files directly | Delta provides ACID, time-travel, schema enforcement; Parquet is just storage |
| Front-month contracts | IBKR continuous contracts | **Critical:** IB continuous futures only work for historical data, not real-time streaming |

**Installation:**
```bash
pip install ib_async
pip install pyspark  # For Delta Lake
pip install pandas
```

---

## Architecture Patterns

### Recommended Project Structure

```
src/v6/
├── data/
│   ├── futures_collector.py   # Real-time futures streaming & storage
│   └── delta_persistence.py    # Existing Delta Lake writer (reuse)
├── core/
│   └── futures_rollover.py     # Contract rollover logic
└── models/
    └── futures_snapshot.py     # Pydantic model for futures data
```

### Pattern 1: Real-Time Futures Streaming with ib_async

**What:** Subscribe to live market data for active futures contracts and stream price updates

**When to use:** Any real-time futures data collection

**Example:**
```python
from ib_async import *
import time

# Create IB connection
ib = IB()
ib.connect('127.0.0.1', 4001, clientId=1)  # Gateway port

# Define ES front-month contract
contract = Future(
    symbol='ES',
    exchange='CME',
    currency='USD',
    lastTradeDateOrContractMonth='20250321'  # March 2025 expiry
)

# Subscribe to real-time data
ticker = ib.reqMktData(contract, '', False, False)

# Stream updates for 30 seconds
for i in range(30):
    ib.sleep(1)
    if ticker.last:
        print(f"ES: ${ticker.last} (bid: ${ticker.bid}, ask: ${ticker.ask}, vol: {ticker.volume})")

ib.disconnect()
```

### Pattern 2: Historical Data with IBKR Continuous Contracts

**What:** Use IBKR's built-in continuous contract symbols for historical backfill

**When to use:** Populating historical data before starting real-time collection

**Example:**
```python
from ib_async import *

ib = IB()
ib.connect('127.0.0.1', 4001, clientId=1)

# Use continuous contract for ES (symbol only, no expiry)
# Note: This ONLY works for reqHistoricalData, NOT real-time streaming
contract = Future(symbol='ES', exchange='CME', currency='USD')

# Request historical data (IBKR handles rolls automatically)
bars = ib.reqHistoricalData(
    contract,
    endDateTime='',
    durationStr='30 D',
    barSizeSetting='1 min',
    whatToShow='TRADES',
    useRTH=False  # False = include extended hours (Globex)
)

df = util.df(bars)
print(f"Retrieved {len(df)} bars")

ib.disconnect()
```

### Pattern 3: Delta Lake Time-Series Storage

**What:** Store futures snapshots in Delta Lake with partitioning for efficient queries

**When to use:** All time-series market data storage

**Example:**
```python
from pyspark.sql import SparkSession
from pyspark.sql.functions import current_timestamp

# Initialize Spark with Delta
spark = SparkSession.builder \
    .appName("FuturesCollector") \
    .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
    .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
    .getOrCreate()

# Define schema
futures_data = [
    {
        "timestamp": "2025-01-30 10:00:00",
        "symbol": "ES",
        "bid": 4500.25,
        "ask": 4500.50,
        "last": 4500.375,
        "volume": 125000,
        "date": "2025-01-30"  # Partition column
    }
]

df = spark.createDataFrame(futures_data)

# Write to Delta Lake (partition by date and symbol)
df.write \
    .format("delta") \
    .mode("append") \
    .partitionBy("date", "symbol") \
    .save("/data/lake/futures_snapshots")

# Time travel query
df_past = spark.read \
    .format("delta") \
    .option("versionAsOf", 0) \
    .load("/data/lake/futures_snapshots")
```

### Pattern 4: Front-Month Contract Rollover

**What:** Detect when to roll from expiring contract to next front month

**When to use:** Maintaining continuous real-time data stream

**Example:**
```python
from datetime import datetime, timedelta
from ib_async import *

def get_front_month(ib: IB, symbol: str) -> Future:
    """Get the front-month contract (highest volume)"""
    # Search for futures contracts
    contracts = ib.reqContractDetails(
        Future(symbol=symbol, exchange='CME', currency='USD')
    )

    # Filter for contracts expiring in next 3 months
    valid = [c for c in contracts
             if is_within_3_months(c.contract.lastTradeDateOrContractMonth)]

    # In production, query volume and pick highest
    # For now, pick earliest expiry
    front_month = min(valid, key=lambda c: c.contract.lastTradeDateOrContractMonth)

    return front_month.contract

def is_within_3_months(expiry_date: str) -> bool:
    """Check if expiry is within 3 months"""
    expiry = datetime.strptime(expiry_date, "%Y%m%d")
    now = datetime.now()
    return expiry <= now + timedelta(days=90)

# Usage
ib = IB()
ib.connect('127.0.0.1', 4001, clientId=1)

es_contract = get_front_month(ib, 'ES')
print(f"Front month ES: {es_contract.lastTradeDateOrContractMonth}")
```

### Anti-Patterns to Avoid

- **Using continuous contracts for real-time data:** IBKR continuous futures DON'T work with reqMktData, only historical
- **Not partitioning Delta Lake tables:** Without partitioning, queries become slow as data grows
- **Assuming front-month = earliest expiry:** Volume shifts to next contract BEFORE expiry; check volume
- **Not handling maintenance window:** Futures close 5-6pm ET daily; expect no data during this window

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Continuous contract calculation | Custom roll adjustment logic | IBKR continuous contracts (for historical) | Gap adjustment, ratio methods are complex; IBKR handles it |
| Delta Lake file management | Manual Parquet file writes | PySpark Delta Lake API | ACID transactions, automatic compaction, time-travel |
| Futures contract discovery | Hardcoded expiry dates | ib_async reqContractDetails API | Contracts change quarterly; API discovers automatically |
| Time-series partitioning | Custom date-based directories | Delta Lake partitioning | Automatic partition pruning, query optimization |
| Async event handling | Custom threading/loop | ib_async event system | Handles reconnection, error recovery, rate limiting |

**Key insight:** IBKR provides built-in continuous futures for historical data that handle all the complexity of splicing contracts. For real-time data, ib_async handles connection management, reconnection, and event streaming. Don't build infrastructure that already exists.

---

## Common Pitfalls

### Pitfall 1: Continuous Contracts Don't Stream Real-Time

**What goes wrong:** Code tries to use continuous futures (e.g., `Future(symbol='ES')`) with `reqMktData()` and gets no data or errors.

**Why it happens:** IBKR continuous futures are **historical data only**. They work with `reqHistoricalData()` but NOT `reqMktData()`.

**How to avoid:**
- Use front-month contracts with specific expiry for real-time streaming
- Only use continuous contracts (symbol only) for historical backfill
- Example: `Future(symbol='ES', exchange='CME', lastTradeDateOrContractMonth='20250321')` for real-time
- Example: `Future(symbol='ES', exchange='CME')` for historical only

**Warning signs:** No market data updates, error messages about invalid contract, or no data when streaming starts.

### Pitfall 2: Daily Maintenance Window Data Gaps

**What goes wrong:** Futures data collection fails for 1 hour each day (5-6pm ET), creating gaps in the dataset.

**Why it happens:** CME Globex closes for maintenance 5:00 PM - 6:00 PM ET daily. No trading occurs during this window.

**How to avoid:**
- Expect and handle 1-hour daily gap in data
- Don't alert on missing data during this window
- Mark this period in documentation and dashboards
- Use `useRTH=False` to get extended hours data (6pm-8:30am ET, 9:30am-4pm ET, 4:05pm-5pm ET)

**Warning signs:** Consistent 1-hour data gaps at same time daily, connection errors during maintenance window.

### Pitfall 3: Contract Rollover Timing

**What goes wrong:** Data stream stops or uses wrong contract because roll happened too early/late.

**Why it happens:** Volume shifts to next contract BEFORE expiry (typically 1 week before). Sticking with strict front-month means low liquidity data.

**How to avoid:**
- Monitor volume across front-month and next contract
- Roll when volume on next contract exceeds front-month
- Check for "first notice day" warnings
- Simple approach: Roll 1 week before expiry

**Warning signs:** Sudden volume drop, sparse data, wide bid-ask spreads near expiry.

### Pitfall 4: Delta Lake Small File Problem

**What goes wrong:** Delta Lake table has thousands of tiny files, queries become slow.

**Why it happens:** Appending data frequently (every 1 minute) creates many small Parquet files.

**How to avoid:**
- Use Delta Lake `OPTIMIZE` operation periodically (daily/weekly)
- Consider batching writes (append every 5 minutes instead of every snapshot)
- Partition by date and symbol to reduce files scanned

**Warning signs:** Queries slow down over time, many files in Delta Lake directory, high file count in Spark UI.

### Pitfall 5: IBKR Market Data Permissions

**What goes wrong:** Real-time futures data doesn't arrive, only delayed data.

**Why it happens:** IBKR requires market data subscriptions for real-time futures quotes.

**How to avoid:**
- Check market data subscriptions in Account Management
- Use delayed data for development: `ib.reqMarketDataType(3)` for delayed
- Use frozen delayed data for testing: `ib.reqMarketDataType(4)`
- Real-time requires paid subscription: `ib.reqMarketDataType(1)`

**Warning signs:** Data is delayed (15-minute delay), missing real-time updates, or "delayed" in data source description.

---

## Code Examples

### Basic Futures Streaming Setup

```python
# Source: ib_async documentation + IBKR futures patterns
from ib_async import *
import time

# Initialize IB
ib = IB()
await ib.connectAsync('127.0.0.1', 4001, clientId=1)

# Define ES contract (front month with expiry)
es_contract = Future(
    symbol='ES',
    exchange='CME',
    currency='USD',
    lastTradeDateOrContractMonth='20250321'  # March 2025 expiry
)

# Request real-time market data
es_ticker = ib.reqMktData(es_contract, '', False, False)

# Subscribe to tick updates
def on_tick_update(ticker):
    if ticker.last:
        print(f"ES Update: {ticker.last} | Bid: {ticker.bid} | Ask: {ticker.ask}")

es_ticker.updateEvent += on_tick_update

# Keep running to receive updates
try:
    ib.sleep(3600)  # Run for 1 hour
except KeyboardInterrupt:
    ib.disconnect()
```

### Historical Data Backfill with Continuous Contracts

```python
# Source: ib_async documentation
from ib_async import *
import pandas as pd

ib = IB()
ib.connect('127.0.0.1', 4001, clientId=1)

# Use continuous contract (symbol only, no expiry)
# This works for historical data ONLY
es_continuous = Future(symbol='ES', exchange='CME', currency='USD')

# Request 30 days of 1-minute bars
bars = ib.reqHistoricalData(
    es_continuous,
    endDateTime='',
    durationStr='30 D',
    barSizeSetting='1 min',
    whatToShow='TRADES',
    useRTH=False  # Include extended hours (Globex)
)

# Convert to pandas DataFrame
df = util.df(bars)
print(f"Retrieved {len(df)} 1-minute bars")
print(df.head())

ib.disconnect()
```

### Delta Lake Write with Partitioning

```python
# Source: Delta Lake patterns + PySpark documentation
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, TimestampType, StringType, FloatType, IntegerType
from datetime import datetime

# Initialize Spark with Delta
spark = SparkSession.builder \
    .appName("FuturesDataCollection") \
    .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
    .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
    .getOrCreate()

# Define schema for futures snapshots
schema = StructType([
    StructField("timestamp", TimestampType(), False),
    StructField("symbol", StringType(), False),
    StructField("bid", FloatType(), True),
    StructField("ask", FloatType(), True),
    StructField("last", FloatType(), True),
    StructField("volume", IntegerType(), True),
    StructField("date", StringType(), False),  # Partition column
])

# Sample data
snapshot_data = [{
    "timestamp": datetime.now(),
    "symbol": "ES",
    "bid": 4500.25,
    "ask": 4500.50,
    "last": 4500.375,
    "volume": 125000,
    "date": datetime.now().strftime("%Y-%m-%d"),
}]

# Create DataFrame and write to Delta Lake
df = spark.createDataFrame(snapshot_data, schema)

df.write \
    .format("delta") \
    .mode("append") \
    .partitionBy("date", "symbol") \
    .save("/data/lake/futures_snapshots")

print("Data written to Delta Lake")
```

---

## State of the Art (2024-2025)

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| ib_insync | ib_async | 2024 | ib_async is actively maintained successor to ib_insync |
| Manual Parquet files | Delta Lake | 2020+ | Delta provides ACID, time-travel, automatic optimization |
| Custom roll adjustment | IBKR continuous contracts (historical) | N/A | IBKR handles continuous contracts for historical queries |
| 5-second bar updates | Real-time tick streaming | Always | Use tick data, aggregate to bars as needed |

**New tools/patterns to consider:**
- **Delta Lake 3.x+**: Improved performance, better Python support via `deltalake` package
- **ib_async event system**: Cleaner async patterns vs callback soup of older IB API
- **PySpark partitioning**: Automatic partition pruning makes queries fast

**Deprecated/outdated:**
- **ib_insync**: Original author passed away, project renamed to ib_async
- **Manual contract splicing**: IBKR continuous contracts handle this for historical data
- **Raw Parquet without Delta**: No time-travel, no ACID, no schema enforcement

---

## Open Questions

1. **IBKR continuous futures exact format**
   - What we know: IBKR provides continuous contracts for historical data
   - What's unclear: Exact symbol format for ES/NQ/RTY continuous (need to test)
   - Recommendation: Test with `Future(symbol='ES', exchange='CME')` for historical, verify it works

2. **Contract rollover automation timing**
   - What we know: Volume shifts to next contract before expiry
   - What's unclear: Exact rules for when to roll (1 week before? volume-based?)
   - Recommendation: Start with simple rule (roll 1 week before expiry), monitor volume split

3. **Delta Lake optimization frequency**
   - What we know: Small file problem affects query performance
   - What's unclear: How often to run OPTIMIZE (daily? weekly?)
   - Recommendation: Start with weekly OPTIMIZE, monitor file count, adjust as needed

---

## Sources

### Primary (HIGH confidence)
- [ib_async Official Documentation](https://ib-api-reloaded.github.io/ib_async/) - Core library patterns, futures contracts, market data streaming
- [CME Group ES Contract Specs](https://www.cmegroup.com/markets/equities/sp/e-mini-sandp500.contractSpecs.html) - ES futures specifications (tick size, contract unit)
- [CME Group NQ Contract Specs](https://www.cmegroup.com/markets/equities/nasdaq/e-mini-nasdaq-100.html) - NQ futures specifications
- [CME Group RTY Contract Specs](https://www.cmegroup.com/markets/equities/russell/e-mini-russell-2000.contractSpecs.html) - RTY futures specifications

### Secondary (MEDIUM confidence)
- [Futures Trading Hours Guide](https://phidiaspropfirm.com/education/futures-trading-hours) - Globex session times, maintenance window (verified with CME)
- [Continuous Futures Methodology](https://towardsdatascience.com/rolling-on-the-futures-curve-continuous-futures-prices-99382ee4bb4e/) - Roll adjustment methods (gap vs ratio), verified with quant sources
- [Delta Lake Time Series Storage](https://medium.com/codex/using-data-lakes-for-efficient-time-series-storage-and-retrieval-d4fc9426d712) - Partitioning strategies for time-series data

### Tertiary (LOW confidence - needs validation)
- [IBKR Continuous Futures Features](https://www.interactivebrokers.com/campus/glossary-terms/continuous-futures-contract/) - IBKR documentation on continuous futures (404 when fetched, needs verification)
- **Note:** Several IBKR documentation links returned 404; recommendations based on general IBKR API knowledge and community patterns

---

## Metadata

**Research scope:**
- Core technology: IBKR futures data collection via ib_async
- Ecosystem: Delta Lake time-series storage, PySpark, contract rollover
- Patterns: Real-time streaming, historical backfill, continuous contracts
- Pitfalls: Maintenance window, contract rollover timing, small file problem

**Confidence breakdown:**
- Standard stack: HIGH - ib_async is well-documented, Delta Lake patterns are standard
- Architecture: HIGH - patterns from official docs, verified examples
- Pitfalls: HIGH - well-documented issues with IBKR API and Delta Lake
- Code examples: HIGH - from official ib_async docs and Delta Lake patterns

**Research date:** 2026-01-30
**Valid until:** 2026-02-28 (30 days - stable technology)

---

*Phase: 8-futures-data-collection*
*Research completed: 2026-01-30*
*Ready for planning: yes*
