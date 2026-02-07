"""
Futures Configuration Loader

Loads and validates futures collection configuration from YAML file.

Config location: config/futures_config.yaml

Schema:
- enabled: Enable/disable futures collection
- symbols: List of futures symbols (ES, NQ, RTY)
- collection_interval: Seconds between collections (default: 300 = 5 min)
- batch_write_interval: Seconds between batch writes (default: 60)
- batch_size: Write when buffer reaches this size (default: 100)
- maintenance_window: Start/end time for maintenance (ET)
- contract_rollover: Days before expiry to roll contracts
- ib_connection: IB Gateway connection settings
- collection: Collection timeout and retry settings
- storage: Delta Lake storage path
- rate_limiting: Rate limiting settings
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from loguru import logger


@dataclass
class MaintenanceWindow:
    """Maintenance window configuration."""
    start: str  # HH:MM format
    end: str    # HH:MM format

    def parse_time(self, time_str: str):
        """Parse HH:MM string to time object."""
        from datetime import time
        hour, minute = map(int, time_str.split(":"))
        return time(hour, minute)


@dataclass
class ContractRollover:
    """Contract rollover configuration."""
    days_before_expiry: int = 7


@dataclass
class IBConnectionConfig:
    """IB Gateway connection configuration."""
    host: str = "127.0.0.1"
    port: int = 4002
    client_id: int = 9981


@dataclass
class CollectionConfig:
    """Collection settings."""
    timeout: int = 60
    max_retries: int = 2
    retry_delay: int = 5


@dataclass
class StorageConfig:
    """Storage configuration."""
    table_path: str = "data/lake/futures_snapshots"


@dataclass
class RateLimitingConfig:
    """Rate limiting configuration."""
    wait_after_batch: int = 60  # seconds
    max_requests_per_minute: int = 12


@dataclass
class ChangeMetricsConfig:
    """Change metrics configuration."""
    enable_1h: bool = True
    enable_4h: bool = True
    enable_overnight: bool = True
    enable_daily: bool = True


@dataclass
class FuturesConfig:
    """Complete futures configuration."""

    enabled: bool = True
    symbols: List[str] = None
    collection_interval: int = 300
    batch_write_interval: int = 60
    batch_size: int = 100
    maintenance_window: Optional[MaintenanceWindow] = None
    contract_rollover: Optional[ContractRollover] = None
    ib_connection: Optional[IBConnectionConfig] = None
    collection: Optional[CollectionConfig] = None
    storage: Optional[StorageConfig] = None
    rate_limiting: Optional[RateLimitingConfig] = None
    change_metrics: Optional[ChangeMetricsConfig] = None

    def __post_init__(self):
        """Set defaults after initialization."""
        if self.symbols is None:
            self.symbols = ["ES", "NQ", "RTY"]
        if self.maintenance_window is None:
            self.maintenance_window = MaintenanceWindow(start="17:00", end="18:00")
        if self.contract_rollover is None:
            self.contract_rollover = ContractRollover()
        if self.ib_connection is None:
            self.ib_connection = IBConnectionConfig()
        if self.collection is None:
            self.collection = CollectionConfig()
        if self.storage is None:
            self.storage = StorageConfig()
        if self.rate_limiting is None:
            self.rate_limiting = RateLimitingConfig()
        if self.change_metrics is None:
            self.change_metrics = ChangeMetricsConfig()

    @classmethod
    def from_dict(cls, data: dict) -> "FuturesConfig":
        """Create config from dictionary."""
        maintenance = data.get("maintenance_window", {})
        contract = data.get("contract_rollover", {})
        ib = data.get("ib_connection", {})
        collection = data.get("collection", {})
        storage = data.get("storage", {})
        rate = data.get("rate_limiting", {})
        metrics = data.get("change_metrics", {})

        return cls(
            enabled=data.get("enabled", True),
            symbols=data.get("symbols", ["ES", "NQ", "RTY"]),
            collection_interval=data.get("collection_interval", 300),
            batch_write_interval=data.get("batch_write_interval", 60),
            batch_size=data.get("batch_size", 100),
            maintenance_window=MaintenanceWindow(
                start=maintenance.get("start", "17:00"),
                end=maintenance.get("end", "18:00")
            ),
            contract_rollover=ContractRollover(
                days_before_expiry=contract.get("days_before_expiry", 7)
            ),
            ib_connection=IBConnectionConfig(
                host=ib.get("host", "127.0.0.1"),
                port=ib.get("port", 4002),
                client_id=ib.get("client_id", 9981)
            ),
            collection=CollectionConfig(
                timeout=collection.get("timeout", 60),
                max_retries=collection.get("max_retries", 2),
                retry_delay=collection.get("retry_delay", 5)
            ),
            storage=StorageConfig(
                table_path=storage.get("table_path", "data/lake/futures_snapshots")
            ),
            rate_limiting=RateLimitingConfig(
                wait_after_batch=rate.get("wait_after_batch", 60),
                max_requests_per_minute=rate.get("max_requests_per_minute", 12)
            ),
            change_metrics=ChangeMetricsConfig(
                enable_1h=metrics.get("enable_1h", True),
                enable_4h=metrics.get("enable_4h", True),
                enable_overnight=metrics.get("enable_overnight", True),
                enable_daily=metrics.get("enable_daily", True)
            )
        )

    def validate(self) -> List[str]:
        """
        Validate configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Validate symbols
        valid_symbols = {"ES", "NQ", "RTY"}
        for symbol in self.symbols:
            if symbol not in valid_symbols:
                errors.append(f"Invalid symbol: {symbol}. Must be one of {valid_symbols}")

        # Validate intervals
        if self.collection_interval < 60:
            errors.append("collection_interval must be >= 60 seconds")
        if self.batch_write_interval < 10:
            errors.append("batch_write_interval must be >= 10 seconds")
        if self.batch_size < 1:
            errors.append("batch_size must be >= 1")

        # Validate maintenance window format
        try:
            self.maintenance_window.parse_time(self.maintenance_window.start)
            self.maintenance_window.parse_time(self.maintenance_window.end)
        except Exception as e:
            errors.append(f"Invalid maintenance_window time format: {e}")

        # Validate IB connection
        if self.ib_connection.port < 1 or self.ib_connection.port > 65535:
            errors.append(f"Invalid IB port: {self.ib_connection.port}")
        if self.ib_connection.client_id < 1:
            errors.append(f"Invalid client_id: {self.ib_connection.client_id}")

        # Validate contract rollover
        if self.contract_rollover.days_before_expiry < 1:
            errors.append("contract_rollover.days_before_expiry must be >= 1")

        # Validate collection settings
        if self.collection.timeout < 10:
            errors.append("collection.timeout must be >= 10 seconds")
        if self.collection.max_retries < 0:
            errors.append("collection.max_retries must be >= 0")

        return errors


