# V6 Scheduler Scripts

This directory contains scheduling scripts for automated data collection in the V6 trading system.

## Morning Scheduler

**Purpose:** Collect historical ETF data (SPY, QQQ, IWM) at 9:00 AM ET daily.

**What it does:**
- Fetches daily OHLCV bars (last 5 trading days)
- Collects Implied Volatility (IV) data
- Collects Historical Volatility (HV) data
- Stores data to Delta Lake for backtesting and analysis

**Time window:** 9:00-9:45 AM ET (Monday-Friday, market days only)

### Usage

#### Manual execution

```bash
# From v6 directory
cd /home/bigballs/project/bot/v6

# Run immediately (skip time check)
python -m src.v6.scheduler.morning_scheduler --force

# Run with time check (only within 9:00-9:45 AM ET window)
python -m src.v6.scheduler.morning_scheduler
```

#### Using the startup script

```bash
# Run immediately (skip time check)
/home/bigballs/project/bot/v6/scripts/start_morning_scheduler.sh --force

# Run with time check
/home/bigballs/project/bot/v6/scripts/start_morning_scheduler.sh
```

### Cron Setup

Add the following line to your crontab (`crontab -e`):

```bash
# Run Monday-Friday at 9:00 AM ET
0 9 * * 1-5 /home/bigballs/project/bot/v6/scripts/start_morning_scheduler.sh
```

### Logs

- **Main log:** `logs/scheduler/morning_scheduler.log`
- **Daily logs:** `logs/scheduler/morning_scheduler_YYYYMMDD.log`
- **Rotation:** 50 MB per file, 30-day retention

### Time Zone

The scheduler uses the system time zone. Ensure your server is set to ET (Eastern Time):

```bash
# Check current timezone
timedatectl

# Set to ET (if needed)
sudo timedatectl set-timezone America/New_York
```

### Troubleshooting

#### Scheduler won't run (time check fails)

Use the `--force` flag to skip the time window check:

```bash
python -m src.v6.scheduler.morning_scheduler --force
```

#### IB Gateway connection errors

Check that IB Gateway is running on port 4002:

```bash
# Check if IB Gateway is listening
netstat -an | grep 4002

# Or test connection
telnet 127.0.0.1 4002
```

Common issues:
- **Client ID in use:** Another process is connected to IB Gateway
  - Solution: Stop other IB connections or use a different client ID
- **IB Gateway not running:** Start IB Gateway before the scheduler runs
- **Port mismatch:** Verify IB Gateway is configured to use port 4002

#### No data collected

Check the logs for errors:

```bash
tail -f logs/scheduler/morning_scheduler.log
```

Verify data is being written to Delta Lake:

```bash
# Check if bars were written
python -c "
from v6.data.market_bars import MarketBarsTable
table = MarketBarsTable()
summary = table.get_bars_summary()
print(f'Total bars: {summary[\"total_rows\"]}')
print(f'Symbols: {summary[\"symbols\"]}')
print(f'Latest: {summary[\"latest_timestamp\"]}')
"
```

## Intraday Scheduler

See `unified_scheduler.py` for the 9:30 AM - 4:00 PM ET intraday data collection scheduler.

## Architecture

The V6 scheduling system uses:

- **NYSE Calendar:** Trading day detection, market hours
- **Delta Lake:** Data storage (Parquet format)
- **IB Gateway:** Market data source via ib_async
- **Asyncio:** Async/await for concurrent operations

## Development

### Adding new scheduled tasks

1. Create a new scheduler script in `src/v6/scheduler/`
2. Follow the pattern in `morning_scheduler.py`:
   - Time window check
   - Trading day check
   - Data collection with retry logic
   - Comprehensive logging
3. Add a startup script in `scripts/`
4. Update this README with cron instructions

### Testing schedulers

Always test with the `--force` flag to bypass time checks:

```bash
python -m src.v6.scheduler.your_scheduler --force
```

Verify data was written before deploying to cron.

## Related Files

- `src/v6/scheduler/nyse_calendar.py` - NYSE trading calendar
- `src/v6/scheduler/unified_scheduler.py` - Master scheduler for all tasks
- `src/v6/scripts/load_historical_data.py` - Historical data loading module
- `src/v6/data/market_bars.py` - Delta Lake table for market bars
- `src/v6/utils/ib_connection.py` - IB Gateway connection manager
