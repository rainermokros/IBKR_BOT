"""
Test Suite for Strategy Selector Dashboard Component

Tests the Streamlit dashboard visualization for regime-aware strategy selection.
Uses mocking to avoid Streamlit runtime dependencies.

Key test scenarios:
- Display current regime with color coding
- Display strategy rankings table
- Display recommended strategy details
- Display regime performance heatmap
- Error handling for missing data
"""

from datetime import datetime, timedelta, date
from unittest.mock import MagicMock, Mock, patch

import pytest
import polars as pl

from v6.system_monitor.dashboard.components.strategy_selector import StrategySelectorDashboard
from v6.strategies.regime_aware_selector import (
    RegimeAwareSelector,
    RegimeDetector,
    StrategyRanking,
    StrategyRecommendation,
)
from v6.strategies.performance_tracker import StrategyPerformanceTracker
from v6.strategies.models import Strategy, LegSpec, OptionRight, LegAction, StrategyType
from v6.system_monitor.data.market_regimes_persistence import MarketRegimesTable


@pytest.fixture
def mock_regime_selector():
    """Create mock RegimeAwareSelector."""
    selector = MagicMock(spec=RegimeAwareSelector)

    # Mock rank_strategies_for_regime
    selector.rank_strategies_for_regime.return_value = [
        StrategyRanking(
            strategy_name='iron_condor',
            score=0.75,
            win_rate=0.65,
            avg_pnl=150.0,
            trade_count=45
        ),
        StrategyRanking(
            strategy_name='put_spread',
            score=0.68,
            win_rate=0.60,
            avg_pnl=120.0,
            trade_count=38
        ),
        StrategyRanking(
            strategy_name='call_spread',
            score=0.62,
            win_rate=0.58,
            avg_pnl=100.0,
            trade_count=32
        ),
    ]

    # Mock get_recommended_strategy
    # Create future expiration date
    future_expiry = (datetime.now() + timedelta(days=35)).date()

    strategy = Strategy(
        strategy_id='test-strategy-123',
        symbol='SPY',
        strategy_type=StrategyType.IRON_CONDOR,
        legs=[
            LegSpec(
                right=OptionRight.PUT,
                strike=380.0,
                quantity=1,
                action=LegAction.BUY,
                expiration=future_expiry,
                price=0.0
            ),
            LegSpec(
                right=OptionRight.PUT,
                strike=390.0,
                quantity=1,
                action=LegAction.SELL,
                expiration=future_expiry,
                price=0.0
            ),
            LegSpec(
                right=OptionRight.CALL,
                strike=410.0,
                quantity=1,
                action=LegAction.SELL,
                expiration=future_expiry,
                price=0.0
            ),
            LegSpec(
                right=OptionRight.CALL,
                strike=420.0,
                quantity=1,
                action=LegAction.BUY,
                expiration=future_expiry,
                price=0.0
            ),
        ],
        entry_time=datetime.now(),
        metadata={
            'template': 'IronCondorTemplate',
            'params': {'wing_width': 10.0, 'DTE': 35}
        }
    )

    selector.get_recommended_strategy.return_value = StrategyRecommendation(
        strategy=strategy,
        template_name='iron_condor',
        regime='neutral',
        confidence=0.85,
        estimated_risk_reward=(250.0, 750.0),
        ranking=StrategyRanking(
            strategy_name='iron_condor',
            score=0.75,
            win_rate=0.65,
            avg_pnl=150.0,
            trade_count=45
        )
    )

    # Mock DEFAULT_REGIME_MAPPING
    selector.DEFAULT_REGIME_MAPPING = {
        'bullish': 'call_spread',
        'bearish': 'put_spread',
        'neutral': 'iron_condor',
        'volatile': 'iron_condor',
    }

    return selector


@pytest.fixture
def mock_regime_detector():
    """Create mock RegimeDetector."""
    detector = MagicMock(spec=RegimeDetector)

    # Mock detect_current_regime
    from v6.strategies.regime_aware_selector import RegimeDetection

    detector.detect_current_regime.return_value = RegimeDetection(
        regime='neutral',
        confidence=0.85,
        indicators={
            'es_trend': 0.3,
            'nq_trend': 0.2,
            'rty_trend': 0.1,
            'vix': 18.5,
            'spy_ma_ratio': 1.005,
        },
        timestamp=datetime.now()
    )

    return detector