def load_futures_config(config_path: Optional[str] = None) -> FuturesConfig:
    """
    Load futures configuration from YAML file.

    Args:
        config_path: Path to config file (default: config/futures_config.yaml)

    Returns:
        FuturesConfig object

    Raises:
        ValueError: If configuration is invalid
        FileNotFoundError: If config file doesn't exist
    """
    if config_path is None:
        # Determine project root and config path
        project_root = Path(__file__).parent.parent.parent
        config_path = project_root / "config" / "futures_config.yaml"

    config_file = Path(config_path)

    if not config_file.exists():
        logger.warning(f"Futures config file not found: {config_file}, using defaults")
        return FuturesConfig()

    try:
        with open(config_file, "r") as f:
            data = yaml.safe_load(f)

        if not data:
            logger.warning(f"Empty config file: {config_file}, using defaults")
            return FuturesConfig()

        config = FuturesConfig.from_dict(data)

        # Validate
        errors = config.validate()
        if errors:
            error_msg = "Configuration validation errors:\n" + "\n".join(f"  - {e}" for e in errors)
            raise ValueError(error_msg)

        logger.info(f"✓ Loaded futures config from {config_file}")
        logger.debug(f"  Symbols: {config.symbols}")
        logger.debug(f"  Collection interval: {config.collection_interval}s")
        logger.debug(f"  Batch write interval: {config.batch_write_interval}s")
        logger.debug(f"  Maintenance window: {config.maintenance_window.start}-{config.maintenance_window.end}")

        return config

    except yaml.YAMLError as e:
        raise ValueError(f"Error parsing YAML config: {e}")
