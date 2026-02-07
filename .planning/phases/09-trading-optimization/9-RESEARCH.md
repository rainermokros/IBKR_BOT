# Phase 9: Trading Optimization & Analysis - Research

**Researched:** 2026-02-07
**Domain:** Options Trading System Optimization (Python, Delta Lake, IB API)
**Confidence:** HIGH

## Summary

Phase 9 focuses on enhancing trading performance through seven targeted improvements: portfolio integration, configurable infrastructure, Delta Lake optimization, advanced rebalance actions, skew-aware strike selection, dynamic profit targets, and historical/live variance analysis. The V6 trading system has a solid foundation with existing components for portfolio risk calculation, decision engine, strategy selection, and performance tracking. This phase requires extending these components rather than rebuilding them.

**Primary recommendation:** Leverage existing V6 architecture (PortfolioRiskCalculator, DecisionEngine, StrategySelector) and extend with targeted improvements. Use dataclass-based configuration patterns from `futures_config.py` as the template for centralized configuration. Implement Delta Lake partitioning using existing `strike_partition` structure. For rebalancing, extend DecisionAction enum rather than create new execution paths.

## User Constraints (from CONTEXT.md)

No CONTEXT.md exists for this phase - this is a fresh phase with user-defined requirements.

**Locked Requirements:**
- Python 3.11+ required
- ib_async for IB connections
- Delta Lake for persistence
- Clean slate architecture (avoid v5 complexity)
- Rule-based v1 with ML added later
- Unified IBConnectionManager for shared connections

**7 Pre-defined Improvements to Implement:**
1. Unified Portfolio Integration (Medium complexity)
2. Configurable Infrastructure (Low complexity)
3. Delta Lake Optimization (Medium complexity)
4. Advanced "Rebalance" Action (High complexity)
5. Skew-Aware Strike Selection (Medium complexity)
6. Dynamic Profit Targets (Low complexity)
7. Historical/Live Variance Analysis (Medium complexity)

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| **Python** | 3.11+ | Core runtime | Project requirement, async/await support |
| **ib_async** | latest | IBKR API connectivity | Project standard, async-native |
| **Delta Lake** (deltalake) | latest | ACID persistence | Existing tables, time travel, partitioning |
| **Polars** | latest | Data manipulation | Already used, LazyFrame for optimization |
| **PyYAML** | latest | Configuration parsing | Industry standard, type-safe with dataclasses |
| **loguru** | latest | Structured logging | Already used throughout project |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **dataclasses** | stdlib | Configuration schema | Type-safe configs (futures_config.py pattern) |
| **pydantic** | optional | Config validation | If stronger validation needed than dataclasses |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| dataclasses | Pydantic models | Pydantic offers stronger validation but adds dependency; dataclasses are sufficient |
| Polars LazyFrame | Pandas + Dask | Polars is faster, has native Delta Lake support |
| Delta Lake partitioning | Liquid clustering | Partitioning already implemented (strike_partition), liquid clustering is newer |

**Installation:**
```bash
# Core already installed
pip install deltalake polars pyyaml loguru ib_async
```

## Architecture Patterns

### Recommended Project Structure
```
src/v6/
├── config/
│   ├── __init__.py
│   ├── futures_config.py      # Existing - use as template
│   ├── trading_config.py      # NEW - centralized trading config
│   └── profit_targets.yaml    # NEW - regime-based TP config
├── risk_manager/
│   ├── portfolio_limits.py     # Existing - PortfolioLimitsChecker
│   ├── portfolio_sync.py       # NEW - PositionSync integration
│   └── trading_workflows/
│       ├── entry.py            # Existing - add portfolio integration
│       └── regime_sizing.py    # Existing - already integrated
├── strategy_builder/
│   ├── decision_engine/
│   │   ├── engine.py           # Existing - add REBALANCE action
│   │   ├── models.py           # Existing - extend DecisionAction enum
│   │   ├── enhanced_market_regime.py  # Existing - use for dynamic TP
│   │   └── protection_rules.py # Existing - modify for dynamic TP
│   ├── strategy_selector.py    # Existing - add skew awareness
│   ├── smart_strike_selector.py # Existing - add skew calculation
│   └── performance_tracker.py  # Existing - extend for variance analysis
├── data/
│   └── lake/
│       ├── option_snapshots/   # Existing - has strike_partition
│       ├── position_updates/   # Existing - use for variance
│       └── strategy_predictions/  # NEW - store 10 AM predictions
└── utils/
    ├── ib_connection.py        # Existing - use config
    └── config_loader.py        # NEW - unified config loading
```

