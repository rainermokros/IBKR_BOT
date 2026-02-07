---
phase: 09-trading-optimization
plan: 02
type: execute
wave: 1
depends_on: []
files_modified:
  - src/v6/config/trading_config.py
  - src/v6/utils/ib_connection.py
  - config/trading_config.yaml
  - src/v6/system_monitor/scheduler/scheduler_config.py
autonomous: true
user_setup: []

must_haves:
  truths:
    - "All hardcoded values (127.0.0.1, ports, intervals) are centralized in trading_config.yaml"
    - "TradingConfig dataclass provides type-safe configuration loading"
    - "IBConnectionManager reads connection settings from config"
    - "Scheduler reads intervals from config"
    - "YAML changes apply without code modification"
  artifacts:
    - path: "src/v6/config/trading_config.py"
      provides: "Centralized trading configuration loader"
      contains: "class TradingConfig, class IBConnectionConfig, class RefreshIntervals"
    - path: "config/trading_config.yaml"
      provides: "Runtime configurable parameters"
      contains: "ib_connection, refresh_intervals"
    - path: "src/v6/utils/ib_connection.py"
      provides: "Config-aware IB connection management"
      exports: ["IBConnectionManager"]
  key_links:
    - from: "src/v6/utils/ib_connection.py"
      to: "config/trading_config.yaml"
      via: "load_trading_config() reads ib_connection section"
      pattern: "IBConnectionConfig|trading_config"
    - from: "src/v6/system_monitor/scheduler/scheduler_config.py"
      to: "config/trading_config.yaml"
      via: "SchedulerConfig reads refresh_intervals"
      pattern: "refresh_intervals|load_trading_config"
---

<objective>
Centralize all hardcoded configuration values into a single YAML configuration system.

Current system has hardcoded values scattered across modules:
- IB connection: 127.0.0.1, ports 4002/7497 in ib_connection.py
- Refresh intervals: 300s, 60s in various modules
- Trading parameters: delta limits, position counts in code

This plan creates a unified TradingConfig dataclass following the futures_config.py pattern,
allowing runtime configuration without code changes.

Purpose: Improve deployability and operational flexibility by centralizing configuration.
Output: TradingConfig dataclass + trading_config.yaml with all configurable values.
</objective>

<execution_context>
@/home/bigballs/.claude/get-shit-done/workflows/execute-plan.md
@/home/bigballs/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/09-trading-optimization/9-RESEARCH.md
@.planning/ROADMAP.md
@.planning/STATE.md

@src/v6/config/futures_config.py
@src/v6/utils/ib_connection.py
@src/v6/system_monitor/scheduler/scheduler_config.py
</context>

<tasks>

<task type="auto">
  <name>Create TradingConfig dataclass in config/trading_config.py</name>
  <files>src/v6/config/trading_config.py</files>
  <action>
    Create src/v6/config/trading_config.py following the futures_config.py pattern.

    Include these dataclasses:
    ```python
    @dataclass
    class IBConnectionConfig:
        """IB Gateway connection configuration."""
        host: str = "127.0.0.1"
        port: int = 4002
        client_id: int = 1
        readonly_port: int = 7497  # For market data only
        connect_timeout: int = 10
        max_retries: int = 3
        retry_delay: float = 2.0

    @dataclass
    class RefreshIntervals:
        """Refresh interval configuration (seconds)."""
        position_sync: int = 300      # 5 minutes
        option_chain: int = 300       # 5 minutes
        portfolio_delta: int = 60     # 1 minute
        market_data: int = 60         # 1 minute
        futures_data: int = 300       # 5 minutes

    @dataclass
    class TradingLimitsConfig:
        """Trading limits configuration."""
        max_portfolio_delta: float = 0.30
        max_positions_per_symbol: int = 5
        max_single_position_pct: float = 0.20
        max_correlated_pct: float = 0.40

    @dataclass
    class TradingConfig:
        """Complete trading configuration."""

        ib_connection: IBConnectionConfig
        refresh_intervals: RefreshIntervals
        trading_limits: TradingLimitsConfig

        @classmethod
        def from_dict(cls, data: dict) -> "TradingConfig":
            """Create config from dictionary with nested dataclass instantiation."""

        def validate(self) -> List[str]:
            """Validate configuration, return list of errors."""

    def load_trading_config(config_path: Optional[str] = None) -> TradingConfig:
        """Load trading configuration from YAML file."""
    ```

    Use the exact same pattern as futures_config.py for consistency:
    - Dataclasses with defaults in __post_init__
    - from_dict() classmethod for nested instantiation
    - validate() method returning list of errors
    - load_* function for YAML loading with error handling
  </action>
  <verify>
    1. TradingConfig class exists with ib_connection, refresh_intervals, trading_limits
    2. All nested dataclasses defined (IBConnectionConfig, RefreshIntervals, TradingLimitsConfig)
    3. from_dict() method handles nested dataclass instantiation
    4. validate() returns list of validation errors
    5. load_trading_config() function reads YAML and returns TradingConfig
  </verify>
  <done>
    TradingConfig dataclass created with all configuration sections, follows
    futures_config.py pattern, includes validation and YAML loading.
  </done>
</task>

