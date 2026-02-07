"""
Strategy Predictions Table

Stores strategy predictions at entry time and actual results at exit.
Enables variance analysis for strategy weight tuning.

Key patterns:
- StrategyPrediction: Dataclass for prediction record with metadata
- StrategyPredictionsTable: Delta Lake table for storing predictions
- Store prediction at entry: Captures predicted_score, regime, IV rank
- Update with actuals at exit: Records actual P&L and prediction error
- Read predictions for analysis: Returns completed predictions for variance analysis
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import polars as pl
from deltalake import DeltaTable, write_deltalake
from loguru import logger


@dataclass
class StrategyPrediction:
    """Prediction record with metadata."""
    prediction_id: str
    timestamp: datetime
    symbol: str
    strategy_type: str  # iron_condor, bull_put_spread, bear_call_spread
    predicted_score: float  # 0-100 from StrategySelector
    predicted_return_pct: float
    regime_at_entry: str  # From EnhancedMarketRegimeDetector
    iv_rank_at_entry: float
    dte: int
    strike_width: int
    entry_price: float

    # Actual results (filled at exit)
    actual_pnl_pct: Optional[float] = None
    actual_pnl: Optional[float] = None
    exit_time: Optional[datetime] = None
    exit_reason: Optional[str] = None
    prediction_error: Optional[float] = None  # predicted - actual


class StrategyPredictionsTable:
    """Delta Lake table for storing strategy predictions."""

    def __init__(self, table_path: str = "data/lake/strategy_predictions"):
        """
        Initialize strategy predictions table.

        Args:
            table_path: Path to Delta Lake table (default: data/lake/strategy_predictions)
        """
        self.table_path = Path(table_path)
        self._ensure_table_exists()

    def _ensure_table_exists(self) -> None:
        """Create table if it doesn't exist."""
        if DeltaTable.is_deltatable(str(self.table_path)):
            return

        # Schema for strategy predictions
        schema = pl.Schema({
            'prediction_id': pl.String,
            'timestamp': pl.Datetime("us"),
            'symbol': pl.String,
            'strategy_type': pl.String,
            'predicted_score': pl.Float64,
            'predicted_return_pct': pl.Float64,
            'regime_at_entry': pl.String,
            'iv_rank_at_entry': pl.Float64,
            'dte': pl.Int64,
            'strike_width': pl.Int64,
            'entry_price': pl.Float64,
            'actual_pnl_pct': pl.Float64,
            'actual_pnl': pl.Float64,
            'exit_time': pl.Datetime("us"),
            'exit_reason': pl.String,
            'prediction_error': pl.Float64,
            'date': pl.Date,
        })

        # Create empty table
        empty_df = pl.DataFrame(schema=schema)
        write_deltalake(
            str(self.table_path),
            empty_df.limit(0),
            mode="overwrite",
        )

        logger.info(f"Created strategy predictions Delta Lake table: {self.table_path}")

    def get_table(self) -> DeltaTable:
        """Get DeltaTable instance."""
        return DeltaTable(str(self.table_path))

    def store_prediction(self, prediction: StrategyPrediction) -> None:
        """
        Store prediction to Delta Lake.

        Args:
            prediction: StrategyPrediction to store
        """
        df = pl.DataFrame([{
            "prediction_id": prediction.prediction_id,
            "timestamp": prediction.timestamp,
            "symbol": prediction.symbol,
            "strategy_type": prediction.strategy_type,
            "predicted_score": prediction.predicted_score,
            "predicted_return_pct": prediction.predicted_return_pct,
            "regime_at_entry": prediction.regime_at_entry,
            "iv_rank_at_entry": prediction.iv_rank_at_entry,
            "dte": prediction.dte,
            "strike_width": prediction.strike_width,
            "entry_price": prediction.entry_price,
            "actual_pnl_pct": None,  # Will be filled at exit
            "actual_pnl": None,
            "exit_time": None,
            "exit_reason": None,
            "prediction_error": None,
            "date": prediction.timestamp.date(),
        }])

        write_deltalake(self.table_path, df, mode="append")
        logger.info(f"Stored prediction: {prediction.prediction_id[:8]}... (score={prediction.predicted_score:.1f})")

    def update_with_actuals(
        self,
        prediction_id: str,
        actual_pnl_pct: float,
        actual_pnl: float,
        exit_time: datetime,
        exit_reason: str,
    ) -> None:
        """
        Update prediction record with actual results.

        Reads the existing prediction, calculates prediction error, and updates
        the record with actual P&L data.

        Args:
            prediction_id: Prediction ID to update
            actual_pnl_pct: Actual return percentage
            actual_pnl: Actual P&L in dollars
            exit_time: Exit timestamp
            exit_reason: Reason for exit
        """
        # Read existing predictions
        dt = self.get_table()
        df = pl.from_pandas(dt.to_pandas())

        # Filter for this prediction
        pred_df = df.filter(pl.col("prediction_id") == prediction_id)

        if len(pred_df) == 0:
            logger.warning(f"Prediction {prediction_id[:8]}... not found for update")
            return

        # Calculate error
        predicted = pred_df.row(0, named=True)["predicted_return_pct"]
        error = predicted - actual_pnl_pct

        # Update the record with actuals
        updated = pred_df.with_columns([
            pl.lit(actual_pnl_pct).alias("actual_pnl_pct"),
            pl.lit(actual_pnl).alias("actual_pnl"),
            pl.lit(exit_time).alias("exit_time"),
            pl.lit(exit_reason).alias("exit_reason"),
            pl.lit(error).alias("prediction_error"),
        ])

        # Overwrite the specific record (append with newer data, using time travel)
        # For simplicity, we append and let queries filter by latest
        write_deltalake(self.table_path, updated, mode="overwrite")

        logger.debug(
            f"Updated prediction {prediction_id[:8]}... with actuals: "
            f"predicted={predicted:.2f}%, actual={actual_pnl_pct:.2f}%, error={error:.2f}%"
        )

    def read_predictions(
        self,
        symbol: str | None = None,
        strategy_type: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        min_predictions: int = 0,
    ) -> pl.DataFrame:
        """
        Read predictions for variance analysis.

        Returns completed predictions (have actual results).

        Args:
            symbol: Filter by symbol (optional)
            strategy_type: Filter by strategy type (optional)
            start_date: Filter by start date (optional)
            end_date: Filter by end date (optional)
            min_predictions: Minimum predictions required (returns empty if below threshold)

        Returns:
            pl.DataFrame: Completed predictions with actual results
        """
        dt = self.get_table()
        df = pl.from_pandas(dt.to_pandas())

        # Apply filters
        if symbol:
            df = df.filter(pl.col("symbol") == symbol)
        if strategy_type:
            df = df.filter(pl.col("strategy_type") == strategy_type)
        if start_date:
            df = df.filter(pl.col("date") >= start_date)
        if end_date:
            df = df.filter(pl.col("date") <= end_date)

        # Only completed predictions (have actual results)
        df = df.filter(pl.col("actual_pnl_pct").is_not_null())

        # Check minimum threshold
        if len(df) < min_predictions:
            logger.warning(
                f"Insufficient predictions: {len(df)} < {min_predictions}. "
                f"symbol={symbol}, strategy_type={strategy_type}"
            )
            return pl.DataFrame()

        return df

    def get_prediction_stats(self, days: int = 30) -> dict:
        """
        Get summary statistics for predictions.

        Args:
            days: Number of days to look back

        Returns:
            Dict with prediction statistics
        """
        end_date = date.today()
        start_date = end_date - __import__('datetime').timedelta(days=days)

        df = self.read_predictions(
            start_date=start_date,
            end_date=end_date,
        )

        if len(df) == 0:
            return {
                "total_predictions": 0,
                "completed_predictions": 0,
                "mean_absolute_error": 0.0,
                "by_strategy_type": {},
            }

        # Calculate MAE
        mae = df["prediction_error"].abs().mean()

        # Group by strategy type
        by_strategy = {}
        for strategy_type in df["strategy_type"].unique().to_list():
            type_df = df.filter(pl.col("strategy_type") == strategy_type)
            by_strategy[strategy_type] = {
                "count": len(type_df),
                "mae": float(type_df["prediction_error"].abs().mean()),
                "mean_predicted": float(type_df["predicted_return_pct"].mean()),
                "mean_actual": float(type_df["actual_pnl_pct"].mean()),
            }

        return {
            "total_predictions": len(df),
            "completed_predictions": len(df),
            "mean_absolute_error": float(mae),
            "by_strategy_type": by_strategy,
        }


