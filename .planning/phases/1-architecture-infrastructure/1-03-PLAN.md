---
phase: 1-architecture-infrastructure
plan: 03
type: execute
depends_on: ["1-01"]
files_modified: [src/v6/utils/ib_connection.py, src/v6/utils/__init__.py]
---

<objective>
Implement IB connection manager with auto-reconnect, circuit breaker, and heartbeat monitoring.

Purpose: Create reliable IB connection layer that handles connection failures gracefully and prevents retry storms with circuit breaker pattern.
Output: Working IBConnectionManager with retry logic, circuit breaker, and heartbeat monitoring.
</objective>

<execution_context>
~/.claude/get-shit-done/workflows/execute-plan.md
./summary.md
~/.claude/get-shit-done/references/checkpoints.md
</execution_context>

<context>
@v6/.planning/PROJECT.md
@v6/.planning/ROADMAP.md
@v6/.planning/phases/1-architecture-infrastructure/1-RESEARCH.md
@v6/.planning/phases/1-architecture-infrastructure/1-01-SUMMARY.md
@~/.claude/skills/expertise/ib-async-api/SKILL.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Implement IBConnectionManager with retry logic</name>
  <files>src/v6/utils/ib_connection.py, src/v6/utils/__init__.py</files>
  <action>
Create IB connection manager with retry logic and proper lifecycle:

**File: src/v6/utils/ib_connection.py**
```python
import asyncio
from ib_async import IB
from loguru import logger
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, stop requests
    HALF_OPEN = "half_open"  # Testing if recovered

@dataclass
class CircuitBreaker:
    """Circuit breaker to prevent retry storms."""
    failure_threshold: int = 5
    timeout: int = 60  # seconds
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0

    def record_failure(self) -> None:
        """Record a failure and potentially open circuit."""
        self.failure_count += 1
        self.last_failure_time = datetime.now().timestamp()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit breaker OPEN after {self.failure_count} failures")

    def record_success(self) -> None:
        """Record success and close circuit if in half-open."""
        self.failure_count = 0
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            logger.info("Circuit breaker CLOSED after successful recovery")

    def can_attempt(self) -> bool:
        """Check if request should be allowed."""
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            # Check if timeout has passed
            if datetime.now().timestamp() - self.last_failure_time > self.timeout:
                self.state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker HALF_OPEN (testing recovery)")
                return True
            return False
        return True  # HALF_OPEN

class IBConnectionManager:
    """Manages IB connection with retry logic, circuit breaker, and heartbeat."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 1,
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.ib = IB()
        self.circuit_breaker = CircuitBreaker()
        self._is_connected = False

    async def connect(self) -> None:
        """Connect with exponential backoff retry (Pitfall 2 from research)."""
        if not self.circuit_breaker.can_attempt():
            raise ConnectionError("Circuit breaker is OPEN - blocking IB connection attempt")

        for attempt in range(self.max_retries):
            try:
                await self.ib.connectAsync(
                    host=self.host,
                    port=self.port,
                    clientId=self.client_id,
                    timeout=10
                )
                self._is_connected = True
                self.circuit_breaker.record_success()
                logger.info(f"Connected to IB on attempt {attempt + 1}")
                return
            except TimeoutError as e:
                self.circuit_breaker.record_failure()
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay ** attempt  # Exponential backoff: 2s, 4s, 8s
                    logger.warning(f"Connection timeout, retrying in {wait_time}s (attempt {attempt + 1}/{self.max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Failed to connect after {self.max_retries} attempts")
                    raise

    async def disconnect(self) -> None:
        """Clean disconnect."""
        try:
            await self.ib.disconnect()
            self._is_connected = False
            logger.info("Disconnected from IB")
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._is_connected and self.ib.isConnected()

    async def ensure_connected(self) -> None:
        """Ensure connection is active, reconnect if needed."""
        if not self.is_connected:
            logger.warning("Connection lost, attempting reconnect...")
            await self.connect()
```

**Key patterns from research:**
- **Exponential backoff**: 2s, 4s, 8s delays between retries (Pitfall 2: IB first connection often fails)
- **Circuit breaker**: Prevents retry storms when IB is down (Pitfall 5)
- **Async context manager**: `async with IBConnectionManager()` handles lifecycle

**File: src/v6/utils/__init__.py**
```python
from .ib_connection import IBConnectionManager, CircuitBreaker

__all__ = ["IBConnectionManager", "CircuitBreaker"]
```
  </action>
  <verify>
    IBConnectionManager can be imported from src.v6.utils
    CircuitBreaker state transitions work (CLOSED → OPEN → HALF_OPEN → CLOSED)
    Connection retry logic implements exponential backoff (2^attempt seconds)
    Circuit breaker blocks attempts when OPEN (can_attempt returns False)
  </verify>
  <done>
    IBConnectionManager class created with retry logic
    CircuitBreaker prevents retry storms
    Exponential backoff: 2s, 4s, 8s delays
    Async context manager support (__aenter__, __aexit__)
  </done>
