# Unified Queue System - V6 Refactoring

## 🎯 Goal

Replace ALL direct IB connections with ONE unified queue system:
- **ONE** queue table for all IB requests
- **ONE** QueueWorker processing everything
- **ONE** IB connection point
- Simple, unified architecture

---

## 📊 Current State (V5 Mess Recreated)

```
❌ Multiple IB connection paths:
   - PositionQueue (position updates)
   - DataCollector (direct streaming for options/futures)
   - MarketDataFetcher (direct connection)
   - FuturesFetcher (direct connection)

❌ Multiple streaming slots consumed
❌ Complex to monitor/debug
❌ Hard to manage connection lifecycle
```

---

## ✅ Target State (Unified V6)

```
✅ ONE queue table: ib_requests
   → All option data collection
   → All futures data collection
   → All position updates
   → All market data requests
   → EVERYTHING

✅ ONE QueueWorker
   → Processes queue in batches
   → Single IB connection
   → Conserves streaming slots
   → Easy to monitor

✅ Simple architecture:
   Queue Table → QueueWorker → IB Gateway → Result Tables
```

---

## 📋 Implementation Plan

### Phase 1: Extend Queue Schema

**File:** `src/v6/data/ib_request_queue.py`

**New Schema:**
```python
@dataclass
class IBRequest:
    request_id: str                    # UUID
    request_type: str                  # "option_chain", "futures_snapshot",
                                     # "position_update", "market_bars"
    symbol: str
    priority: int                      # 1=immediate, 2=normal, 3=background
    status: str                        # PENDING, PROCESSING, SUCCESS, FAILED
    parameters: dict                   # JSON: {strike, expiry, interval, etc.}
    result_table: str                  # Where to save result
    created_at: datetime
    updated_at: datetime
    result_data: Optional[dict] = None
    error_message: Optional[str] = None
```

**Request Types:**
- `option_chain`: Fetch option chain for symbol
- `futures_snapshot`: Fetch futures snapshot (ES, NQ, RTY)
- `market_bars`: Fetch historical market bars (SPY, QQQ, IWM)
- `position_update`: Update position data

---

### Phase 2: Create UnifiedQueueWorker

**File:** `src/v6/core/unified_queue_worker.py`

**Responsibilities:**
1. Connect to IB Gateway (single connection)
2. Pull requests from queue (by priority)
3. Process each request type
4. Save results to appropriate tables
5. Mark requests as SUCCESS/FAILED
6. Handle errors and retries

**Key Features:**
- Batch processing (process 50 requests at a time)
- Circuit breaker for error handling
- Connection pooling (single IB connection)
- Graceful shutdown

---

### Phase 3: Update Unified Scheduler

**File:** `src/v6/scheduler/unified_scheduler.py`

**Changes:**
- Remove direct IB connections
- Queue all data collection requests
- Let QueueWorker handle everything

**Example:**
```python
# OLD (direct connection):
await self._collect_option_data()

# NEW (via queue):
await self.queue.insert(
    request_type="option_chain",
    symbol="SPY",
    priority=2,
    parameters={"dte": 45},
    result_table="option_snapshots"
)
```

---

### Phase 4: Update Data Collection Scripts

**Scripts to update:**
- `src/v6/scripts/load_futures_data.py`
- `src/v6/scripts/load_historical_data.py`
- `src/v6/scripts/derive_statistics.py`

**Change:** All scripts queue requests instead of direct IB calls

---

### Phase 5: Retire Old Components

**Components to deprecate:**
- `DataCollector` (replace with queue)
- `OptionDataFetcher` (replace with queue)
- `FuturesFetcher` (replace with queue)
- Direct IB connections in scheduler

**Keep:**
- `IBConnectionManager` (used by QueueWorker)
- Delta Lake tables (storage layer)

---

## 🗂️ New File Structure

```
src/v6/
├── data/
│   ├── ib_request_queue.py          # NEW: Unified queue
│   ├── position_queue.py             # DEPRECATE: Merge into ib_request_queue
│   ├── option_snapshots.py           # KEEP: Storage
│   ├── futures_snapshots.py          # KEEP: Storage
│   ├── market_bars.py                # KEEP: Storage
│   └── derived_statistics.py         # KEEP: Storage
├── core/
│   ├── unified_queue_worker.py       # NEW: Single IB processor
│   ├── ib_connection.py              # KEEP: Connection manager
│   ├── market_data_fetcher.py        # DEPRECATE: Use queue
│   └── futures_fetcher.py            # DEPRECATE: Use queue
└── scheduler/
    └── unified_scheduler.py          # UPDATE: Use queue
```

---

## 🔄 Queue Flow

```
┌──────────────────────────────────────────────────────────────┐
│ 1. REQUEST QUEUE                                              │
├──────────────────────────────────────────────────────────────┤
│  UnifiedScheduler / Scripts                                  │
│       │                                                        │
│       ▼                                                        │
│  ib_request_queue (Delta Lake)                                │
│  - request_type: "option_chain"                               │
│  - symbol: "SPY"                                             │
│  - priority: 2                                                │
│  - parameters: {"dte": 45}                                    │
│  - result_table: "option_snapshots"                          │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ 2. QUEUEWORKER PROCESSING                                     │
├──────────────────────────────────────────────────────────────┤
│  UnifiedQueueWorker                                           │
│  - Pull batch (50 requests)                                  │
│  - Sort by priority                                           │
│  - Connect to IB Gateway                                     │
│  - Process each request:                                     │
│    • option_chain → OptionSnapshotsTable                    │
│    • futures_snapshot → FuturesSnapshotsTable               │
│    • market_bars → MarketBarsTable                          │
│    • position_update → PositionQueue (if needed)           │
│  - Mark SUCCESS/FAILED                                       │
│  - Save results                                               │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ 3. RESULT TABLES                                             │
├──────────────────────────────────────────────────────────────┤
│  Delta Lake Tables (filled by QueueWorker):                   │
│  - option_snapshots (real-time options)                       │
│  - futures_snapshots (real-time futures)                     │
│  - market_bars (historical OHLCV)                             │
│  - derived_statistics (calculated daily)                      │
└──────────────────────────────────────────────────────────────┘
```

---

## ✅ Benefits

1. **Simplicity**: ONE queue, ONE worker, ONE connection
2. **Monitoring**: All IB activity in one place
3. **Efficiency**: Batch processing conserves streaming slots
4. **Reliability**: Easy retry/error handling via queue
5. **Debugging**: Single point to monitor all IB requests
6. **Scalability**: Easy to add new request types

---

## 📝 Success Criteria

- [ ] All IB requests go through ib_request_queue
- [ ] Single UnifiedQueueWorker processes everything
- [ ] No more direct IB connections in scheduler
- [ ] DataCollector deprecated (use queue)
- [ ] All 4 Delta Lake tables populated via queue
- [ ] Unified scheduler queues all requests
- [ ] System tested and working

---

**Status:** Ready to implement
**Complexity:** Medium (refactor existing components)
**Impact:** High (unifies architecture, eliminates complexity)

---

**Created:** January 28, 2026
**Purpose:** Unify V6 IB Gateway channel (eliminate V5 complexity)
