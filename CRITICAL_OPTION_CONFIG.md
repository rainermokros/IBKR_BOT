# CRITICAL OPTION COLLECTION CONFIGURATION

## EXCHANGE SETTINGS (MUST REMEMBER)

### STOCK Contracts
- Exchange: **SMART** ✓ CORRECT
- Example: `Stock('SPY', 'SMART', 'USD')`

### OPTION Contracts
- Exchange: **CBOE** ✓ CORRECT
- Exchange: **SMART** ✗ WRONG - DOES NOT WORK
- Example: `Option('SPY', '20260320', 690, 'P', 'CBOE', 'USD')`

## ERROR HANDLING

### Error 200 (No security definition found)
- **STATUS**: NORMAL - Some option contracts don't exist
- **ACTION**: IGNORE and skip these contracts
- **DO NOT**: Retry, add to queue, or log as error

### Other Errors
- **ACTION**: Log as warning, skip, DO NOT retry

## OPTION DATA COLLECTION

### Working Configuration (from yesterday's data)
- **Expiry Format**: YYYYMMDD (e.g., '20260320' = March 20, 2026)
- **Strike Selection**: Within ±5% of current price
- **Expiry Selection**: Monthly expirations (day >= 15 of month)
- **DTE Filter**: Within 45 days of expiration
- **Collection Frequency**: Every 5 minutes during market hours

### Table Schema
```
Table: option_snapshots
Partition: [strike_partition, symbol]
Columns: timestamp, symbol, strike, expiry, right, bid, ask, last,
          volume, open_interest, iv, delta, gamma, theta, vega, date, yearmonth
```

### Data Model
```python
from v6.system_monitor.futures_analyzer.models import OptionContract
contract = OptionContract(
    timestamp=datetime.now(),
    symbol="SPY",
    strike=690.0,
    expiry="20260320",
    right="P",  # or "C"
    bid=1.50,
    ask=1.52,
    last=1.51,
    volume=100,
    open_interest=1000,
    iv=0.20,
    delta=-0.45,
    gamma=0.01,
    theta=-0.05,
    vega=0.10
)
```

### Collection Code Pattern
```python
from v6.pybike.ib_wrapper import IBWrapper
from v6.system_monitor.data.option_snapshots import OptionSnapshotsTable

async with IBWrapper() as ib:
    snapshots = await ib.get_option_chains('SPY')

    # Convert to OptionContract objects
    contracts = [OptionContract(**s) for s in snapshots]

    # Write to Delta Lake
    table = OptionSnapshotsTable()
    written = table.write_snapshots(contracts)
```

## VERIFICATION CHECKLIST

Before running Strategy Builder:
1. ✓ Check logs for "Collected N snapshots"
2. ✓ Check logs for "Wrote N rows"
3. ✓ Verify option_snapshots table has new rows (timestamp > today)
4. ✓ Verify data has Greeks (iv, delta, gamma, theta, vega not all 0)

## FILES TO REMEMBER

- **IBWrapper**: `src/v6/pybike/ib_wrapper.py`
- **Snapshots Table**: `src/v6/system_monitor/data/option_snapshots.py`
- **Collection Script**: `scripts/collect_option_snapshots.py`
- **Data Model**: `src/v6/system_monitor/futures_analyzer/models.py`

## SESSION HISTORY

- Date: 2026-02-03
- Problem: IBWrapper using SMART exchange for options (WRONG)
- Fix: Use CBOE exchange for options, SMART only for stocks
- Working data from: 2026-02-02 16:19:47 (84,874 rows)
- Issue today: 0 rows collected due to wrong exchange
