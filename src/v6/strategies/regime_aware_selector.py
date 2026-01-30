"""
Regime-Aware Strategy Selection Module

Provides market regime detection and regime-aware strategy selection.
Integrates with futures data, market regimes table, strategy templates, and performance tracker.

Key patterns:
- RegimeDetector: Detect market regime from futures indicators
- RegimeAwareSelector: Rank strategies by historical regime performance
- Regime-adjusted parameters: Optimize strategy params for current regime
- Integration: market_regimes table, strategy templates, performance tracker
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import polars as pl
from loguru import logger

from v6.core.futures_fetcher import FuturesFetcher, FuturesSnapshot
from v6.data.market_regimes_persistence import (
    MarketRegime,
    MarketRegimesTable,
    RegimeReader,
    RegimeWriter,
)
from v6.strategies.performance_tracker import StrategyPerformanceTracker
from v6.strategies.strategy_templates import (
    StrategyTemplate,
    StrategyTemplateRegistry,
    get_registry,
)
from v6.strategies.models import Strategy


@dataclass
class RegimeDetection:
    """
    Market regime detection result.

    Attributes:
        regime: Regime type ('bullish', 'bearish', 'neutral', 'volatile')
        confidence: Confidence score (0.0-1.0)
        indicators: Dictionary of indicator values used for detection
        timestamp: Detection timestamp
    """
    regime: str
    confidence: float
    indicators: Dict[str, Any]
    timestamp: datetime

    def __repr__(self) -> str:
        """Return string representation of regime detection."""
        return (
            f"RegimeDetection(regime={self.regime}, confidence={self.confidence:.2f}, "
            f"timestamp={self.timestamp})"
        )


@dataclass
class StrategyRanking:
    """
    Strategy ranking result.

    Attributes:
        strategy_name: Strategy template name (e.g., 'iron_condor')
        score: Composite score (0.0-1.0)
        win_rate: Historical win rate in this regime
        avg_pnl: Average realized P&L per trade
        trade_count: Number of trades in sample
    """
    strategy_name: str
    score: float
    win_rate: float
    avg_pnl: float
    trade_count: int

    def __repr__(self) -> str:
        """Return string representation of strategy ranking."""
        return (
            f"StrategyRanking({self.strategy_name}, score={self.score:.2f}, "
            f"win_rate={self.win_rate:.2f}, trades={self.trade_count})"
        )


@dataclass
class StrategyRecommendation:
    """
    Strategy recommendation result.

    Attributes:
        strategy: Strategy object
        template_name: Template name used
        regime: Current market regime
        confidence: Regime detection confidence
        estimated_risk_reward: (max_profit, max_loss) tuple
        ranking: Strategy ranking info
    """
    strategy: Strategy
    template_name: str
    regime: str
    confidence: float
    estimated_risk_reward: Tuple[float, float]
    ranking: Optional[StrategyRanking] = None

    def __repr__(self) -> str:
        """Return string representation of strategy recommendation."""
        return (
            f"StrategyRecommendation(template={self.template_name}, regime={self.regime}, "
            f"confidence={self.confidence:.2f}, risk_reward={self.estimated_risk_reward})"
        )


class RegimeDetector:
    """
    Market regime detection engine.

    Detects current market regime from futures indicators (ES, NQ, RTY trends),
    VIX levels, and SPY moving average ratio.

    Regime types:
    - Bullish: All futures positive, SPY ratio > 1.02, VIX < 20
    - Bearish: All futures negative, SPY ratio < 0.98, VIX > 25
    - Volatile: VIX > 30 OR any futures move > 2% in 1h
    - Neutral: Everything else

    Confidence scoring based on indicator alignment.
    """

    # Default regime thresholds
    BULLISH_VIX_THRESHOLD = 20.0
    BEARISH_VIX_THRESHOLD = 25.0
    VOLATILE_VIX_THRESHOLD = 30.0
    VOLATILE_FUTURES_MOVE_PCT = 2.0

    # SPY moving average ratio thresholds
    BULLISH_SPY_MA_RATIO = 1.02
    BEARISH_SPY_MA_RATIO = 0.98

    def __init__(
        self,
        futures_fetcher: FuturesFetcher,
        regime_writer: Optional[RegimeWriter] = None,
        regime_table: Optional[MarketRegimesTable] = None,
        create_writer_if_missing: bool = False
    ):
        """
        Initialize regime detector.

        Args:
            futures_fetcher: FuturesFetcher instance for ES, NQ, RTY data
            regime_writer: Optional RegimeWriter for storing regime detections
            regime_table: Optional MarketRegimesTable (created if not provided)
            create_writer_if_missing: Auto-create writer from table (default: False)
        """
        self.futures_fetcher = futures_fetcher
        self.writer = regime_writer
        self.table = regime_table or MarketRegimesTable()

        if self.writer is None and create_writer_if_missing and self.table:
            # Create writer if explicitly requested
            self.writer = RegimeWriter(self.table)

        logger.info("✓ RegimeDetector initialized")

    async def detect_current_regime(
        self,
        spy_price: Optional[float] = None,
        spy_ma_20: Optional[float] = None,
        vix: Optional[float] = None
    ) -> RegimeDetection:
        """
        Detect current market regime from futures data.

        Args:
            spy_price: Optional current SPY price (for MA ratio calculation)
            spy_ma_20: Optional SPY 20-day moving average
            vix: Optional VIX level (uses implied vol from futures if not provided)

        Returns:
            RegimeDetection with regime, confidence, and indicators

        Raises:
            ConnectionError: If futures fetcher not connected
            ValueError: If futures data unavailable
        """
        # Fetch futures snapshots for ES, NQ, RTY
        snapshots = await self.futures_fetcher.get_all_snapshots()

        if not snapshots:
            raise ValueError("No futures data available for regime detection")

        # Extract trend indicators (1-hour change)
        es_trend = self._extract_trend(snapshots.get('ES'))
        nq_trend = self._extract_trend(snapshots.get('NQ'))
        rty_trend = self._extract_trend(snapshots.get('RTY'))

        if es_trend is None and nq_trend is None and rty_trend is None:
            raise ValueError("No trend data available in futures snapshots")

        # Calculate SPY MA ratio
        spy_ma_ratio = None
        if spy_price and spy_ma_20 and spy_ma_20 > 0:
            spy_ma_ratio = spy_price / spy_ma_20

        # Use VIX if provided, otherwise use implied vol from futures
        if vix is None:
            # Try to get implied vol from any futures snapshot
            for snapshot in snapshots.values():
                if snapshot and snapshot.implied_vol:
                    vix = snapshot.implied_vol
                    break

        # Detect regime based on rules
        regime, confidence = self._determine_regime(
            es_trend, nq_trend, rty_trend,
            spy_ma_ratio, vix
        )

        # Build indicators dict
        indicators = {
            'es_trend': es_trend,
            'nq_trend': nq_trend,
            'rty_trend': rty_trend,
            'vix': vix,
            'spy_ma_ratio': spy_ma_ratio,
        }

        detection = RegimeDetection(
            regime=regime,
            confidence=confidence,
            indicators=indicators,
            timestamp=datetime.now()
        )

        # Format trends for logging
        es_str = f"{es_trend:.2f}%" if es_trend is not None else "N/A"
        nq_str = f"{nq_trend:.2f}%" if nq_trend is not None else "N/A"
        rty_str = f"{rty_trend:.2f}%" if rty_trend is not None else "N/A"

        logger.info(
            f"✓ Detected regime: {regime} (confidence: {confidence:.2f}, "
            f"ES: {es_str}, NQ: {nq_str}, RTY: {rty_str})"
        )

        return detection

    def _extract_trend(self, snapshot: Optional[FuturesSnapshot]) -> Optional[float]:
        """
        Extract 1-hour trend from futures snapshot.

        Args:
            snapshot: FuturesSnapshot or None

        Returns:
            1-hour trend percentage or None
        """
        if snapshot is None:
            return None

        # Prefer change_1h, fallback to change_4h, etc.
        if snapshot.change_1h is not None:
            return snapshot.change_1h
        elif snapshot.change_4h is not None:
            return snapshot.change_4h
        elif snapshot.change_overnight is not None:
            return snapshot.change_overnight
        elif snapshot.change_daily is not None:
            return snapshot.change_daily
        else:
            return None

    def _determine_regime(
        self,
        es_trend: Optional[float],
        nq_trend: Optional[float],
        rty_trend: Optional[float],
        spy_ma_ratio: Optional[float],
        vix: Optional[float]
    ) -> Tuple[str, float]:
        """
        Determine regime and confidence from indicators.

        Args:
            es_trend: ES futures trend (%)
            nq_trend: NQ futures trend (%)
            rty_trend: RTY futures trend (%)
            spy_ma_ratio: SPY price / MA_20 ratio
            vix: VIX level

        Returns:
            Tuple of (regime, confidence)
        """
        # Count available indicators
        available_trends = [t for t in [es_trend, nq_trend, rty_trend] if t is not None]

        if not available_trends:
            # No trend data - return neutral with low confidence
            return 'neutral', 0.2

        # Check for volatile regime (highest priority)
        if vix and vix > self.VOLATILE_VIX_THRESHOLD:
            return 'volatile', 0.8

        # Check if any futures moved > VOLATILE_FUTURES_MOVE_PCT
        for trend in available_trends:
            if abs(trend) > self.VOLATILE_FUTURES_MOVE_PCT:
                return 'volatile', 0.7

        # Check bullish regime
        bullish_indicators = 0
        if es_trend and es_trend > 0:
            bullish_indicators += 1
        if nq_trend and nq_trend > 0:
            bullish_indicators += 1
        if rty_trend and rty_trend > 0:
            bullish_indicators += 1
        if spy_ma_ratio and spy_ma_ratio > self.BULLISH_SPY_MA_RATIO:
            bullish_indicators += 1
        if vix and vix < self.BULLISH_VIX_THRESHOLD:
            bullish_indicators += 1

        # Check bearish regime
        bearish_indicators = 0
        if es_trend and es_trend < 0:
            bearish_indicators += 1
        if nq_trend and nq_trend < 0:
            bearish_indicators += 1
        if rty_trend and rty_trend < 0:
            bearish_indicators += 1
        if spy_ma_ratio and spy_ma_ratio < self.BEARISH_SPY_MA_RATIO:
            bearish_indicators += 1
        if vix and vix > self.BEARISH_VIX_THRESHOLD:
            bearish_indicators += 1

        # Determine regime based on indicator counts
        total_indicators = 5  # Max possible indicators

        if bullish_indicators >= 4:
            # Strong bullish
            return 'bullish', 0.9
        elif bullish_indicators >= 3:
            # Moderate bullish
            return 'bullish', 0.7
        elif bearish_indicators >= 4:
            # Strong bearish
            return 'bearish', 0.9
        elif bearish_indicators >= 3:
            # Moderate bearish
            return 'bearish', 0.7
        elif bullish_indicators == bearish_indicators:
            # Mixed signals - neutral
            return 'neutral', 0.5
        elif bullish_indicators > bearish_indicators:
            # Leaning bullish
            return 'bullish', 0.6
        else:
            # Leaning bearish
            return 'bearish', 0.6

    async def store_regime(self, detection: RegimeDetection) -> None:
        """
        Store regime detection to market_regimes table.

        Args:
            detection: RegimeDetection result

        Raises:
            ValueError: If writer not initialized
        """
        # Check if writer exists
        if self.writer is None:
            raise ValueError("RegimeWriter not initialized - cannot store regime")

        # Create MarketRegime dataclass
        regime = MarketRegime(
            timestamp=detection.timestamp,
            regime=detection.regime,
            confidence=detection.confidence,
            es_trend=detection.indicators.get('es_trend', 0.0),
            nq_trend=detection.indicators.get('nq_trend', 0.0),
            rty_trend=detection.indicators.get('rty_trend', 0.0),
            vix=detection.indicators.get('vix'),
            spy_ma_ratio=detection.indicators.get('spy_ma_ratio'),
            metadata=detection.indicators
        )

        # Write to table
        await self.writer.on_regime(regime)

        logger.info(f"✓ Stored regime: {detection.regime} at {detection.timestamp}")

    def get_regime_history(
        self,
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """
        Get regime history for last N hours.

        Args:
            hours: Number of hours to look back

        Returns:
            List of regime state dictionaries with timestamps
        """
        reader = RegimeReader(self.table)

        end = datetime.now()
        start = end - timedelta(hours=hours)

        df = reader.read_time_range(start, end)

        if len(df) == 0:
            return []

        # Convert to list of dicts
        history = df.to_dicts()

        logger.debug(f"Retrieved {len(history)} regime records for last {hours}h")

        return history


class RegimeAwareSelector:
    """
    Regime-aware strategy selection engine.

    Ranks strategies by historical performance in current market regime,
    provides regime-adjusted parameter recommendations, and generates
    optimal strategies for current conditions.

    Integration points:
    - StrategyPerformanceTracker: Get historical regime performance
    - StrategyTemplateRegistry: Create strategies from templates
    - RegimeDetector: Detect current market regime
    """

    # Minimum sample size for regime-specific statistics
    MIN_SAMPLE_SIZE = 10

    # Default strategy mapping when no historical data available
    DEFAULT_REGIME_MAPPING = {
        'bullish': 'call_spread',      # Debit call spread for upside
        'bearish': 'put_spread',       # Credit put spread for downside
        'neutral': 'iron_condor',      # Theta decay from both sides
        'volatile': 'iron_condor',     # Wide wings or wheel if high IV
    }

    def __init__(
        self,
        performance_tracker: StrategyPerformanceTracker,
        template_registry: Optional[StrategyTemplateRegistry] = None,
        regime_detector: Optional[RegimeDetector] = None
    ):
        """
        Initialize regime-aware selector.

        Args:
            performance_tracker: StrategyPerformanceTracker for historical data
            template_registry: Optional StrategyTemplateRegistry (uses global if None)
            regime_detector: Optional RegimeDetector for regime detection
        """
        self.performance_tracker = performance_tracker
        self.registry = template_registry or get_registry()
        self.detector = regime_detector

        logger.info("✓ RegimeAwareSelector initialized")

    async def rank_strategies_for_regime(
        self,
        current_regime: str,
        symbol: str
    ) -> List[StrategyRanking]:
        """
        Rank strategies by historical performance in current regime.

        Args:
            current_regime: Market regime ('bullish', 'bearish', 'neutral', 'volatile')
            symbol: Underlying symbol

        Returns:
            List of StrategyRanking sorted by score (descending)

        Note:
            Score formula: (win_rate * 0.6) + (avg_pnl / max_possible_pnl * 0.4)
            Filters to strategies with >= MIN_SAMPLE_SIZE trades in regime
        """
        # Get regime performance from tracker
        regime_perf = self.performance_tracker.get_regime_performance(current_regime)

        if regime_perf['total_trades'] == 0:
            # No historical data
            logger.warning(f"No historical performance data for regime: {current_regime}")
            return []

        # Get list of available templates
        available_templates = self.registry.list_templates()

        rankings = []

        # For each strategy template, calculate score
        for template_name in available_templates:
            # TODO: Get strategy-specific performance when tracker supports it
            # For now, use overall regime performance as placeholder

            # Placeholder: Generate mock performance data per strategy
            # In production, would query performance_metrics by strategy_id
            win_rate = regime_perf.get('win_rate', 0.5)
            avg_pnl = regime_perf.get('avg_realized_pnl', 0.0)
            trade_count = regime_perf.get('total_trades', 0)

            if trade_count < self.MIN_SAMPLE_SIZE:
                # Skip strategies with insufficient data
                continue

            # Normalize PnL to 0-1 range (assume max possible PnL = $1000 per trade)
            max_possible_pnl = 1000.0
            normalized_pnl = max(0, min(1, avg_pnl / max_possible_pnl))

            # Calculate composite score
            score = (win_rate * 0.6) + (normalized_pnl * 0.4)

            ranking = StrategyRanking(
                strategy_name=template_name,
                score=score,
                win_rate=win_rate,
                avg_pnl=avg_pnl,
                trade_count=trade_count
            )

            rankings.append(ranking)

        # Sort by score descending
        rankings.sort(key=lambda r: r.score, reverse=True)

        logger.info(
            f"✓ Ranked {len(rankings)} strategies for {current_regime} regime: "
            f"{[r.strategy_name for r in rankings[:3]]}"
        )

        return rankings

    async def get_recommended_strategy(
        self,
        symbol: str,
        capital_available: float,
        params: Optional[Dict[str, Any]] = None,
        current_regime: Optional[str] = None
    ) -> StrategyRecommendation:
        """
        Get recommended strategy for current market regime.

        Args:
            symbol: Underlying symbol
            capital_available: Available capital for trade
            params: Optional strategy parameters (uses defaults if None)
            current_regime: Optional current regime (auto-detects if None)

        Returns:
            StrategyRecommendation with strategy and metadata

        Raises:
            ValueError: If strategy creation fails or capital insufficient
        """
        # Detect current regime if not provided
        if current_regime is None:
            if self.detector is None:
                raise ValueError("RegimeDetector not initialized - cannot auto-detect regime")

            detection = await self.detector.detect_current_regime()
            current_regime = detection.regime
            regime_confidence = detection.confidence
        else:
            regime_confidence = 1.0  # Assume high confidence if provided

        # Rank strategies for regime
        rankings = await self.rank_strategies_for_regime(current_regime, symbol)

        # Select top strategy or use default fallback
        if rankings:
            top_ranking = rankings[0]
            template_name = top_ranking.strategy_name
            ranking = top_ranking

            logger.info(
                f"✓ Using historical data: {template_name} ranked #{1} "
                f"(score: {top_ranking.score:.2f})"
            )
        else:
            # No historical data - use default mapping
            template_name = self.DEFAULT_REGIME_MAPPING.get(current_regime, 'iron_condor')
            ranking = None

            logger.info(
                f"✓ Using default mapping: {template_name} for {current_regime} regime"
            )

        # Get regime-adjusted parameters
        if params is None:
            # Get template defaults and adjust for regime
            template = self.registry.get_template(template_name)
            base_params = template.get_default_params()
            adjusted_params = self.get_regime_adjusted_params(
                template_name, current_regime, base_params
            )
        else:
            # Use provided params and adjust for regime
            adjusted_params = self.get_regime_adjusted_params(
                template_name, current_regime, params
            )

        # Create strategy from template
        try:
            strategy = self.registry.create_strategy(
                template_name=template_name,
                symbol=symbol,
                direction=current_regime,  # Use regime as direction hint
                params=adjusted_params
            )
        except Exception as e:
            raise ValueError(f"Failed to create strategy from template '{template_name}': {e}")

        # Estimate risk/reward
        template = self.registry.get_template(template_name)
        max_profit, max_loss = template.estimate_risk_reward(adjusted_params)

        # Validate strategy fits capital
        if max_loss > capital_available:
            raise ValueError(
                f"Strategy max loss (${max_loss:.2f}) exceeds available capital "
                f"(${capital_available:.2f})"
            )

        recommendation = StrategyRecommendation(
            strategy=strategy,
            template_name=template_name,
            regime=current_regime,
            confidence=regime_confidence,
            estimated_risk_reward=(max_profit, max_loss),
            ranking=ranking
        )

        logger.info(
            f"✓ Recommended {template_name} for {symbol}: "
            f"max_profit=${max_profit:.2f}, max_loss=${max_loss:.2f}"
        )

        return recommendation

    def get_regime_adjusted_params(
        self,
        template_name: str,
        current_regime: str,
        base_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Adjust strategy parameters based on regime characteristics.

        Args:
            template_name: Strategy template name
            current_regime: Current market regime
            base_params: Base parameters from template defaults

        Returns:
            Adjusted parameters dict

        Adjustments:
        - Volatile regime: increase wing_width by 1.5x, use farther OTM strikes
        - Neutral regime: use standard wing_width, target delta 0.20
        - Bullish regime: for calls, use closer ITM; for puts, use farther OTM
        - Bearish regime: for puts, use closer ITM; for calls, use farther OTM
        """
        adjusted = base_params.copy()

        if current_regime == 'volatile':
            # Increase wing width for safety
            if 'wing_width' in adjusted:
                adjusted['wing_width'] = adjusted['wing_width'] * 1.5
                logger.debug(f"Adjusted wing_width for volatile regime: {adjusted['wing_width']:.2f}")

            # Use farther OTM strikes (lower delta target)
            if 'delta_target' in adjusted:
                adjusted['delta_target'] = adjusted['delta_target'] * 0.7
                logger.debug(f"Adjusted delta_target for volatile regime: {adjusted['delta_target']:.3f}")

        elif current_regime == 'neutral':
            # Use standard parameters (no adjustment needed)
            if 'delta_target' in adjusted:
                adjusted['delta_target'] = 0.20  # Standard neutral delta
                logger.debug(f"Set delta_target for neutral regime: {adjusted['delta_target']:.3f}")

        elif current_regime == 'bullish':
            # For call spreads: use closer ITM (higher delta)
            if template_name == 'call_spread' and 'delta_target' in adjusted:
                adjusted['delta_target'] = adjusted['delta_target'] * 1.2
                logger.debug(f"Adjusted delta_target for bullish call spread: {adjusted['delta_target']:.3f}")

            # For put spreads: use farther OTM (lower delta)
            if template_name == 'put_spread' and 'delta_target' in adjusted:
                adjusted['delta_target'] = adjusted['delta_target'] * 0.8
                logger.debug(f"Adjusted delta_target for bullish put spread: {adjusted['delta_target']:.3f}")

        elif current_regime == 'bearish':
            # For put spreads: use closer ITM (higher delta)
            if template_name == 'put_spread' and 'delta_target' in adjusted:
                adjusted['delta_target'] = adjusted['delta_target'] * 1.2
                logger.debug(f"Adjusted delta_target for bearish put spread: {adjusted['delta_target']:.3f}")

            # For call spreads: use farther OTM (lower delta)
            if template_name == 'call_spread' and 'delta_target' in adjusted:
                adjusted['delta_target'] = adjusted['delta_target'] * 0.8
                logger.debug(f"Adjusted delta_target for bearish call spread: {adjusted['delta_target']:.3f}")

        return adjusted
