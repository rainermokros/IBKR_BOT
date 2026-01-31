---
phase: 8-futures-data-collection
plan: 01
type: execute
depends_on: []
files_modified: [src/v6/data/futures_persistence.py, src/v6/core/futures_fetcher.py, src/v6/utils/scheduler.py, config/futures_config.yaml, scripts/collect_futures_snapshots.py, tests/futures/test_futures_integration.py]
---

<objective>
Implement futures data collection infrastructure (ES, NQ, RTY) using unified IBKR connection and queue table patterns.

Purpose: Collect 24/7 futures data (except maintenance window 5-6pm ET) as leading indicators for entry signal prediction. Uses existing IBKR connection infrastructure and follows established queue table rate-limiting patterns.

Output: Working futures data collection system that stores snapshots to Delta Lake, integrated with existing IB connection and queue worker infrastructure.
</objective>

<execution_context>
@~/.claude/get-shit-done/workflows/execute-plan.md
@.planning/STATE.md
@.planning/phases/8-futures-data-collection/8-01-PLAN.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/8-futures-data-collection/8-CONTEXT.md
@.planning/phases/8-futures-data-collection/8-RESEARCH.md
@src/v6/data/futures_persistence.py
@src/v6/core/futures_fetcher.py
@src/v6/data/queue_worker.py
@src/v6/data/ib_request_queue.py
@src/v6/utils/ib_connection.py
@src/v6/config/futures_config.py

**Tech stack available:**
- ib_async (2.0+) for IBKR API
- Delta Lake (via deltalake Python package) for time-series storage
- Polars for DataFrame operations
- Existing IBConnectionManager with circuit breaker

**Established patterns:**
- Queue table pattern for rate limiting (ib_request_queue.py)
- Batch writes with 1-minute intervals (avoid small files)
- Circuit breaker for error recovery (IBConnectionManager)
- Delta Lake persistence with partitioning

**Constraining decisions:**
- **Phase 2-2**: Hybrid position sync uses StrategyRegistry for slot management - futures should share IB connection
- **Phase 2-1**: Position queue pattern for non-active positions - futures should use similar queue-based approach
- **Phase 7**: Production deployment uses systemd services - futures collector should integrate with existing services

**What exists:**
- FuturesFetcher class in src/v6/core/futures_fetcher.py (partially implemented)
- FuturesSnapshotsTable and DeltaLakeFuturesWriter in src/v6/data/futures_persistence.py
- FuturesConfig in src/v6/config/futures_config.py
- Basic tests in tests/futures/

**Issues being addressed:**
- Futures data collection needs to integrate with existing IB connection (not separate connection)
- Must follow queue table pattern to avoid rate limiting issues
- Need unified collection script that can run as systemd service

**Concerns being verified:**
- IBKR continuous futures only work for historical data, not real-time streaming (from RESEARCH.md)
- Daily maintenance window 5-6pm ET will cause data gaps (expected behavior)
- Contract rollover timing needs simple approach (1 week before expiry)
</context>

<tasks>