@pytest.fixture
def mock_performance_tracker():
    """Create mock StrategyPerformanceTracker."""
    tracker = MagicMock(spec=StrategyPerformanceTracker)

    # Mock get_regime_performance
    tracker.get_regime_performance.return_value = {
        'total_trades': 45,
        'win_rate': 0.65,
        'avg_realized_pnl': 150.0,
        'total_realized_pnl': 6750.0,
        'avg_hold_duration': 1440.0,  # 1 day
        'pnl_by_exit_reason': {
            'expiry': {'count': 30, 'total_pnl': 5000.0, 'avg_pnl': 166.67},
            'stop_loss': {'count': 5, 'total_pnl': -1000.0, 'avg_pnl': -200.0},
        },
        'max_drawdown': 500.0,
    }

    return tracker


@pytest.fixture
def mock_regime_table():
    """Create mock MarketRegimesTable with sample data."""
    table = MagicMock(spec=MarketRegimesTable)

    # Mock get_table() to return DeltaTable with sample data
    mock_dt = MagicMock()

    # Create sample regime data
    sample_data = {
        'timestamp': [datetime.now() - timedelta(hours=i) for i in range(24, 0, -1)],
        'regime': ['neutral'] * 12 + ['bullish'] * 8 + ['volatile'] * 4,
        'confidence': [0.7 + i * 0.01 for i in range(24)],
        'es_trend': [0.1 + i * 0.05 for i in range(24)],
        'nq_trend': [0.2 + i * 0.03 for i in range(24)],
        'rty_trend': [0.05 + i * 0.02 for i in range(24)],
        'vix': [18.0 + i * 0.5 for i in range(24)],
        'spy_ma_ratio': [1.0 + i * 0.001 for i in range(24)],
        'metadata': ['{}'] * 24,
    }

    sample_df = pl.DataFrame(sample_data)

    # Mock DeltaTable behavior
    mock_dt.to_pandas.return_value = sample_df.to_pandas()

    table.get_table.return_value = mock_dt

    return table


@pytest.fixture
def dashboard(mock_regime_selector, mock_regime_detector, mock_performance_tracker, mock_regime_table):
    """Create StrategySelectorDashboard instance with mocks."""
    return StrategySelectorDashboard(
        regime_selector=mock_regime_selector,
        regime_detector=mock_regime_detector,
        performance_tracker=mock_performance_tracker,
        regime_table=mock_regime_table
    )


class TestStrategySelectorDashboardInitialization:
    """Test dashboard initialization."""

    def test_init_with_all_dependencies(self, mock_regime_selector, mock_regime_detector):
        """Test initialization with all dependencies."""
        tracker = MagicMock(spec=StrategyPerformanceTracker)
        table = MagicMock(spec=MarketRegimesTable)

        dashboard = StrategySelectorDashboard(
            regime_selector=mock_regime_selector,
            regime_detector=mock_regime_detector,
            performance_tracker=tracker,
            regime_table=table
        )

        assert dashboard.selector == mock_regime_selector
        assert dashboard.detector == mock_regime_detector
        assert dashboard.tracker == tracker
        assert dashboard.table == table

    def test_init_with_minimal_dependencies(self, mock_regime_selector):
        """Test initialization with only required dependencies."""
        dashboard = StrategySelectorDashboard(
            regime_selector=mock_regime_selector,
            regime_detector=None,
            performance_tracker=None,
            regime_table=None
        )

        assert dashboard.selector == mock_regime_selector
        assert dashboard.detector is None
        assert dashboard.tracker is None
        assert dashboard.table is not None  # Should create default table

    def test_regime_colors_mapping(self, dashboard):
        """Test regime color scheme."""
        colors = dashboard.REGIME_COLORS

        assert colors['bullish'] == '#00C853'  # Green
        assert colors['bearish'] == '#D32F2F'  # Red
        assert colors['neutral'] == '#757575'  # Gray
        assert colors['volatile'] == '#FF6D00'  # Orange

    def test_strategy_names_mapping(self, dashboard):
        """Test strategy display names."""
        names = dashboard.STRATEGY_NAMES

        assert names['iron_condor'] == 'Iron Condor'
        assert names['call_spread'] == 'Call Spread'
        assert names['put_spread'] == 'Put Spread'
        assert names['wheel'] == 'Wheel'


