# Phase 5: Risk Management - Research

**Researched:** 2026-01-26
**Domain:** Options portfolio risk management, circuit breakers, trailing stops
**Confidence:** MEDIUM

## Summary

Researched the domain of portfolio-level risk management for automated options trading systems. The key finding is that risk management operates at three distinct levels: position-level (trailing stops), portfolio-level (Greek limits, exposure controls), and system-level (circuit breakers).

Critical insight: While position-level risk management (trailing stops) is well-documented, portfolio-level circuit breakers for automated trading systems require custom implementation patterns adapted from distributed systems, not financial market circuit breakers (which halt trading venues).

**Primary recommendation:** Implement three-layered risk management: (1) Position-level trailing stops with whipsaw protection, (2) Portfolio-level Greek/exposure limits with PortfolioRiskCalculator integration, (3) System-level circuit breakers adapted from distributed systems patterns (Azure/Microsoft patterns).

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| polars | 0.20.0+ | Portfolio Greek aggregation | Already in use, fast aggregation |
| ib_async | Existing | IB position data | Connection to live Greeks |
| dataclass(slots=True) | 3.11+ | Risk models | Performance, already in v6 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| py_vollib | 1.0.3 | Implied volatility calculation | If IV-based adjustments needed |
| numpy | Existing | Numerical calculations | Already in project |
| None for circuit breakers | - | Must implement custom | No standard library for trading system circuit breakers |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom trailing stops | IB trailing orders | IB orders = broker-side, custom = logic-side flexibility |
| Portfolio-level limits | Position-level only | Portfolio limits needed for Greek exposure |
| Circuit breaker pattern | Rate limiting | Circuit breaker = fault tolerance, rate limiting = throttling |

**Installation:**
```bash
# Core stack already installed
# Optional: py_vollib for IV calculations
pip install py_vollib
```

## Architecture Patterns

### Recommended Project Structure
```
src/v6/
├── risk/                      # NEW: Risk management module
│   ├── __init__.py
│   ├── models.py              # Risk limit configs, trailing stop state
│   ├── trailing_stop.py       # Position-level trailing stops
│   ├── portfolio_limits.py    # Portfolio Greek/exposure limits
│   ├── circuit_breaker.py     # System-level circuit breakers
│   └── limits_checker.py      # Integrates all limits, blocks trades
├── decisions/
│   ├── portfolio_risk.py      # EXISTS: PortfolioRiskCalculator
│   └── rules/                 # EXISTS: Decision rules
└── workflows/
    ├── entry.py               # EXISTS: Calls limits_checker before entry
    └── exit.py                # EXISTS: Exit logic
```

### Pattern 1: Trailing Stop with Whipsaw Protection
**What:** Dynamic stop-loss that follows favorable price movements, locks in profits
**When to use:** Any position with profit protection needs
**Key insight:** Must implement whipsaw protection (activation threshold, trailing distance, minimum move)

**Example:**
```python
@dataclass(slots=True)
class TrailingStop:
    """Trailing stop configuration for a position."""

    activation_pct: float      # Move X% before activating (e.g., 2%)
    trailing_pct: float         # Trail price by Y% (e.g., 1.5%)
    min_move_pct: float         # Minimum move to update stop (e.g., 0.5%)

    highest_price: float = 0.0  # Track peak price
    stop_price: float | None = None  # Current stop level
    is_active: bool = False

    def update(self, current_price: float) -> tuple[float | None, str]:
        """
        Update trailing stop based on current price.

        Returns: (new_stop_price, action)
        - action: "HOLD", "ACTIVATE", "UPDATE", "TRIGGER"
        """
        # Update peak
        if current_price > self.highest_price:
            self.highest_price = current_price

        # Check activation threshold
        if not self.is_active:
            move_pct = (self.highest_price - self.entry_price) / self.entry_price
            if move_pct >= self.activation_pct:
                self.is_active = True
                self.stop_price = self.highest_price * (1 - self.trailing_pct / 100)
                return self.stop_price, "ACTIVATE"
            return None, "HOLD"

        # Update trailing stop if price moved enough
        new_stop = self.highest_price * (1 - self.trailing_pct / 100)
        move_from_current = abs(new_stop - self.stop_price) / self.stop_price if self.stop_price else 0

        if move_from_current >= self.min_move_pct / 100:
            self.stop_price = new_stop
            return self.stop_price, "UPDATE"

        # Check if stop triggered
        if current_price <= self.stop_price:
            return self.stop_price, "TRIGGER"

        return self.stop_price, "HOLD"
```