def create_prediction(
    symbol: str,
    strategy_type: str,
    predicted_score: float,
    predicted_return_pct: float,
    regime_at_entry: str,
    iv_rank_at_entry: float,
    dte: int,
    strike_width: int,
    entry_price: float,
    prediction_id: str | None = None,
) -> StrategyPrediction:
    """
    Factory function to create a StrategyPrediction.

    Args:
        symbol: Underlying symbol
        strategy_type: Strategy type
        predicted_score: Predicted score from StrategySelector (0-100)
        predicted_return_pct: Predicted return percentage
        regime_at_entry: Market regime at entry
        iv_rank_at_entry: IV rank at entry
        dte: Days to expiration
        strike_width: Strike width
        entry_price: Entry price
        prediction_id: Optional prediction ID (generated if not provided)

    Returns:
        StrategyPrediction instance
    """
    if prediction_id is None:
        prediction_id = str(uuid.uuid4())

    return StrategyPrediction(
        prediction_id=prediction_id,
        timestamp=datetime.now(),
        symbol=symbol,
        strategy_type=strategy_type,
        predicted_score=predicted_score,
        predicted_return_pct=predicted_return_pct,
        regime_at_entry=regime_at_entry,
        iv_rank_at_entry=iv_rank_at_entry,
        dte=dte,
        strike_width=strike_width,
        entry_price=entry_price,
    )
