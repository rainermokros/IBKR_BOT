# Phase 7 Plan 1: Integration Testing Framework

**Phase:** 7
**Plan:** 01
**Type:** Implementation
**Granularity:** plan
**Depends on:** None (can run in parallel with 7-02, 7-03)
**Files modified:** (tracked after execution)

## Objective

Build a comprehensive integration testing framework that validates end-to-end workflows with mock IB connections, ensuring all system components work together correctly before deploying to production.

## Execution Context

@~/.claude/get-shit-done/workflows/execute-plan.md
@~/.claude/get-shit-done/templates/phase-prompt.md
@~/.claude/get-shit-done/references/checkpoints.md
@~/.claude/get-shit-done/references/tdd.md

## Context

### Project State
@.planning/STATE.md
@.planning/ROADMAP.md
@.planning/PROJECT.md

### Completed Phases
@.planning/phases/1-architecture-infrastructure/1-04-SUMMARY.md
@.planning/phases/2-position-synchronization/2-03-SUMMARY.md
@.planning/phases/3-decision-rules-engine/3-04-SUMMARY.md
@.planning/phases/4-strategy-execution/4-03-SUMMARY.md
@.planning/phases/5-risk-management/5-03-SUMMARY.md
@.planning/phases/6-monitoring-dashboard/6-03-SUMMARY.md

### Existing Test Infrastructure
@tests/conftest.py
@tests/execution/test_engine.py
@tests/workflows/test_entry.py

### System Components Under Test
@src/v6/execution/engine.py
@src/v6/workflows/entry.py
@src/v6/workflows/monitoring.py
@src/v6/workflows/exit.py
@src/v6/decisions/engine.py
@src/v6/risk/portfolio_limits.py
@src/v6/risk/circuit_breaker.py

### Expertise Areas
~/.claude/skills/expertise/ib-async-api/SKILL.md (IB connection testing patterns)
~/.claude/skills/expertise/position-manager/SKILL.md (Position tracking for validation)
~/.claude/skills/expertise/quant-options/SKILL.md (Options strategy validation)

## Tasks

### Task 1: Create Test Fixtures and Mock Infrastructure
**Type:** auto

Build reusable test fixtures for IB connections, market data, and strategy state.

**Steps:**
1. Create `tests/fixtures/ib_fixtures.py` with:
   - `mock_ib_connection()` - AsyncMock IB with realistic responses
   - `mock_portfolio_response()` - Sample portfolio data
   - `mock_position_data()` - Sample option positions with Greeks
   - `mock_market_data()` - Sample market snapshots (bid/ask, IV, Greeks)
2. Create `tests/fixtures/strategy_fixtures.py` with:
   - `sample_iron_condor()` - Complete Iron Condor strategy
   - `sample_vertical_spread()` - Vertical spread (call/put)
   - `sample_strategy_state()` - Strategy with execution status
3. Create `tests/fixtures/market_fixtures.py` with:
   - `mock_option_chain()` - Realistic option chain data
   - `mock_greeks_snapshot()` - Greeks with realistic values
4. Add all fixtures to `tests/conftest.py` for global availability

**Acceptance Criteria:**
- All fixtures are importable from `tests.fixtures`
- Fixtures return realistic data matching Pydantic models
- Fixtures are composable (can combine for complex scenarios)
- Fixtures include edge cases (empty portfolio, single position, many positions)

### Task 2: Implement End-to-End Workflow Tests
**Type:** auto

Create integration tests for complete trading workflows (entry → monitoring → exit).

**Steps:**
1. Create `tests/integration/test_entry_to_monitoring.py`:
   - Test: Entry workflow creates position in Delta Lake
   - Test: Position sync picks up new position
   - Test: Monitoring workflow evaluates decisions
   - Test: Alerts generated for risk limit breaches
   - Use mock IB and in-memory Delta Lake (test directory)
2. Create `tests/integration/test_monitoring_to_exit.py`:
   - Test: Stop loss decision triggers exit workflow
   - Test: Exit workflow cancels orders and closes position
   - Test: Position state updated correctly
   - Test: Delta Lake records exit transaction
3. Create `tests/integration/test_full_trade_lifecycle.py`:
   - Test: Complete trade from signal → entry → monitoring → exit
   - Test: Multiple positions tracked simultaneously
   - Test: Portfolio Greeks calculated correctly across positions
   - Test: Circuit breaker triggers on repeated failures
4. Use pytest-asyncio for async workflow testing
5. Create test Delta Lake directory: `tests/data/lake/` (cleaned after each test)

**Acceptance Criteria:**
- All tests pass with mock IB connection
- Tests validate state transitions (PENDING → OPEN → CLOSED)
- Tests validate Delta Lake persistence (read back written data)
- Tests validate portfolio calculations (sum of position Greeks)
- Edge cases covered: connection failures, empty data, malformed responses

### Task 3: Implement Component Integration Tests
**Type:** auto

Test interactions between system components (decision engine + execution, risk + workflows, etc.).

**Steps:**
1. Create `tests/integration/test_decision_execution.py`:
   - Test: Decision engine triggers exit workflow
   - Test: Exit workflow calls execution engine with correct orders
   - Test: Order failures propagated correctly to decision engine
   - Test: Circuit breaker prevents execution after threshold failures
