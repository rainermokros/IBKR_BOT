"""
Test suite for RegimeAwareSelector class.

Tests strategy ranking by regime, regime-based recommendations, and parameter adjustments.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from v6.strategies.regime_aware_selector import (
    RegimeAwareSelector,
    StrategyRanking,
    StrategyRecommendation,
)
from v6.strategies.performance_tracker import StrategyPerformanceTracker
from v6.strategies.strategy_templates import (
    IronCondorTemplate,
    CallSpreadTemplate,
    PutSpreadTemplate,
    WheelTemplate,
    get_registry,
)


@pytest.fixture
def mock_performance_tracker():
    """Create mock StrategyPerformanceTracker."""
    tracker = MagicMock(spec=StrategyPerformanceTracker)
    tracker.get_regime_performance = MagicMock()
    return tracker


@pytest.fixture
def mock_regime_detector():
    """Create mock RegimeDetector."""
    detector = MagicMock()
    detector.detect_current_regime = AsyncMock()
    return detector


@pytest.fixture
def regime_aware_selector(mock_performance_tracker, mock_regime_detector):
    """Create RegimeAwareSelector instance."""
    # Register templates for testing (if not already registered)
    registry = get_registry()

    templates = {
        'iron_condor': IronCondorTemplate,
        'call_spread': CallSpreadTemplate,
        'put_spread': PutSpreadTemplate,
        'wheel': WheelTemplate
    }

    for name, template_class in templates.items():
        try:
            registry.register_template(name, template_class)
        except ValueError:
            # Template already registered - skip
            pass

    return RegimeAwareSelector(
        performance_tracker=mock_performance_tracker,
        regime_detector=mock_regime_detector
    )


@pytest.fixture
def sample_regime_performance():
    """Create sample regime performance data."""
    return {
        'total_trades': 50,
        'win_rate': 0.65,
        'avg_realized_pnl': 150.0,
        'total_realized_pnl': 7500.0,
        'avg_hold_duration': 120.0,
        'pnl_by_exit_reason': {
            'expiry': {'count': 30, 'total_pnl': 5000.0, 'avg_pnl': 166.67},
            'take_profit': {'count': 15, 'total_pnl': 2500.0, 'avg_pnl': 166.67}
        },
        'max_drawdown': -300.0
    }


class TestStrategyRanking:
    """Test strategy ranking by historical regime performance."""

    @pytest.mark.asyncio
    async def test_rank_strategies_for_regime(
        self,
        regime_aware_selector,
        mock_performance_tracker,
        sample_regime_performance
    ):
        """Test ranking strategies by historical performance in regime."""
        # Mock performance data
        mock_performance_tracker.get_regime_performance.return_value = sample_regime_performance

        # Rank strategies for bullish regime
        rankings = await regime_aware_selector.rank_strategies_for_regime('bullish', 'SPY')

        # Verify rankings returned
        assert isinstance(rankings, list)
        assert len(rankings) > 0

        # Verify rankings are sorted by score (descending)
        scores = [r.score for r in rankings]
        assert scores == sorted(scores, reverse=True)

        # Verify ranking structure
        for ranking in rankings:
            assert isinstance(ranking, StrategyRanking)
            assert hasattr(ranking, 'strategy_name')
            assert hasattr(ranking, 'score')
            assert hasattr(ranking, 'win_rate')
            assert hasattr(ranking, 'avg_pnl')
            assert hasattr(ranking, 'trade_count')

    @pytest.mark.asyncio
    async def test_rank_strategies_filters_low_sample_size(
        self,
        regime_aware_selector,
        mock_performance_tracker
    ):
        """Test that strategies with insufficient trades are filtered out."""
        # Mock low sample size
        mock_performance_tracker.get_regime_performance.return_value = {
            'total_trades': 5,  # Below MIN_SAMPLE_SIZE (10)
            'win_rate': 0.6,
            'avg_realized_pnl': 100.0
        }

        rankings = await regime_aware_selector.rank_strategies_for_regime('neutral', 'SPY')

        # Should return empty list (insufficient data)
        assert len(rankings) == 0

    @pytest.mark.asyncio
    async def test_rank_strategies_no_historical_data(
        self,
        regime_aware_selector,
        mock_performance_tracker
    ):
        """Test ranking when no historical data available."""
        # Mock no trades
        mock_performance_tracker.get_regime_performance.return_value = {
            'total_trades': 0,
            'win_rate': 0.0,
            'avg_realized_pnl': 0.0
        }

        rankings = await regime_aware_selector.rank_strategies_for_regime('volatile', 'SPY')

        # Should return empty list
        assert len(rankings) == 0

    @pytest.mark.asyncio
    async def test_ranking_score_calculation(
        self,
        regime_aware_selector,
        mock_performance_tracker
    ):
        """Test score formula: (win_rate * 0.6) + (avg_pnl / max_possible_pnl * 0.4)."""
        # Mock performance data
        mock_performance_tracker.get_regime_performance.return_value = {
            'total_trades': 20,
            'win_rate': 0.70,  # 70% win rate
            'avg_realized_pnl': 200.0  # $200 per trade
        }

        rankings = await regime_aware_selector.rank_strategies_for_regime('bullish', 'SPY')

        # Verify score calculation
        # Expected: (0.70 * 0.6) + (200/1000 * 0.4) = 0.42 + 0.08 = 0.50
        expected_score = (0.70 * 0.6) + (200.0 / 1000.0 * 0.4)

        assert len(rankings) > 0
        assert rankings[0].score == pytest.approx(expected_score, rel=0.01)


class TestRegimeBasedRecommendation:
    """Test regime-based strategy recommendations."""

    @pytest.mark.asyncio
    async def test_get_recommended_strategy_with_historical_data(
        self,
        regime_aware_selector,
        mock_performance_tracker,
        mock_regime_detector,
        sample_regime_performance
    ):
        """Test getting recommended strategy using historical performance."""
        # Mock regime detection
        mock_regime_detector.detect_current_regime.return_value = MagicMock(
            regime='bullish',
            confidence=0.9
        )

        # Mock performance data
        mock_performance_tracker.get_regime_performance.return_value = sample_regime_performance

        # Get recommendation - with full params to avoid template errors
        from datetime import date
        params = {
            'short_put_strike': 470.0,
            'short_call_strike': 480.0,
            'long_put_strike': 465.0,
            'long_call_strike': 485.0,
            'expiry': date.today() + timedelta(days=35),
            'quantity': 1
        }

        recommendation = await regime_aware_selector.get_recommended_strategy(
            symbol='SPY',
            capital_available=5000.0,
            params=params
        )

        # Verify recommendation structure
        assert isinstance(recommendation, StrategyRecommendation)
        assert hasattr(recommendation, 'strategy')
        assert hasattr(recommendation, 'template_name')
        assert hasattr(recommendation, 'regime')
        assert hasattr(recommendation, 'confidence')
        assert hasattr(recommendation, 'estimated_risk_reward')
        assert hasattr(recommendation, 'ranking')

        # Verify regime detected
        assert recommendation.regime == 'bullish'

        # Verify strategy created
        assert recommendation.strategy is not None

    @pytest.mark.asyncio
    async def test_get_recommended_strategy_default_fallback(
        self,
        regime_aware_selector,
        mock_performance_tracker,
        mock_regime_detector
    ):
        """Test default strategy mapping when no historical data."""
        # Mock regime detection
        mock_regime_detector.detect_current_regime.return_value = MagicMock(
            regime='bearish',
            confidence=0.7
        )

        # Mock no historical data
        mock_performance_tracker.get_regime_performance.return_value = {
            'total_trades': 0,
            'win_rate': 0.0,
            'avg_realized_pnl': 0.0
        }

        # Get recommendation
        recommendation = await regime_aware_selector.get_recommended_strategy(
            symbol='SPY',
            capital_available=5000.0
        )

        # Verify default mapping used (bearish -> put_spread)
        assert recommendation.template_name == 'put_spread'
        assert recommendation.regime == 'bearish'

    @pytest.mark.asyncio
    async def test_get_recommended_strategy_capital_validation(
        self,
        regime_aware_selector,
        mock_performance_tracker,
        mock_regime_detector,
        sample_regime_performance
    ):
        """Test that strategy validates against available capital."""
        # Mock regime detection
        mock_regime_detector.detect_current_regime.return_value = MagicMock(
            regime='neutral',
            confidence=0.8
        )

        # Mock performance data
        mock_performance_tracker.get_regime_performance.return_value = sample_regime_performance

        # Get recommendation with insufficient capital
        with pytest.raises(ValueError, match="exceeds available capital"):
            await regime_aware_selector.get_recommended_strategy(
                symbol='SPY',
                capital_available=50.0  # Too low
            )

    @pytest.mark.asyncio
    async def test_get_recommended_strategy_with_explicit_regime(
        self,
        regime_aware_selector,
        mock_performance_tracker,
        sample_regime_performance
    ):
        """Test recommendation with explicitly provided regime (no auto-detection)."""
        # Mock performance data
        mock_performance_tracker.get_regime_performance.return_value = sample_regime_performance

        # Get recommendation with explicit regime
        recommendation = await regime_aware_selector.get_recommended_strategy(
            symbol='SPY',
            capital_available=5000.0,
            current_regime='volatile'
        )

        # Verify explicit regime used
        assert recommendation.regime == 'volatile'
        assert recommendation.confidence == 1.0  # High confidence when provided

        # Verify detector NOT called (regime provided)
        mock_regime_detector = regime_aware_selector.detector
        if mock_regime_detector:
            mock_regime_detector.detect_current_regime.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_recommended_strategy_without_detector_raises_error(
        self,
        mock_performance_tracker
    ):
        """Test that missing detector and no regime raises ValueError."""
        # Create selector without detector
        selector = RegimeAwareSelector(
            performance_tracker=mock_performance_tracker,
            regime_detector=None
        )

        # Try to get recommendation without regime
        with pytest.raises(ValueError, match="RegimeDetector not initialized"):
            await selector.get_recommended_strategy(
                symbol='SPY',
                capital_available=5000.0
            )


class TestRegimeParameterAdjustment:
    """Test regime-adjusted parameter optimization."""

    def test_volatile_regime_adjusts_wing_width(self, regime_aware_selector):
        """Test volatile regime increases wing width by 1.5x."""
        base_params = {
            'wing_width': 10.0,
            'delta_target': 0.20,
            'quantity': 1
        }

        adjusted = regime_aware_selector.get_regime_adjusted_params(
            template_name='iron_condor',
            current_regime='volatile',
            base_params=base_params
        )

        # Verify wing width increased
        assert adjusted['wing_width'] == 15.0  # 10.0 * 1.5

        # Verify delta target decreased (farther OTM)
        assert adjusted['delta_target'] == 0.14  # 0.20 * 0.7

    def test_neutral_regime_standard_params(self, regime_aware_selector):
        """Test neutral regime uses standard parameters."""
        base_params = {
            'wing_width': 10.0,
            'delta_target': 0.25,
            'quantity': 1
        }

        adjusted = regime_aware_selector.get_regime_adjusted_params(
            template_name='iron_condor',
            current_regime='neutral',
            base_params=base_params
        )

        # Verify delta target set to standard
        assert adjusted['delta_target'] == 0.20

    def test_bullish_regime_adjusts_call_spread(self, regime_aware_selector):
        """Test bullish regime increases call spread delta (closer ITM)."""
        base_params = {
            'spread_width': 5.0,
            'delta_target': 0.30,
            'quantity': 1
        }

        adjusted = regime_aware_selector.get_regime_adjusted_params(
            template_name='call_spread',
            current_regime='bullish',
            base_params=base_params
        )

        # Verify delta target increased for bullish call spread
        assert adjusted['delta_target'] == 0.36  # 0.30 * 1.2

    def test_bullish_regime_adjusts_put_spread(self, regime_aware_selector):
        """Test bullish regime decreases put spread delta (farther OTM)."""
        base_params = {
            'spread_width': 5.0,
            'delta_target': 0.25,
            'quantity': 1
        }

        adjusted = regime_aware_selector.get_regime_adjusted_params(
            template_name='put_spread',
            current_regime='bullish',
            base_params=base_params
        )

        # Verify delta target decreased for bullish put spread
        assert adjusted['delta_target'] == 0.20  # 0.25 * 0.8

    def test_bearish_regime_adjusts_put_spread(self, regime_aware_selector):
        """Test bearish regime increases put spread delta (closer ITM)."""
        base_params = {
            'spread_width': 5.0,
            'delta_target': 0.25,
            'quantity': 1
        }

        adjusted = regime_aware_selector.get_regime_adjusted_params(
            template_name='put_spread',
            current_regime='bearish',
            base_params=base_params
        )

        # Verify delta target increased for bearish put spread
        assert adjusted['delta_target'] == 0.30  # 0.25 * 1.2

    def test_bearish_regime_adjusts_call_spread(self, regime_aware_selector):
        """Test bearish regime decreases call spread delta (farther OTM)."""
        base_params = {
            'spread_width': 5.0,
            'delta_target': 0.30,
            'quantity': 1
        }

        adjusted = regime_aware_selector.get_regime_adjusted_params(
            template_name='call_spread',
            current_regime='bearish',
            base_params=base_params
        )

        # Verify delta target decreased for bearish call spread
        assert adjusted['delta_target'] == 0.24  # 0.30 * 0.8

    def test_adjustment_preserves_other_params(self, regime_aware_selector):
        """Test that adjustment preserves non-adjusted parameters."""
        base_params = {
            'wing_width': 10.0,
            'quantity': 2,
            'DTE': 35,
            'min_wing_width': 5.0
        }

        adjusted = regime_aware_selector.get_regime_adjusted_params(
            template_name='iron_condor',
            current_regime='volatile',
            base_params=base_params
        )

        # Verify other params preserved
        assert adjusted['quantity'] == 2
        assert adjusted['DTE'] == 35
        assert adjusted['min_wing_width'] == 5.0


class TestDefaultRegimeMapping:
    """Test default strategy fallback mapping."""

    def test_bullish_default_mapping(self, regime_aware_selector):
        """Test bullish regime defaults to call_spread."""
        assert RegimeAwareSelector.DEFAULT_REGIME_MAPPING['bullish'] == 'call_spread'

    def test_bearish_default_mapping(self, regime_aware_selector):
        """Test bearish regime defaults to put_spread."""
        assert RegimeAwareSelector.DEFAULT_REGIME_MAPPING['bearish'] == 'put_spread'

    def test_neutral_default_mapping(self, regime_aware_selector):
        """Test neutral regime defaults to iron_condor."""
        assert RegimeAwareSelector.DEFAULT_REGIME_MAPPING['neutral'] == 'iron_condor'

    def test_volatile_default_mapping(self, regime_aware_selector):
        """Test volatile regime defaults to iron_condor."""
        assert RegimeAwareSelector.DEFAULT_REGIME_MAPPING['volatile'] == 'iron_condor'
