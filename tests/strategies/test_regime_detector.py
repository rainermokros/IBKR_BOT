"""
Test suite for RegimeDetector class.

Tests regime detection from futures indicators with confidence scoring.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from v6.core.futures_fetcher import FuturesSnapshot
from v6.strategies.regime_aware_selector import RegimeDetector, RegimeDetection


@pytest.fixture
def mock_futures_fetcher():
    """Create mock FuturesFetcher."""
    fetcher = MagicMock()
    fetcher.get_all_snapshots = AsyncMock()
    return fetcher


@pytest.fixture
def mock_regime_writer():
    """Create mock RegimeWriter."""
    writer = MagicMock()
    writer.on_regime = AsyncMock()
    return writer


@pytest.fixture
def regime_detector(mock_futures_fetcher, mock_regime_writer):
    """Create RegimeDetector instance."""
    return RegimeDetector(
        futures_fetcher=mock_futures_fetcher,
        regime_writer=mock_regime_writer
    )


class TestRegimeDetection:
    """Test regime detection logic."""

    @pytest.mark.asyncio
    async def test_bullish_regime_detection(self, regime_detector, mock_futures_fetcher):
        """Test bullish regime detection (all futures positive, SPY ratio > 1.02, VIX < 20)."""
        # Mock bullish futures data
        mock_futures_fetcher.get_all_snapshots.return_value = {
            'ES': FuturesSnapshot(
                symbol='ES',
                timestamp=datetime.now(),
                bid=5000.0,
                ask=5000.5,
                last=5000.25,
                volume=1000000,
                change_1h=0.8,  # Positive
                change_4h=1.2,
                change_overnight=0.5,
                change_daily=1.5
            ),
            'NQ': FuturesSnapshot(
                symbol='NQ',
                timestamp=datetime.now(),
                bid=18000.0,
                ask=18000.5,
                last=18000.25,
                volume=500000,
                change_1h=0.9,  # Positive
                change_4h=1.5,
                change_overnight=0.6,
                change_daily=1.8
            ),
            'RTY': FuturesSnapshot(
                symbol='RTY',
                timestamp=datetime.now(),
                bid=2100.0,
                ask=2100.5,
                last=2100.25,
                volume=300000,
                change_1h=0.7,  # Positive
                change_4h=1.1,
                change_overnight=0.4,
                change_daily=1.3
            )
        }

        # Detect regime
        detection = await regime_detector.detect_current_regime(
            spy_price=500.0,
            spy_ma_20=485.0,  # Ratio = 1.03 > 1.02
            vix=18.0  # < 20
        )

        # Verify bullish regime with high confidence
        assert detection.regime == 'bullish'
        assert detection.confidence >= 0.8
        assert detection.indicators['es_trend'] == 0.8
        assert detection.indicators['nq_trend'] == 0.9
        assert detection.indicators['rty_trend'] == 0.7
        assert detection.indicators['spy_ma_ratio'] == pytest.approx(1.03, rel=0.01)
        assert detection.indicators['vix'] == 18.0

    @pytest.mark.asyncio
    async def test_bearish_regime_detection(self, regime_detector, mock_futures_fetcher):
        """Test bearish regime detection (all futures negative, SPY ratio < 0.98, VIX > 25)."""
        # Mock bearish futures data
        mock_futures_fetcher.get_all_snapshots.return_value = {
            'ES': FuturesSnapshot(
                symbol='ES',
                timestamp=datetime.now(),
                bid=5000.0,
                ask=5000.5,
                last=5000.25,
                volume=1000000,
                change_1h=-0.8,  # Negative
                change_4h=-1.2,
                change_overnight=-0.5,
                change_daily=-1.5
            ),
            'NQ': FuturesSnapshot(
                symbol='NQ',
                timestamp=datetime.now(),
                bid=18000.0,
                ask=18000.5,
                last=18000.25,
                volume=500000,
                change_1h=-0.9,  # Negative
                change_4h=-1.5,
                change_overnight=-0.6,
                change_daily=-1.8
            ),
            'RTY': FuturesSnapshot(
                symbol='RTY',
                timestamp=datetime.now(),
                bid=2100.0,
                ask=2100.5,
                last=2100.25,
                volume=300000,
                change_1h=-0.7,  # Negative
                change_4h=-1.1,
                change_overnight=-0.4,
                change_daily=-1.3
            )
        }

        # Detect regime
        detection = await regime_detector.detect_current_regime(
            spy_price=480.0,
            spy_ma_20=490.0,  # Ratio = 0.98 < 0.98
            vix=26.0  # > 25
        )

        # Verify bearish regime with high confidence
        assert detection.regime == 'bearish'
        assert detection.confidence >= 0.8
        assert detection.indicators['es_trend'] == -0.8
        assert detection.indicators['nq_trend'] == -0.9
        assert detection.indicators['rty_trend'] == -0.7
        assert detection.indicators['spy_ma_ratio'] == pytest.approx(0.98, rel=0.01)
        assert detection.indicators['vix'] == 26.0

    @pytest.mark.asyncio
    async def test_volatile_regime_detection_high_vix(self, regime_detector, mock_futures_fetcher):
        """Test volatile regime detection (VIX > 30)."""
        # Mock futures data with high VIX
        mock_futures_fetcher.get_all_snapshots.return_value = {
            'ES': FuturesSnapshot(
                symbol='ES',
                timestamp=datetime.now(),
                bid=5000.0,
                ask=5000.5,
                last=5000.25,
                volume=1000000,
                change_1h=0.3,
                change_4h=0.5,
                implied_vol=32.0  # VIX > 30
            ),
        }

        # Detect regime
        detection = await regime_detector.detect_current_regime(vix=32.0)

        # Verify volatile regime
        assert detection.regime == 'volatile'
        assert detection.confidence >= 0.7

    @pytest.mark.asyncio
    async def test_volatile_regime_detection_large_move(self, regime_detector, mock_futures_fetcher):
        """Test volatile regime detection (any futures move > 2%)."""
        # Mock futures data with large move
        mock_futures_fetcher.get_all_snapshots.return_value = {
            'ES': FuturesSnapshot(
                symbol='ES',
                timestamp=datetime.now(),
                bid=5000.0,
                ask=5000.5,
                last=5000.25,
                volume=1000000,
                change_1h=2.5,  # > 2%
                change_4h=3.0,
                implied_vol=22.0
            ),
        }

        # Detect regime
        detection = await regime_detector.detect_current_regime(vix=22.0)

        # Verify volatile regime
        assert detection.regime == 'volatile'
        assert detection.confidence >= 0.6

    @pytest.mark.asyncio
    async def test_neutral_regime_detection(self, regime_detector, mock_futures_fetcher):
        """Test neutral regime detection (mixed signals)."""
        # Mock mixed futures data
        mock_futures_fetcher.get_all_snapshots.return_value = {
            'ES': FuturesSnapshot(
                symbol='ES',
                timestamp=datetime.now(),
                bid=5000.0,
                ask=5000.5,
                last=5000.25,
                volume=1000000,
                change_1h=0.2,  # Slightly positive
                change_4h=0.3
            ),
            'NQ': FuturesSnapshot(
                symbol='NQ',
                timestamp=datetime.now(),
                bid=18000.0,
                ask=18000.5,
                last=18000.25,
                volume=500000,
                change_1h=-0.1,  # Slightly negative
                change_4h=-0.2
            ),
        }

        # Detect regime
        detection = await regime_detector.detect_current_regime(
            spy_price=490.0,
            spy_ma_20=490.0,  # Ratio = 1.0 (neutral)
            vix=22.0  # Between thresholds
        )

        # Verify neutral regime
        assert detection.regime == 'neutral'
        assert detection.confidence >= 0.4

    @pytest.mark.asyncio
    async def test_confidence_calculation(self, regime_detector, mock_futures_fetcher):
        """Test confidence score calculation based on indicator alignment."""
        # Test strong agreement (all indicators aligned)
        mock_futures_fetcher.get_all_snapshots.return_value = {
            'ES': FuturesSnapshot(
                symbol='ES',
                timestamp=datetime.now(),
                bid=5000.0,
                ask=5000.5,
                last=5000.25,
                volume=1000000,
                change_1h=1.0,
                implied_vol=15.0
            ),
            'NQ': FuturesSnapshot(
                symbol='NQ',
                timestamp=datetime.now(),
                bid=18000.0,
                ask=18000.5,
                last=18000.25,
                volume=500000,
                change_1h=1.2,
                implied_vol=15.0
            ),
            'RTY': FuturesSnapshot(
                symbol='RTY',
                timestamp=datetime.now(),
                bid=2100.0,
                ask=2100.5,
                last=2100.25,
                volume=300000,
                change_1h=0.9,
                implied_vol=15.0
            )
        }

        detection = await regime_detector.detect_current_regime(
            spy_price=505.0,
            spy_ma_20=490.0,
            vix=15.0
        )

        # Strong agreement should yield high confidence
        assert detection.confidence >= 0.8

    @pytest.mark.asyncio
    async def test_no_futures_data_raises_error(self, regime_detector, mock_futures_fetcher):
        """Test that missing futures data raises ValueError."""
        mock_futures_fetcher.get_all_snapshots.return_value = {}

        with pytest.raises(ValueError, match="No futures data available"):
            await regime_detector.detect_current_regime()

    @pytest.mark.asyncio
    async def test_extract_trend_fallback(self, regime_detector, mock_futures_fetcher):
        """Test trend extraction falls back to alternative time windows."""
        # Mock data with only 4h change
        mock_futures_fetcher.get_all_snapshots.return_value = {
            'ES': FuturesSnapshot(
                symbol='ES',
                timestamp=datetime.now(),
                bid=5000.0,
                ask=5000.5,
                last=5000.25,
                volume=1000000,
                change_1h=None,  # Missing
                change_4h=1.5,  # Use this
                change_overnight=1.0,
                change_daily=2.0
            ),
        }

        detection = await regime_detector.detect_current_regime()

        # Should use 4h trend as fallback
        assert detection.indicators['es_trend'] == 1.5


class TestRegimeStorage:
    """Test regime storage to market_regimes table."""

    @pytest.mark.asyncio
    async def test_store_regime(self, regime_detector, mock_regime_writer):
        """Test storing regime detection to Delta Lake."""
        detection = RegimeDetection(
            regime='bullish',
            confidence=0.9,
            indicators={
                'es_trend': 1.0,
                'nq_trend': 1.2,
                'rty_trend': 0.8,
                'vix': 18.0,
                'spy_ma_ratio': 1.03
            },
            timestamp=datetime.now()
        )

        # Store regime
        await regime_detector.store_regime(detection)

        # Verify writer was called
        mock_regime_writer.on_regime.assert_called_once()

        # Verify stored data
        call_args = mock_regime_writer.on_regime.call_args[0][0]
        assert call_args.regime == 'bullish'
        assert call_args.confidence == 0.9
        assert call_args.es_trend == 1.0

    @pytest.mark.asyncio
    async def test_store_regime_without_writer_raises_error(self, mock_futures_fetcher):
        """Test that storing without writer raises ValueError."""
        detector = RegimeDetector(
            futures_fetcher=mock_futures_fetcher,
            regime_writer=None,
            create_writer_if_missing=False  # Don't auto-create
        )

        detection = RegimeDetection(
            regime='bullish',
            confidence=0.9,
            indicators={},
            timestamp=datetime.now()
        )

        with pytest.raises(ValueError, match="RegimeWriter not initialized"):
            await detector.store_regime(detection)


class TestRegimeHistory:
    """Test regime history retrieval."""

    def test_get_regime_history(self, regime_detector):
        """Test retrieving regime history for last N hours."""
        # This test requires actual Delta Lake table with data
        # For now, just verify method exists and doesn't crash
        history = regime_detector.get_regime_history(hours=24)

        # Should return list (empty if no data)
        assert isinstance(history, list)

    def test_get_regime_history_custom_hours(self, regime_detector):
        """Test retrieving regime history with custom time window."""
        history = regime_detector.get_regime_history(hours=12)

        # Should return list
        assert isinstance(history, list)
