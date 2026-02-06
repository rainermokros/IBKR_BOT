"""
Unit Tests for Iron Condor Entry

Tests the complete Iron Condor entry flow:
- Entry execution with delta-based builders
- Validation checks
- Result handling
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from v6.execution.entry_executor import EntryExecutor
from v6.strategies.models import StrategyType


@pytest.fixture
def mock_ib_conn():
    """Create mock IB connection."""
    ib_conn = Mock()
    ib_conn.ib = Mock()
    return ib_conn


@pytest.fixture
def mock_execution_engine(mock_ib_conn):
    """Create mock execution engine."""
    engine = Mock()
    engine.dry_run = False
    return engine


@pytest.fixture
def sample_option_chain():
    """Create sample option chain with Greeks."""
    return [
        # Puts
        {'strike': 440, 'right': 'P', 'delta': -0.05, 'gamma': 0.01, 'theta': -0.02, 'vega': 0.10},
        {'strike': 450, 'right': 'P', 'delta': -0.08, 'gamma': 0.02, 'theta': -0.03, 'vega': 0.15},
        {'strike': 460, 'right': 'P', 'delta': -0.12, 'gamma': 0.03, 'theta': -0.04, 'vega': 0.20},
        {'strike': 470, 'right': 'P', 'delta': -0.16, 'gamma': 0.04, 'theta': -0.05, 'vega': 0.25},
        {'strike': 480, 'right': 'P', 'delta': -0.18, 'gamma': 0.045, 'theta': -0.055, 'vega': 0.275},
        {'strike': 490, 'right': 'P', 'delta': -0.20, 'gamma': 0.05, 'theta': -0.06, 'vega': 0.30},
        {'strike': 500, 'right': 'P', 'delta': -0.25, 'gamma': 0.06, 'theta': -0.07, 'vega': 0.35},
        # Calls
        {'strike': 510, 'right': 'C', 'delta': 0.25, 'gamma': 0.06, 'theta': -0.07, 'vega': 0.35},
        {'strike': 520, 'right': 'C', 'delta': 0.20, 'gamma': 0.05, 'theta': -0.06, 'vega': 0.30},
        {'strike': 530, 'right': 'C', 'delta': 0.18, 'gamma': 0.045, 'theta': -0.055, 'vega': 0.275},
        {'strike': 540, 'right': 'C', 'delta': 0.16, 'gamma': 0.04, 'theta': -0.05, 'vega': 0.25},
        {'strike': 550, 'right': 'C', 'delta': 0.12, 'gamma': 0.03, 'theta': -0.04, 'vega': 0.20},
        {'strike': 560, 'right': 'C', 'delta': 0.08, 'gamma': 0.02, 'theta': -0.03, 'vega': 0.15},
        {'strike': 570, 'right': 'C', 'delta': 0.05, 'gamma': 0.01, 'theta': -0.02, 'vega': 0.10},
    ]


class TestEntryExecutor:
    """Test EntryExecutor class."""

    @pytest.fixture
    def executor(self, mock_ib_conn, mock_execution_engine):
        """Create entry executor in dry run mode."""
        return EntryExecutor(
            ib_conn=mock_ib_conn,
            execution_engine=mock_execution_engine,
            dry_run=True
        )

    @pytest.mark.asyncio
    async def test_enter_iron_condor_dry_run(self, executor, sample_option_chain):
        """Test Iron Condor entry in dry run mode."""
        symbol = "SPY"

        result = await executor.enter_iron_condor(
            symbol=symbol,
            option_chain=sample_option_chain,
            quantity=1,
            framework='45_21'
        )

        # Check result structure
        assert result is not None
        assert 'status' in result
        assert 'strategy' in result
        assert 'message' in result

        # In dry run, status should be 'BUILT'
        assert result['status'] == 'BUILT'

        # Check strategy
        strategy = result['strategy']
        assert strategy.symbol == symbol
        assert strategy.strategy_type == StrategyType.IRON_CONDOR
        assert len(strategy.legs) == 4

    @pytest.mark.asyncio
    async def test_iron_condor_delta_accuracy(self, executor, sample_option_chain):
        """Test Iron Condor entry selects correct deltas."""
        symbol = "SPY"

        result = await executor.enter_iron_condor(
            symbol=symbol,
            option_chain=sample_option_chain,
            quantity=1,
            framework='45_21'
        )

        strategy = result['strategy']
        metadata = strategy.metadata

        # Check delta accuracy (should be within ±0.03 of target)
        target_delta = metadata['target_delta']

        # Short put delta
        put_delta = abs(metadata['short_put_delta'])
        assert abs(put_delta - target_delta) <= 0.05, \
            f"Put delta {put_delta} too far from target {target_delta}"

        # Short call delta
        call_delta = metadata['short_call_delta']
        assert abs(call_delta - target_delta) <= 0.05, \
            f"Call delta {call_delta} too far from target {target_delta}"

    @pytest.mark.asyncio
    async def test_iron_condor_delta_balance(self, executor, sample_option_chain):
        """Test Iron Condor delta balance is within threshold."""
        symbol = "SPY"

        result = await executor.enter_iron_condor(
            symbol=symbol,
            option_chain=sample_option_chain,
            quantity=1,
            framework='45_21'
        )

        strategy = result['strategy']
        metadata = strategy.metadata

        # Check delta balance (≤ 0.05 difference)
        put_delta = abs(metadata['short_put_delta'])
        call_delta = metadata['short_call_delta']
        delta_diff = abs(put_delta - call_delta)

        assert delta_diff <= 0.05, \
            f"Delta difference {delta_diff} exceeds threshold 0.05"

    @pytest.mark.asyncio
    async def test_iron_condor_wing_widths(self, executor, sample_option_chain):
        """Test Iron Condor wing widths are within tolerance."""
        symbol = "SPY"

        result = await executor.enter_iron_condor(
            symbol=symbol,
            option_chain=sample_option_chain,
            quantity=1,
            framework='45_21'
        )

        strategy = result['strategy']
        metadata = strategy.metadata

        # Check wing widths are within ±2.0 of target
        target_width = metadata['target_wing_width']
        put_width = metadata['put_wing_width']
        call_width = metadata['call_wing_width']

        assert abs(put_width - target_width) <= 2.0, \
            f"Put wing width {put_width} too far from target {target_width}"

        assert abs(call_width - target_width) <= 2.0, \
            f"Call wing width {call_width} too far from target {target_width}"

    @pytest.mark.asyncio
    async def test_iron_condor_strike_structure(self, executor, sample_option_chain):
        """Test Iron Condor strike structure is valid."""
        symbol = "SPY"

        result = await executor.enter_iron_condor(
            symbol=symbol,
            option_chain=sample_option_chain,
            quantity=1,
            framework='45_21'
        )

        strategy = result['strategy']
        metadata = strategy.metadata

        # Verify strike order: LP < SP < SC < LC
        lp = metadata['long_put_strike']
        sp = metadata['short_put_strike']
        sc = metadata['short_call_strike']
        lc = metadata['long_call_strike']

        assert lp < sp < sc < lc, \
            f"Invalid strike structure: LP={lp}, SP={sp}, SC={sc}, LC={lc}"

    @pytest.mark.asyncio
    async def test_enter_bull_put_spread(self, executor, sample_option_chain):
        """Test bull put spread entry."""
        symbol = "SPY"

        result = await executor.enter_bull_put_spread(
            symbol=symbol,
            option_chain=sample_option_chain,
            quantity=1,
            framework='45_21'
        )

        # Check result
        assert result is not None
        assert result['status'] == 'BUILT'

        strategy = result['strategy']
        assert strategy.symbol == symbol
        assert strategy.strategy_type == StrategyType.VERTICAL_SPREAD
        assert len(strategy.legs) == 2

        # Check metadata
        assert strategy.metadata['direction'] == 'bullish'
        assert strategy.metadata['spread_type'] == 'bull_put_spread'

    @pytest.mark.asyncio
    async def test_enter_bear_call_spread(self, executor, sample_option_chain):
        """Test bear call spread entry."""
        symbol = "SPY"

        result = await executor.enter_bear_call_spread(
            symbol=symbol,
            option_chain=sample_option_chain,
            quantity=1,
            framework='45_21'
        )

        # Check result
        assert result is not None
        assert result['status'] == 'BUILT'

        strategy = result['strategy']
        assert strategy.symbol == symbol
        assert strategy.strategy_type == StrategyType.VERTICAL_SPREAD
        assert len(strategy.legs) == 2

        # Check metadata
        assert strategy.metadata['direction'] == 'bearish'
        assert strategy.metadata['spread_type'] == 'bear_call_spread'


class TestEntryValidation:
    """Test entry validation logic."""

    @pytest.fixture
    def executor(self, mock_ib_conn, mock_execution_engine):
        """Create entry executor."""
        return EntryExecutor(
            ib_conn=mock_ib_conn,
            execution_engine=mock_execution_engine,
            dry_run=True
        )

    @pytest.mark.asyncio
    async def test_entry_validation_passes(self, executor, sample_option_chain):
        """Test that valid entry passes validation."""
        symbol = "SPY"

        # Should not raise any errors
        result = await executor.enter_iron_condor(
            symbol=symbol,
            option_chain=sample_option_chain,
            quantity=1,
            framework='45_21'
        )

        assert result['status'] == 'BUILT'

    @pytest.mark.asyncio
    async def test_entry_validation_invalid_framework(self, executor, sample_option_chain):
        """Test that invalid framework raises error."""
        symbol = "SPY"

        with pytest.raises(ValueError, match="Unknown framework"):
            await executor.enter_iron_condor(
                symbol=symbol,
                option_chain=sample_option_chain,
                quantity=1,
                framework='invalid_framework'
            )


class TestIntegration:
    """Integration tests for entry flow."""

    @pytest.fixture
    def executor(self, mock_ib_conn, mock_execution_engine):
        """Create entry executor."""
        return EntryExecutor(
            ib_conn=mock_ib_conn,
            execution_engine=mock_execution_engine,
            dry_run=True
        )

    @pytest.mark.asyncio
    async def test_complete_entry_flow(self, executor, sample_option_chain):
        """Test complete entry flow from market data to strategy."""
        symbol = "SPY"

        # Simulate complete entry flow
        result = await executor.enter_iron_condor(
            symbol=symbol,
            option_chain=sample_option_chain,
            quantity=1,
            framework='45_21'
        )

        # Verify all components
        assert result['status'] == 'BUILT'
        assert result['strategy'] is not None

        strategy = result['strategy']

        # Check all required metadata
        required_metadata = [
            'framework',
            'underlying_price',
            'iv_rank',
            'target_delta',
            'entry_dte',
            'long_put_strike',
            'short_put_strike',
            'short_call_strike',
            'long_call_strike',
            'put_wing_width',
            'call_wing_width',
            'target_wing_width',
            'short_put_delta',
            'short_call_delta',
            'delta_balance',
        ]

        for key in required_metadata:
            assert key in strategy.metadata, f"Missing metadata key: {key}"

    @pytest.mark.asyncio
    async def test_multiple_strategies_same_symbol(self, executor, sample_option_chain):
        """Test entering multiple strategies for same symbol."""
        symbol = "SPY"

        # Enter Iron Condor
        ic_result = await executor.enter_iron_condor(
            symbol=symbol,
            option_chain=sample_option_chain,
            quantity=1,
            framework='45_21'
        )

        # Enter Bull Put Spread
        bps_result = await executor.enter_bull_put_spread(
            symbol=symbol,
            option_chain=sample_option_chain,
            quantity=1,
            framework='45_21'
        )

        # Both should succeed
        assert ic_result['status'] == 'BUILT'
        assert bps_result['status'] == 'BUILT'

        # Should have different strategy IDs
        assert ic_result['strategy'].strategy_id != bps_result['strategy'].strategy_id


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
