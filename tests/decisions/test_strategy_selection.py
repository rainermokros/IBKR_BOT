"""
Tests for Strategy Selection Matrix

Tests the complete options strategy selection based on market outlook and IV level:
- Bullish + High IV
- Bullish + Low IV
- Bearish + High IV
- Bearish + Low IV
- Neutral + High IV
- Neutral + Low IV
"""

import pytest
from datetime import datetime, timedelta

from src.v6.decisions.market_regime import (
    IVLevel,
    MarketOutlook,
    MarketRegime,
    MarketRegimeDetector,
    VolTrend,
)
from src.v6.decisions.rules.entry_rules import (
    BearishHighIVEntry,
    BearishLowIVEntry,
    BullishHighIVEntry,
    BullishLowIVEntry,
    NeutralHighIVEntry,
    NeutralLowIVEntry,
)
from src.v6.decisions.models import DecisionAction, Urgency
from src.v6.strategies.models import StrategyType


class TestMarketRegimeDetection:
    """Test market regime detection."""

    @pytest.mark.asyncio
    async def test_bullish_high_iv_detection(self):
        """Test detection of bullish market with high IV."""
        detector = MarketRegimeDetector()

        # Simulate bullish high IV regime
        regime = await detector.detect_regime(
            symbol="SPY",
            current_iv_rank=65.0,  # High IV
            current_vix=28.0,
            underlying_price=480.0,
            historical_data=None,
        )

        assert regime.symbol == "SPY"
        assert regime.outlook == MarketOutlook.BULLISH
        assert regime.iv_level == IVLevel.HIGH
        assert regime.iv_rank == 65.0
        assert regime.vol_trend in [VolTrend.RISING, VolTrend.STABLE]

    @pytest.mark.asyncio
    async def test_bearish_low_iv_detection(self):
        """Test detection of bearish market with low IV."""
        detector = MarketRegimeDetector()

        regime = await detector.detect_regime(
            symbol="QQQ",
            current_iv_rank=30.0,  # Low IV
            current_vix=14.0,
            underlying_price=440.0,
            historical_data=None,
        )

        assert regime.symbol == "QQQ"
        assert regime.outlook == MarketOutlook.BEARISH
        assert regime.iv_level == IVLevel.LOW
        assert regime.iv_rank == 30.0

    @pytest.mark.asyncio
    async def test_neutral_extreme_iv_detection(self):
        """Test detection of neutral market with extreme IV."""
        detector = MarketRegimeDetector()

        regime = await detector.detect_regime(
            symbol="IWM",
            current_iv_rank=78.0,  # Extreme IV
            current_vix=35.0,
            underlying_price=180.0,
            historical_data=None,
        )

        assert regime.symbol == "IWM"
        assert regime.outlook == MarketOutlook.NEUTRAL
        assert regime.iv_level == IVLevel.EXTREME


class TestBullishHighIVEntry:
    """Test bullish + high IV entry decisions."""

    @pytest.mark.asyncio
    async def test_bullish_high_iv_triggers_entry(self):
        """Test that bullish + high IV triggers entry."""
        rule = BullishHighIVEntry()

        market_data = {
            "symbol": "SPY",
            "outlook": MarketOutlook.BULLISH.value,
            "iv_level": IVLevel.HIGH.value,
            "vol_trend": VolTrend.STABLE.value,
            "iv_rank": 65.0,
            "vix": 28.0,
        }

        decision = await rule.evaluate(None, market_data)

        assert decision is not None
        assert decision.action == DecisionAction.ENTER
        assert "bullish" in decision.reason.lower()
        assert "high iv" in decision.reason.lower()
        assert decision.metadata["strategy_type"] in ["VERTICAL_SPREAD", "CUSTOM"]

    @pytest.mark.asyncio
    async def test_bullish_high_iv_falling_vol_skips(self):
        """Test that bullish + high IV + falling vol is skipped."""
        rule = BullishHighIVEntry()

        market_data = {
            "symbol": "SPY",
            "outlook": MarketOutlook.BULLISH.value,
            "iv_level": IVLevel.HIGH.value,
            "vol_trend": VolTrend.FALLING.value,  # Bad for debit strategies
            "iv_rank": 65.0,
            "vix": 28.0,
        }

        decision = await rule.evaluate(None, market_data)

        assert decision is None  # Should skip entry