2. Create `tests/integration/test_risk_workflows.py`:
   - Test: Portfolio limits checked before entry
   - Test: PortfolioLimitExceeded raised when limits exceeded
   - Test: Entry workflow rejects strategy when limits hit
   - Test: Portfolio limits updated after position exit
3. Create `tests/integration/test_alerts_integration.py`:
   - Test: Alerts generated for all 12 decision rules
   - Test: Alert severity calculated correctly (WARNING, CRITICAL)
   - Test: Alert history saved to Delta Lake
   - Test: Dashboard reads alerts correctly
4. Mock external dependencies (IB API) but test real interactions between components

**Acceptance Criteria:**
- Component interactions tested without mocking components themselves
- Integration points validated (decision → execution, risk → workflow, alerts → dashboard)
- Error propagation tested (failures bubble up correctly)
- State synchronization tested (all components see consistent state)

### Task 4: Create Performance and Stress Tests
**Type:** auto

Validate system performance under load and with large datasets.

**Steps:**
1. Create `tests/performance/test_large_portfolios.py`:
   - Test: System handles 100+ positions without degradation
   - Test: Portfolio Greeks calculation completes in <1s for 100 positions
   - Test: Delta Lake queries performant with 1000+ historical records
2. Create `tests/performance/test_concurrent_workflows.py`:
   - Test: Multiple entry workflows run concurrently
   - Test: Monitoring workflow doesn't block entry/exit workflows
   - Test: Dashboard updates don't slow down trading workflows
3. Create `tests/performance/test_memory_usage.py`:
   - Test: Memory usage stable over time (no leaks)
   - Test: Delta Lake cache doesn't grow unbounded
   - Test: Position sync queue doesn't accumulate
4. Use pytest-benchmark for performance regression detection
5. Set performance thresholds (e.g., portfolio calc <1s, entry workflow <5s)

**Acceptance Criteria:**
- Performance tests establish baseline metrics
- Tests fail if performance degrades beyond threshold
- Memory tests run for 10+ minutes without leaks
- Concurrent tests don't cause race conditions or deadlocks

## Verification

### Manual Testing
1. Run all integration tests: `pytest tests/integration/ -v`
2. Run performance tests: `pytest tests/performance/ -v`
3. Check test coverage: `pytest --cov=src/v6 --cov-report=html`
4. Verify tests pass in <5 minutes total
5. Verify Delta Lake test data cleaned up after tests

### Automated Checks
```bash
# Run all tests
pytest tests/ -v

# Run integration tests only
pytest tests/integration/ -v

# Run performance tests
pytest tests/performance/ -v --benchmark-only

# Check coverage (target: >80%)
pytest --cov=src/v6 --cov-report=term-missing | grep TOTAL
```

## Success Criteria

- [ ] 20+ integration tests created (workflows, components, performance)
- [ ] All tests pass consistently (no flaky tests)
- [ ] Test coverage >80% for critical paths (workflows, execution, decisions, risk)
- [ ] Performance baselines established (portfolio calc, entry/exit workflows)
- [ ] Test execution time <5 minutes (fast feedback)
- [ ] Delta Lake test data properly isolated and cleaned up
- [ ] Tests validate end-to-end workflows (entry → monitor → exit)
- [ ] Component interactions tested (decision → execution, risk → workflows)
- [ ] Performance tests detect regressions (pytest-benchmark configured)

## Output

**Created Files:**
- `tests/fixtures/__init__.py`
- `tests/fixtures/ib_fixtures.py` (IB connection, portfolio, market data mocks)
- `tests/fixtures/strategy_fixtures.py` (strategy samples, state fixtures)
- `tests/fixtures/market_fixtures.py` (option chains, Greeks snapshots)
- `tests/conftest.py` (updated with global fixtures)
- `tests/integration/__init__.py`
- `tests/integration/test_entry_to_monitoring.py` (entry → monitoring integration)
- `tests/integration/test_monitoring_to_exit.py` (monitoring → exit integration)
- `tests/integration/test_full_trade_lifecycle.py` (complete trade cycle)
- `tests/integration/test_decision_execution.py` (decision + execution)
- `tests/integration/test_risk_workflows.py` (risk + workflow integration)
- `tests/integration/test_alerts_integration.py` (alerts + dashboard)
- `tests/performance/__init__.py`
- `tests/performance/test_large_portfolios.py` (100+ positions)
- `tests/performance/test_concurrent_workflows.py` (concurrency tests)
- `tests/performance/test_memory_usage.py` (memory leak detection)
- `tests/data/lake/` (test Delta Lake directory, gitignored)

**Modified Files:**
- `pyproject.toml` (add pytest-benchmark, pytest-asyncio if not present)
- `.gitignore` (add tests/data/lake/)

**Documentation:**
- Test fixtures documented in docstrings with usage examples
- Integration test scenarios documented in test class docstrings
- Performance thresholds documented in test files
- CONTRIBUTING.md section: "Running Tests" (if exists, else create TESTING.md)

**Tests Created:**
- 20+ integration and performance tests
- All tests passing
- Coverage report generated