### Pattern 1: Configuration Dataclasses (from futures_config.py)
**What:** Use Python dataclasses with YAML loading for type-safe, validated configuration
**When to use:** All new configuration needs
**Example:**
```python
# Source: /home/bigballs/project/bot/v6/src/v6/config/futures_config.py (verified 2026-02-07)

@dataclass
class TradingConfig:
    """Centralized trading configuration."""
    ib_connection: IBConnectionConfig
    refresh_intervals: RefreshIntervals
    profit_targets: ProfitTargetsConfig

    @classmethod
    def from_dict(cls, data: dict) -> "TradingConfig":
        """Create config from dictionary."""
        # Nested dataclass instantiation

    def validate(self) -> List[str]:
        """Validate configuration."""
        # Return list of validation errors
```

### Pattern 2: LazyFrame for Delta Lake Optimization
**What:** Use Polars LazyFrame with scan_delta() for partition-pruning
**When to use:** All Delta Lake reads, especially option_snapshots (partitioned by strike)
**Example:**
```python
# Source: Based on delta-rs patterns and Polars docs
import polars as pl

# Lazy loading with partition pruning
df = pl.scan_delta("data/lake/option_snapshots")
    .filter(pl.col("strike_partition") == 470)
    .filter(pl.col("timestamp") > start_time)
    .collect()  # Only executes here
```

### Pattern 3: DecisionAction Extension for Rebalance
**What:** Extend DecisionAction enum instead of creating new execution paths
**When to use:** Adding new trading actions (REBALANCE)
**Example:**
```python
# Source: /home/bigballs/project/bot/v6/src/v6/strategy_builder/decision_engine/models.py (verified)

class DecisionAction(Enum):
    HOLD = "hold"
    CLOSE = "close"
    REDUCE = "reduce"
    REBALANCE = "rebalance"  # NEW - for delta-neutral adjustments
    ADJUST = "adjust"        # NEW - for partial leg adjustments
```

### Anti-Patterns to Avoid
- **Hardcoded connection strings**: Already found in ib_connection.py (127.0.0.1, 4002, 7497) - must move to config
- **Direct DeltaTable.to_pandas()**: Use LazyFrame for large tables (option_snapshots has 200+ partitions)
- **Creating new execution paths**: Extend existing DecisionEngine/OrderExecutionEngine
- **Manual strike selection without skew**: Add skew calculation to SmartStrikeSelector

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Configuration validation | Custom validators | dataclasses + yaml.safe_load | Type safety, less code, existing pattern |
| Delta Lake partitioning | Manual partition filtering | Polars scan_delta() with filters | Predicate pushdown, 99% reduction in data scanned |
| Portfolio risk calculation | Custom delta summation | PortfolioRiskCalculator | Already handles Greeks, position deltas |
| Strike selection with skew | Custom IV comparison | SmartStrikeSelector + skew calculation | Existing binary search, just add IV ratio |
| Decision execution | Custom action handlers | DecisionEngine + OrderExecutionEngine | Existing priority queue, async patterns |
| Performance metrics storage | Custom file formats | performance_metrics Delta Lake table | Existing schema, time travel support |

**Key insight:** The V6 system already has mature components. The optimizations are integration work, not greenfield development. For example, PortfolioRiskCalculator already computes portfolio delta - it just needs to be wired into EntryWorkflow.evaluate_entry_signal().

