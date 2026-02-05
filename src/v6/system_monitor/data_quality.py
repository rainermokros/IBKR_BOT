"""
Data Quality Monitoring Module

This module provides real-time data quality monitoring using IsolationForest anomaly detection.
It monitors Delta Lake tables for data quality issues including anomalies, missing values,
stale data, and corrupted data.

Key features:
- IsolationForest-based anomaly detection with automatic threshold detection
- Health score calculation (0-100 scale)
- Data quality checks: missing values, stale data, corrupted data, out-of-range
- Integration with Delta Lake for reading market data
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from deltalake import DeltaTable
from loguru import logger
from sklearn.ensemble import IsolationForest


@dataclass
class DataQualityReport:
    """Data quality assessment report."""
    health_score: int
    anomaly_count: int
    missing_values: dict[str, int]
    stale_data: bool
    corrupted_data: bool
    out_of_range: bool
    anomalies: pd.DataFrame
    timestamp: datetime


class DataQualityMonitor:
    """
    Monitor data quality using IsolationForest anomaly detection.

    Trains on historical "normal" market data and detects anomalies in new data.
    Calculates health score based on multiple data quality dimensions.
    """

    def __init__(
        self,
        futures_table_path: str = "data/lake/futures_snapshots",
        market_data_table_path: str = "data/lake/market_data_daily",
        training_days: int = 30,
        contamination: str = "auto",
        n_estimators: int = 100,
        random_state: int = 42,
    ):
        """
        Initialize data quality monitor.

        Args:
            futures_table_path: Path to futures_snapshots Delta Lake table
            market_data_table_path: Path to market_data_daily Delta Lake table
            training_days: Number of days of historical data for training
            contamination: IsolationForest contamination parameter ('auto' or float)
            n_estimators: Number of trees in IsolationForest
            random_state: Random seed for reproducibility
        """
        self.futures_table_path = Path(futures_table_path)
        self.market_data_table_path = Path(market_data_table_path)
        self.training_days = training_days
        self.contamination = contamination
        self.n_estimators = n_estimators
        self.random_state = random_state

        self._isolation_forest: IsolationForest | None = None
        self._feature_columns: list[str] = []

        logger.info(
            f"DataQualityMonitor initialized: "
            f"futures={futures_table_path}, market_data={market_data_table_path}"
        )

    def _load_training_data(self) -> pd.DataFrame:
        """
        Load last N days of market data for training.

        Returns:
            DataFrame with features for anomaly detection
        """
        try:
            # Try loading from futures_snapshots first
            if DeltaTable.is_deltatable(str(self.futures_table_path)):
                table = DeltaTable(str(self.futures_table_path))
                cutoff_date = (datetime.now() - timedelta(days=self.training_days)).strftime(
                    "%Y-%m-%d"
                )

                # Read recent data
                df = table.to_pandas(
                    filters=[("timestamp", ">=", cutoff_date)],
                )

                if len(df) > 0:
                    logger.info(f"Loaded {len(df)} rows from futures_snapshots for training")
                    return df

            # Fallback to market_data_daily
            if DeltaTable.is_deltatable(str(self.market_data_table_path)):
                table = DeltaTable(str(self.market_data_table_path))
                cutoff_date = (datetime.now() - timedelta(days=self.training_days)).strftime(
                    "%Y-%m-%d"
                )

                df = table.to_pandas(
                    filters=[("timestamp", ">=", cutoff_date)],
                )

                if len(df) > 0:
                    logger.info(f"Loaded {len(df)} rows from market_data_daily for training")
                    return df

            # If no data available, return empty DataFrame
            logger.warning(
                "No training data available in Delta Lake tables. "
                "Monitor will need explicit training data."
            )
            return pd.DataFrame()

        except Exception as e:
            logger.error(f"Error loading training data: {e}")
            return pd.DataFrame()

    def _prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Prepare features for anomaly detection.

        Args:
            df: Raw market data DataFrame

        Returns:
            DataFrame with feature columns ready for IsolationForest
        """
        # Select numeric columns that are likely to contain market data
        feature_cols = []

        # Common market data columns
        possible_features = [
            "close",
            "open",
            "high",
            "low",
            "volume",
            "bid",
            "ask",
            "last_price",
            "mark_price",
            "settlement_price",
            "volatility",
            "hv",
            "iv",
        ]

        for col in possible_features:
            if col in df.columns:
                feature_cols.append(col)

        # If no standard columns found, use all numeric columns
        if not feature_cols:
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            # Exclude timestamp and ID columns
            feature_cols = [c for c in numeric_cols if "time" not in c.lower() and "id" not in c.lower()]

        if not feature_cols:
            logger.warning("No suitable feature columns found for anomaly detection")
            return pd.DataFrame()

        # Extract features and handle missing values
        features_df = df[feature_cols].copy()

        # Fill missing values with forward fill then backward fill
        features_df = features_df.ffill().bfill()

        # Fill any remaining NaN with 0
        features_df = features_df.fillna(0)

        # Replace infinite values
        features_df = features_df.replace([np.inf, -np.inf], 0)

        self._feature_columns = feature_cols
        logger.info(f"Prepared {len(feature_cols)} features: {feature_cols}")

        return features_df

    def train(self, training_data: pd.DataFrame | None = None) -> None:
        """
        Train IsolationForest on normal market data.

        Args:
            training_data: Optional pre-loaded training data. If None, loads from Delta Lake.
        """
        if training_data is None:
            training_data = self._load_training_data()

        if len(training_data) == 0:
            logger.warning("No training data available. Cannot train anomaly detector.")
            return

        # Prepare features
        features = self._prepare_features(training_data)

        if len(features) == 0:
            logger.warning("No features available for training. Cannot train anomaly detector.")
            return

        # Train IsolationForest
        self._isolation_forest = IsolationForest(
            contamination=self.contamination,
            n_estimators=self.n_estimators,
            random_state=self.random_state,
            n_jobs=-1,  # Use all CPU cores
        )

        self._isolation_forest.fit(features)

        logger.info(
            f"✓ Trained IsolationForest on {len(features)} samples "
            f"with {len(self._feature_columns)} features"
        )

    def detect_anomalies(self, data: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        """
        Detect anomalies in market data.

        Args:
            data: DataFrame with market data to analyze

        Returns:
            Tuple of (anomaly_labels, anomaly_scores)
            - anomaly_labels: 1 for inliers, -1 for outliers
            - anomaly_scores: Anomaly scores (lower = more anomalous)
        """
        if self._isolation_forest is None:
            logger.warning("IsolationForest not trained. Training now...")
            self.train()
            if self._isolation_forest is None:
                # Return empty arrays if training failed
                return np.array([]), np.array([])

        # Prepare features
        features = self._prepare_features(data)

        if len(features) == 0:
            logger.warning("No features available for anomaly detection")
            return np.array([]), np.array([])

        # Detect anomalies
        anomaly_labels = self._isolation_forest.predict(features)
        anomaly_scores = self._isolation_forest.score_samples(features)

        anomaly_count = (anomaly_labels == -1).sum()
        logger.info(f"Detected {anomaly_count} anomalies in {len(data)} records")

        return anomaly_labels, anomaly_scores

    def check_missing_values(self, df: pd.DataFrame) -> dict[str, int]:
        """
        Check for missing values in DataFrame.

        Args:
            df: DataFrame to check

        Returns:
            Dictionary mapping column names to count of missing values
        """
        missing = df.isnull().sum()
        missing_dict = missing[missing > 0].to_dict()

        if missing_dict:
            logger.warning(f"Missing values detected: {missing_dict}")

        return missing_dict

    def check_stale_data(self, df: pd.DataFrame, max_age_minutes: int = 5) -> bool:
        """
        Check if data is stale (too old).

        Args:
            df: DataFrame with timestamp column
            max_age_minutes: Maximum age in minutes

        Returns:
            True if data is stale, False otherwise
        """
        if "timestamp" not in df.columns:
            logger.warning("No timestamp column found for staleness check")
            return False

        # Get most recent timestamp
        latest_timestamp = pd.to_datetime(df["timestamp"]).max()
        age = datetime.now() - latest_timestamp

        is_stale = age > timedelta(minutes=max_age_minutes)

        if is_stale:
            logger.warning(
                f"Stale data detected: Latest timestamp is {age.total_seconds() / 60:.1f} minutes old"
            )

        return is_stale

    def check_corrupted_data(self, df: pd.DataFrame, max_change_pct: float = 0.20) -> bool:
        """
        Check for corrupted data (extreme price changes).

        Args:
            df: DataFrame with price columns
            max_change_pct: Maximum price change percentage

        Returns:
            True if corrupted data detected, False otherwise
        """
        # Find price columns
        price_cols = [c for c in df.columns if c.lower() in ["close", "price", "last", "mark"]]

        if not price_cols:
            return False

        corrupted = False
        for col in price_cols:
            if col in df.columns:
                # Calculate percentage change
                pct_change = df[col].pct_change().abs()

                # Check for extreme changes
                extreme_changes = pct_change[pct_change > max_change_pct]

                if len(extreme_changes) > 0:
                    logger.warning(
                        f"Corrupted data detected in {col}: "
                        f"{len(extreme_changes)} extreme price changes >{max_change_pct * 100}%"
                    )
                    corrupted = True

        return corrupted

    def check_out_of_range(self, df: pd.DataFrame) -> bool:
        """
        Check for out-of-range values (negative prices, zero volume, etc.).

        Args:
            df: DataFrame to check

        Returns:
            True if out-of-range values detected, False otherwise
        """
        out_of_range = False

        # Check for negative prices
        price_cols = [c for c in df.columns if c.lower() in ["close", "price", "last", "mark", "open", "high", "low"]]
        for col in price_cols:
            if col in df.columns:
                negative_count = (df[col] < 0).sum()
                if negative_count > 0:
                    logger.warning(f"Out-of-range data: {negative_count} negative values in {col}")
                    out_of_range = True

        # Check for zero volume (if volume column exists)
        if "volume" in df.columns:
            zero_volume = (df["volume"] == 0).sum()
            if zero_volume > len(df) * 0.5:  # More than 50% zero volume
                logger.warning(f"Out-of-range data: {zero_volume} zero volume values")
                out_of_range = True

        return out_of_range

    def calculate_health_score(
        self,
        data: pd.DataFrame,
        anomaly_labels: np.ndarray | None = None,
    ) -> int:
        """
        Calculate data quality health score (0-100 scale).

        Scoring:
        - Base score: 100
        - -5 per anomaly detected (max -50)
        - -10 if stale data detected
        - -20 if missing values >5%
        - Clamp to 0-100 range

        Args:
            data: DataFrame to assess
            anomaly_labels: Optional pre-computed anomaly labels

        Returns:
            Health score from 0 to 100
        """
        score = 100

        # Anomaly penalty
        if anomaly_labels is not None and len(anomaly_labels) > 0:
            anomaly_count = (anomaly_labels == -1).sum()
            anomaly_penalty = min(anomaly_count * 5, 50)  # Max -50
            score -= anomaly_penalty

        # Stale data penalty
        if self.check_stale_data(data):
            score -= 10

        # Missing values penalty
        missing = self.check_missing_values(data)
        if missing:
            total_missing = sum(missing.values())
            total_cells = len(data) * len(data.columns)
            missing_pct = total_missing / total_cells if total_cells > 0 else 0

            if missing_pct > 0.05:  # More than 5% missing
                score -= 20

        # Clamp to 0-100
        score = max(0, min(100, score))

        logger.info(f"Data quality health score: {score}/100")

        return score

    def assess_data_quality(
        self,
        data: pd.DataFrame | None = None,
    ) -> DataQualityReport:
        """
        Comprehensive data quality assessment.

        Args:
            data: Optional DataFrame to assess. If None, loads latest from Delta Lake.

        Returns:
            DataQualityReport with all quality metrics
        """
        # Load data if not provided
        if data is None:
            # Try loading from futures_snapshots
            if DeltaTable.is_deltatable(str(self.futures_table_path)):
                table = DeltaTable(str(self.futures_table_path))
                # Get last 5 minutes of data
                cutoff_time = (datetime.now() - timedelta(minutes=5)).isoformat()
                data = table.to_pandas(filters=[("timestamp", ">=", cutoff_time)])

            # Fallback to market_data_daily
            elif DeltaTable.is_deltatable(str(self.market_data_table_path)):
                table = DeltaTable(str(self.market_data_table_path))
                cutoff_time = (datetime.now() - timedelta(minutes=5)).isoformat()
                data = table.to_pandas(filters=[("timestamp", ">=", cutoff_time)])
            else:
                logger.error("No data available for quality assessment")
                return DataQualityReport(
                    health_score=0,
                    anomaly_count=0,
                    missing_values={},
                    stale_data=True,
                    corrupted_data=False,
                    out_of_range=False,
                    anomalies=pd.DataFrame(),
                    timestamp=datetime.now(),
                )

        if len(data) == 0:
            logger.warning("No data available for quality assessment")
            return DataQualityReport(
                health_score=0,
                anomaly_count=0,
                missing_values={},
                stale_data=True,
                corrupted_data=False,
                out_of_range=False,
                anomalies=pd.DataFrame(),
                timestamp=datetime.now(),
            )

        # Train if needed
        if self._isolation_forest is None:
            self.train()

        # Detect anomalies
        anomaly_labels, anomaly_scores = self.detect_anomalies(data)

        # Identify anomalous rows
        if len(anomaly_labels) > 0:
            anomalies = data[anomaly_labels == -1].copy()
            anomalies["anomaly_score"] = anomaly_scores[anomaly_labels == -1]
        else:
            anomalies = pd.DataFrame()

        # Calculate health score
        health_score = self.calculate_health_score(data, anomaly_labels)

        # Check data quality dimensions
        missing_values = self.check_missing_values(data)
        stale_data = self.check_stale_data(data)
        corrupted_data = self.check_corrupted_data(data)
        out_of_range = self.check_out_of_range(data)

        report = DataQualityReport(
            health_score=health_score,
            anomaly_count=len(anomalies),
            missing_values=missing_values,
            stale_data=stale_data,
            corrupted_data=corrupted_data,
            out_of_range=out_of_range,
            anomalies=anomalies,
            timestamp=datetime.now(),
        )

        logger.info(
            f"Data quality assessment complete: "
            f"score={health_score}, anomalies={len(anomalies)}, "
            f"stale={stale_data}, corrupted={corrupted_data}"
        )

        return report
