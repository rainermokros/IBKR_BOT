# Market Data Collection System - V6

## Overview

Complete market data collection system for V6 that continuously fetches and stores option contract data for SPY, QQQ, and IWM. The system runs as a background service in the paper trading orchestrator and provides real-time market data for entry signal evaluation.

## Architecture

### Components

1. **OptionDataFetcher** (`src/v6/core/market_data_fetcher.py`)
   - Fetches complete option chains from IB API
   - Calculates IV Rank from historical Delta Lake data
   - Fetches VIX index value
   - Determines underlying trend (uptrend/downtrend/neutral)
   - Uses circuit breaker for error handling

2. **OptionSnapshotsTable** (`src/v6/data/option_snapshots.py`)
   - Delta Lake table for option contract storage
   - Partitioned by symbol and yearmonth(expiry)
   - Idempotent writes using timestamp+symbol+strike+expiry deduplication
   - Query methods for latest chain and historical IV

3. **DataCollector** (`src/v6/scripts/data_collector.py`)
   - Background service for continuous data collection
   - Fetches option chains every 5 minutes (configurable)
   - Stores snapshots to Delta Lake
   - Health check and monitoring

4. **PaperTrader Integration** (`src/v6/orchestration/paper_trader.py`)
   - Starts data collector on startup
   - Uses real market data for entry evaluation
   - Stops data collector on shutdown

## Data Flow

```
┌─────────────────┐
│   IB Gateway    │
│  (Paper Account)│
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│              OptionDataFetcher                          │
│  • fetch_option_chain()  → List[OptionContract]         │
│  • calculate_iv_rank()   → float (0-100)               │
│  • get_vix()            → float                         │
│  • get_underlying_trend() → str (uptrend/down/neutral) │
└────────┬────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│            OptionSnapshotsTable                         │
│  Delta Lake: data/lake/option_snapshots                 │
│  Partition: symbol, yearmonth(expiry)                   │
│                                                           │
│  Schema:                                                  │
│  - timestamp, symbol, strike, expiry, right             │
│  - bid, ask, last, volume, open_interest               │
│  - iv, delta, gamma, theta, vega                        │
└─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│                DataCollector                            │
│  Background Task: Collect every 5 minutes               │
│  • Fetch option chains for SPY, QQQ, IWM               │
│  • Calculate IV Rank, VIX, trend                        │
│  • Write snapshots to Delta Lake                        │
│  • Idempotent (handles duplicates)                      │
└─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│              PaperTrader                                │
│  Entry Workflow:                                         │
│  • get_latest_market_data(symbol) → market_data         │
│  • evaluate_entry_signal(symbol, market_data)           │
│  • Execute entry with real market conditions            │
└─────────────────────────────────────────────────────────┘
```

## Schema

### OptionSnapshotsTable

**Table Path:** `data/lake/option_snapshots`

**Schema:**
```python
{
    'timestamp': pl.Datetime("us"),      # Snapshot timestamp
    'symbol': pl.String,                 # SPY, QQQ, IWM
    'strike': pl.Float64,                # Strike price
    'expiry': pl.String,                 # YYYYMMDD format
    'right': pl.String,                  # 'P' or 'C'
    'bid': pl.Float64,                   # Best bid
    'ask': pl.Float64,                   # Best ask
    'last': pl.Float64,                  # Last trade price
    'volume': pl.Int64,                  # Trading volume
    'open_interest': pl.Int64,           # Open interest
    'iv': pl.Float64,                    # Implied volatility
    'delta': pl.Float64,                 # Option delta
    'gamma': pl.Float64,                 # Option gamma
    'theta': pl.Float64,                 # Option theta
    'vega': pl.Float64,                  # Option vega
    'yearmonth': pl.Int32,               # For partitioning (202502)
    'date': pl.Date,                     # For partitioning
}
```

**Partitions:**
- `symbol`: SPY, QQQ, IWM
- `yearmonth`: Expiry year-month (e.g., 202502 for Feb 2025)

**Deduplication Key:**
- timestamp + symbol + strike + expiry + right
- Last-Write-Wins conflict resolution

## Usage

### Basic Usage (PaperTrader Integration)

The data collector is automatically started when PaperTrader starts:

```python
from src.v6.orchestration import PaperTrader
from src.v6.config import PaperTradingConfig

config = PaperTradingConfig.load_from_file("config/paper_trading.yaml")
paper_trader = PaperTrader(config)

await paper_trader.start()  # Starts data collector automatically
await paper_trader.run_entry_cycle()  # Uses real market data
await paper_trader.stop()
```

### Standalone Usage

You can also run the data collector standalone:

```python
from src.v6.scripts.data_collector import DataCollector
from src.v6.data.option_snapshots import OptionSnapshotsTable
from src.v6.utils.ib_connection import IBConnectionManager

# Create components
ib_conn = IBConnectionManager(host="127.0.0.1", port=7497, client_id=1)
option_snapshots_table = OptionSnapshotsTable()
data_collector = DataCollector(ib_conn, option_snapshots_table)

# Start collection
await ib_conn.connect()
await data_collector.start()

# Runs in background...
await asyncio.sleep(3600)  # Run for 1 hour

# Stop
await data_collector.stop()
await ib_conn.disconnect()
```

### Single Collection Cycle

For testing or manual collection:

```python
results = await data_collector.collect_once()

for symbol, data in results.items():
    print(f"{symbol}: {data['contracts_written']} contracts, "
          f"IV Rank={data['iv_rank']}, VIX={data['vix']}")
```

### Querying Data

Read latest option chain:

```python
latest_chain = option_snapshots_table.read_latest_chain("SPY")
print(f"Found {len(latest_chain)} contracts")

# Filter for ATM options
atm_options = latest_chain.filter(
    (pl.col("right") == "P") &
    (pl.col("delta").is_between(-0.3, -0.2))
)
```

Read historical IV data:

```python
historical_iv = option_snapshots_table.read_historical_iv("SPY", days=60)
print(f"IV Range: {historical_iv.select('min_iv').min()} - "
      f"{historical_iv.select('max_iv').max()}")
```

## Configuration

### Data Collection Parameters

```python
data_collector = DataCollector(
    ib_conn=ib_conn,
    option_snapshots_table=option_snapshots_table,
    symbols=["SPY", "QQQ", "IWM"],           # Symbols to collect
    collection_interval=300,                  # Seconds (5 minutes)
)
```

### IB Connection

Uses existing IBConnectionManager:

```python
ib_conn = IBConnectionManager(
    host="127.0.0.1",      # IB Gateway host
    port=7497,             # Paper trading port
    client_id=1,           # Unique client ID
    max_retries=3,         # Retry attempts
    retry_delay=2.0,       # Exponential backoff base
)
```

## IV Rank Calculation

**Formula:**
```
IV Rank = (Current IV - Min IV) / (Max IV - Min IV) * 100
```

**Implementation:**
1. Read last 60 days of IV data from Delta Lake
2. Calculate daily IV averages (ATM options or all options)
3. Find min/max IV in the period
4. Calculate current IV rank

**Default Values:**
- If insufficient data (< 30 days): Returns 50.0 (mid-range)
- If max_iv == min_iv: Returns 50.0 (avoid division by zero)

## Trend Calculation

**Method:** Simple Moving Average Crossover

**Logic:**
- **Uptrend:** Price > SMA(20) and SMA(20) > SMA(50)
- **Downtrend:** Price < SMA(20) and SMA(20) < SMA(50)
- **Neutral:** Neither condition met

**Data:** Fetches 50 days of daily bars from IB

## Error Handling

### Circuit Breaker

Prevents retry storms when IB API fails:

```python
circuit_breaker = CircuitBreaker(
    failure_threshold=5,    # Open after 5 consecutive failures
    timeout=60,            # Try again after 60 seconds
)

# States:
# - CLOSED: Normal operation
# - OPEN: Failing, block requests
# - HALF_OPEN: Testing if recovered
```

### Idempotent Writes

Handles duplicate snapshots automatically:

1. Deduplicate within batch (keep latest timestamp)
2. Anti-join with existing data
3. Only write new or updated records
4. Last-Write-Wins conflict resolution

### Retry Logic

IB connection uses exponential backoff:

- Attempt 1: Immediate
- Attempt 2: Wait 2s (2^1)
- Attempt 3: Wait 4s (2^2)
- Attempt 4: Wait 8s (2^3)

## Testing

### Run Test Suite

```bash
python -m src.v6.scripts.test_data_collection
```

**Tests:**
1. ✓ Create OptionSnapshotsTable
2. ✓ Connect to IB
3. ✓ Create OptionDataFetcher
4. ✓ Fetch VIX
5. ✓ Calculate underlying trend
6. ✓ Calculate IV Rank
7. ✓ Fetch option chain
8. ✓ Write snapshots to Delta Lake
9. ✓ Read back latest chain
10. ✓ Verify data integrity
11. ✓ Get table statistics
12. ✓ Check connection health

### Manual Testing

Test data collection manually:

```python
# Fetch single option chain
contracts = await option_fetcher.fetch_option_chain("SPY")
print(f"Fetched {len(contracts)} contracts")

# Check IV Rank
iv_rank = await option_fetcher.calculate_iv_rank("SPY")
print(f"IV Rank: {iv_rank}")

# Get market data
market_data = await option_fetcher.get_market_data("SPY")
print(f"VIX: {market_data['vix']}, Trend: {market_data['underlying_trend']}")
```