class TestBullishLowIVEntry:
    """Test bullish + low IV entry decisions."""

    @pytest.mark.asyncio
    async def test_bullish_low_iv_triggers_entry(self):
        """Test that bullish + low IV triggers entry."""
        rule = BullishLowIVEntry()

        market_data = {
            "symbol": "SPY",
            "outlook": MarketOutlook.BULLISH.value,
            "iv_level": IVLevel.LOW.value,
            "iv_rank": 35.0,
            "vix": 15.0,
        }

        decision = await rule.evaluate(None, market_data)

        assert decision is not None
        assert decision.action == DecisionAction.ENTER
        assert "bullish" in decision.reason.lower()
        assert "low iv" in decision.reason.lower()

    @pytest.mark.asyncio
    async def test_bullish_low_iv_uses_credit_strategy(self):
        """Test that bullish + low IV uses credit strategy."""
        rule = BullishLowIVEntry()

        market_data = {
            "symbol": "SPY",
            "outlook": MarketOutlook.BULLISH.value,
            "iv_level": IVLevel.LOW.value,
            "iv_rank": 35.0,
            "vix": 15.0,
        }

        decision = await rule.evaluate(None, market_data)

        assert decision is not None
        # Should suggest bull put spread (credit)
        assert "credit" in decision.reason.lower() or "put spread" in decision.reason.lower()


class TestBearishHighIVEntry:
    """Test bearish + high IV entry decisions."""

    @pytest.mark.asyncio
    async def test_bearish_high_iv_triggers_entry(self):
        """Test that bearish + high IV triggers entry."""
        rule = BearishHighIVEntry()

        market_data = {
            "symbol": "SPY",
            "outlook": MarketOutlook.BEARISH.value,
            "iv_level": IVLevel.HIGH.value,
            "vol_trend": VolTrend.RISING.value,
            "iv_rank": 68.0,
            "vix": 30.0,
        }

        decision = await rule.evaluate(None, market_data)

        assert decision is not None
        assert decision.action == DecisionAction.ENTER
        assert "bearish" in decision.reason.lower()
        assert "high iv" in decision.reason.lower()


class TestBearishLowIVEntry:
    """Test bearish + low IV entry decisions."""

    @pytest.mark.asyncio
    async def test_bearish_low_iv_triggers_entry(self):
        """Test that bearish + low IV triggers entry."""
        rule = BearishLowIVEntry()

        market_data = {
            "symbol": "SPY",
            "outlook": MarketOutlook.BEARISH.value,
            "iv_level": IVLevel.LOW.value,
            "iv_rank": 30.0,
            "vix": 14.0,
        }

        decision = await rule.evaluate(None, market_data)

        assert decision is not None
        assert decision.action == DecisionAction.ENTER
        assert "bearish" in decision.reason.lower()
        assert "low iv" in decision.reason.lower()
        assert "credit" in decision.reason.lower()  # Bear call spread is credit


class TestNeutralHighIVEntry:
    """Test neutral + high IV entry decisions."""

    @pytest.mark.asyncio
    async def test_neutral_high_iv_triggers_entry(self):
        """Test that neutral + high IV triggers entry."""
        rule = NeutralHighIVEntry()

        market_data = {
            "symbol": "SPY",
            "outlook": MarketOutlook.NEUTRAL.value,
            "iv_level": IVLevel.HIGH.value,
            "iv_rank": 65.0,
            "vix": 28.0,
        }

        decision = await rule.evaluate(None, market_data)

        assert decision is not None
        assert decision.action == DecisionAction.ENTER
        assert "neutral" in decision.reason.lower()
        assert "high iv" in decision.reason.lower()

    @pytest.mark.asyncio
    async def test_neutral_high_iv_warns_of_risk(self):
        """Test that neutral + high IV includes risk warning."""
        rule = NeutralHighIVEntry()

        market_data = {
            "symbol": "SPY",
            "outlook": MarketOutlook.NEUTRAL.value,
            "iv_level": IVLevel.HIGH.value,
            "iv_rank": 65.0,
            "vix": 28.0,
        }

        decision = await rule.evaluate(None, market_data)

        assert decision is not None
        # Should include risk warning
        assert "risk_warning" in decision.metadata