</task>

<task type="auto">
  <name>Task 2: Add heartbeat monitoring and connection health checks</name>
  <files>src/v6/utils/ib_connection.py</files>
  <action>
Add heartbeat monitoring to IBConnectionManager:

**Add to IBConnectionManager class:**
```python
import asyncio

class IBConnectionManager:
    # ... existing __init__ ...

    def __init__(self, ...):
        # ... existing init ...
        self.heartbeat_interval = 30  # seconds
        self._heartbeat_task: Optional[asyncio.Task] = None
        self.last_heartbeat = datetime.now()

    async def _heartbeat_loop(self) -> None:
        """Periodic heartbeat to monitor connection health."""
        while self.is_connected:
            try:
                # Request account summary to verify connection is alive
                # This is lightweight and confirms connection works
                await self.ib.reqAccountSummaryAsync()
                self.last_heartbeat = datetime.now()
                logger.debug("Heartbeat: connection is alive")
            except Exception as e:
                logger.error(f"Heartbeat failed: {e}")
                self._is_connected = False
                break

            await asyncio.sleep(self.heartbeat_interval)

    async def start_heartbeat(self) -> None:
        """Start heartbeat monitoring task."""
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            logger.info("Heartbeat monitoring started")

    async def stop_heartbeat(self) -> None:
        """Stop heartbeat monitoring task."""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            logger.info("Heartbeat monitoring stopped")

    async def connection_health(self) -> dict:
        """Get connection health status."""
        age_seconds = (datetime.now() - self.last_heartbeat).total_seconds()
        return {
            "connected": self.is_connected,
            "last_heartbeat_age_seconds": age_seconds,
            "circuit_breaker_state": self.circuit_breaker.state.value,
            "healthy": self.is_connected and age_seconds < self.heartbeat_interval * 2
        }

    async def __aenter__(self):
        await self.connect()
    # Note: heartbeat not started in __aenter__ to allow manual control
    return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop_heartbeat()
        await self.disconnect()
```

**Why heartbeat:**
- Monitors connection health proactively
- Detects silent failures (IB connected but not responsive)
- Enables automatic reconnection on health issues

**Usage pattern:**
```python
# For long-running processes
async with IBConnectionManager() as ib:
    await ib.start_heartbeat()
    # ... do work ...
    await ib.stop_heartbeat()

# For short-lived operations
async with IBConnectionManager() as ib:
    # ... do work without heartbeat ...
    pass
```
  </action>
  <verify>
    IBConnectionManager has heartbeat_interval attribute
    start_heartbeat() and stop_heartbeat() methods exist
    connection_health() returns dict with connected, last_heartbeat_age_seconds, circuit_breaker_state, healthy
    Heartbeat loop requests account summary periodically
  </verify>
  <done>
    Heartbeat monitoring implemented with configurable interval
    connection_health() method provides health status
    Heartbeat loop detects silent failures
    Usage patterns documented for long-running and short-lived operations
  </done>
</task>

</tasks>

<verification>
Before declaring plan complete:
- [ ] IBConnectionManager connects to IB with retry logic
- [ ] Circuit breaker opens after threshold failures, closes after success
- [ ] Exponential backoff works: 2s, 4s, 8s delays
- [ ] Heartbeat monitors connection health (account summary requests)
- [ ] connection_health() returns accurate status
- [ ] Async context manager works (async with statement)
</verification>

<success_criteria>
- All tasks completed
- IBConnectionManager handles connection failures gracefully
- Circuit breaker prevents retry storms (opens after 5 failures)
- Heartbeat detects silent failures
- Connection health monitoring in place
- Ready for next plan (base models)
</success_criteria>

<output>
After completion, create `v6/.planning/phases/1-architecture-infrastructure/1-03-SUMMARY.md`:

# Phase 1 Plan 3: IB Connection Manager Summary

**Implemented reliable IB connection layer with circuit breaker pattern and heartbeat monitoring.**

## Accomplishments

- Created IBConnectionManager with async connection lifecycle
- Implemented exponential backoff retry (2s, 4s, 8s) for IB first connection issue
- Added CircuitBreaker class to prevent retry storms
- Implemented heartbeat monitoring for connection health
- Created connection_health() method for health status

## Files Created/Modified

- `src/v6/utils/ib_connection.py` - IB connection manager with retry, circuit breaker, heartbeat
- `src/v6/utils/__init__.py` - Utils package export

## Decisions Made

- **Exponential backoff**: Addresses Pitfall 2 from research (IB first connection timeout)
- **Circuit breaker**: Addresses Pitfall 5 (no retry storms)
- **Heartbeat interval**: 30 seconds (configurable) for proactive health monitoring
- **Circuit breaker threshold**: 5 failures before opening (configurable)
- **Circuit breaker timeout**: 60 seconds before half-open (configurable)

## Issues Encountered

None

## Next Step

Ready for 01-04-PLAN.md (base models)
</output>
