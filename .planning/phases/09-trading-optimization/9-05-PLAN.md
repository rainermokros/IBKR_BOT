---
phase: 09-trading-optimization
plan: 05
type: execute
wave: 2
depends_on: [9-01]
files_modified:
  - src/v6/strategy_builder/performance_tracker.py
  - src/v6/system_monitor/data/strategy_predictions.py
  - src/v6/data/lake/strategy_predictions (new)
  - config/trading_config.yaml
autonomous: true
user_setup: []

must_haves:
  truths:
    - "Strategy predictions stored at 10 AM with regime metadata"
    - "Actual performance captured at 4 PM (close values)"
    - "Variance analysis compares predicted vs actual by strategy type and regime"
    - "Strategy scoring weights adjusted based on variance feedback"
    - "Delta Lake table stores historical predictions for analysis"
  artifacts:
    - path: "src/v6/system_monitor/data/strategy_predictions.py"
      provides: "Strategy prediction storage and retrieval"
      contains: "class StrategyPredictionsTable, store_prediction(), read_predictions()"
    - path: "data/lake/strategy_predictions"
      provides: "Delta Lake table for prediction tracking"
      contains: "schema: prediction_id, timestamp, symbol, strategy_type, predicted_score, actual_pnl, regime"
    - path: "src/v6/strategy_builder/performance_tracker.py"
      provides: "Variance analysis and weight adjustment"
      contains: "analyze_prediction_variance(), adjust_strategy_weights()"
    - path: "config/trading_config.yaml"
      provides: "Variance analysis configuration"
      contains: "variance_analysis section"
  key_links:
    - from: "src/v6/system_monitor/data/strategy_predictions.py"
      to: "data/lake/strategy_predictions"
      via: "write_deltalake() stores predictions"
      pattern: "strategy_predictions|write_deltalake"
    - from: "src/v6/strategy_builder/performance_tracker.py"
      to: "src/v6/system_monitor/data/strategy_predictions.py"
      via: "PerformanceTracker calls store_prediction() at 10 AM"
      pattern: "store_prediction|StrategyPredictionsTable"
    - from: "src/v6/strategy_builder/strategy_selector.py"
      to: "src/v6/strategy_builder/performance_tracker.py"
      via: "StrategySelector uses adjusted weights from variance analysis"
      pattern: "adjust_strategy_weights|get_strategy_weights"
---

<objective>
Implement prediction vs actual variance analysis to create a feedback loop for
strategy scoring improvement.

Current StrategySelector scores strategies using fixed weights, but there's no
mechanism to learn from actual performance. This plan stores predictions at entry
time (10 AM) and compares against actual results (4 PM close), calculating variance
by strategy type and regime.

Purpose: Continuously improve strategy selection by learning from prediction accuracy.
Output: StrategyPredictionsTable + variance analysis + dynamic weight adjustment.
</objective>

<execution_context>
@/home/bigballs/.claude/get-shit-done/workflows/execute-plan.md
@/home/bigballs/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/09-trading-optimization/9-RESEARCH.md
@.planning/ROADMAP.md
@.planning/STATE.md

@src/v6/strategy_builder/performance_tracker.py
@src/v6/strategy_builder/strategy_selector.py
@src/v6/system_monitor/data/performance_metrics_persistence.py
</context>

<tasks>

