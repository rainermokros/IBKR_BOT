"""
Futures Correlation Analyzer

Analyzes correlations between futures (ES, NQ, RTY) and spot ETFs (SPY, QQQ, IWM).
Provides lead-lag analysis and predictive value assessment for futures data.

Purpose: Determine if futures movements predict spot ETF movements to improve entry signals.

Usage:
    analyzer = FuturesAnalyzer()
    correlation = analyzer.calculate_correlation("ES", "SPY", days=7)
    lead_lag = analyzer.calculate_lead_lag("ES", "SPY", max_lead_minutes=60)
    predictive = analyzer.assess_predictive_value("ES", "SPY", days=7)
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import polars as pl
from deltalake import DeltaTable
from loguru import logger


class FuturesAnalyzer:
    """
    Analyze futures correlations and predictive value for trading decisions.

    Provides:
    - Rolling correlations between futures and spot ETFs
    - Lead-lag analysis (do futures move before spot?)
    - Predictive value assessment (directional accuracy, signal-to-noise)
    """

    # Futures to ETF mappings
    FUTURES_ETF_MAPPING = {
        "ES": "SPY",  # S&P 500 futures -> SPDR S&P 500 ETF
        "NQ": "QQQ",  # Nasdaq 100 futures -> Invesco QQQ Trust
        "RTY": "IWM",  # Russell 2000 futures -> iShares Russell 2000 ETF
    }

    def __init__(
        self,
        futures_table_path: str = "data/lake/futures_snapshots",
        spot_table_path: str = "data/lake/option_snapshots"
    ):
        """
        Initialize futures analyzer.

        Args:
            futures_table_path: Path to futures snapshots Delta Lake table
            spot_table_path: Path to option snapshots Delta Lake table (for spot ETF prices)
        """
        self.futures_table_path = futures_table_path
        self.spot_table_path = spot_table_path
        self._check_tables_exist()

    def _check_tables_exist(self) -> None:
        """Verify required Delta Lake tables exist."""
        if not DeltaTable.is_deltatable(self.futures_table_path):
            logger.warning(f"Futures table does not exist: {self.futures_table_path}")
        if not DeltaTable.is_deltatable(self.spot_table_path):
            logger.warning(f"Spot table does not exist: {self.spot_table_path}")

    def calculate_correlation(
        self,
        futures_symbol: str,
        spot_symbol: str,
        days: int = 7,
        field: str = "last"
    ) -> float:
        """
        Calculate rolling correlation between futures and spot ETF.

        Args:
            futures_symbol: Futures symbol (ES, NQ, RTY)
            spot_symbol: Spot ETF symbol (SPY, QQQ, IWM)
            days: Number of days to analyze (minimum 7 for meaningful results)
            field: Field to correlate (default: "last" price)

        Returns:
            float: Correlation coefficient (-1 to 1)
                   Returns 0.0 if insufficient data

        Raises:
            ValueError: If days < 7 (insufficient data)
        """
        if days < 7:
            logger.warning(f"Insufficient data for correlation: {days} days < 7 days minimum")
            return 0.0

        try:
            # Calculate time range
            end = datetime.now()
            start = end - timedelta(days=days)

            # Load futures data
            futures_df = self._load_futures_data(futures_symbol, start, end, [field])
            if futures_df.is_empty() or len(futures_df) < 10:
                logger.warning(f"Insufficient futures data for {futures_symbol}: {len(futures_df)} points")
                return 0.0

            # Load spot data (use option snapshots to get underlying price)
            spot_df = self._load_spot_data(spot_symbol, start, end)
            if spot_df.is_empty() or len(spot_df) < 10:
                logger.warning(f"Insufficient spot data for {spot_symbol}: {len(spot_df)} points")
                return 0.0

            # Merge on timestamp (nearest match within 1 minute)
            merged = self._merge_on_timestamp(futures_df, spot_df, field)

            if len(merged) < 10:
                logger.warning(
                    f"Insufficient overlapping data for {futures_symbol}-{spot_symbol}: "
                    f"{len(merged)} points"
                )
                return 0.0

            # Calculate correlation
            futures_col = field
            spot_col = "spot_price"

            # Drop nulls
            merged = merged.drop_nulls([futures_col, spot_col])

            if len(merged) < 10:
                logger.warning(f"Insufficient valid data after dropping nulls: {len(merged)}")
                return 0.0

            # Calculate correlation using Polars
            corr = merged.select(
                pl.corr(pl.col(futures_col), pl.col(spot_col))
            ).item()

            logger.info(
                f"Correlation {futures_symbol}-{spot_symbol}: {corr:.3f} "
                f"(n={len(merged)}, days={days})"
            )

            return corr if corr is not None else 0.0

        except Exception as e:
            logger.error(f"Error calculating correlation: {e}", exc_info=True)
            return 0.0

    def calculate_lead_lag(
        self,
        futures_symbol: str,
        spot_symbol: str,
        max_lead_minutes: int = 60,
        days: int = 7
    ) -> Dict[int, float]:
        """
        Calculate lead-lag relationship between futures and spot.

        Tests if futures movements lead spot movements by X minutes.
        Calculates correlation at different lead times.

        Args:
            futures_symbol: Futures symbol (ES, NQ, RTY)
            spot_symbol: Spot ETF symbol (SPY, QQQ, IWM)
            max_lead_minutes: Maximum lead time to test (default: 60 minutes)
            days: Number of days to analyze

        Returns:
            Dict mapping lead_minutes -> correlation_coefficient
            Example: {5: 0.85, 15: 0.82, 30: 0.78, 60: 0.72}
            Returns empty dict if insufficient data (< 7 days)

        Interpretation:
            - Higher correlation at lead time = futures lead spot
            - Peak correlation indicates optimal lead time
            - If all correlations similar = no clear lead-lag
        """
        if days < 7:
            logger.warning(f"Insufficient data for lead-lag: {days} days < 7 days minimum")
            return {}

        try:
            # Calculate time range
            end = datetime.now()
            start = end - timedelta(days=days)

            # Load data
            futures_df = self._load_futures_data(futures_symbol, start, end, ["last"])
            spot_df = self._load_spot_data(spot_symbol, start, end)

            if futures_df.is_empty() or spot_df.is_empty():
                logger.warning("Insufficient data for lead-lag analysis")
                return {}

            # Test lead times: 5, 15, 30, 60 minutes
            lead_times = [5, 15, 30, 60]
            lead_times = [t for t in lead_times if t <= max_lead_minutes]

            correlations = {}

            for lead_minutes in lead_times:
                # Shift futures data forward by lead_minutes
                # This aligns futures(t) with spot(t + lead_minutes)
                futures_shifted = futures_df.with_columns(
                    pl.col("timestamp").dt.offset_by(f"{lead_minutes}m")
                )

                # Merge shifted futures with spot
                merged = self._merge_on_timestamp(
                    futures_shifted,
                    spot_df,
                    "last"
                )

                if len(merged) < 10:
                    logger.warning(f"Insufficient data for lead={lead_minutes}m: {len(merged)} points")
                    continue

                # Calculate correlation
                merged = merged.drop_nulls(["last", "spot_price"])
                if len(merged) < 10:
                    continue

                corr = merged.select(
                    pl.corr(pl.col("last"), pl.col("spot_price"))
                ).item()

                if corr is not None:
                    correlations[lead_minutes] = corr
                    logger.info(f"Lead-lag {lead_minutes}m: correlation={corr:.3f}")

            return correlations

        except Exception as e:
            logger.error(f"Error calculating lead-lag: {e}", exc_info=True)
            return {}

    def assess_predictive_value(
        self,
        futures_symbol: str,
        spot_symbol: str,
        days: int = 7
    ) -> Dict[str, float]:
        """
        Assess predictive value of futures for spot ETF movements.

        Measures:
        - Directional accuracy: Do futures predict spot direction correctly?
        - Signal-to-noise ratio: Strength of predictive signal vs noise
        - Lead strength: Correlation improvement at optimal lead time

        Args:
            futures_symbol: Futures symbol (ES, NQ, RTY)
            spot_symbol: Spot ETF symbol (SPY, QQQ, IWM)
            days: Number of days to analyze

        Returns:
            Dict with metrics:
            - directional_accuracy: % of times futures correctly predict spot direction (0-1)
            - signal_to_noise: Ratio of signal strength to noise (higher is better)
            - optimal_lead_minutes: Lead time with highest correlation
            - base_correlation: Correlation without lead (0-minute lead)
            - peak_correlation: Correlation at optimal lead time
            - lead_improvement: Improvement from base to peak correlation

            Returns dict with None values if insufficient data (< 7 days)
        """
        if days < 7:
            logger.warning(f"Insufficient data for predictive value: {days} days < 7 days minimum")
            return {
                "directional_accuracy": None,
                "signal_to_noise": None,
                "optimal_lead_minutes": None,
                "base_correlation": None,
                "peak_correlation": None,
                "lead_improvement": None,
            }

        try:
            # Calculate base correlation (no lead)
            base_corr = self.calculate_correlation(futures_symbol, spot_symbol, days=days)

            # Calculate lead-lag correlations
            lead_lag = self.calculate_lead_lag(futures_symbol, spot_symbol, days=days)

            if not lead_lag:
                # No lead-lag data, return base metrics only
                return {
                    "directional_accuracy": None,
                    "signal_to_noise": None,
                    "optimal_lead_minutes": None,
                    "base_correlation": base_corr,
                    "peak_correlation": base_corr,
                    "lead_improvement": 0.0,
                }

            # Find optimal lead time
            optimal_lead = max(lead_lag.items(), key=lambda x: x[1])
            optimal_lead_minutes = optimal_lead[0]
            peak_corr = optimal_lead[1]

            # Calculate lead improvement
            lead_improvement = peak_corr - base_corr

            # Calculate directional accuracy
            directional_accuracy = self._calculate_directional_accuracy(
                futures_symbol, spot_symbol, optimal_lead_minutes, days
            )

            # Calculate signal-to-noise ratio
            signal_to_noise = self._calculate_signal_to_noise(
                futures_symbol, spot_symbol, optimal_lead_minutes, days
            )

            return {
                "directional_accuracy": directional_accuracy,
                "signal_to_noise": signal_to_noise,
                "optimal_lead_minutes": optimal_lead_minutes,
                "base_correlation": base_corr,
                "peak_correlation": peak_corr,
                "lead_improvement": lead_improvement,
            }

        except Exception as e:
            logger.error(f"Error assessing predictive value: {e}", exc_info=True)
            return {
                "directional_accuracy": None,
                "signal_to_noise": None,
                "optimal_lead_minutes": None,
                "base_correlation": None,
                "peak_correlation": None,
                "lead_improvement": None,
            }

    def _load_futures_data(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        fields: List[str]
    ) -> pl.DataFrame:
        """Load futures data from Delta Lake."""
        try:
            if not DeltaTable.is_deltatable(self.futures_table_path):
                return pl.DataFrame()

            dt = DeltaTable(self.futures_table_path)
            df = pl.from_pandas(dt.to_pandas())

            # Filter by symbol and time range
            df = df.filter(
                (pl.col("symbol") == symbol) &
                (pl.col("timestamp") >= start) &
                (pl.col("timestamp") <= end)
            )

            # Select fields
            all_fields = ["symbol", "timestamp"] + fields
            df = df.select(all_fields)

            return df.sort("timestamp")

        except Exception as e:
            logger.error(f"Error loading futures data: {e}")
            return pl.DataFrame()

    def _load_spot_data(
        self,
        symbol: str,
        start: datetime,
        end: datetime
    ) -> pl.DataFrame:
        """
        Load spot ETF data from option snapshots.

        Uses underlying_price field from option snapshots.
        """
        try:
            if not DeltaTable.is_deltatable(self.spot_table_path):
                return pl.DataFrame()

            dt = DeltaTable(self.spot_table_path)
            df = pl.from_pandas(dt.to_pandas())

            # Filter by symbol and time range
            df = df.filter(
                (pl.col("symbol") == symbol) &
                (pl.col("timestamp") >= start) &
                (pl.col("timestamp") <= end)
            )

            # Select underlying price
            df = df.select(["timestamp", "underlying_price"])

            # Rename to spot_price for clarity
            df = df.rename({"underlying_price": "spot_price"})

            # Drop nulls
            df = df.drop_nulls()

            return df.sort("timestamp")

        except Exception as e:
            logger.error(f"Error loading spot data: {e}")
            return pl.DataFrame()

    def _merge_on_timestamp(
        self,
        df1: pl.DataFrame,
        df2: pl.DataFrame,
        field: str,
        tolerance_seconds: int = 60
    ) -> pl.DataFrame:
        """
        Merge two dataframes on timestamp with tolerance.

        Uses asof join (nearest match within tolerance).
        """
        try:
            # Ensure both sorted by timestamp
            df1 = df1.sort("timestamp")
            df2 = df2.sort("timestamp")

            # Use asof_join for nearest match
            merged = df1.asof_join(
                df2,
                on="timestamp",
                strategy="nearest"
            )

            return merged

        except Exception as e:
            logger.error(f"Error merging on timestamp: {e}")
            return pl.DataFrame()

    def _calculate_directional_accuracy(
        self,
        futures_symbol: str,
        spot_symbol: str,
        lead_minutes: int,
        days: int
    ) -> Optional[float]:
        """
        Calculate directional accuracy of futures predicting spot.

        Measures: When futures go up, does spot go up lead_minutes later?
        """
        try:
            end = datetime.now()
            start = end - timedelta(days=days)

            # Load data
            futures_df = self._load_futures_data(futures_symbol, start, end, ["last"])
            spot_df = self._load_spot_data(spot_symbol, start, end)

            if futures_df.is_empty() or spot_df.is_empty():
                return None

            # Calculate futures returns (1-minute changes)
            futures_df = futures_df.with_columns(
                pl.col("last").pct_change().alias("futures_return")
            )

            # Calculate spot returns (1-minute changes)
            spot_df = spot_df.with_columns(
                pl.col("spot_price").pct_change().alias("spot_return")
            )

            # Shift futures returns by lead_minutes
            # This aligns futures_return(t) with spot_return(t + lead_minutes)
            futures_shifted = futures_df.with_columns(
                pl.col("timestamp").dt.offset_by(f"{lead_minutes}m")
            )

            # Merge on timestamp
            merged = futures_shifted.select(["timestamp", "futures_return"]).asof_join(
                spot_df.select(["timestamp", "spot_return"]),
                on="timestamp",
                strategy="nearest"
            )

            # Drop nulls
            merged = merged.drop_nulls(["futures_return", "spot_return"])

            if len(merged) < 10:
                return None

            # Calculate directional accuracy
            # Count times both returns are positive or both are negative
            correct_direction = (
                (pl.col("futures_return") > 0) & (pl.col("spot_return") > 0) |
                (pl.col("futures_return") < 0) & (pl.col("spot_return") < 0)
            )

            accuracy = merged.select(
                pl.mean(correct_direction.cast(pl.Float64))
            ).item()

            return accuracy if accuracy is not None else 0.0

        except Exception as e:
            logger.error(f"Error calculating directional accuracy: {e}")
            return None

    def _calculate_signal_to_noise(
        self,
        futures_symbol: str,
        spot_symbol: str,
        lead_minutes: int,
        days: int
    ) -> Optional[float]:
        """
        Calculate signal-to-noise ratio for futures predictive value.

        Higher values indicate stronger predictive signal.
        """
        try:
            # Get correlation at optimal lead
            lead_lag = self.calculate_lead_lag(futures_symbol, spot_symbol, days=days)

            if not lead_lag or lead_minutes not in lead_lag:
                return None

            corr = lead_lag[lead_minutes]

            # Signal-to-noise = corr^2 / (1 - corr^2)
            # This is the F-statistic transformation of correlation
            if corr >= 1.0:
                return float('inf')

            snr = (corr ** 2) / (1 - corr ** 2)

            return snr

        except Exception as e:
            logger.error(f"Error calculating signal-to-noise: {e}")
            return None
