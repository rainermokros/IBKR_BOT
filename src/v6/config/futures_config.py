"""
Futures Configuration Module

Provides futures contract specifications and data collection settings for
ES (E-mini S&P 500), NQ (E-mini Nasdaq 100), and RTY (E-mini Russell 2000).

Purpose: Collect futures data as leading indicators for entry signal prediction.
Futures trade 23h/day vs 6.5h for equities, giving pre-market and after-hours insights.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class FuturesContract:
    """
    Individual futures contract specification.

    Attributes:
        symbol: Futures symbol (ES, NQ, RTY)
        secType: Security type (FUT for futures)
        exchange: Exchange (CME for Chicago Mercantile Exchange)
        currency: Contract currency (USD)
        lastTradeDateOrContractMonth: Expiration date (empty for continuous)
        multipler: Contract multiplier (e.g., 50 for ES)
        minTick: Minimum tick size
        display_name: Human-readable name
    """
    symbol: str
    secType: str = "FUT"
    exchange: str = "CME"
    currency: str = "USD"
    lastTradeDateOrContractMonth: str = ""  # Empty for continuous futures
    multiplier: Optional[str] = None
    minTick: Optional[float] = None
    display_name: Optional[str] = None

    def __post_init__(self):
        """Set defaults based on symbol."""
        if self.display_name is None:
            names = {
                "ES": "E-mini S&P 500",
                "NQ": "E-mini Nasdaq 100",
                "RTY": "E-mini Russell 2000"
            }
            self.display_name = names.get(self.symbol, self.symbol)

        if self.multiplier is None:
            multipliers = {
                "ES": "50",
                "NQ": "20",
                "RTY": "50"
            }
            self.multiplier = multipliers.get(self.symbol, "50")

        if self.minTick is None:
            minTicks = {
                "ES": 0.25,
                "NQ": 0.25,
                "RTY": 0.1
            }
            self.minTick = minTicks.get(self.symbol, 0.25)


@dataclass
class FuturesDataCollection:
    """
    Data collection settings for futures.

    Attributes:
        snapshot_interval_sec: Seconds between data snapshots (default: 60s)
        aggregate_interval_min: Minutes between aggregate calculations (default: 5m)
        fields_to_collect: List of fields to collect from IB
        change_windows: Time windows for change calculations (in minutes)
    """
    snapshot_interval_sec: int = 60  # 1 minute
    aggregate_interval_min: int = 5   # 5 minutes
    fields_to_collect: List[str] = None
    change_windows: Dict[str, int] = None

    def __post_init__(self):
        """Set defaults if not provided."""
        if self.fields_to_collect is None:
            self.fields_to_collect = [
                "bid",
                "ask",
                "last",
                "volume",
                "open_interest",
                "implied_vol"
            ]

        if self.change_windows is None:
            self.change_windows = {
                "change_1h": 60,           # 1 hour
                "change_4h": 240,          # 4 hours
                "change_overnight": 480,   # 8 hours (typical overnight session)
                "change_daily": 1440       # 24 hours
            }


@dataclass
class FuturesConnectionConfig:
    """
    IB connection settings for futures data.

    Attributes:
        ib_host: IB gateway host
        ib_port: IB gateway port (7497 for TWS, 4001 for gateway)
        ib_client_id: Client ID for IB connection
        max_retries: Maximum connection retry attempts
        retry_delay: Seconds between retries
        heartbeat_interval: Seconds between heartbeat checks
    """
    ib_host: str = "127.0.0.1"
    ib_port: int = 7497
    ib_client_id: int = 1
    max_retries: int = 3
    retry_delay: float = 2.0
    heartbeat_interval: int = 30


@dataclass
class FuturesConfig:
    """
    Complete futures configuration for data collection.

    Combines contract specifications, data collection settings,
    and connection configuration for ES, NQ, RTY futures.

    Attributes:
        contracts: Dictionary of futures contract specs by symbol
        data_collection: Data collection settings
        connection: IB connection settings
        continuous_futures: Use continuous futures (auto-roll on expiration)
        enabled_symbols: List of symbols to collect data for

    Example:
        config = FuturesConfig()
        es_contract = config.contracts["ES"]
        interval = config.data_collection.snapshot_interval_sec
    """

    contracts: Dict[str, FuturesContract] = None
    data_collection: FuturesDataCollection = None
    connection: FuturesConnectionConfig = None
    continuous_futures: bool = True
    enabled_symbols: List[str] = None

    def __post_init__(self):
        """Initialize default configuration."""
        if self.contracts is None:
            self.contracts = {
                "ES": FuturesContract(symbol="ES"),
                "NQ": FuturesContract(symbol="NQ"),
                "RTY": FuturesContract(symbol="RTY")
            }

        if self.data_collection is None:
            self.data_collection = FuturesDataCollection()

        if self.connection is None:
            self.connection = FuturesConnectionConfig()

        if self.enabled_symbols is None:
            self.enabled_symbols = ["ES", "NQ", "RTY"]

    def get_contract(self, symbol: str) -> FuturesContract:
        """
        Get contract specification for symbol.

        Args:
            symbol: Futures symbol (ES, NQ, RTY)

        Returns:
            FuturesContract: Contract specification

        Raises:
            ValueError: If symbol not in contracts
        """
        if symbol not in self.contracts:
            raise ValueError(f"Unknown futures symbol: {symbol}. Available: {list(self.contracts.keys())}")
        return self.contracts[symbol]

    def is_enabled(self, symbol: str) -> bool:
        """
        Check if symbol is enabled for data collection.

        Args:
            symbol: Futures symbol

        Returns:
            bool: True if enabled
        """
        return symbol in self.enabled_symbols

    def get_enabled_contracts(self) -> Dict[str, FuturesContract]:
        """
        Get all enabled contracts.

        Returns:
            dict: Dictionary of enabled contracts by symbol
        """
        return {
            symbol: self.contracts[symbol]
            for symbol in self.enabled_symbols
            if symbol in self.contracts
        }


# Default configuration instance
default_futures_config = FuturesConfig()