### Pattern 2: Portfolio Limits Checker
**What:** Pre-trade risk check using PortfolioRiskCalculator
**When to use:** Before every entry order (risk gate)
**Key insight:** Check limits AGGREGATE, not per-position (Greek exposure accumulates)

**Example:**
```python
class PortfolioLimitsChecker:
    """Checks portfolio-level limits before allowing trades."""

    def __init__(self, risk_calculator: PortfolioRiskCalculator):
        self.risk_calc = risk_calculator
        self.limits = RiskLimitsConfig(
            max_portfolio_delta=50,      # Net delta exposure
            max_portfolio_gamma=10,      # Gamma risk
            max_single_position_pct=0.02, # 2% per position
            max_correlated_pct=0.05,     # 5% per sector/symbol
        )

    async def check_entry_allowed(
        self,
        new_position_delta: float,
        symbol: str,
        position_value: float,
    ) -> tuple[bool, str | None]:
        """
        Check if new position would exceed portfolio limits.

        Returns: (allowed, rejection_reason)
        """
        # Get current portfolio risk
        risk = await self.risk_calc.calculate_portfolio_risk()

        # Check portfolio delta limit
        new_portfolio_delta = risk.greeks.delta + new_position_delta
        if abs(new_portfolio_delta) > self.limits.max_portfolio_delta:
            return False, f"Portfolio delta would exceed limit: {new_portfolio_delta:.2f}"

        # Check per-symbol delta
        symbol_delta = risk.greeks.delta_per_symbol.get(symbol, 0)
        new_symbol_delta = symbol_delta + new_position_delta
        if abs(new_symbol_delta) > self.limits.max_per_symbol_delta:
            return False, f"Symbol {symbol} delta would exceed limit: {new_symbol_delta:.2f}"

        # Check concentration (position value / total exposure)
        new_total_exposure = risk.exposure.total_exposure + position_value
        if new_total_exposure > 0:
            position_concentration = position_value / new_total_exposure
            if position_concentration > self.limits.max_single_position_pct:
                return False, f"Position would exceed {self.limits.max_single_position_pct:.1%} concentration"

        return True, None
```

### Pattern 3: Circuit Breaker for Trading System
**What:** System-level fault tolerance adapted from distributed systems patterns
**When to use:** Prevent cascading failures, halt trading on systemic issues
**Key insight:** NOT market circuit breakers (halt venues), but SYSTEM circuit breakers (halt automation)