## Common Pitfalls

### Pitfall 1: Configuration Drift
**What goes wrong:** Hardcoded values scattered across codebase (127.0.0.1, ports, intervals)
**Why it happens:** Quick fixes during development without config consolidation
**How to avoid:**
1. Audit all hardcoded values first (`grep -r "127.0.0.1\|4002\|7497"`)
2. Create TradingConfig dataclass following futures_config.py pattern
3. Replace all hardcoded values with config references
**Warning signs:** Same value defined in multiple files, deployment failures

### Pitfall 2: Full Table Scans on Delta Lake
**What goes wrong:** Reading entire option_snapshots table (224+ partitions) for single query
**Why it happens:** Using DeltaTable.to_pandas() without filters
**How to avoid:**
1. Always use pl.scan_delta() for reads
2. Apply partition filters (strike_partition, date) before .collect()
3. Use predicate pushdown: `pl.col("strike") == target`
**Warning signs:** Queries taking >5 seconds, high memory usage

### Pitfall 3: Rebalance Without Delta Calculation
**What goes wrong:** REBALANCE action doesn't know which legs to adjust
**Why it happens:** Implementing action without Greek calculations
**How to avoid:**
1. Calculate current position delta from PortfolioRiskCalculator
2. Determine offset needed to center delta at zero
3. Use existing leg adjustment patterns from OrderExecutionEngine
**Warning signs:** Rebalance increasing exposure instead of reducing it

### Pitfall 4: Skew Calculation Without Normalization
**What goes wrong:** Skew values meaningless across different strikes/expirations
**Why it happens:** Using raw IV differences without normalization
**How to avoid:**
1. Calculate skew as IV ratio: (IV_put / IV_call) or (IV_OTM / IV_ATM)
2. Normalize by time to expiration
3. Use percentile ranking for skew comparison
**Warning signs:** Skew values always favoring one side, inconsistent selection

### Pitfall 5: Variance Analysis Without Baseline
**What goes wrong:** Can't determine if prediction variance is normal or problematic
**Why it happens:** Comparing absolute P&L without accounting for market conditions
**How to avoid:**
1. Store strategy predictions with metadata (regime, IV rank, VIX)
2. Group variance analysis by market regime
3. Use statistical significance tests (t-test) for variance detection
**Warning signs:** All strategies showing "needs tuning", noisy feedback loop

## Code Examples

### Delta Lake Lazy Loading with Partition Pruning
```python
# Source: Based on Polars + Delta Lake best practices
import polars as pl

# BAD: Full table scan
dt = DeltaTable("data/lake/option_snapshots")
df = pl.from_pandas(dt.to_pandas())  # Scans all 224+ partitions

# GOOD: Lazy loading with partition pruning
df = (
    pl.scan_delta("data/lake/option_snapshots")
    .filter(pl.col("strike_partition") == 470)  # Partition pruning
    .filter(pl.col("timestamp") > "2026-02-01")  # Time filtering
    .select(["strike", "iv", "delta", "gamma"])  # Column pruning
    .collect()  # Only executes here
)
```

### Configuration Extension Pattern
```python
# Source: Extended from futures_config.py pattern
@dataclass
class IBConnectionConfig:
    """IB Gateway connection configuration."""
    host: str = "127.0.0.1"
    port: int = 4002
    client_id: int = 1

@dataclass
class RefreshIntervals:
    """Refresh interval configuration."""
    position_sync: int = 300  # seconds
    option_chain: int = 300
    portfolio_delta: int = 60
    market_data: int = 60

@dataclass
class TradingConfig:
    """Complete trading configuration."""
    ib_connection: IBConnectionConfig
    refresh_intervals: RefreshIntervals

    @classmethod
    def from_dict(cls, data: dict) -> "TradingConfig":
        return cls(
            ib_connection=IBConnectionConfig(**data.get("ib_connection", {})),
            refresh_intervals=RefreshIntervals(**data.get("refresh_intervals", {}))
        )
```