<task type="auto">
  <name>Create trading_config.yaml with all configurable values</name>
  <files>config/trading_config.yaml</files>
  <action>
    Create config/trading_config.yaml with all sections:

    ```yaml
    # Trading Configuration
    # Centralized configuration for V6 trading system

    # IB Gateway Connection Settings
    ib_connection:
      host: "127.0.0.1"
      port: 4002              # Paper trading port (7497 for live)
      client_id: 1
      readonly_port: 7497
      connect_timeout: 10
      max_retries: 3
      retry_delay: 2.0

    # Refresh Intervals (seconds)
    refresh_intervals:
      position_sync: 300       # Position synchronization (5 min)
      option_chain: 300        # Option chain refresh (5 min)
      portfolio_delta: 60      # Portfolio delta calculation (1 min)
      market_data: 60          # Market data refresh (1 min)
      futures_data: 300        # Futures data collection (5 min)

    # Trading Limits
    trading_limits:
      max_portfolio_delta: 0.30    # Maximum net portfolio delta
      max_positions_per_symbol: 5  # Max positions per underlying
      max_single_position_pct: 0.20  # Max concentration in single position
      max_correlated_pct: 0.40     # Max correlated exposure

    # Note: Profit targets configured in profit_targets section
    # (managed by 9-01 Dynamic Profit Targets plan)
    ```

    Document each value with inline comments.
  </action>
  <verify>
    1. config/trading_config.yaml exists and is valid YAML
    2. ib_connection section matches IBConnectionConfig fields
    3. refresh_intervals section matches RefreshIntervals fields
    4. trading_limits section matches TradingLimitsConfig fields
    5. All default values documented with comments
  </verify>
  <done>
    trading_config.yaml created with all configuration sections, values match
    dataclass defaults, inline comments document each setting.
  </done>
</task>

<task type="auto">
  <name>Update IBConnectionManager to use TradingConfig</name>
  <files>src/v6/utils/ib_connection.py</files>
  <action>
    Update IBConnectionManager.__init__ to accept TradingConfig.IBConnectionConfig.

    Changes:
    1. Import load_trading_config from v6.config.trading_config
    2. Update __init__ signature to accept ib_connection_config parameter
    3. Remove hardcoded defaults (127.0.0.1, 4002, etc.)
    4. Add factory method from_config() for easy instantiation

    Pattern:
    ```python
    from v6.config.trading_config import load_trading_config, IBConnectionConfig

    class IBConnectionManager:
        def __init__(
            self,
            ib_connection_config: IBConnectionConfig,
        ):
            self.host = ib_connection_config.host
            self.port = ib_connection_config.port
            self.client_id = ib_connection_config.client_id
            self.max_retries = ib_connection_config.max_retries
            self.retry_delay = ib_connection_config.retry_delay
            # ... rest of initialization

        @classmethod
        def from_config(cls, config_path: str = None) -> "IBConnectionManager":
            """Create IBConnectionManager from trading config file."""
            trading_config = load_trading_config(config_path)
            return cls(ib_connection_config=trading_config.ib_connection)
    ```

    Maintain backward compatibility: allow direct parameter passing for tests.
  </action>
  <verify>
    1. IBConnectionManager imports from config.trading_config
    2. __init__ accepts IBConnectionConfig parameter
    3. from_config() classmethod creates instance from config file
    4. Hardcoded values (127.0.0.1, 4002, etc.) removed from defaults
    5. CircuitBreaker still works with new config-based initialization
  </verify>
  <done>
    IBConnectionManager reads connection settings from TradingConfig,
    from_config() factory method provided, backward compatible.
  </done>
</task>

<task type="auto">
  <name>Update SchedulerConfig to use TradingConfig refresh intervals</name>
  <files>src/v6/system_monitor/data/scheduler_config.py</files>
  <action>
    Update SchedulerConfig to read refresh intervals from TradingConfig.

    If scheduler_config.py exists with hardcoded intervals, update to:
    1. Import load_trading_config from v6.config.trading_config
    2. Load TradingConfig and use refresh_intervals values
    3. Remove hardcoded interval values

    Pattern:
    ```python
    from v6.config.trading_config import load_trading_config

    @dataclass
    class SchedulerConfig:
        """Scheduler configuration using TradingConfig refresh intervals."""

        def __init__(self, config_path: str = None):
            trading_config = load_trading_config(config_path)
            self.position_sync_interval = trading_config.refresh_intervals.position_sync
            self.option_chain_interval = trading_config.refresh_intervals.option_chain
            # ... other intervals
    ```

    If scheduler_config.py doesn't exist or doesn't have intervals, skip this task.
  </action>
  <verify>
    1. SchedulerConfig imports load_trading_config
    2. Intervals read from TradingConfig.refresh_intervals
    3. Hardcoded interval values removed
    4. Scheduler uses configured intervals correctly
  </verify>
  <done>
    SchedulerConfig reads intervals from TradingConfig, no hardcoded refresh
    intervals remain in scheduler code.
  </done>
</task>

</tasks>

<verification>
Overall phase checks:
1. Python syntax check: python -m py_compile src/v6/config/trading_config.py
2. YAML validation: python -c "import yaml; yaml.safe_load(open('config/trading_config.yaml'))"
3. Config loading test: python -c "from v6.config.trading_config import load_trading_config; c = load_trading_config(); print(c)"
4. IBConnectionManager instantiation: python -c "from v6.utils.ib_connection import IBConnectionManager; IBConnectionManager.from_config()"
5. Verify all hardcoded values removed from ib_connection.py
</verification>

<success_criteria>
1. All hardcoded connection values (127.0.0.1, ports) moved to trading_config.yaml
2. All hardcoded refresh intervals moved to trading_config.yaml
3. TradingConfig.validate() catches invalid configuration
4. IBConnectionManager works with config-based initialization
5. Scheduler intervals read from config
6. Changing YAML values affects behavior without code changes
</success_criteria>

<output>
After completion, create `.planning/phases/09-trading-optimization/9-02-SUMMARY.md`
</output>
