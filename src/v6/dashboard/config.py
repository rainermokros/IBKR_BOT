"""
Dashboard Configuration

Provides configuration settings for the Streamlit dashboard.
Includes cache TTL, refresh intervals, and Delta Lake paths.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class DashboardConfig:
    """
    Dashboard configuration settings.

    Attributes:
        streamlit_port: Port for Streamlit server
        debug_mode: Enable debug mode (verbose logging)
        cache_ttl_positions: Cache TTL for positions data (seconds)
        cache_ttl_alerts: Cache TTL for alerts data (seconds)
        auto_refresh_options: Available auto-refresh intervals (seconds, 0 = off)
        default_refresh: Default auto-refresh interval (seconds)
        delta_lake_base_path: Base path to Delta Lake tables
    """

    streamlit_port: int = 8501
    debug_mode: bool = False
    cache_ttl_positions: int = 30  # seconds
    cache_ttl_alerts: int = 60  # seconds
    auto_refresh_options: list[int] = None
    default_refresh: int = 30
    delta_lake_base_path: str = "data/lake"

    def __post_init__(self):
        """Initialize default values for lists."""
        if self.auto_refresh_options is None:
            self.auto_refresh_options = [5, 30, 60, 0]  # 0 = off

    @property
    def strategy_executions_path(self) -> str:
        """Get path to strategy_executions Delta Lake table."""
        return str(Path(self.delta_lake_base_path) / "strategy_executions")

    @property
    def alerts_path(self) -> str:
        """Get path to alerts Delta Lake table."""
        return str(Path(self.delta_lake_base_path) / "alerts")