## Monitoring

### Health Check

```python
health = await data_collector.health_check()
print(f"Healthy: {health['healthy']}")
print(f"IB Connected: {health['ib_connected']}")
print(f"Table Rows: {health['table_rows']}")
print(f"Errors: {health['errors']}")
```

### Collection Stats

```python
stats = data_collector.get_collection_stats()
print(f"Running: {stats['running']}")
print(f"Symbols: {stats['symbols']}")
print(f"Interval: {stats['collection_interval']}s")
print(f"Table Stats: {stats['table_stats']}")
```

### Table Statistics

```python
stats = option_snapshots_table.get_snapshot_stats()
print(f"Total Rows: {stats['total_rows']}")
print(f"Symbols: {stats['symbols']}")
print(f"Date Range: {stats['date_range']}")
print(f"Latest Timestamp: {stats['latest_timestamp']}")
```

## Performance Considerations

### Collection Interval

- **Default:** 5 minutes (300 seconds)
- **Minimum:** 60 seconds (IB rate limits)
- **Recommended:** 300 seconds for 3 symbols

### Data Volume

Per collection cycle (approximate):
- SPY: 500-1000 contracts
- QQQ: 400-800 contracts
- IWM: 300-600 contracts
- **Total:** 1200-2400 contracts per cycle

### Storage Growth

- Per snapshot: ~500 bytes
- Per cycle (3 symbols): ~1 MB
- Per day (12 cycles): ~12 MB
- Per month: ~360 MB

### Query Performance

Partitioning by symbol and yearmonth ensures:
- Fast queries for specific symbols
- Efficient time-based queries
- Minimal data scanning

## Troubleshooting

### No Data Collected

**Symptom:** `table_rows = 0`

**Causes:**
1. IB connection failed
2. Market closed
3. Circuit breaker open
4. Rate limit exceeded

**Solutions:**
1. Check IB Gateway is running
2. Verify market hours (9:30 AM - 4:00 PM ET)
3. Check logs for circuit breaker state
4. Increase collection_interval

### IV Rank Returns 50.0

**Symptom:** IV Rank always returns 50.0

**Causes:**
1. Insufficient historical data (< 30 days)
2. No IV data in Delta Lake
3. All IV values are identical

**Solutions:**
1. Run collector for 2+ days to accumulate data
2. Check if IV values are being stored
3. Verify IV calculation in option chain

### Circuit Breaker Open

**Symptom:** Logs show "Circuit breaker OPEN"

**Causes:**
1. IB Gateway not responding
2. Network issues
3. Invalid credentials

**Solutions:**
1. Restart IB Gateway
2. Check network connection
3. Verify account settings
4. Wait for timeout (60 seconds)

### Missing Greeks

**Symptom:** Delta, gamma, theta, vega are None

**Causes:**
1. IB not returning Greeks (market closed?)
2. Incorrect generic tick request
3. Option not trading

**Solutions:**
1. Verify market is open
2. Check generic tick string "100,101,104,105,106"
3. Wait for market data to populate

## Future Enhancements

### Phase 8: Futures Data Collection

Follow the same pattern for futures:

```python
# Similar structure
class FuturesDataFetcher:
    async def fetch_futures_chain(self, symbol: str) -> List[FuturesContract]
    async def calculate_contango_backwardation(self, symbol: str) -> float
    ...

class FuturesSnapshotsTable:
    # Delta Lake for futures data
    ...
```

### ML Training Data

The option snapshots table will be used for ML training:

```python
# Read historical data for ML training
training_data = option_snapshots_table.read_historical_iv("SPY", days=365)

# Features: IV Rank, VIX, trend, Greeks
# Targets: Future returns, realized volatility
```

### Backtesting

Complete option chain history enables backtesting:

```python
# Get historical option chain for backtesting
historical_chain = option_snapshots_table.read_latest_chain("SPY")
    .filter(pl.col("timestamp") == target_date)

# Test strategy performance
backtest_results = run_backtest(historical_chain, strategy)
```

## Summary

The V6 market data collection system provides:

- ✓ Continuous option chain collection for SPY, QQQ, IWM
- ✓ IV Rank calculation from historical data
- ✓ VIX and trend indicators for entry signals
- ✓ Delta Lake storage for backtesting and ML
- ✓ Idempotent writes with deduplication
- ✓ Circuit breaker for error handling
- ✓ PaperTrader integration
- ✓ Health monitoring and statistics

Start collecting data immediately to build historical dataset for ML training!
