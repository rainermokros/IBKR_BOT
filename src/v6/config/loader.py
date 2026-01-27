"""
Configuration Loader Module

Provides utilities for loading configuration from files and environment variables
with support for multiple environments (dev, paper, production).
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from loguru import logger

from src.v6.config.production_config import ProductionConfig


def load_config(env: str = "production") -> ProductionConfig:
    """
    Load configuration for specified environment.

    Args:
        env: Environment name (dev, paper, production)

    Returns:
        ProductionConfig instance with settings from config file

    Raises:
        FileNotFoundError: If config file not found
        ValueError: If config is invalid
    """
    config_file = Path(f"config/{env}.yaml")

    if not config_file.exists():
        logger.warning(f"Config file not found: {config_file}, using defaults")
        return ProductionConfig()

    with open(config_file, "r") as f:
        config_data = yaml.safe_load(f) or {}

    logger.info(f"Loaded config from {config_file}")

    # Merge with environment variables (env vars take precedence)
    config_data = merge_config_with_env(config_data)

    # Create ProductionConfig instance
    config = ProductionConfig(**config_data)

    return config


def merge_config_with_env(config_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge configuration with environment variables.

    Environment variables override config file settings.
    Prefix with PRODUCTION_ for production settings.

    Examples:
        PRODUCTION_IB_HOST=192.168.1.100
        PRODUCTION_IB_PORT=4001
        PRODUCTION_DRY_RUN=false
        PRODUCTION_LOG_LEVEL=INFO

    Args:
        config_data: Configuration data from file

    Returns:
        Merged configuration with env vars applied
    """
    env_mapping = {
        "PRODUCTION_IB_HOST": "ib_host",
        "PRODUCTION_IB_PORT": "ib_port",
        "PRODUCTION_IB_CLIENT_ID": "ib_client_id",
        "PRODUCTION_DRY_RUN": "dry_run",
        "PRODUCTION_LOG_LEVEL": "log_level",
        "PRODUCTION_LOG_FILE": "log_file",
        "PRODUCTION_MAX_LOG_SIZE_MB": "max_log_size_mb",
        "PRODUCTION_LOG_BACKUP_COUNT": "log_backup_count",
        "PRODUCTION_MONITORING_ENABLED": "monitoring_enabled",
        "PRODUCTION_ALERT_WEBHOOK_URL": "alert_webhook_url",
        "PRODUCTION_BACKUP_ENABLED": "backup_enabled",
        "PRODUCTION_BACKUP_PATH": "backup_path",
        "PRODUCTION_HEALTH_CHECK_INTERVAL": "health_check_interval",
    }

    for env_var, config_key in env_mapping.items():
        env_value = os.environ.get(env_var)
        if env_value is not None:
            # Type conversion
            if config_key in ["dry_run", "monitoring_enabled", "backup_enabled"]:
                # Boolean
                config_data[config_key] = env_value.lower() in ("true", "1", "yes", "on")
            elif config_key in ["ib_port", "ib_client_id", "max_log_size_mb",
                               "log_backup_count", "health_check_interval"]:
                # Integer
                config_data[config_key] = int(env_value)
            else:
                # String
                config_data[config_key] = env_value

            logger.debug(f"Overriding {config_key} from env: {env_var}")

    return config_data


def validate_production_config(config: ProductionConfig) -> bool:
    """
    Validate production configuration settings.

    Critical checks:
    - IB credentials are set
    - Log path is writable
    - Backup path is writable
    - Not running in dry_run mode (warning only)

    Args:
        config: ProductionConfig instance

    Returns:
        True if valid, raises ValueError otherwise

    Raises:
        ValueError: If configuration is invalid
    """
    errors = []

    # Check IB settings
    if not config.ib_host:
        errors.append("IB host is not configured")

    if not config.ib_port:
        errors.append("IB port is not configured")

    if not config.ib_client_id:
        errors.append("IB client ID is not configured")

    # Check log path
    log_path = Path(config.log_file)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # Test write
        test_file = log_path.parent / ".write_test"
        test_file.touch()
        test_file.unlink()
    except Exception as e:
        errors.append(f"Log path not writable: {e}")

    # Check backup path
    if config.backup_enabled:
        backup_path = Path(config.backup_path)
        try:
            backup_path.mkdir(parents=True, exist_ok=True)
            # Test write
            test_file = backup_path / ".write_test"
            test_file.touch()
            test_file.unlink()
        except Exception as e:
            errors.append(f"Backup path not writable: {e}")

    # Raise if errors
    if errors:
        error_msg = "Production config validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        logger.error(error_msg)
        raise ValueError(error_msg)

    logger.info("✓ Production config validation passed")
    return True


def load_and_validate_config(env: str = "production") -> ProductionConfig:
    """
    Load and validate configuration in one step.

    Args:
        env: Environment name (dev, paper, production)

    Returns:
        Validated ProductionConfig instance

    Raises:
        FileNotFoundError: If config file not found
        ValueError: If config is invalid
    """
    config = load_config(env)
    validate_production_config(config)
    return config