class TestDisplayCurrentRegime:
    """Test current regime display functionality."""

    @patch('v6.dashboard.components.strategy_selector.st')
    def test_display_current_regime_with_data(self, mock_st, dashboard, mock_regime_table):
        """Test displaying current regime with valid data."""
        # Mock st.columns to return column mocks
        mock_col1 = MagicMock()
        mock_col2 = MagicMock()
        mock_col3 = MagicMock()
        mock_st.columns.return_value = [mock_col1, mock_col2, mock_col3]

        dashboard.display_current_regime()

        # Verify Streamlit calls
        assert mock_st.subheader.called
        assert mock_st.markdown.called
        assert mock_st.metric.called
        assert mock_st.columns.called

    @patch('v6.dashboard.components.strategy_selector.st')
    def test_display_current_regime_no_data(self, mock_st, mock_regime_selector):
        """Test displaying current regime when no data available."""
        # Create empty table
        empty_table = MagicMock(spec=MarketRegimesTable)
        empty_reader = MagicMock()
        empty_reader.read_latest_regime.return_value = None

        empty_table.get_table.return_value = MagicMock()
        empty_dt = MagicMock()
        empty_dt.to_pandas.return_value = pl.DataFrame().to_pandas()
        empty_table.get_table.return_value = empty_dt

        # Patch RegimeReader to return empty data
        with patch('v6.dashboard.components.strategy_selector.RegimeReader', return_value=empty_reader):
            dashboard = StrategySelectorDashboard(
                regime_selector=mock_regime_selector,
                regime_table=empty_table
            )

            dashboard.display_current_regime()

            # Verify warning displayed
            assert mock_st.warning.called

    @patch('v6.dashboard.components.strategy_selector.st')
    def test_display_regime_history_chart(self, mock_st, dashboard):
        """Test regime history chart display."""
        dashboard._display_regime_history_chart()

        # Verify chart section created
        assert mock_st.markdown.called


class TestDisplayStrategyRankings:
    """Test strategy rankings display functionality."""

    @patch('v6.dashboard.components.strategy_selector.st')
    @patch('asyncio.run')
    def test_display_strategy_rankings_with_data(
        self, mock_asyncio, mock_st, dashboard, mock_regime_selector
    ):
        """Test displaying strategy rankings with valid data."""
        mock_asyncio.return_value = mock_regime_selector.rank_strategies_for_regime.return_value

        dashboard.display_strategy_rankings('SPY', 'neutral')

        # Verify Streamlit calls
        assert mock_st.subheader.called
        assert mock_st.dataframe.called

    @patch('v6.dashboard.components.strategy_selector.st')
    @patch('asyncio.run')
    def test_display_strategy_rankings_empty_rankings(
        self, mock_asyncio, mock_st, mock_regime_selector
    ):
        """Test displaying strategy rankings when no historical data."""
        # Mock empty rankings
        mock_regime_selector.rank_strategies_for_regime.return_value = []
        mock_asyncio.return_value = []

        dashboard = StrategySelectorDashboard(
            regime_selector=mock_regime_selector
        )

        dashboard.display_strategy_rankings('SPY', 'neutral')

        # Verify default mapping shown
        # Note: info may not be called if regime is provided directly
        assert mock_st.markdown.called

    @patch('v6.dashboard.components.strategy_selector.st')
    @patch('asyncio.run')
    def test_display_strategy_rankings_auto_detect_regime(
        self, mock_asyncio, mock_st, dashboard, mock_regime_detector, mock_regime_selector
    ):
        """Test auto-detecting regime when not provided."""
        # Mock regime detection
        from v6.strategies.regime_aware_selector import RegimeDetection

        # First call: detect regime, Second call: get rankings
        mock_asyncio.side_effect = [
            RegimeDetection(
                regime='bullish',
                confidence=0.8,
                indicators={},
                timestamp=datetime.now()
            ),
            mock_regime_selector.rank_strategies_for_regime.return_value
        ]

        dashboard.display_strategy_rankings('SPY')  # No regime provided

        # Verify detection triggered
        assert mock_st.info.called
        assert mock_st.success.called

    @patch('v6.dashboard.components.strategy_selector.st')
    def test_display_trade_distribution(self, mock_st, dashboard, mock_performance_tracker):
        """Test trade distribution by regime display."""
        dashboard._display_trade_distribution('SPY')

        # Verify metrics displayed
        assert mock_st.markdown.called
        assert mock_st.columns.called