class TestNeutralLowIVEntry:
    """Test neutral + low IV entry decisions."""

    @pytest.mark.asyncio
    async def test_neutral_low_iv_triggers_entry(self):
        """Test that neutral + low IV triggers entry."""
        rule = NeutralLowIVEntry()

        market_data = {
            "symbol": "SPY",
            "outlook": MarketOutlook.NEUTRAL.value,
            "iv_level": IVLevel.LOW.value,
            "iv_rank": 35.0,
            "vix": 15.0,
        }

        decision = await rule.evaluate(None, market_data)

        assert decision is not None
        assert decision.action == DecisionAction.ENTER
        assert "neutral" in decision.reason.lower()
        assert "low iv" in decision.reason.lower()

    @pytest.mark.asyncio
    async def test_neutral_low_iv_uses_iron_condor(self):
        """Test that neutral + low IV suggests iron condor."""
        rule = NeutralLowIVEntry()

        market_data = {
            "symbol": "SPY",
            "outlook": MarketOutlook.NEUTRAL.value,
            "iv_level": IVLevel.LOW.value,
            "iv_rank": 35.0,
            "vix": 15.0,
        }

        decision = await rule.evaluate(None, market_data)

        assert decision is not None
        assert decision.metadata["strategy_type"] == StrategyType.IRON_CONDOR.value


class TestStrategyMatrix:
    """Test complete strategy matrix coverage."""

    @pytest.mark.asyncio
    async def test_all_regime_combinations_have_entry_rules(self):
        """Test that all 6 regime combinations have entry rules."""
        from src.v6.decisions.rules.entry_rules import (
            BearishHighIVEntry,
            BearishLowIVEntry,
            BullishHighIVEntry,
            BullishLowIVEntry,
            NeutralHighIVEntry,
            NeutralLowIVEntry,
        )

        # All rules should have unique priorities
        priorities = [
            BullishHighIVEntry.priority,
            BullishLowIVEntry.priority,
            BearishHighIVEntry.priority,
            BearishLowIVEntry.priority,
            NeutralHighIVEntry.priority,
            NeutralLowIVEntry.priority,
        ]

        assert len(priorities) == len(set(priorities)), "All priorities should be unique"
        assert sorted(priorities) == priorities, "Priorities should be sequential"

    @pytest.mark.asyncio
    async def test_incorrect_outlook_doesnt_trigger(self):
        """Test that incorrect outlook doesn't trigger entry."""
        rule = BullishHighIVEntry()

        # Should not trigger for bearish market
        market_data = {
            "symbol": "SPY",
            "outlook": MarketOutlook.BEARISH.value,  # Wrong outlook!
            "iv_level": IVLevel.HIGH.value,
            "iv_rank": 65.0,
            "vix": 28.0,
        }

        decision = await rule.evaluate(None, market_data)

        assert decision is None, "Should not trigger for bearish outlook"

    @pytest.mark.asyncio
    async def test_incorrect_iv_level_doesnt_trigger(self):
        """Test that incorrect IV level doesn't trigger entry."""
        rule = BullishLowIVEntry()

        # Should not trigger for high IV
        market_data = {
            "symbol": "SPY",
            "outlook": MarketOutlook.BULLISH.value,
            "iv_level": IVLevel.HIGH.value,  # Wrong IV level!
            "iv_rank": 65.0,
            "vix": 28.0,
        }

        decision = await rule.evaluate(None, market_data)

        assert decision is None, "Should not trigger for high IV"