### Skew-Aware Strike Selection
```python
# Source: Extension of SmartStrikeSelector pattern
def calculate_skew_ratio(
    put_iv: float,
    call_iv: float,
    normalization_factor: float = 1.0
) -> float:
    """
    Calculate volatility skew ratio.

    Returns:
        Ratio > 1.0: Put skew elevated (favor selling puts)
        Ratio < 1.0: Call skew elevated (favor selling calls)
    """
    if call_iv <= 0:
        return 1.0  # Avoid division by zero
    return (put_iv / call_iv) * normalization_factor

def select_strike_with_skew(
    strikes: list[float],
    ivs: list[float],
    skew_ratio: float,
    target_delta: float
) -> tuple[float, float]:
    """
    Select strike considering skew.

    If skew_ratio > 1.2 (high put skew): prefer OTM puts
    If skew_ratio < 0.8 (high call skew): prefer OTM calls
    """
    # Apply skew preference to strike selection
    # Returns (strike, delta)
    pass
```

### Dynamic Take Profit by Regime
```python
# Source: Extension of protection_rules.py pattern
class DynamicTakeProfit:
    """
    Dynamic take profit based on market regime.

    High volatility: 50% TP (lock profits quickly)
    Low volatility: 90% TP (let winners run)
    """

    def __init__(self, regime_detector: EnhancedMarketRegimeDetector):
        self.regime_detector = regime_detector
        self.tp_by_regime = {
            "crash": 0.40,      # Very defensive
            "high_volatility": 0.50,
            "normal": 0.80,     # Default (current)
            "low_volatility": 0.90,
            "trending": 0.85,
            "range_bound": 0.80,
        }

    async def get_tp_threshold(self, symbol: str) -> float:
        """Get take profit threshold based on current regime."""
        regime = await self.regime_detector.detect_regime(...)
        return self.tp_by_regime.get(
            regime.derived_regime,
            self.tp_by_regime["normal"]  # Default
        )
```

