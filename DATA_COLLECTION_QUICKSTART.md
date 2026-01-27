# Data Collection Quick Start Guide

## Quick Start (Market is Open!)

```bash
# 1. Ensure IB Gateway is running (paper trading account)
# TWS/Gateway → Configure → API → Enable ActiveX/Socket Clients
# Port: 7497 (paper) or 7496 (live)

# 2. Run test to verify everything works
python -m src.v6.scripts.test_data_collection

# 3. Start paper trading system (includes data collector)
python -m src.v6.orchestration.paper_trader
```

## File Structure

```
src/v6/
├── core/
│   └── market_data_fetcher.py       # OptionDataFetcher class
├── data/
│   └── option_snapshots.py          # OptionSnapshotsTable class
├── scripts/
│   ├── data_collector.py            # DataCollector background service
│   └── test_data_collection.py      # Test suite
└── orchestration/
    └── paper_trader.py              # Updated with data collector

data/lake/
└── option_snapshots/                # Delta Lake table (auto-created)
    ├── symbol=SPY/
    │   ├── yearmonth=202502/
    │   └── yearmonth=202503/
    ├── symbol=QQQ/
    └── symbol=IWM/
```

## Key Classes

### 1. OptionDataFetcher

```python
from src.v6.core.market_data_fetcher import OptionDataFetcher

fetcher = OptionDataFetcher(ib_conn, option_snapshots_table)

# Fetch option chain
contracts = await fetcher.fetch_option_chain("SPY")

# Calculate IV Rank
iv_rank = await fetcher.calculate_iv_rank("SPY")

# Get VIX
vix = await fetcher.get_vix()

# Get trend
trend = await fetcher.get_underlying_trend("SPY")

# Get all market data
market_data = await fetcher.get_market_data("SPY")
# Returns: {
#     "symbol": "SPY",
#     "iv_rank": 65.2,
#     "vix": 18.5,
#     "underlying_trend": "uptrend",
#     "option_chain": [...],
#     "timestamp": datetime(...)
# }
```

### 2. OptionSnapshotsTable

```python
from src.v6.data.option_snapshots import OptionSnapshotsTable

table = OptionSnapshotsTable("data/lake/option_snapshots")

# Write snapshots (deduplicated)
written = table.write_snapshots(contracts)

# Read latest chain
latest = table.read_latest_chain("SPY")

# Read historical IV
iv_history = table.read_historical_iv("SPY", days=60)

# Get statistics
stats = table.get_snapshot_stats()
```

### 3. DataCollector

```python
from src.v6.scripts.data_collector import DataCollector

collector = DataCollector(ib_conn, option_snapshots_table)

# Start background collection
await collector.start()

# Get latest market data (for entry signals)
market_data = await collector.get_latest_market_data("SPY")

# Health check
health = await collector.health_check()

# Stop
await collector.stop()
```

### 4. PaperTrader (Auto-Integration)

```python
from src.v6.orchestration import PaperTrader

trader = PaperTrader(config)

await trader.start()  # Starts data collector automatically
await trader.run_entry_cycle()  # Uses real market data
await trader.stop()  # Stops data collector
```

## Market Data Format

### OptionContract

```python
@dataclass
class OptionContract:
    symbol: str              # "SPY"
    timestamp: datetime      # Snapshot time
    strike: float            # 400.0
    expiry: str              # "20250221" (YYYYMMDD)
    right: str               # "P" or "C"
    bid: float               # 2.50
    ask: float               # 2.55
    last: float              # 2.52
    volume: int              # 1250
    open_interest: int       # 5000
    iv: float                # 0.185 (18.5%)
    delta: float             # -0.25
    gamma: float             # 0.02
    theta: float             # -0.05
    vega: float              # 0.15
```

### Market Data (Entry Input)

```python
{
    "symbol": "SPY",
    "iv_rank": 65.2,              # 0-100
    "vix": 18.5,                  # VIX index
    "underlying_trend": "uptrend", # "uptrend" | "downtrend" | "neutral"
    "timestamp": datetime(...)
}
```

## Collection Schedule

### Default Schedule

```
Every 5 minutes (300 seconds):
├─ SPY option chain (~500-1000 contracts)
├─ QQQ option chain (~400-800 contracts)
├─ IWM option chain (~300-600 contracts)
└─ Calculate IV Rank, VIX, trend for each
```

### Schedule Configuration

```python
# In paper_trader.py or standalone
collector = DataCollector(
    ib_conn=ib_conn,
    option_snapshots_table=option_snapshots_table,
    symbols=["SPY", "QQQ", "IWM"],
    collection_interval=300,  # Seconds (5 minutes)
)
```

### Recommended Intervals

- **Production:** 300 seconds (5 minutes)
- **Testing:** 60 seconds (1 minute)
- **High-frequency:** 30 seconds (may hit rate limits)

## Delta Lake Queries

### Latest Option Chain