class TestStrategySelectionIntegration:
    """Integration tests for complete strategy selection."""

    @pytest.mark.asyncio
    async def test_bullish_regime_with_high_iv(self):
        """Test complete flow: Bullish market with high IV."""
        # Simulate market data
        market_data = {
            "symbol": "SPY",
            "outlook": MarketOutlook.BULLISH.value,
            "iv_level": IVLevel.HIGH.value,
            "iv_rank": 68.0,
            "vix": 29.0,
            "underlying_price": 485.0,
            "vol_trend": VolTrend.RISING.value,
            "timestamp": datetime.now().isoformat(),
        }

        # Test rule
        rule = BullishHighIVEntry()
        decision = await rule.evaluate(None, market_data)

        assert decision is not None
        assert decision.action == DecisionAction.ENTER
        assert decision.metadata["strategy_type"] == StrategyType.VERTICAL_SPREAD.value
        assert "bull call spread" in decision.reason.lower()

    @pytest.mark.asyncio
    async def test_bullish_regime_with_low_iv(self):
        """Test complete flow: Bullish market with low IV."""
        market_data = {
            "symbol": "SPY",
            "outlook": MarketOutlook.BULLISH.value,
            "iv_level": IVLevel.LOW.value,
            "iv_rank": 32.0,
            "vix": 16.0,
            "underlying_price": 450.0,
            "vol_trend": VolTrend.FALLING.value,
            "timestamp": datetime.now().isoformat(),
        }

        rule = BullishLowIVEntry()
        decision = await rule.evaluate(None, market_data)

        assert decision is not None
        assert decision.action == DecisionAction.ENTER
        assert "bull put spread" in decision.reason.lower()

    @pytest.mark.asyncio
    async def test_bearish_regime_with_low_iv(self):
        """Test complete flow: Bearish market with low IV."""
        market_data = {
            "symbol": "QQQ",
            "outlook": MarketOutlook.BEARISH.value,
            "iv_level": IVLevel.LOW.value,
            "iv_rank": 28.0,
            "vix": 14.0,
            "underlying_price": 435.0,
            "vol_trend": VolTrend.STABLE.value,
            "timestamp": datetime.now().isoformat(),
        }

        rule = BearishLowIVEntry()
        decision = await rule.evaluate(None, market_data)

        assert decision is not None
        assert decision.action == DecisionAction.ENTER
        assert "bear call spread" in decision.reason.lower()

    @pytest.mark.asyncio
    async def test_neutral_regime_with_high_iv(self):
        """Test complete flow: Neutral market with high IV."""
        market_data = {
            "symbol": "IWM",
            "outlook": MarketOutlook.NEUTRAL.value,
            "iv_level": IVLevel.HIGH.value,
            "iv_rank": 72.0,
            "vix": 32.0,
            "underlying_price": 195.0,
            "vol_trend": VolTrend.FALLING.value,
            "timestamp": datetime.now().isoformat(),
        }

        rule = NeutralHighIVEntry()
        decision = await rule.evaluate(None, market_data)

        assert decision is not None
        assert decision.action == DecisionAction.ENTER
        assert "short straddle" in decision.reason.lower() or "short strangle" in decision.reason.lower()

    @pytest.mark.asyncio
    async def test_neutral_regime_with_low_iv(self):
        """Test complete flow: Neutral market with low IV."""
        market_data = {
            "symbol": "IWM",
            "outlook": MarketOutlook.NEUTRAL.value,
            "iv_level": IVLevel.LOW.value,
            "iv_rank": 35.0,
            "vix": 15.0,
            "underlying_price": 195.0,
            "vol_trend": VolTrend.STABLE.value,
            "timestamp": datetime.now().isoformat(),
        }

        rule = NeutralLowIVEntry()
        decision = await rule.evaluate(None, market_data)

        assert decision is not None
        assert decision.action == DecisionAction.ENTER
        assert decision.metadata["strategy_type"] == StrategyType.IRON_CONDOR.value
        assert "iron condor" in decision.reason.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
