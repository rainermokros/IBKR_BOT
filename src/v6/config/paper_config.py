"""
Paper Trading Configuration

This module provides configuration for paper trading environment with safety limits
and separate settings from production.

Usage:
    from src.v6.config import PaperTradingConfig

    config = PaperTradingConfig.load_from_file("config/paper_trading.yaml")
    assert config.dry_run == True  # Enforce dry-run mode
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class PaperTradingConfig:
    """
    Paper trading configuration with enforced safety limits.

    Attributes:
        ib_host: IB gateway host
        ib_port: IB gateway port (typically 7497 for paper trading)
        ib_client_id: IB client ID (must be different from production)
        dry_run: Enforce dry-run mode (always True for paper trading)
        max_positions: Maximum number of concurrent positions
        max_order_size: Maximum number of contracts per order
        allowed_symbols: Whitelist of symbols allowed for paper trading
        paper_start_date: When paper trading started
        paper_starting_capital: Simulated starting capital
        log_level: Logging level for paper trading
        data_dir: Directory for paper trading data
    """

    # IB Connection (paper trading account)
    ib_host: str = "127.0.0.1"
    ib_port: int = 7497
    ib_client_id: int = 2

    # Safety limits (enforced)
    dry_run: bool = True
    max_positions: int = 5
    max_order_size: int = 1
    allowed_symbols: list[str] = field(default_factory=lambda: ["SPY", "QQQ", "IWM"])

    # Paper trading tracking
    paper_start_date: Optional[datetime] = None
    paper_starting_capital: float = 100000.0

    # Logging
    log_level: str = "INFO"
    log_file: str = "logs/paper_trading.log"

    # Data directory
    data_dir: str = "data/lake"

    def __post_init__(self):
        """Validate configuration after initialization."""
        # Enforce dry_run mode
        if not self.dry_run:
            logger.warning("Paper trading config requires dry_run=True, setting it now")
            self.dry_run = True

        # Validate IB connection settings
        if self.ib_port == 7496:
            raise ValueError(
                "Port 7496 is for production trading. "
                "Use 7497 for paper trading account."
            )

        # Validate safety limits
        if self.max_positions > 10:
            raise ValueError(
                f"max_positions={self.max_positions} is too high for paper trading. "
                "Limit to 10 positions."
            )

        if self.max_order_size > 5:
            raise ValueError(
                f"max_order_size={self.max_order_size} is too high for paper trading. "
                "Limit to 5 contracts per order."
            )

        # Validate symbol whitelist
        if not self.allowed_symbols:
            raise ValueError("allowed_symbols cannot be empty")

        # Convert all symbols to uppercase
        self.allowed_symbols = [s.upper() for s in self.allowed_symbols]

        # Set default start date if not provided
        if self.paper_start_date is None:
            self.paper_start_date = datetime.now()

        # Ensure data directory exists
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)

        # Ensure log directory exists
        Path(self.log_file).parent.mkdir(parents=True, exist_ok=True)

    def validate_symbol(self, symbol: str) -> bool:
        """
        Check if a symbol is allowed for paper trading.

        Args:
            symbol: Symbol to check

        Returns:
            True if symbol is in whitelist, False otherwise
        """
        return symbol.upper() in self.allowed_symbols

    def validate_position_count(self, current_count: int) -> bool:
        """
        Check if adding a new position would exceed max_positions.

        Args:
            current_count: Current number of positions

        Returns:
            True if within limit, False otherwise
        """
        return current_count < self.max_positions

    def validate_order_size(self, quantity: int) -> bool:
        """
        Check if order size is within limits.

        Args:
            quantity: Number of contracts

        Returns:
            True if within limit, False otherwise
        """
        return quantity <= self.max_order_size

    @classmethod
    def load_from_file(cls, config_path: str) -> "PaperTradingConfig":
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to YAML config file

        Returns:
            PaperTradingConfig instance

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config is invalid
        """
        config_path = Path(config_path)

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r") as f:
            config_data = yaml.safe_load(f)

        # Parse paper_start_date if provided
        if config_data.get("paper_start_date"):
            config_data["paper_start_date"] = datetime.fromisoformat(
                config_data["paper_start_date"]
            )

        return cls(**config_data)

    @classmethod
    def load_from_env(cls) -> "PaperTradingConfig":
        """
        Load configuration from environment variables.

        Environment variables:
            PAPER_TRADING_IB_HOST
            PAPER_TRADING_IB_PORT
            PAPER_TRADING_IB_CLIENT_ID
            PAPER_TRADING_MAX_POSITIONS
            PAPER_TRADING_MAX_ORDER_SIZE
            PAPER_TRADING_ALLOWED_SYMBOLS
            PAPER_TRADING_START_DATE
            PAPER_TRADING_STARTING_CAPITAL

        Returns:
            PaperTradingConfig instance
        """
        def parse_symbols(symbols_str: str) -> list[str]:
            """Parse comma-separated symbols from env var."""
            if not symbols_str:
                return ["SPY", "QQQ", "IWM"]
            return [s.strip().upper() for s in symbols_str.split(",")]

        config = cls(
            ib_host=os.getenv("PAPER_TRADING_IB_HOST", "127.0.0.1"),
            ib_port=int(os.getenv("PAPER_TRADING_IB_PORT", "7497")),
            ib_client_id=int(os.getenv("PAPER_TRADING_IB_CLIENT_ID", "2")),
            max_positions=int(os.getenv("PAPER_TRADING_MAX_POSITIONS", "5")),
            max_order_size=int(os.getenv("PAPER_TRADING_MAX_ORDER_SIZE", "1")),
            allowed_symbols=parse_symbols(
                os.getenv("PAPER_TRADING_ALLOWED_SYMBOLS", "SPY,QQQ,IWM")
            ),
            paper_start_date=datetime.fromisoformat(
                os.getenv("PAPER_TRADING_START_DATE", datetime.now().isoformat())
            ),
            paper_starting_capital=float(
                os.getenv("PAPER_TRADING_STARTING_CAPITAL", "100000.0")
            ),
        )

        return config

    def save_to_file(self, config_path: str) -> None:
        """
        Save configuration to YAML file.

        Args:
            config_path: Path to save config file
        """
        config_path = Path(config_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to dict for YAML serialization
        config_dict = {
            "ib_host": self.ib_host,
            "ib_port": self.ib_port,
            "ib_client_id": self.ib_client_id,
            "dry_run": self.dry_run,
            "max_positions": self.max_positions,
            "max_order_size": self.max_order_size,
            "allowed_symbols": self.allowed_symbols,
            "paper_start_date": self.paper_start_date.isoformat()
            if self.paper_start_date
            else None,
            "paper_starting_capital": self.paper_starting_capital,
            "log_level": self.log_level,
            "log_file": self.log_file,
            "data_dir": self.data_dir,
        }

        with open(config_path, "w") as f:
            yaml.dump(config_dict, f, default_flow_style=False)

        logger.info(f"Saved paper trading config to {config_path}")