<task type="auto">
  <name>Create StrategyPredictionsTable for storing predictions</name>
  <files>src/v6/system_monitor/data/strategy_predictions.py</files>
  <action>
    Create src/v6/system_monitor/data/strategy_predictions.py.

    Implement prediction storage and retrieval:

    ```python
    """
    Strategy Predictions Table

    Stores strategy predictions at entry time and actual results at exit.
    Enables variance analysis for strategy weight tuning.
    """

    from dataclasses import dataclass
    from datetime import datetime, date
    from typing import Optional
    import polars as pl
    from deltalake import write_deltalake
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
            self.table_path = table_path

        def store_prediction(self, prediction: StrategyPrediction) -> None:
            """Store prediction to Delta Lake."""
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
                "actual_pnl_pct": prediction.actual_pnl_pct,
                "actual_pnl": prediction.actual_pnl,
                "exit_time": prediction.exit_time,
                "exit_reason": prediction.exit_reason,
                "prediction_error": prediction.prediction_error,
                "date": prediction.timestamp.date(),
            }])

            write_deltalake(self.table_path, df, mode="append")
            logger.info(f"Stored prediction: {prediction.prediction_id[:8]}...")

        def update_with_actuals(
            self,
            prediction_id: str,
            actual_pnl_pct: float,
            actual_pnl: float,
            exit_time: datetime,
            exit_reason: str,
        ) -> None:
            """Update prediction record with actual results."""
            # Read existing predictions
            df = pl.scan_delta(self.table_path)
                .filter(pl.col("prediction_id") == prediction_id)
                .collect()

            if len(df) == 0:
                logger.warning(f"Prediction {prediction_id[:8]}... not found")
                return

            # Calculate error
            predicted = df.row(0, named=True)["predicted_return_pct"]
            error = predicted - actual_pnl_pct

            # Create updated record
            updated = df.with_columns([
                pl.lit(actual_pnl_pct).alias("actual_pnl_pct"),
                pl.lit(actual_pnl).alias("actual_pnl"),
                pl.lit(exit_time).alias("exit_time"),
                pl.lit(exit_reason).alias("exit_reason"),
                pl.lit(error).alias("prediction_error"),
            ])

            # Overwrite original (Delta Lake time travel keeps history)
            write_deltalake(self.table_path, updated, mode="overwrite")
            logger.debug(f"Updated prediction {prediction_id[:8]}... with actuals")

        def read_predictions(
            self,
            symbol: str = None,
            strategy_type: str = None,
            start_date: date = None,
            end_date: date = None,
            min_predictions: int = 10,
        ) -> pl.DataFrame:
            """
            Read predictions for variance analysis.

            Returns completed predictions (have actual results).
            """
            df = pl.scan_delta(self.table_path)

            if symbol:
                df = df.filter(pl.col("symbol") == symbol)
            if strategy_type:
                df = df.filter(pl.col("strategy_type") == strategy_type)
            if start_date:
                df = df.filter(pl.col("date") >= start_date)
            if end_date:
                df = df.filter(pl.col("date") <= end_date)

            # Only completed predictions
            df = df.filter(pl.col("actual_pnl_pct").is_not_null())

            return df.collect()
    ```

    This provides the storage layer for prediction tracking.
  </action>
  <verify>
    1. StrategyPredictionsTable class exists
    2. store_prediction() method writes to Delta Lake
    3. update_with_actuals() method updates with actual results
    4. read_predictions() returns completed predictions
    5. Schema includes all required fields
  </verify>
  <done>
    StrategyPredictionsTable created with Delta Lake storage, methods for
    storing, updating, and reading predictions with actuals.
  </done>
</task>