<task type="auto">
  <name>Task 1: Verify futures fetcher integration with IB connection</name>
  <files>src/v6/core/futures_fetcher.py</files>
  <action>
    Verify and update FuturesFetcher to use unified IB connection:

    1. Ensure FuturesFetcher uses IBConnectionManager (not separate IB connection)
    2. Implement subscribe_to_futures() method for ES, NQ, RTY using front-month contracts
    3. Add change metrics calculation (1h, 4h, overnight, daily) from historical data
    4. Implement contract rollover detection (1 week before expiry)
    5. Handle daily maintenance window (5-6pm ET) gracefully - log warning, don't alert

    Key implementation details:
    - Use ib_async Contract with secType='FUT', symbol='ES', exchange='CME', currency='USD'
    - For real-time: include lastTradeDateOrContractMonth (e.g., '20250321')
    - For historical: omit lastTradeDateOrContractMonth (IBKR continuous contracts)
    - Change metrics: calculate % change from price N hours ago
    - Contract rollover: check expiry date, roll when < 7 days to expiry

    Error handling:
    - Circuit breaker for connection failures (already in IBConnectionManager)
    - Log warnings for maintenance window data gaps
    - Return empty snapshot on IB errors (don't crash collector)
  </action>
  <verify>
    - FuturesFetcher connects using IBConnectionManager
    - Subscribe to ES, NQ, RTY works without errors
    - Change metrics are calculated correctly
    - Contract rollover detection works
    - Maintenance window handled gracefully
  </verify>
  <done>
    FuturesFetcher integrated with unified IB connection, subscribes to ES/NQ/RTY, calculates change metrics, handles contract rollover and maintenance window
  </done>
</task>

<task type="auto">
  <name>Task 2: Implement queue-based futures collection</name>
  <files>src/v6/data/futures_persistence.py, scripts/collect_futures_snapshots.py</files>
  <action>
    Implement queue-based futures collection following established patterns:

    1. Create futures collection request type for IB request queue
    2. Add futures snapshot handler to queue worker
    3. Implement rate limiting with wait periods after each round
    4. Batch writes to Delta Lake every 1 minute (avoid small files)
    5. Use anti-join deduplication for idempotent writes

    Queue table integration:
    - Add request_type='futures_snapshot' to ib_request_queue table
    - Queue worker processes futures requests same way as option snapshots
    - Use same rate limiting: wait 60s after completing all requests in a batch
    - Priority: same as option snapshots (can process in same batch)

    Collection flow:
    1. Queue up futures snapshot requests (ES, NQ, RTY) every 5 minutes
    2. Queue worker picks up requests, calls FuturesFetcher
    3. FuturesFetcher subscribes, gets tick data, calculates metrics
    4. Snapshots buffered in DeltaLakeFuturesWriter
    5. Batch write every 60 seconds (or when buffer >= 100 snapshots)

    Script: scripts/collect_futures_snapshots.py
    - Cron-friendly (can run every 5 minutes)
    - Arguments: --symbols, --timeout, --dry-run
    - Exit codes: 0 (success), 1 (retry), 2 (fatal)
    - Uses queue pattern, not direct IB calls
  </action>
  <verify>
    - Queue table accepts futures snapshot requests
    - Queue worker processes futures requests correctly
    - Rate limiting works (60s wait after batch)
    - Batch writes to Delta Lake work (every 60s or 100 snapshots)
    - Collection script runs without errors
    - Dry-run mode works (doesn't write to Delta Lake)
  </verify>
  <done>
    Queue-based futures collection implemented, follows established patterns, rate-limited with 60s wait periods, batch writes every 60s
  </done>
</task>

<task type="auto">
  <name>Task 3: Create futures configuration and scheduler integration</name>
  <files>config/futures_config.yaml, src/v6/utils/scheduler.py</files>
  <action>
    Create futures configuration and integrate with scheduler:

    1. Create config/futures_config.yaml with:
       - enabled_symbols: [ES, NQ, RTY]
       - collection_interval: 300 (5 minutes)
       - batch_write_interval: 60 (1 minute)
       - maintenance_window: "17:00-18:00" ET
       - contract_rollover_days: 7
       - ib_connection: shared (use existing connection)

    2. Add futures collection job to scheduler:
       - Job name: "collect_futures_snapshots"
       - Schedule: cron '*/5 * * * 1-5' (every 5 min, Mon-Fri)
       - Extended hours: '*/5 23-16 * * 1-5' (6pm ET - 4pm ET next day)
       - Command: python scripts/collect_futures_snapshots.py
       - Retry: 3 times with 60s backoff
       - Timeout: 120 seconds

    3. Configuration loader updates:
       - Load futures_config.yaml alongside other configs
       - Validate enabled_symbols are valid (ES, NQ, RTY only)
       - Validate collection_interval >= 60 (min 1 minute)
       - Add to production config (production.yaml.example)

    Scheduler integration:
    - Add to existing scheduler.py (not new scheduler)
    - Use same job queue as other collection tasks
    - Respect maintenance window (skip collection 5-6pm ET)
    - Log skip with reason "maintenance window"
  </action>
  <verify>
    - futures_config.yaml is valid YAML
    - Config loader loads and validates futures config
    - Scheduler includes futures collection job
    - Job schedule respects maintenance window
    - Production config example includes futures settings
  </verify>
  <done>
    Futures configuration created, integrated with scheduler, respects maintenance window, validates on load
  </done>
</task>

<task type="auto">
  <name>Task 4: Create integration tests for futures collection</name>
  <files>tests/futures/test_futures_integration.py</files>
  <action>
    Create integration tests for futures collection:

    Test cases (use pytest with fixtures):
    1. test_futures_fetcher_subscribes_to_es:
       - Mock IB connection
       - Subscribe to ES
       - Verify subscription created
       - Verify on_tick_update called

    2. test_change_metrics_calculation:
       - Mock price history (1h, 4h, overnight, daily)
       - Fetch current price
       - Verify all change metrics calculated correctly
       - Test edge cases (insufficient history, missing data)

    3. test_contract_rollover_detection:
       - Mock contracts with different expiry dates
       - Test rollover trigger (< 7 days)
       - Verify new contract selected
       - Test no rollover when > 7 days

    4. test_maintenance_window_handling:
       - Try to collect during 5-6pm ET
       - Verify warning logged, no exception raised
       - Verify empty snapshot returned
       - Test outside maintenance window works

    5. test_delta_lake_write:
       - Write test snapshots
       - Verify Delta Lake table created
       - Verify partition by symbol
       - Verify idempotent (no duplicates)

    6. test_queue_processing:
       - Queue futures snapshot request
       - Process through queue worker
       - Verify snapshot written to Delta Lake
       - Verify rate limiting (60s wait)

    Fixtures:
    - mock_ib_connection: Mock IB with canned responses
    - sample_futures_snapshots: Test data for ES, NQ, RTY
    - temp_delta_table: Temporary Delta Lake table for testing
  </action>
  <verify>
    - All tests pass: pytest tests/futures/test_futures_integration.py -v
    - Coverage >= 80% for futures_fetcher.py and futures_persistence.py
    - Tests run in < 30 seconds
    - No integration with live IB (all mocked)
  </verify>
  <done>
    Integration tests created, all pass with >= 80% coverage, no live IB dependency
  </done>
</task>

</tasks>

<verification>
Before declaring plan complete:
- [ ] FuturesFetcher uses unified IB connection (IBConnectionManager)
- [ ] Subscribe to ES, NQ, RTY works with real-time data
- [ ] Change metrics calculated (1h, 4h, overnight, daily)
- [ ] Queue-based collection works (futures requests processed)
- [ ] Rate limiting enforced (60s wait after batch)
- [ ] Batch writes to Delta Lake (every 60s or 100 snapshots)
- [ ] Maintenance window handled gracefully (5-6pm ET)
- [ ] Configuration loaded and validated
- [ ] Scheduler job created with correct schedule
- [ ] Integration tests pass (>= 80% coverage)
- [ ] Collection script runs without errors
- [ ] Dry-run mode works (no Delta Lake writes)
</verification>

<success_criteria>

- Futures data collection infrastructure working
- ES, NQ, RTY data collected every 5 minutes
- Data stored in Delta Lake futures_snapshots table
- Queue-based rate limiting working
- Integrated with existing IB connection
- Scheduler job configured
- Integration tests passing
- Ready for 2-4 week data collection period

</success_criteria>

<output>
After completion, create `.planning/phases/8-futures-data-collection/8-01-SUMMARY.md`:

# Phase 8 Plan 1: Futures Data Collection Infrastructure Summary

**Futures data collection infrastructure implemented with unified IB connection and queue-based rate limiting**

## Accomplishments

- FuturesFetcher integrated with IBConnectionManager for unified IB access
- Real-time subscriptions to ES, NQ, RTY with change metrics calculation
- Contract rollover detection (1 week before expiry)
- Queue-based collection following established patterns
- Batch writes to Delta Lake every 60 seconds
- Maintenance window handling (5-6pm ET)
- Scheduler integration with extended hours coverage
- Integration tests with >= 80% coverage

## Files Created/Modified

- `src/v6/core/futures_fetcher.py` - Updated for unified connection, change metrics, rollover
- `src/v6/data/futures_persistence.py` - Queue-based collection, batch writes
- `config/futures_config.yaml` - Futures collection configuration
- `scripts/collect_futures_snapshots.py` - Cron-friendly collection script
- `tests/futures/test_futures_integration.py` - Integration tests
- `src/v6/utils/scheduler.py` - Added futures collection job

## Deviations from Plan

None expected - following established IB connection and queue patterns.

## Issues Encountered

None expected.

## Next Step

Ready for 8-02-PLAN.md (Dashboard Integration & Analysis) or start collecting futures data for 2-4 weeks.

**Data Collection Period:**
- Run futures collector for 2-4 weeks
- Accumulate time-series data for ES/NQ/RTY
- After 2-4 weeks: analyze correlations and predictive value
- Decision: Integrate futures signals into DecisionEngine if valuable

</output>