class TestDisplayRecommendedStrategy:
    """Test recommended strategy display functionality."""

    @patch('v6.dashboard.components.strategy_selector.st')
    @patch('asyncio.run')
    def test_display_recommended_strategy_success(
        self, mock_asyncio, mock_st, dashboard, mock_regime_selector
    ):
        """Test displaying recommended strategy successfully."""
        # Mock st.columns to return column mocks
        mock_col1 = MagicMock()
        mock_col2 = MagicMock()
        mock_st.columns.return_value = [mock_col1, mock_col2]

        mock_asyncio.return_value = mock_regime_selector.get_recommended_strategy.return_value

        dashboard.display_recommended_strategy('SPY', 5000.0)

        # Verify all components displayed
        assert mock_st.subheader.called
        assert mock_st.markdown.called
        assert mock_st.metric.called
        assert mock_st.button.called

    @patch('v6.dashboard.components.strategy_selector.st')
    @patch('asyncio.run')
    def test_display_recommended_strategy_with_custom_params(
        self, mock_asyncio, mock_st, dashboard, mock_regime_selector
    ):
        """Test displaying recommended strategy with custom parameters."""
        # Mock st.columns to return column mocks
        mock_col1 = MagicMock()
        mock_col2 = MagicMock()
        mock_st.columns.return_value = [mock_col1, mock_col2]

        mock_asyncio.return_value = mock_regime_selector.get_recommended_strategy.return_value

        custom_params = {'wing_width': 15.0, 'DTE': 45}
        dashboard.display_recommended_strategy('SPY', 5000.0, params=custom_params)

        # Verify recommendation shown
        assert mock_st.subheader.called

    @patch('v6.dashboard.components.strategy_selector.st')
    @patch('asyncio.run')
    def test_display_recommended_strategy_error(
        self, mock_asyncio, mock_st, mock_regime_selector
    ):
        """Test error handling when recommendation fails."""
        # Mock error
        mock_asyncio.side_effect = Exception("Test error")

        dashboard = StrategySelectorDashboard(
            regime_selector=mock_regime_selector
        )

        dashboard.display_recommended_strategy('SPY', 5000.0)

        # Verify error displayed
        assert mock_st.error.called

    @patch('v6.dashboard.components.strategy_selector.st')
    @patch('asyncio.run')
    def test_display_strategy_details_expansion(
        self, mock_asyncio, mock_st, dashboard, mock_regime_selector
    ):
        """Test strategy details expansion panel."""
        # Mock st.columns to return column mocks
        mock_col1 = MagicMock()
        mock_col2 = MagicMock()
        mock_col3 = MagicMock()
        mock_st.columns.return_value = [mock_col1, mock_col2, mock_col3]

        mock_asyncio.return_value = mock_regime_selector.get_recommended_strategy.return_value

        # Mock button to return True (simulate click)
        mock_st.button.return_value = True

        dashboard.display_recommended_strategy('SPY', 5000.0)

        # Verify success message and expander shown
        assert mock_st.success.called
        assert mock_st.expander.called
        assert mock_st.json.called


class TestDisplayRegimePerformanceComparison:
    """Test regime performance comparison display."""

    @patch('v6.dashboard.components.strategy_selector.st')
    def test_display_regime_performance_comparison_with_tracker(
        self, mock_st, dashboard
    ):
        """Test displaying performance heatmap with tracker."""
        dashboard.display_regime_performance_comparison('SPY')

        # Verify heatmap displayed
        assert mock_st.subheader.called
        assert mock_st.dataframe.called
        assert mock_st.markdown.called

    @patch('v6.dashboard.components.strategy_selector.st')
    def test_display_regime_performance_comparison_no_tracker(
        self, mock_st, mock_regime_selector
    ):
        """Test displaying performance comparison without tracker."""
        dashboard = StrategySelectorDashboard(
            regime_selector=mock_regime_selector,
            performance_tracker=None
        )

        dashboard.display_regime_performance_comparison('SPY')

        # Verify warning shown
        assert mock_st.warning.called