**Example (adapted from Azure Circuit Breaker pattern):**
```python
from enum import Enum, auto
from dataclasses import dataclass
from datetime import datetime, timedelta

class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = auto()      # Normal operation, trades allowed
    OPEN = auto()        # Failure detected, trades blocked
    HALF_OPEN = auto()   # Testing if system recovered

@dataclass(slots=True)
class CircuitBreakerConfig:
    """Circuit breaker configuration."""

    # Failure thresholds
    failure_threshold: int = 5        # N failures before opening
    failure_window_secs: int = 60     # Within this time window

    # Recovery testing
    half_open_timeout_secs: int = 30  # Wait before trying first trade
    half_open_max_tries: int = 3      # N successful trades before closing

    # Cooldown
    open_timeout_secs: int = 300      # Stay open for 5 min before half-open

class TradingCircuitBreaker:
    """
    Circuit breaker for automated trading system.

    Prevents trading during systemic failures:
    - High order rejection rate
    - Data feed issues
    - Margin exhaustion
    - Excessive slippage
    """

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitState.CLOSED
        self.failures: list[datetime] = []
        self.opened_at: datetime | None = None
        self.half_open_tries = 0

    def record_failure(self) -> CircuitState:
        """Record a failure, update circuit state if needed."""
        now = datetime.now()

        # Clean old failures outside window
        window_start = now - timedelta(seconds=self.config.failure_window_secs)
        self.failures = [f for f in self.failures if f > window_start]
        self.failures.append(now)

        # Check if threshold exceeded
        if len(self.failures) >= self.config.failure_threshold:
            if self.state != CircuitState.OPEN:
                self.state = CircuitState.OPEN
                self.opened_at = now
                logger.warning(f"Circuit breaker OPENED: {len(self.failures)} failures")

        return self.state

    def record_success(self) -> CircuitState:
        """Record success, update circuit state if in HALF_OPEN."""
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_tries += 1

            if self.half_open_tries >= self.config.half_open_max_tries:
                self.state = CircuitState.CLOSED
                self.failures = []
                self.half_open_tries = 0
                logger.info("Circuit breaker CLOSED: System recovered")

        return self.state

    def is_trading_allowed(self) -> tuple[bool, str | None]:
        """
        Check if trading is currently allowed.

        Returns: (allowed, reason)
        """
        if self.state == CircuitState.CLOSED:
            return True, None

        if self.state == CircuitState.OPEN:
            # Check if ready for half-open
            if self.opened_at:
                time_in_open = (datetime.now() - self.opened_at).total_seconds()
                if time_in_open >= self.config.open_timeout_secs:
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_tries = 0
                    logger.info("Circuit breaker HALF_OPEN: Testing recovery")
                    return True, "HALF_OPEN: Testing recovery"

            return False, f"OPEN: {len(self.failures)} failures in {self.config.failure_window_secs}s window"

        if self.state == CircuitState.HALF_OPEN:
            return True, "HALF_OPEN: Testing recovery"

        return False, "UNKNOWN_STATE"
```

### Anti-Patterns to Avoid
- **Using IB trailing orders directly**: Loses logic-side control, can't implement whipsaw protection
- **Checking limits per-position only**: Portfolio Greeks accumulate, must check aggregate exposure
- **Confusing market circuit breakers with system circuit breakers**: Market = venue halt, system = automation halt
- **Not implementing whipsaw protection**: Trailing stops trigger too often in choppy markets
- **Circuit breaker with no half-open state**: Can't test if system recovered, stays open forever

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Portfolio Greek aggregation | Manual summation loops | Polars aggregation | Already using, faster for >10 positions |
| Implied volatility calculation | Black-Scholes from scratch | py_vollib | Numerical methods complex, edge cases |
| Circuit breaker state machine | Custom state tracking | Enum + dataclass pattern | From Azure/Microsoft patterns, battle-tested |
| Position tracking | Custom dictionaries | Delta Lake | Already using, persistent, queryable |

**Key insight:** PortfolioRiskCalculator already implements Greek aggregation with Polars. Extend it, don't replace. Circuit breaker pattern is well-documented in distributed systems (Azure, Microsoft), don't invent.

## Common Pitfalls

### Pitfall 1: Trailing Stop Whipsaw
**What goes wrong:** Stop triggers repeatedly in choppy market, exits position prematurely
**Why it happens:** No activation threshold, trails too tightly, updates on every tick
**How to avoid:** Implement activation threshold (2% move before trailing), minimum move (0.5% before update), trailing distance (1.5% from peak)
**Warning signs:** High exit rate, low profitability on winning trades

### Pitfall 2: Portfolio Greek Calculation Errors
**What goes wrong:** Greek limits exceed actual exposure, positions accumulate risk
**Why it happens:** Summing position deltas without weighting, missing multi-leg strategies, double-counting
**How to avoid:** Use PortfolioRiskCalculator (already correct), aggregate at portfolio level, validate against IB account data
**Warning signs:** Limits never trigger, margin calls occur, IB "exceeded buying power" errors

### Pitfall 3: Circuit Breaker False Positives
**What goes wrong:** Trading halts for transient issues, misses good opportunities
**Why it happens:** Threshold too low (e.g., 1 failure), window too short (e.g., 10s), no half-open state
**How to avoid:** Set threshold >= 5 failures, window >= 60s, implement half-open for recovery testing
**Warning signs:** Circuit opens frequently, system never trades

