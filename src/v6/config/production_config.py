"""
Production Configuration Module

Provides production-specific configuration with security, logging, monitoring,
and backup settings. Enforces safety checks for production trading.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from loguru import logger


@dataclass
class ProductionConfig:
    """
    Production configuration for V6 trading system.

    Enforces safety checks and provides production-grade settings for
    logging, monitoring, and backup.

    Attributes:
        ib_host: IB gateway host
        ib_port: IB gateway port (7497 for TWS, 4001 for gateway)
        ib_client_id: Client ID for IB connection
        dry_run: If True, no live orders (should be False in production)
        log_level: Logging level (INFO, WARNING, ERROR)
        log_file: Path to production log file
        max_log_size_mb: Maximum log file size before rotation
        log_backup_count: Number of backup logs to retain
        monitoring_enabled: Enable monitoring and alerting
        alert_webhook_url: Optional webhook URL for alerts (Slack, Discord, etc.)
        backup_enabled: Enable automatic backups
        backup_path: Directory for backup storage
        health_check_interval: Seconds between health checks
    """

    # IB Connection
    ib_host: str = "127.0.0.1"
    ib_port: int = 7497
    ib_client_id: int = 1

    # Trading Mode
    dry_run: bool = False  # Should be False in production

    # Logging
    log_level: str = "INFO"
    log_file: str = "logs/v6_production.log"
    max_log_size_mb: int = 100
    log_backup_count: int = 10

    # Monitoring
    monitoring_enabled: bool = True
    alert_webhook_url: Optional[str] = None

    # Backup
    backup_enabled: bool = True
    backup_path: str = "backups/"

    # Health Check
    health_check_interval: int = 60  # seconds

    def __post_init__(self):
        """
        Validate configuration after initialization.

        Raises:
            ValueError: If configuration is invalid for production use
        """
        # Warn if dry_run is enabled in production
        if self.dry_run:
            logger.warning(
                "🚨 PRODUCTION CONFIG: dry_run=True - No live orders will be executed. "
                "Set dry_run=False for production trading."
            )

        # Validate log level
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.log_level.upper() not in valid_levels:
            raise ValueError(f"Invalid log_level: {self.log_level}. Must be one of {valid_levels}")
        self.log_level = self.log_level.upper()

        # Validate port
        if self.ib_port not in [7497, 4001]:
            logger.warning(f"Unusual IB port: {self.ib_port}. Standard ports: 7497 (TWS), 4001 (gateway)")

        # Validate backup path
        if self.backup_enabled:
            backup_dir = Path(self.backup_path)
            backup_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Backup directory: {backup_dir.absolute()}")

        # Validate log directory
        log_path = Path(self.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"Production config loaded: "
            f"IB={self.ib_host}:{self.ib_port}, "
            f"dry_run={self.dry_run}, "
            f"monitoring={self.monitoring_enabled}, "
            f"backup={self.backup_enabled}"
        )

    def is_production(self) -> bool:
        """Check if this is a production configuration (dry_run=False)."""
        return not self.dry_run

    def get_log_config(self) -> dict:
        """
        Get logging configuration for loguru.

        Returns:
            Dictionary with loguru configuration
        """
        return {
            "rotation": f"{self.max_log_size_mb} MB",
            "retention": f"{self.log_backup_count} days",
            "compression": "zip",
            "level": self.log_level,
            "format": (
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            ),
        }