class TestDisplayFullDashboard:
    """Test complete dashboard display."""

    @patch('v6.dashboard.components.strategy_selector.st')
    def test_display_full_dashboard(self, mock_st, dashboard):
        """Test displaying complete dashboard."""
        # Mock all display methods to avoid side effects
        dashboard.display_current_regime = Mock()
        dashboard.display_strategy_rankings = Mock()
        dashboard.display_recommended_strategy = Mock()
        dashboard.display_regime_performance_comparison = Mock()

        dashboard.display_full_dashboard('SPY', 5000.0)

        # Verify title and description
        assert mock_st.title.called
        assert mock_st.markdown.called

        # Verify all components called
        dashboard.display_current_regime.assert_called_once()
        dashboard.display_strategy_rankings.assert_called_once()
        dashboard.display_recommended_strategy.assert_called_once()
        dashboard.display_regime_performance_comparison.assert_called_once()

    @patch('v6.dashboard.components.strategy_selector.st')
    def test_display_full_dashboard_with_custom_params(self, mock_st, dashboard):
        """Test displaying dashboard with custom parameters."""
        # Mock all display methods
        dashboard.display_current_regime = Mock()
        dashboard.display_strategy_rankings = Mock()
        dashboard.display_recommended_strategy = Mock()
        dashboard.display_regime_performance_comparison = Mock()

        custom_params = {'wing_width': 20.0, 'delta_target': 0.15}
        dashboard.display_full_dashboard('SPY', 5000.0, params=custom_params)

        # Verify recommendation called with params
        dashboard.display_recommended_strategy.assert_called_once_with(
            'SPY', 5000.0, custom_params
        )


class TestErrorHandling:
    """Test error handling in dashboard."""

    @patch('v6.dashboard.components.strategy_selector.st')
    def test_regime_history_error_handling(self, mock_st, mock_regime_selector):
        """Test error handling in regime history display."""
        # Create table that raises error
        error_table = MagicMock(spec=MarketRegimesTable)
        error_table.get_table.side_effect = Exception("Database error")

        dashboard = StrategySelectorDashboard(
            regime_selector=mock_regime_selector,
            regime_table=error_table
        )

        dashboard._display_regime_history_chart()

        # Verify error handled (no exception raised)
        # May log error or show warning

    @patch('v6.dashboard.components.strategy_selector.st')
    def test_trade_distribution_error_handling(
        self, mock_st, mock_regime_selector, mock_performance_tracker
    ):
        """Test error handling in trade distribution display."""
        # Mock tracker to raise error
        mock_performance_tracker.get_regime_performance.side_effect = Exception("Performance error")

        dashboard = StrategySelectorDashboard(
            regime_selector=mock_regime_selector,
            performance_tracker=mock_performance_tracker
        )

        dashboard._display_trade_distribution('SPY')

        # Verify error handled without exception
        # Should show warning or skip display


class TestIntegration:
    """Integration tests for dashboard components."""

    @patch('v6.dashboard.components.strategy_selector.st')
    @patch('asyncio.run')
    def test_full_workflow_integration(
        self, mock_asyncio, mock_st, dashboard, mock_regime_selector
    ):
        """Test complete workflow from regime detection to recommendation."""
        # Mock st.columns to return column mocks
        mock_col1 = MagicMock()
        mock_col2 = MagicMock()
        mock_col3 = MagicMock()
        mock_st.columns.return_value = [mock_col1, mock_col2, mock_col3]

        # Mock async operations
        mock_asyncio.side_effect = [
            mock_regime_selector.rank_strategies_for_regime.return_value,
            mock_regime_selector.get_recommended_strategy.return_value
        ]

        # Display components in sequence
        dashboard.display_current_regime()
        dashboard.display_strategy_rankings('SPY', 'neutral')
        dashboard.display_recommended_strategy('SPY', 5000.0)
        dashboard.display_regime_performance_comparison('SPY')

        # Verify all components displayed successfully
        assert mock_st.subheader.call_count >= 3  # Multiple subheaders
        assert mock_st.markdown.called