<task type="auto">
  <name>Add variance analysis to PerformanceTracker</name>
  <files>src/v6/strategy_builder/performance_tracker.py</files>
  <action>
    Add variance analysis methods to StrategyPerformanceTracker class.

    Add these methods after get_strategy_performance():

    ```python
    from v6.system_monitor.data.strategy_predictions import StrategyPredictionsTable

    class StrategyPerformanceTracker:
        def __init__(self, strategy_id, metrics_writer, metrics_table=None):
            # ... existing init
            self.predictions_table = StrategyPredictionsTable()

        def analyze_prediction_variance(
            self,
            days: int = 30,
            min_predictions: int = 10,
        ) -> dict:
            """
            Analyze prediction variance by strategy type and regime.

            Returns:
                Dict with variance metrics and weight adjustments:
                {
                    "strategy_type": {
                        "mean_absolute_error": float,
                        "mean_squared_error": float,
                        "prediction_count": int,
                        "weight_adjustment": float,  # Multiplier for scoring
                        "by_regime": {
                            "regime_name": {"mae": float, "count": int}
                        }
                    }
                }
            """
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)

            # Read predictions
            df = self.predictions_table.read_predictions(
                start_date=start_date,
                end_date=end_date,
            )

            if len(df) < min_predictions:
                logger.warning(
                    f"Insufficient predictions for variance analysis: "
                    f"{len(df)} < {min_predictions}"
                )
                return {}

            # Group by strategy type
            variance_by_type = {}
            for strategy_type in df["strategy_type"].unique().to_list():
                type_df = df.filter(pl.col("strategy_type") == strategy_type)

                # Calculate metrics
                mae = type_df["prediction_error"].abs().mean()
                mse = (type_df["prediction_error"] ** 2).mean()
                count = len(type_df)

                # Weight adjustment: reduce weight for high error
                # Error 0% -> multiplier 1.0, Error 20% -> multiplier 0.5
                weight_adjustment = max(0.5, 1.0 - min(abs(mae) / 0.40, 0.5))

                # By regime breakdown
                by_regime = {}
                for regime in type_df["regime_at_entry"].unique().to_list():
                    regime_df = type_df.filter(pl.col("regime_at_entry") == regime)
                    by_regime[regime] = {
                        "mae": float(regime_df["prediction_error"].abs().mean()),
                        "count": len(regime_df),
                    }

                variance_by_type[strategy_type] = {
                    "mean_absolute_error": float(mae),
                    "mean_squared_error": float(mse),
                    "prediction_count": count,
                    "weight_adjustment": weight_adjustment,
                    "by_regime": by_regime,
                }

            logger.info(
                f"Variance analysis: {variance_by_type}"
            )

            return variance_by_type

        def get_strategy_weights(self, use_variance_adjustment: bool = True) -> dict:
            """
            Get strategy scoring weights with optional variance adjustment.

            Returns:
                Dict mapping strategy_type to weight multiplier
            """
            # Base weights (equal weighting)
            base_weights = {
                "iron_condor": 1.0,
                "bull_put_spread": 1.0,
                "bear_call_spread": 1.0,
            }

            if not use_variance_adjustment:
                return base_weights

            # Apply variance adjustments
            variance = self.analyze_prediction_variance()

            if not variance:
                return base_weights

            adjusted_weights = {}
            for strategy_type, base_weight in base_weights.items():
                adjustment = variance.get(strategy_type, {}).get("weight_adjustment", 1.0)
                adjusted_weights[strategy_type] = base_weight * adjustment

            logger.info(f"Adjusted strategy weights: {adjusted_weights}")
            return adjusted_weights
    ```

    These methods provide the feedback loop for strategy tuning.
  </action>
  <verify>
    1. analyze_prediction_variance() method exists
    2. Returns dict with MAE, MSE, count, weight_adjustment by strategy type
    3. Breaks down variance by regime
    4. get_strategy_weights() applies variance adjustments
    5. Falls back to base weights if insufficient data
  </verify>
  <done>
    PerformanceTracker has variance analysis, returns weight adjustments,
    get_strategy_weights() provides tuned weights for StrategySelector.
  </done>
</task>

<task type="auto">
  <name>Wire prediction storage into EntryWorkflow</name>
  <files>src/v6/risk_manager/trading_workflows/entry.py</files>
  <action>
    Update EntryWorkflow.execute_entry() to store predictions at entry time.

    Add after strategy is built and validated (around line 303):

    ```python
    from v6.system_monitor.data.strategy_predictions import StrategyPredictionsTable, StrategyPrediction
    import uuid

    class EntryWorkflow:
        def __init__(self, ..., track_predictions: bool = True):
            # ... existing init
            self.track_predictions = track_predictions
            self.predictions_table = StrategyPredictionsTable() if track_predictions else None

        async def execute_entry(self, symbol, strategy_type, params):
            # ... strategy built and validated

            # NEW: Store prediction for variance analysis
            if self.predictions_table and "predicted_score" in strategy.metadata:
                from datetime import date

                # Get regime if available
                regime = params.get("regime", "unknown")
                iv_rank = params.get("iv_rank", 50.0)

                prediction = StrategyPrediction(
                    prediction_id=str(uuid.uuid4()),
                    timestamp=datetime.now(),
                    symbol=symbol,
                    strategy_type=strategy_type.value,
                    predicted_score=strategy.metadata.get("predicted_score", 0.0),
                    predicted_return_pct=strategy.metadata.get("expected_return_pct", 0.0),
                    regime_at_entry=regime,
                    iv_rank_at_entry=iv_rank,
                    dte=params.get("dte", 45),
                    strike_width=strategy.metadata.get("width", 10),
                    entry_price=strategy.metadata.get("entry_price", 0.0),
                )

                self.predictions_table.store_prediction(prediction)

                # Store prediction_id in execution metadata for updating later
                execution.metadata["prediction_id"] = prediction.prediction_id

            # ... continue with order placement
    ```

    This captures predictions at entry for later variance analysis.
  </action>
  <verify>
    1. EntryWorkflow imports StrategyPredictionsTable
    2. track_predictions parameter in __init__
    3. execute_entry() stores prediction after strategy validation
    4. prediction_id stored in execution.metadata
    5. Regime and IV rank captured from params
  </verify>
  <done>
    EntryWorkflow stores predictions at entry time, prediction_id tracked
    in execution metadata for later update with actuals.
  </done>
</task>

