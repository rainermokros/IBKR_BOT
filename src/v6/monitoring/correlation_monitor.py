"""
Correlation Divergence Monitor

Monitors futures-ETF correlation divergences with alerting and Delta Lake logging.

Checks all 9 pairs (ES/NQ/RTY vs SPY/QQQ/IWM) for divergence using z-score analysis.
Implements rate limiting (1 alert/day per pair) and market hours filtering.
Logs divergences to Delta Lake for historical tracking.

This module was extracted from v6/system_monitor/alerts.py to separate concerns:
- AlertManager (v6/system_monitor/alert_system/manager.py) is for persistent alerts
- CorrelationDivergenceMonitor (this file) is for correlation monitoring
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import polars as pl
from deltalake import DeltaTable, write_deltalake
from loguru import logger

from v6.system_monitor.alerts import AlertManager


class CorrelationDivergenceMonitor:
    """
    Monitor correlation divergences for all futures-ETF pairs.

    Checks all 9 pairs (ES/NQ/RTY vs SPY/QQQ/IWM) for divergence using z-score analysis.
    Implements rate limiting (1 alert/day per pair) and market hours filtering.
    Logs divergences to Delta Lake for historical tracking.
    """

    # Market hours: 8am-5pm ET
    MARKET_HOUR_START = 8
    MARKET_HOUR_END = 17

    # All futures-ETF pairs to monitor
    ALL_PAIRS = [
        ("ES", "SPY"),
        ("ES", "QQQ"),
        ("ES", "IWM"),
        ("NQ", "SPY"),
        ("NQ", "QQQ"),
        ("NQ", "IWM"),
        ("RTY", "SPY"),
        ("RTY", "QQQ"),
        ("RTY", "IWM"),
    ]

    def __init__(
        self,
        alert_manager: AlertManager,
        rate_limit_hours: int = 24,  # 1 alert per day per pair
        divergence_table_path: str = "data/lake/correlation_divergences",
    ):
        """
        Initialize correlation divergence monitor.

        Args:
            alert_manager: AlertManager instance for sending alerts
            rate_limit_hours: Hours between alerts for same pair (default 24)
            divergence_table_path: Path to Delta Lake table for logging divergences
        """
        self.alert_manager = alert_manager
        self.rate_limit_hours = rate_limit_hours
        self.divergence_table_path = Path(divergence_table_path)

        # Track last alert time per pair
        self._last_alert_times: dict[str, datetime] = {}

        # Ensure divergence table exists
        self._ensure_divergence_table()

        logger.info(
            f"CorrelationDivergenceMonitor initialized: "
            f"rate_limit={rate_limit_hours}h"
        )

    def _ensure_divergence_table(self) -> None:
        """Create Delta Lake table for correlation divergences if it doesn't exist."""
        if DeltaTable.is_deltatable(str(self.divergence_table_path)):
            return

        # Create empty DataFrame with schema
        import pandas as pd
        schema_df = pd.DataFrame(
            {
                "timestamp": [],
                "pair_name": [],
                "correlation": [],
                "z_score": [],
                "resolved": [],
            }
        )

        # Write to Delta Lake
        write_deltalake(
            str(self.divergence_table_path),
            schema_df,
            mode="overwrite",
        )

        logger.info(f"Created correlation divergences table: {self.divergence_table_path}")

    def is_market_hours(self, timestamp: datetime) -> bool:
        """
        Check if timestamp is during market hours (8am-5pm ET, weekdays only).

        Args:
            timestamp: Timestamp to check

        Returns:
            True if during market hours, False otherwise
        """
        # Check if weekday (Monday=0, Friday=5)
        if timestamp.weekday() > 4:
            return False

        # Market hours: 8am-5pm ET
        hour = timestamp.hour
        return self.MARKET_HOUR_START <= hour < self.MARKET_HOUR_END

    def _should_alert_pair(self, pair_name: str) -> bool:
        """
        Check if pair should alert based on rate limiting.

        Args:
            pair_name: Pair name to check

        Returns:
            True if alert should be sent, False otherwise
        """
        last_alert_time = self._last_alert_times.get(pair_name)

        if last_alert_time is None:
            return True

        time_since_last = datetime.now() - last_alert_time

        if time_since_last < timedelta(hours=self.rate_limit_hours):
            logger.debug(
                f"Correlation alert for {pair_name} rate limited "
                f"({time_since_last.total_seconds() / 3600:.1f}h ago)"
            )
            return False

        return True

    def _update_last_alert_time(self, pair_name: str) -> None:
        """
        Update last alert time for pair.

        Args:
            pair_name: Pair name
        """
        self._last_alert_times[pair_name] = datetime.now()

    def _log_divergence(
        self,
        result: "DivergenceResult",
    ) -> None:
        """
        Log divergence to Delta Lake for historical tracking.

        Args:
            result: DivergenceResult to log
        """
        import pandas as pd

        try:
            divergence_df = pd.DataFrame(
                {
                    "timestamp": [result.timestamp],
                    "pair_name": [result.pair_name],
                    "correlation": [result.current_correlation],
                    "z_score": [result.z_score],
                    "resolved": [False],  # Will be updated when correlation normalizes
                }
            )

            write_deltalake(
                str(self.divergence_table_path),
                divergence_df,
                mode="append",
            )

            logger.info(f"Logged divergence to Delta Lake: {result.pair_name}")

        except Exception as e:
            logger.error(f"Failed to log divergence to Delta Lake: {e}")

    def monitor_all_pairs(
        self,
        hours_back: int = 2,
    ) -> list:
        """
        Monitor all futures-ETF pairs for divergence.

        Args:
            hours_back: Hours to look back for correlation data

        Returns:
            List of divergence results (empty if no divergences)
        """
        from v6.monitoring.correlation_tracker import CorrelationTracker

        divergences = []

        # Check all pairs
        for futures_symbol, etf_symbol in self.ALL_PAIRS:
            # Skip if not during market hours
            if not self.is_market_hours(datetime.now()):
                logger.debug("Outside market hours, skipping correlation check")
                continue

            # Create tracker
            tracker = CorrelationTracker(
                futures_symbol=futures_symbol,
                etf_symbol=etf_symbol,
            )

            # Get current divergence status
            result = tracker.get_current_divergence_status()

            # Check if divergence detected
            if result.divergence_detected:
                # Check rate limiting
                if not self._should_alert_pair(result.pair_name):
                    logger.debug(
                        f"Correlation divergence for {result.pair_name} rate limited"
                    )
                    continue

                # Send alert
                self.alert_manager.send_correlation_alert(
                    divergence_score=abs(result.z_score) / 2.0,  # Normalize to 0-1
                    correlated_symbols=[result.pair_name],
                    metadata={
                        "pair": result.pair_name,
                        "correlation": result.current_correlation,
                        "z_score": result.z_score,
                        "mean_correlation": result.mean_correlation,
                        "std_correlation": result.std_correlation,
                    },
                )

                # Log to Delta Lake
                self._log_divergence(result)

                # Update last alert time
                self._update_last_alert_time(result.pair_name)

                divergences.append(result)

                logger.warning(
                    f"Correlation divergence alert sent: {result.pair_name} "
                    f"(z-score: {result.z_score:.2f})"
                )

        return divergences

    def get_recent_divergences(
        self,
        hours_back: int = 24,
    ) -> pl.DataFrame:
        """
        Get recent divergences from Delta Lake.

        Args:
            hours_back: Hours to look back

        Returns:
            DataFrame of recent divergences
        """
        try:
            if not DeltaTable.is_deltatable(str(self.divergence_table_path)):
                return pl.DataFrame()

            table = DeltaTable(str(self.divergence_table_path))

            # Load all data and filter in Python (avoid Delta Lake type issues)
            df = pl.from_pandas(table.to_pandas())

            if df.is_empty():
                return pl.DataFrame()

            # Filter by timestamp in Python
            cutoff_time = datetime.now() - timedelta(hours=hours_back)
            df = df.filter(pl.col("timestamp") >= cutoff_time)

            return df.sort("timestamp", descending=True)

        except Exception as e:
            logger.error(f"Failed to load recent divergences: {e}")
            return pl.DataFrame()