```python
import polars as pl

table = OptionSnapshotsTable()
df = table.read_latest_chain("SPY")

# Filter for puts
puts = df.filter(pl.col("right") == "P")

# Filter for ATM options (delta -0.3 to -0.2)
atm = df.filter(
    (pl.col("right") == "P") &
    (pl.col("delta").is_between(-0.3, -0.2))
)

# Get cheapest options
cheapest = df.sort("bid").head(10)

# Calculate mid-price
df = df.with_column(
    (pl.col("bid") + pl.col("ask")) / 2
)
```

### Historical Analysis

```python
# Read IV history
iv_history = table.read_historical_iv("SPY", days=60)

# Calculate IV percentiles
iv_percentiles = iv_history.select([
    pl.col("avg_iv").quantile(0.25).alias("p25"),
    pl.col("avg_iv").quantile(0.50).alias("p50"),
    pl.col("avg_iv").quantile(0.75).alias("p75"),
])

# Plot IV over time
iv_history.plot(
    x="timestamp",
    y="avg_iv",
    title="SPY IV (60 days)"
)
```

## Testing

### Run Full Test Suite

```bash
python -m src.v6.scripts.test_data_collection
```

### Test Individual Components

```python
# Test table creation
table = OptionSnapshotsTable()
stats = table.get_snapshot_stats()
print(f"Table has {stats['total_rows']} rows")

# Test IB connection
from src.v6.utils.ib_connection import IBConnectionManager
ib_conn = IBConnectionManager()
await ib_conn.connect()
print(f"Connected: {ib_conn.is_connected}")

# Test option fetcher
fetcher = OptionDataFetcher(ib_conn, table)
vix = await fetcher.get_vix()
print(f"VIX: {vix}")

# Test single collection
collector = DataCollector(ib_conn, table)
results = await collector.collect_once()
print(results)
```

## Monitoring

### Check Collection Status

```python
health = await collector.health_check()

print(f"Healthy: {health['healthy']}")
print(f"IB Connected: {health['ib_connected']}")
print(f"Circuit Breaker: {health['circuit_breaker_state']}")
print(f"Table Rows: {health['table_rows']}")
print(f"Errors: {health['errors']}")
```

### View Collection Stats

```python
stats = collector.get_collection_stats()

print(f"Running: {stats['running']}")
print(f"Symbols: {stats['symbols']}")
print(f"Interval: {stats['collection_interval']}s")
print(f"Total Rows: {stats['table_stats']['total_rows']}")
```

### Log Files

```
logs/
├── paper_trading.log           # Paper trader logs
├── data_collection.log         # Data collector logs (TODO: add)
└── v6.log                      # General V6 logs
```

## Troubleshooting

### Problem: No data collected

```bash
# Check if IB Gateway is running
ps aux | grep ibgateway

# Check if market is open
# Market hours: 9:30 AM - 4:00 PM ET (Mon-Fri)

# Check logs
tail -f logs/paper_trading.log
```

### Problem: Circuit breaker open

```python
# Check circuit breaker state
health = await collector.health_check()
print(f"Circuit breaker: {health['circuit_breaker_state']}")

# Wait for timeout (60 seconds)
# Or restart IB Gateway
```

### Problem: IV Rank always 50.0

```python
# Need at least 30 days of data
stats = table.get_snapshot_stats()
print(f"Total rows: {stats['total_rows']}")

# Check date range
if stats['date_range']:
    start = stats['date_range']['start']
    end = stats['date_range']['end']
    days = (end - start).days
    print(f"Date range: {days} days")
```

## Configuration

### Paper Trading Config

```yaml
# config/paper_trading.yaml
ib_host: "127.0.0.1"
ib_port: 7497                    # Paper trading port
ib_client_id: 1
allowed_symbols: ["SPY", "QQQ", "IWM"]
data_dir: "data/lake"
log_file: "logs/paper_trading.log"
max_positions: 3
max_order_size: 10
```

### Environment Variables

```bash
# Optional: Override config with env vars
export IB_HOST="127.0.0.1"
export IB_PORT="7497"
export IB_CLIENT_ID="1"
```

## Next Steps

1. ✓ Review documentation: `DATA_COLLECTION_SYSTEM.md`
2. ✓ Run test suite: `python -m src.v6.scripts.test_data_collection`
3. ✓ Start paper trading: `python -m src.v6.orchestration.paper_trader`
4. ✓ Monitor logs: `tail -f logs/paper_trading.log`
5. ✓ Check data: Verify data/lake/option_snapshots has data
6. ✓ Query data: Use OptionSnapshotsTable to read back data
7. ✓ Build ML features: Use historical data for feature engineering
8. ✓ Backtest strategies: Use complete option chain history

## Support

For issues or questions:
1. Check logs: `logs/paper_trading.log`
2. Check health: `await collector.health_check()`
3. Run test: `python -m src.v6.scripts.test_data_collection`
4. Review docs: `DATA_COLLECTION_SYSTEM.md`

---

**Status:** ✓ Ready for production
**Market:** Check if market is open (9:30 AM - 4:00 PM ET)
**Start:** Run `python -m src.v6.orchestration.paper_trader` now!