<task type="auto">
  <name>Update PositionMonitoringWorkflow to record actuals</name>
  <files>src/v6/risk_manager/trading_workflows/monitoring.py</files>
  <action>
    Update PositionMonitoringWorkflow to update predictions with actual results at exit.

    Add prediction update logic in the exit handling (where exit decisions are executed):

    ```python
    from v6.system_monitor.data.strategy_predictions import StrategyPredictionsTable

    class PositionMonitoringWorkflow:
        def __init__(self, ..., predictions_table: StrategyPredictionsTable = None):
            # ... existing init
            self.predictions_table = predictions_table or StrategyPredictionsTable()

        async def _update_prediction_with_actuals(
            self,
            position_snapshot,
            exit_reason: str,
        ) -> None:
            """Update prediction record with actual P&L."""
            prediction_id = position_snapshot.get("metadata", {}).get("prediction_id")
            if not prediction_id:
                return

            # Calculate actual P&L percentage
            entry_price = position_snapshot.get("entry_price", 0)
            exit_price = position_snapshot.get("current_price", entry_price)
            actual_pnl_pct = (exit_price - entry_price) / entry_price if entry_price > 0 else 0

            # Get actual P&L in dollars
            actual_pnl = position_snapshot.get("unrealized_pnl", 0)

            self.predictions_table.update_with_actuals(
                prediction_id=prediction_id,
                actual_pnl_pct=actual_pnl_pct,
                actual_pnl=actual_pnl,
                exit_time=datetime.now(),
                exit_reason=exit_reason,
            )

            logger.debug(f"Updated prediction {prediction_id[:8]}... with actuals")
    ```

    Call _update_prediction_with_actuals() after executing exit decisions.
  </action>
  <verify>
    1. PositionMonitoringWorkflow has predictions_table
    2. _update_prediction_with_actuals() method exists
    3. Called after exit decision execution
    4. Calculates actual_pnl_pct correctly
    5. prediction_id retrieved from position metadata
  </verify>
  <done>
    PositionMonitoringWorkflow updates predictions with actual results at exit,
    completing the prediction vs actual feedback loop.
  </done>
</task>

<task type="auto">
  <name>Add variance analysis configuration to trading_config.yaml</name>
  <files>config/trading_config.yaml</files>
  <action>
    Add variance_analysis section to trading_config.yaml.

    Add to existing config/trading_config.yaml:

    ```yaml
    # Variance Analysis Configuration
    variance_analysis:
      enabled: true
      lookback_days: 30              # Days of predictions to analyze
      min_predictions: 10            # Minimum predictions required for analysis
      weight_adjustment_factor: 0.5  # Max weight reduction for high error (0-1)

      # Strategy-specific overrides
      strategy_weights:
        iron_condor: 1.0             # Base weight for Iron Condor
        bull_put_spread: 1.0         # Base weight for Bull Put Spread
        bear_call_spread: 1.0        # Base weight for Bear Call Spread

      # Regime-specific adjustments
      regime_adjustments:
        high_volatility: 0.8         # Reduce weights in high vol
        crash: 0.5                   # Reduce weights significantly in crash
    ```

    This allows tuning of variance analysis behavior without code changes.
  </action>
  <verify>
    1. variance_analysis section exists in trading_config.yaml
    2. enabled, lookback_days, min_predictions fields present
    3. strategy_weights section with base weights
    4. regime_adjustments section defined
    5. YAML is valid (parses correctly)
  </verify>
  <done>
    trading_config.yaml has variance_analysis section with configurable
    parameters for feedback loop tuning.
  </done>
</task>

</tasks>

<verification>
Overall phase checks:
1. Python syntax check: python -m py_compile src/v6/system_monitor/data/strategy_predictions.py
2. Python syntax check: python -m py_compile src/v6/strategy_builder/performance_tracker.py
3. Import test: python -c "from v6.system_monitor.data.strategy_predictions import StrategyPredictionsTable"
4. Verify analyze_prediction_variance() method exists
5. Verify trading_config.yaml has variance_analysis section
</verification>

<success_criteria>
1. StrategyPredictionsTable stores predictions with regime metadata
2. Predictions updated with actual results at position exit
3. Variance analysis calculates MAE/MSE by strategy type and regime
4. StrategySelector uses variance-adjusted weights (via get_strategy_weights)
5. trading_config.yaml allows variance analysis tuning
6. Feedback loop completes: prediction -> actual -> variance -> adjusted weights
</success_criteria>

<output>
After completion, create `.planning/phases/09-trading-optimization/9-05-SUMMARY.md`
</output>