### Variance Analysis Feedback Loop
```python
# Source: Extension of performance_tracker.py pattern
async def analyze_prediction_variance(
    predictions: pl.DataFrame,  # 10 AM predictions
    actuals: pl.DataFrame,      # 4 PM actuals
    regime: str
) -> dict:
    """
    Compare predicted vs actual performance.

    Returns:
        Adjusted scoring weights for StrategySelector
    """
    # Join predictions with actuals
    merged = predictions.join(actuals, on="strategy_id")

    # Calculate variance per strategy type
    variance = merged.group_by("strategy_type").agg([
        pl.col("predicted_score").sub(pl.col("actual_pnl_pct")).alias("error")
        pl.col("error").abs().mean().alias("mean_absolute_error")
    ])

    # Adjust weights based on error
    # Strategies with high error get weight reduction
    adjustments = {}
    for row in variance.iter_rows(named=True):
        error = row["mean_absolute_error"]
        old_weight = current_weights.get(row["strategy_type"], 1.0)
        new_weight = old_weight * (1.0 - min(error, 0.5))
        adjustments[row["strategy_type"]] = new_weight

    return adjustments
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Pandas for Delta Lake | Polars LazyFrame | 2024-2025 | 10-100x query performance with predicate pushdown |
| Hardcoded config | Dataclass + YAML | 2025 (futures_config.py) | Type safety, easier deployment |
| Fixed take profit (80%) | Dynamic by regime | This phase | Adapt to volatility, improve win rate |
| Close on delta hit | Rebalance legs | This phase | Stay in trades longer, reduce transaction costs |
| Blind strike selection | Skew-aware | This phase | Sell expensive side, improve credit received |

**Deprecated/outdated:**
- **DeltaTable.to_pandas()**: Use pl.scan_delta() for lazy loading
- **Hardcoded IB connection**: Already moved to config in futures_config.py, need to extend
- **Static profit targets**: Will be replaced with regime-based targets

## Open Questions

1. **REBALANCE Implementation Complexity**
   - What we know: DecisionEngine supports priority queue, OrderExecutionEngine handles legs
   - What's unclear: Exact API for leg-level adjustments (buy/sell specific legs)
   - Recommendation: Start with REBALANCE as CLOSE + re-entry, evolve to leg adjustment

2. **Skew Data Availability**
   - What we know: option_snapshots has IV data per strike
   - What's unclear: Whether IV surface data is complete for skew calculation
   - Recommendation: Verify IV data quality in option_snapshots before implementation

3. **Variance Analysis Sample Size**
   - What we know: Need minimum N trades for statistical significance
   - What's unclear: How many days of data needed before tuning weights
   - Recommendation: Use 30-day rolling window, minimum 10 trades per strategy

4. **Portfolio Sync Frequency Impact**
   - What we know: PositionSync runs every 5 minutes (scheduler_config.py)
   - What's unclear: Whether EntryWorkflow needs real-time or stale portfolio state acceptable
   - Recommendation: Use cached portfolio state with 1-minute TTL for performance

## Sources

### Primary (HIGH confidence)
- [V6 codebase analysis](file:///home/bigballs/project/bot/v6/src/v6/) - Full code review 2026-02-07
- [futures_config.py](file:///home/bigballs/project/bot/v6/src/v6/config/futures_config.py) - Configuration pattern
- [protection_rules.py](file:///home/bigballs/project/bot/v6/src/v6/strategy_builder/decision_engine/protection_rules.py) - Current TP logic (80%)
- [strategy_selector.py](file:///home/bigballs/project/bot/v6/src/v6/strategy_builder/strategy_selector.py) - Scoring algorithm
- [entry.py](file:///home/bigballs/project/bot/v6/src/v6/risk_manager/trading_workflows/entry.py) - Entry workflow
- [portfolio_limits.py](file:///home/bigballs/project/bot/v6/src/v6/risk_manager/portfolio_limits.py) - Portfolio risk

### Secondary (MEDIUM confidence)
- [Polars, Partitions and Performance with Delta Lake](https://medium.com/@jimmy-jensen/polars-partitions-and-performance-with-delta-lake-5c0d4bdd564b) - Partition pruning patterns
- [How to optimize Delta Lake datasets in Polars](https://stackoverflow.com/questions/79383056/how-to-optimize-delta-lake-datasets-in-polars-sorting-compaction-cleanup) - Stack Overflow verified patterns
- [Delta Lake Part 4: Performance Tuning](https://medium.com/@mohammadshoaib_74869/delta-lake-part-4-performance-tuning-partitioning-liquid-clustering-optimize-z-ordering-and-0d8fe5cfe941) - 99% data reduction claim
- [Best Practices for Configurations in Python-based Pipelines](https://belux.micropole.com/blog/python/blog-best-practices-for-configurations-in-python-based-pipelines/) - Config patterns (June 2025)

### Tertiary (LOW confidence - needs verification)
- [Volatility Skew and Options](https://www.optionseducation.org/news/volatility-skew-and-options-an-overview-1) - Skew fundamentals
- [Delta-Neutral Trading Setups](https://tradewiththepros.com/delta-neutral-trading-setups/) - Rebalancing triggers (Jan 2025)
- [What is Volatility Skew & How to Trade it](https://www.tastylive.com/concepts-strategies/volatility-skew) - Practical skew trading
- [Python Configuration Management with Ansible](https://dasroot.net/posts/2026/01/python-ansible-configuration-management/) - 2026 best practices

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Verified against V6 codebase
- Architecture: HIGH - Based on existing patterns (futures_config.py, DecisionEngine)
- Pitfalls: MEDIUM - Some based on WebSearch, need validation during implementation

**Research date:** 2026-02-07
**Valid until:** 2026-03-07 (30 days - stable domain, but verify deltalake-rs updates)