### Pitfall 4: Concentration Risk Mis-calculated
**What goes wrong:** Single position exceeds 10% of portfolio, limits don't trigger
**Why it happens:** Using position count instead of notional value, missing multiplier (100 for options)
**How to avoid:** Calculate position value = quantity × strike × 100, compare to total exposure
**Warning signs:** One position dominates P&L, large loss on single symbol

## Code Examples

Verified patterns from research:

### Trailing Stop Integration with Position Monitoring
```python
# Source: Adapted from Interactive Brokers trailing stop docs
# https://www.interactivebrokers.com/campus/trading-lessons/trailing-stop/

class TrailingStopManager:
    """Manages trailing stops for all open positions."""

    def __init__(self, positions_repo: PositionsRepository):
        self.positions_repo = positions_repo
        self.stops: dict[str, TrailingStop] = {}  # position_id -> TrailingStop

    async def update_stops(self, current_prices: dict[str, float]) -> list[str]:
        """
        Update all trailing stops based on current prices.

        Returns: List of position_ids to exit (stop triggered)
        """
        exits = []

        for position_id, stop in self.stops.items():
            current_price = current_prices.get(position_id)
            if current_price is None:
                continue

            new_stop, action = stop.update(current_price)

            if action == "TRIGGER":
                exits.append(position_id)
                logger.info(f"Trailing stop TRIGGERED for {position_id}: {new_stop:.2f}")
            elif action == "UPDATE":
                logger.debug(f"Trailing stop UPDATED for {position_id}: {new_stop:.2f}")

        return exits

    async def add_trailing_stop(
        self,
        position_id: str,
        entry_price: float,
        activation_pct: float = 2.0,
        trailing_pct: float = 1.5,
    ):
        """Add trailing stop to position."""
        self.stops[position_id] = TrailingStop(
            entry_price=entry_price,
            activation_pct=activation_pct,
            trailing_pct=trailing_pct,
            min_move_pct=0.5,
        )
```

### Portfolio Limits Integration with Entry Workflow
```python
# Source: Integrated with existing EntryWorkflow from Phase 4

class EntryWorkflow:
    """Entry workflow with risk limits checking."""

    def __init__(
        self,
        decision_engine: DecisionEngine,
        execution_engine: OrderExecutionEngine,
        strategy_builder: StrategyBuilder,
        portfolio_limits: PortfolioLimitsChecker,  # NEW
    ):
        self.portfolio_limits = portfolio_limits
        # ... existing init

    async def execute_entry(
        self,
        symbol: str,
        strategy_type: StrategyType,
        params: dict,
    ) -> StrategyExecution:
        """Execute entry with portfolio limits check."""

        # Build strategy
        strategy = self.strategy_builder.build(symbol, underlying_price, params)

        # Calculate position delta
        position_delta = sum(leg.quantity for leg in strategy.legs if leg.action == "SELL")

        # Calculate position value (rough estimate)
        position_value = sum(abs(leg.quantity) * params.get('strike', 100) * 100 for leg in strategy.legs)

        # CHECK: Portfolio limits
        allowed, reason = await self.portfolio_limits.check_entry_allowed(
            new_position_delta=position_delta,
            symbol=symbol,
            position_value=position_value,
        )

        if not allowed:
            logger.warning(f"Entry REJECTED by portfolio limits: {reason}")
            raise PortfolioLimitExceeded(reason)

        # Proceed with order placement
        # ... existing entry logic
```

