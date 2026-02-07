"""
Trading Configuration Loader

Loads and validates trading configuration from YAML file.

Config location: config/trading_config.yaml

Schema:
- ib_connection: IB Gateway connection settings
- refresh_intervals: Refresh interval configuration (seconds)
- trading_limits: Trading limits configuration
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import yaml
from loguru import logger


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

    def __post_init__(self):
        """Set defaults after initialization."""
        if self.ib_connection is None:
            self.ib_connection = IBConnectionConfig()
        if self.refresh_intervals is None:
            self.refresh_intervals = RefreshIntervals()
        if self.trading_limits is None:
            self.trading_limits = TradingLimitsConfig()

    @classmethod
    def from_dict(cls, data: dict) -> "TradingConfig":
        """Create config from dictionary with nested dataclass instantiation."""
        ib = data.get("ib_connection", {})
        intervals = data.get("refresh_intervals", {})
        limits = data.get("trading_limits", {})

        return cls(
            ib_connection=IBConnectionConfig(
                host=ib.get("host", "127.0.0.1"),
                port=ib.get("port", 4002),
                client_id=ib.get("client_id", 1),
                readonly_port=ib.get("readonly_port", 7497),
                connect_timeout=ib.get("connect_timeout", 10),
                max_retries=ib.get("max_retries", 3),
                retry_delay=ib.get("retry_delay", 2.0),
            ),
            refresh_intervals=RefreshIntervals(
                position_sync=intervals.get("position_sync", 300),
                option_chain=intervals.get("option_chain", 300),
                portfolio_delta=intervals.get("portfolio_delta", 60),
                market_data=intervals.get("market_data", 60),
                futures_data=intervals.get("futures_data", 300),
            ),
            trading_limits=TradingLimitsConfig(
                max_portfolio_delta=limits.get("max_portfolio_delta", 0.30),
                max_positions_per_symbol=limits.get("max_positions_per_symbol", 5),
                max_single_position_pct=limits.get("max_single_position_pct", 0.20),
                max_correlated_pct=limits.get("max_correlated_pct", 0.40),
            )
        )

    def validate(self) -> List[str]:
        """
        Validate configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Validate IB connection
        if self.ib_connection.port < 1 or self.ib_connection.port > 65535:
            errors.append(f"Invalid IB port: {self.ib_connection.port}")
        if self.ib_connection.readonly_port < 1 or self.ib_connection.readonly_port > 65535:
            errors.append(f"Invalid readonly_port: {self.ib_connection.readonly_port}")
        if self.ib_connection.client_id < 1:
            errors.append(f"Invalid client_id: {self.ib_connection.client_id}")
        if self.ib_connection.connect_timeout < 1:
            errors.append(f"Invalid connect_timeout: {self.ib_connection.connect_timeout}")
        if self.ib_connection.max_retries < 0:
            errors.append(f"Invalid max_retries: {self.ib_connection.max_retries}")
        if self.ib_connection.retry_delay < 0:
            errors.append(f"Invalid retry_delay: {self.ib_connection.retry_delay}")

        # Validate refresh intervals
        if self.refresh_intervals.position_sync < 10:
            errors.append("position_sync must be >= 10 seconds")
        if self.refresh_intervals.option_chain < 10:
            errors.append("option_chain must be >= 10 seconds")
        if self.refresh_intervals.portfolio_delta < 10:
            errors.append("portfolio_delta must be >= 10 seconds")
        if self.refresh_intervals.market_data < 10:
            errors.append("market_data must be >= 10 seconds")
        if self.refresh_intervals.futures_data < 10:
            errors.append("futures_data must be >= 10 seconds")

        # Validate trading limits
        if not (0 <= self.trading_limits.max_portfolio_delta <= 1):
            errors.append(f"max_portfolio_delta must be between 0 and 1: {self.trading_limits.max_portfolio_delta}")
        if self.trading_limits.max_positions_per_symbol < 1:
            errors.append(f"max_positions_per_symbol must be >= 1: {self.trading_limits.max_positions_per_symbol}")
        if not (0 <= self.trading_limits.max_single_position_pct <= 1):
            errors.append(f"max_single_position_pct must be between 0 and 1: {self.trading_limits.max_single_position_pct}")
        if not (0 <= self.trading_limits.max_correlated_pct <= 1):
            errors.append(f"max_correlated_pct must be between 0 and 1: {self.trading_limits.max_correlated_pct}")

        return errors


def load_trading_config(config_path: Optional[str] = None) -> TradingConfig:
    """
    Load trading configuration from YAML file.

    Args:
        config_path: Path to config file (default: config/trading_config.yaml)

    Returns:
        TradingConfig object

    Raises:
        ValueError: If configuration is invalid
        FileNotFoundError: If config file doesn't exist
    """
    if config_path is None:
        # Determine project root and config path
        project_root = Path(__file__).parent.parent.parent
        config_path = project_root / "config" / "trading_config.yaml"

    config_file = Path(config_path)

    if not config_file.exists():
        logger.warning(f"Trading config file not found: {config_file}, using defaults")
        return TradingConfig(
            ib_connection=IBConnectionConfig(),
            refresh_intervals=RefreshIntervals(),
            trading_limits=TradingLimitsConfig()
        )

    try:
        with open(config_file, "r") as f:
            data = yaml.safe_load(f)

        if not data:
            logger.warning(f"Empty config file: {config_file}, using defaults")
            return TradingConfig(
                ib_connection=IBConnectionConfig(),
                refresh_intervals=RefreshIntervals(),
                trading_limits=TradingLimitsConfig()
            )

        config = TradingConfig.from_dict(data)

        # Validate
        errors = config.validate()
        if errors:
            error_msg = "Configuration validation errors:\n" + "\n".join(f"  - {e}" for e in errors)
            raise ValueError(error_msg)

        logger.info(f"✓ Loaded trading config from {config_file}")
        logger.debug(f"  IB Connection: {config.ib_connection.host}:{config.ib_connection.port}")
        logger.debug(f"  Position Sync Interval: {config.refresh_intervals.position_sync}s")
        logger.debug(f"  Portfolio Delta Interval: {config.refresh_intervals.portfolio_delta}s")
        logger.debug(f"  Max Portfolio Delta: {config.trading_limits.max_portfolio_delta}")

        return config

    except yaml.YAMLError as e:
        raise ValueError(f"Error parsing YAML config: {e}")
