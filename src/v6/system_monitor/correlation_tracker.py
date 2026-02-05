"""
Correlation Tracker Module

This module provides real-time correlation tracking between futures (ES/NQ/RTY) and ETFs (SPY/QQQ/IWM).
Monitors correlation divergence using z-score statistical analysis to detect market regime changes,
news events, or data issues.

Key features:
- Rolling correlation calculation with configurable windows (default 60 minutes)
- Z-score divergence detection (>2 standard deviations)
- Time alignment for futures (23h trading) vs ETFs (6.5h trading)
- Delta Lake data loading from futures_snapshots and market_data_daily tables
- Pair tracking: ES-SPY, NQ-QQQ, RTY-IWM (direct mapping) + cross-pairs
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from deltalake import DeltaTable
from loguru import logger


@dataclass
class DivergenceResult:
    """Result of divergence detection analysis."""
    pair_name: str
    current_correlation: float
    mean_correlation: float
    std_correlation: float
    z_score: float
    divergence_detected: bool
    timestamp: datetime


class CorrelationTracker:
    """
    Track rolling correlations between futures and ETFs with divergence detection.

    Calculates rolling correlation, monitors z-score deviations from mean, and detects
    significant divergences that may indicate market regime changes or data issues.
    """

    # Futures-ETF mapping
    FUTURE_ETF_PAIRS = {
        "ES": "SPY",  # S&P 500 futures → SPY ETF
        "NQ": "QQQ",  # NASDAQ-100 futures → QQQ ETF
        "RTY": "IWM",  # Russell 2000 futures → IWM ETF
    }

    # All pairs to track (direct + cross-pairs)
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
        futures_symbol: str,
        etf_symbol: str,
        window_minutes: int = 60,
        z_score_threshold: float = 2.0,
        futures_table_path: str = "data/lake/futures_snapshots",
        market_data_table_path: str = "data/lake/market_data_daily",
    ):
        """
        Initialize correlation tracker for a futures-ETF pair.

        Args:
            futures_symbol: Futures symbol (e.g., 'ES', 'NQ', 'RTY')
            etf_symbol: ETF symbol (e.g., 'SPY', 'QQQ', 'IWM')
            window_minutes: Rolling window size in minutes (default 60)
            z_score_threshold: Z-score threshold for divergence (default 2.0)
            futures_table_path: Path to futures_snapshots Delta Lake table
            market_data_table_path: Path to market_data_daily Delta Lake table
        """
        self.futures_symbol = futures_symbol
        self.etf_symbol = etf_symbol
        self.pair_name = f"{futures_symbol}-{etf_symbol}"
        self.window_minutes = window_minutes
        self.z_score_threshold = z_score_threshold
        self.futures_table_path = Path(futures_table_path)
        self.market_data_table_path = Path(market_data_table_path)

        logger.info(
            f"CorrelationTracker initialized: {self.pair_name}, "
            f"window={window_minutes}min, z_threshold={z_score_threshold}"
        )

    def calculate_rolling_correlation(
        self,
        futures_prices: pd.Series,
        etf_prices: pd.Series,
    ) -> pd.Series:
        """
        Calculate rolling correlation between futures and ETF prices.

        Args:
            futures_prices: Series of futures prices with DatetimeIndex
            etf_prices: Series of ETF prices with DatetimeIndex

        Returns:
            Series of rolling correlations with same index as input
        """
        # Align timestamps using asof merge
        # Futures trade 23h/day, ETFs trade 6.5h/day - need time alignment
        df = pd.DataFrame(
            {"futures": futures_prices, "etf": etf_prices}
        )

        # Forward fill ETF data (they don't trade pre-market like futures do)
        df["etf"] = df["etf"].ffill()

        # Drop rows where either instrument has no data
        df = df.dropna()

        if len(df) < self.window_minutes:
            logger.warning(
                f"Not enough data points for {self.pair_name}: "
                f"{len(df)} < {self.window_minutes}"
            )
            return pd.Series(dtype=float)

        # Calculate rolling correlation
        # Convert window_minutes to number of data points
        # Assuming 1-minute frequency (adjust if different)
        window_size = max(1, self.window_minutes)

        rolling_corr = df["futures"].rolling(window=window_size).corr(df["etf"])

        return rolling_corr

    def detect_divergence(
        self,
        correlation_series: pd.Series,
    ) -> DivergenceResult:
        """
        Detect divergence using z-score analysis of correlation.

        Args:
            correlation_series: Series of rolling correlations

        Returns:
            DivergenceResult with current correlation, statistics, and divergence flag
        """
        # Remove NaN values from correlation series
        clean_corr = correlation_series.dropna()

        if len(clean_corr) == 0:
            logger.warning(f"No valid correlation data for {self.pair_name}")
            return DivergenceResult(
                pair_name=self.pair_name,
                current_correlation=0.0,
                mean_correlation=0.0,
                std_correlation=0.0,
                z_score=0.0,
                divergence_detected=False,
                timestamp=datetime.now(),
            )

        # Get current correlation (most recent)
        current_corr = clean_corr.iloc[-1]

        # Calculate rolling statistics for dynamic baseline
        mean_corr = clean_corr.mean()
        std_corr = clean_corr.std()

        # Handle edge case: std = 0 (no variation)
        if std_corr == 0:
            z_score = 0.0
        else:
            z_score = (current_corr - mean_corr) / std_corr

        # Detect divergence
        divergence_detected = abs(z_score) > self.z_score_threshold

        result = DivergenceResult(
            pair_name=self.pair_name,
            current_correlation=float(current_corr),
            mean_correlation=float(mean_corr),
            std_correlation=float(std_corr),
            z_score=float(z_score),
            divergence_detected=divergence_detected,
            timestamp=datetime.now(),
        )

        if divergence_detected:
            logger.warning(
                f"Divergence detected for {self.pair_name}: "
                f"correlation={current_corr:.3f}, z-score={z_score:.2f}"
            )

        return result

    def get_correlation_data(
        self,
        start_time: datetime,
        end_time: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Load price data and calculate correlations for time range.

        Args:
            start_time: Start of time range
            end_time: End of time range (default: now)

        Returns:
            DataFrame with timestamps, correlations, and prices
        """
        if end_time is None:
            end_time = datetime.now()

        # Load futures data
        futures_df = self._load_futures_data(start_time, end_time)

        # Load ETF data
        etf_df = self._load_etf_data(start_time, end_time)

        if futures_df.empty or etf_df.empty:
            logger.warning(
                f"No data available for {self.pair_name} "
                f"in range {start_time} to {end_time}"
            )
            return pd.DataFrame()

        # Merge and align timestamps
        merged_df = pd.merge_asof(
            futures_df.set_index("timestamp"),
            etf_df.set_index("timestamp"),
            left_index=True,
            right_index=True,
            direction="nearest",
            suffixes=("_futures", "_etf"),
        )

        # Forward fill ETF prices (they don't trade as early as futures)
        merged_df["price_etf"] = merged_df["price_etf"].ffill()

        # Drop rows with missing data
        merged_df = merged_df.dropna()

        if merged_df.empty:
            return pd.DataFrame()

        # Calculate rolling correlation
        correlations = self.calculate_rolling_correlation(
            merged_df["price_futures"],
            merged_df["price_etf"],
        )

        # Combine into result DataFrame
        result = pd.DataFrame(
            {
                "timestamp": merged_df.index,
                "futures_price": merged_df["price_futures"].values,
                "etf_price": merged_df["price_etf"].values,
                "correlation": correlations.values,
            }
        ).dropna()

        return result

    def _load_futures_data(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> pd.DataFrame:
        """
        Load futures data from Delta Lake.

        Args:
            start_time: Start time
            end_time: End time

        Returns:
            DataFrame with timestamp and price columns
        """
        try:
            if not DeltaTable.is_deltatable(str(self.futures_table_path)):
                logger.warning(
                    f"Futures table not found: {self.futures_table_path}"
                )
                return pd.DataFrame()

            table = DeltaTable(str(self.futures_table_path))

            # Read data for symbol and time range
            start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
            end_str = end_time.strftime("%Y-%m-%d %H:%M:%S")

            df = table.to_pandas(
                filters=[
                    ("symbol", "==", self.futures_symbol),
                    ("timestamp", ">=", start_str),
                    ("timestamp", "<=", end_str),
                ],
            )

            if df.empty:
                return pd.DataFrame()

            # Use mid-price (average of bid and ask)
            if "bid" in df.columns and "ask" in df.columns:
                df["price"] = (df["bid"] + df["ask"]) / 2
            elif "close" in df.columns:
                df["price"] = df["close"]
            else:
                logger.warning(
                    f"No price columns found in futures data for {self.futures_symbol}"
                )
                return pd.DataFrame()

            return df[["timestamp", "price"]]

        except Exception as e:
            logger.error(f"Error loading futures data for {self.futures_symbol}: {e}")
            return pd.DataFrame()

    def _load_etf_data(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> pd.DataFrame:
        """
        Load ETF data from Delta Lake.

        Args:
            start_time: Start time
            end_time: End time

        Returns:
            DataFrame with timestamp and price columns
        """
        try:
            if not DeltaTable.is_deltatable(str(self.market_data_table_path)):
                logger.warning(
                    f"Market data table not found: {self.market_data_table_path}"
                )
                return pd.DataFrame()

            table = DeltaTable(str(self.market_data_table_path))

            # Read data for symbol and time range
            start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
            end_str = end_time.strftime("%Y-%m-%d %H:%M:%S")

            df = table.to_pandas(
                filters=[
                    ("symbol", "==", self.etf_symbol),
                    ("timestamp", ">=", start_str),
                    ("timestamp", "<=", end_str),
                ],
            )

            if df.empty:
                return pd.DataFrame()

            # Use close price
            if "close" not in df.columns:
                logger.warning(
                    f"No close price found in ETF data for {self.etf_symbol}"
                )
                return pd.DataFrame()

            return df[["timestamp", "close"]].rename(columns={"close": "price"})

        except Exception as e:
            logger.error(f"Error loading ETF data for {self.etf_symbol}: {e}")
            return pd.DataFrame()

    def is_market_hours(self, timestamp: datetime) -> bool:
        """
        Check if timestamp is during market hours (8am-5pm ET).

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
        return 8 <= hour < 17

    def get_current_divergence_status(self) -> DivergenceResult:
        """
        Get current divergence status by loading recent data and analyzing.

        Returns:
            DivergenceResult with current status
        """
        # Load last 5 days of data (minimum for 60-minute window)
        end_time = datetime.now()
        start_time = end_time - timedelta(days=5)

        # Get correlation data
        corr_data = self.get_correlation_data(start_time, end_time)

        if corr_data.empty:
            logger.warning(f"No correlation data available for {self.pair_name}")
            return DivergenceResult(
                pair_name=self.pair_name,
                current_correlation=0.0,
                mean_correlation=0.0,
                std_correlation=0.0,
                z_score=0.0,
                divergence_detected=False,
                timestamp=datetime.now(),
            )

        # Calculate divergence
        correlation_series = pd.Series(
            corr_data["correlation"].values,
            index=pd.to_datetime(corr_data["timestamp"]),
        )

        return self.detect_divergence(correlation_series)