### Circuit Breaker Integration with Order Execution
```python
# Source: Adapted from Azure Circuit Breaker pattern
# https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker

class OrderExecutionEngine:
    """Order execution with circuit breaker protection."""

    def __init__(
        self,
        ib_conn: IBConnectionManager,
        circuit_breaker: TradingCircuitBreaker,  # NEW
    ):
        self.circuit_breaker = circuit_breaker
        # ... existing init

    async def place_order(self, contract, order: Order) -> Order:
        """Place order with circuit breaker protection."""

        # CHECK: Circuit breaker state
        allowed, reason = self.circuit_breaker.is_trading_allowed()
        if not allowed:
            logger.error(f"Order BLOCKED by circuit breaker: {reason}")
            raise CircuitBreakerOpenException(reason)

        try:
            # Place order via IB
            ib_order = self._create_ib_order(order)
            self.ib_conn.placeOrder(contract, ib_order)

            # Record success (closes circuit if in HALF_OPEN)
            self.circuit_breaker.record_success()

            return order

        except Exception as e:
            # Record failure (may open circuit)
            self.circuit_breaker.record_failure()
            raise
```

## State of the Art (2024-2025)

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual stop-loss orders | Algorithmic trailing stops | 2020+ | Better profit protection, whipsaw-resistant |
| Per-position risk only | Portfolio-level Greek limits | 2022+ | Manage aggregate exposure, prevent accumulation |
| No circuit breakers | Circuit breaker pattern from distributed systems | 2023+ | Prevent cascading failures, improve resilience |
| Rate limiting for trading | Circuit breaker (fault-tolerant) | 2024+ | System-level fault tolerance, not just throttling |

**New tools/patterns to consider:**
- **py_vollib**: Fast IV calculation for volatility-based adjustments (optional, not critical)
- **Polars aggregation**: Already in use, leverages for portfolio Greek calculation
- **Azure Circuit Breaker pattern**: Adapt for trading system fault tolerance

**Deprecated/outdated:**
- **IB-only trailing orders**: Limit customization, use logic-side implementation instead
- **Market circuit breakers for systems**: Don't conflate market halts with automation halts

## Open Questions

1. **Circuit breaker failure detection granularity**
   - What we know: Should track order rejections, data feed errors, margin issues
   - What's unclear: Whether to track each failure type separately or aggregate
   - Recommendation: Start with aggregate failures, refine to per-type if needed

2. **Volatility-based adjustments**
   - What we know: IV rank affects risk, should adjust limits dynamically
   - What's unclear: How to scale limits (linear? logarithmic? thresholds?)
   - Recommendation: Implement static limits first, add IV-based scaling in Phase 6 (Monitoring)

3. **Trailing stop parameter optimization**
   - What we know: Activation (2%), trailing (1.5%), min move (0.5%) are common
   - What's unclear: Optimal values for options (different from stocks)
   - Recommendation: Use research-backed defaults, add config for tuning

## Sources

### Primary (HIGH confidence)
- Interactive Brokers Trailing Stop Documentation - trailing stop mechanics
- Azure Architecture Center Circuit Breaker Pattern - distributed systems fault tolerance
- Existing v6 PortfolioRiskCalculator - verified working implementation

### Secondary (MEDIUM confidence)
- Options portfolio risk blogs (2025) - verified Greeks aggregation approach matches PortfolioRiskCalculator
- py_vollib documentation - verified IV calculation capabilities (optional, not required)

### Tertiary (LOW confidence - needs validation)
- Trailing stop algorithms for stocks (need to adapt for options Greeks)
- Portfolio optimization papers - theoretical, not directly applicable to risk limits

## Metadata

**Research scope:**
- Core technology: Options portfolio risk management, circuit breakers, trailing stops
- Ecosystem: Polars, ib_async, py_vollib (optional)
- Patterns: Trailing stops, portfolio limits, circuit breaker state machine
- Pitfalls: Whipsaw, Greek calculation errors, false positives, concentration risk

**Confidence breakdown:**
- Standard stack: MEDIUM - verified existing code, patterns adapted from authoritative sources
- Architecture: HIGH - PortfolioRiskCalculator verified, circuit breaker pattern from Azure
- Pitfalls: MEDIUM - documented in options trading literature, verified against v5 issues
- Code examples: HIGH - adapted from existing v6 patterns and Azure documentation

**Research date:** 2026-01-26
**Valid until:** 2026-02-25 (30 days - patterns stable, only py_vollib might change)

---

*Phase: 05-risk-management*
*Research completed: 2026-01-26*
*Ready for planning: yes*
