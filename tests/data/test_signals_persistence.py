"""
Tests for Signals Persistence

Unit tests for Delta Lake persistence layer including table creation,
batch writing, idempotent writes, and signal filtering queries.
"""

import asyncio
import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

from src.v6.data.signals_persistence import (
    SignalsTable,
    SignalWriter,
    SignalReader,
    Signal
)


@pytest.fixture
def lake_path(tmp_path):
    """Create temporary Delta Lake path for testing."""
    return tmp_path / "signals"


@pytest.fixture
def signals_table(lake_path):
    """Create signals table for testing."""
    table = SignalsTable(table_path=str(lake_path))
    return table


@pytest.fixture
def sample_signal():
    """Create sample signal."""
    return Signal(
        timestamp=datetime.now(),
        signal_id="signal_001",
        symbol="SPY",
        signal_type="entry_long",
        strategy_id="iron_condor_v1",
        confidence=0.85,
        probability_score=0.78,
        regime_context="bullish",
        futures_lead={"ES": 1.5, "NQ": 2.0, "RTY": 1.2},
        greeks_context={"IV": 0.18, "delta": 0.5, "gamma": 0.1},
        price_action={"support": 450.0, "resistance": 460.0, "trend": "up"},
        metadata={"DTE": 21, "strike_width": 5}
    )


@pytest.fixture
def sample_signals():
    """Create multiple sample signals."""
    signals = []
    base_time = datetime.now() - timedelta(hours=2)

    signal_types = ["entry_long", "entry_short", "exit", "adjust"]
    symbols = ["SPY", "QQQ", "IWM"]
    strategies = ["iron_condor_v1", "vertical_spread", "iron_butterfly"]

    for i in range(20):
        signal = Signal(
            timestamp=base_time + timedelta(minutes=i * 10),
            signal_id=f"signal_{i:03d}",
            symbol=symbols[i % 3],
            signal_type=signal_types[i % 4],
            strategy_id=strategies[i % 3],
            confidence=0.7 + (i % 3) * 0.1,
            probability_score=0.65 + (i % 4) * 0.08,
            regime_context="bullish" if i % 2 == 0 else "bearish",
            futures_lead={"ES": 1.0 + i * 0.1, "NQ": 1.5 + i * 0.15, "RTY": 0.8 + i * 0.08},
            greeks_context={"IV": 0.16 + i * 0.01, "delta": 0.5 - i * 0.02, "gamma": 0.1},
            price_action={"support": 450.0 + i, "resistance": 460.0 + i, "trend": "up" if i % 2 == 0 else "down"},
            metadata={"index": i, "priority": "high" if i < 10 else "medium"}
        )
        signals.append(signal)

    return signals


class TestSignalsTable:
    """Test suite for SignalsTable."""

    def test_init_creates_table(self, lake_path):
        """Test that initialization creates Delta Lake table."""
        # Remove table if it exists
        import shutil
        if lake_path.exists():
            shutil.rmtree(lake_path)

        table = SignalsTable(table_path=str(lake_path))

        # Verify table exists
        from deltalake import DeltaTable
        assert DeltaTable.is_deltatable(str(lake_path))

    def test_init_reuses_existing_table(self, signals_table, lake_path):
        """Test that initialization reuses existing table."""
        # Create table first time
        table1 = signals_table

        # Create table second time
        table2 = SignalsTable(table_path=str(lake_path))

        # Should be same path
        assert table1.table_path == table2.table_path

    def test_get_table(self, signals_table):
        """Test getting DeltaTable instance."""
        dt = signals_table.get_table()

        assert dt is not None
        assert dt.version() == 0  # Should be version 0 for new table

    def test_table_schema(self, signals_table):
        """Test that table has correct schema."""
        dt = signals_table.get_table()

        # Get schema fields
        schema = dt.schema()
        field_names = [field.name for field in schema.fields]

        # Verify required fields
        required_fields = [
            'timestamp', 'signal_id', 'symbol', 'signal_type', 'strategy_id',
            'confidence', 'probability_score', 'regime_context',
            'futures_lead', 'greeks_context', 'price_action', 'metadata'
        ]

        for field in required_fields:
            assert field in field_names, f"Field {field} not in schema"


class TestSignalWriter:
    """Test suite for SignalWriter."""

    @pytest.mark.asyncio
    async def test_write_single_signal(self, signals_table, sample_signal):
        """Test writing a single signal."""
        writer = SignalWriter(table=signals_table, batch_interval=1)

        # Write signal directly (bypass buffer)
        await writer._write_signals([sample_signal])

        # Verify write
        dt = signals_table.get_table()
        df = pl.from_pandas(dt.to_pandas())

        assert len(df) == 1
        assert df.row(0)[1] == "signal_001"  # signal_id column

    @pytest.mark.asyncio
    async def test_write_multiple_signals(self, signals_table, sample_signals):
        """Test writing multiple signals."""
        writer = SignalWriter(table=signals_table, batch_interval=1)

        # Write signals
        await writer._write_signals(sample_signals)

        # Verify write
        dt = signals_table.get_table()
        df = pl.from_pandas(dt.to_pandas())

        assert len(df) == 20

    @pytest.mark.asyncio
    async def test_idempotent_write(self, signals_table, sample_signal):
        """Test that duplicate writes are handled correctly."""
        writer = SignalWriter(table=signals_table, batch_interval=1)

        # Write signal first time
        await writer._write_signals([sample_signal])

        # Write same signal again (same signal_id)
        await writer._write_signals([sample_signal])

        # Verify only one record exists
        dt = signals_table.get_table()
        df = pl.from_pandas(dt.to_pandas())

        assert len(df) == 1

    @pytest.mark.asyncio
    async def test_buffer_and_batch_write(self, signals_table, sample_signals):
        """Test buffering and batch writing."""
        writer = SignalWriter(table=signals_table, batch_interval=1)

        # Buffer signals
        for signal in sample_signals[:10]:
            await writer.on_signal(signal)

        # Verify buffer
        assert len(writer._buffer) == 10

        # Start batch writing (should write immediately)
        await writer.start_batch_writing()
        await asyncio.sleep(0.1)  # Small delay for batch to process

        # Stop batch writing
        await writer.stop_batch_writing()

        # Verify writes
        dt = signals_table.get_table()
        df = pl.from_pandas(dt.to_pandas())

        assert len(df) == 10

    @pytest.mark.asyncio
    async def test_empty_write(self, signals_table):
        """Test writing empty list."""
        writer = SignalWriter(table=signals_table, batch_interval=1)

        # Write empty list
        count = await writer._write_signals([])

        # Should return 0
        assert count == 0

    @pytest.mark.asyncio
    async def test_flush_on_stop(self, signals_table, sample_signals):
        """Test that buffer is flushed when stopping."""
        writer = SignalWriter(table=signals_table, batch_interval=60)

        # Buffer signals
        for signal in sample_signals[:5]:
            await writer.on_signal(signal)

        # Stop without waiting for batch interval
        await writer.stop_batch_writing()

        # Verify buffer was flushed
        assert len(writer._buffer) == 0

        dt = signals_table.get_table()
        df = pl.from_pandas(dt.to_pandas())

        assert len(df) == 5

    @pytest.mark.asyncio
    async def test_dict_field_serialization(self, signals_table):
        """Test that dict fields are serialized to JSON correctly."""
        writer = SignalWriter(table=signals_table, batch_interval=1)

        signal = Signal(
            timestamp=datetime.now(),
            signal_id="test_signal",
            symbol="SPY",
            signal_type="entry_long",
            strategy_id="test_strategy",
            confidence=0.8,
            probability_score=0.75,
            regime_context="bullish",
            futures_lead={"ES": 1.5, "NQ": 2.0, "RTY": 1.2},
            greeks_context={"IV": 0.18, "delta": 0.5, "gamma": 0.1},
            price_action={"support": 450.0, "resistance": 460.0},
            metadata={"test_key": "test_value"}
        )

        await writer._write_signals([signal])

        # Verify serialization
        dt = signals_table.get_table()
        df = pl.from_pandas(dt.to_pandas())

        assert len(df) == 1

        # Check futures_lead
        futures_lead_str = df.row(0)[8]
        futures_lead_dict = json.loads(futures_lead_str)
        assert futures_lead_dict["ES"] == 1.5
        assert futures_lead_dict["NQ"] == 2.0

        # Check greeks_context
        greeks_str = df.row(0)[9]
        greeks_dict = json.loads(greeks_str)
        assert greeks_dict["IV"] == 0.18
        assert greeks_dict["delta"] == 0.5

        # Check price_action
        price_action_str = df.row(0)[10]
        price_action_dict = json.loads(price_action_str)
        assert price_action_dict["support"] == 450.0
        assert price_action_dict["resistance"] == 460.0


class TestSignalReader:
    """Test suite for SignalReader."""

    @pytest.mark.asyncio
    async def test_read_signal(self, signals_table, sample_signal):
        """Test reading a specific signal."""
        # Write signal first
        writer = SignalWriter(table=signals_table)
        await writer._write_signals([sample_signal])

        # Read signal
        reader = SignalReader(table=signals_table)
        df = reader.read_signal(signal_id="signal_001")

        assert df is not None
        assert len(df) == 1
        assert df.row(0)[1] == "signal_001"

    @pytest.mark.asyncio
    async def test_read_signal_not_found(self, signals_table):
        """Test reading non-existent signal."""
        reader = SignalReader(table=signals_table)
        df = reader.read_signal(signal_id="nonexistent")

        assert df is None

    @pytest.mark.asyncio
    async def test_read_symbol_signals(self, signals_table, sample_signals):
        """Test reading signals for a specific symbol."""
        # Write signals
        writer = SignalWriter(table=signals_table)
        await writer._write_signals(sample_signals)

        # Read SPY signals
        reader = SignalReader(table=signals_table)
        df = reader.read_symbol_signals(symbol="SPY")

        # Should have SPY signals
        assert len(df) > 0
        for row in df.iter_rows(named=True):
            assert row["symbol"] == "SPY"

    @pytest.mark.asyncio
    async def test_read_symbol_signals_with_type_filter(self, signals_table, sample_signals):
        """Test reading symbol signals with type filter."""
        # Write signals
        writer = SignalWriter(table=signals_table)
        await writer._write_signals(sample_signals)

        # Read SPY entry_long signals
        reader = SignalReader(table=signals_table)
        df = reader.read_symbol_signals(symbol="SPY", signal_type="entry_long")

        # Should filter by symbol and type
        assert len(df) > 0
        for row in df.iter_rows(named=True):
            assert row["symbol"] == "SPY"
            assert row["signal_type"] == "entry_long"

    @pytest.mark.asyncio
    async def test_read_strategy_signals(self, signals_table, sample_signals):
        """Test reading signals for a specific strategy."""
        # Write signals
        writer = SignalWriter(table=signals_table)
        await writer._write_signals(sample_signals)

        # Read strategy signals
        reader = SignalReader(table=signals_table)
        df = reader.read_strategy_signals(strategy_id="iron_condor_v1")

        # Should have signals for that strategy
        assert len(df) > 0
        for row in df.iter_rows(named=True):
            assert row["strategy_id"] == "iron_condor_v1"

    @pytest.mark.asyncio
    async def test_read_time_range(self, signals_table, sample_signals):
        """Test reading signals within time range."""
        # Write signals
        writer = SignalWriter(table=signals_table)
        await writer._write_signals(sample_signals)

        # Read time range
        reader = SignalReader(table=signals_table)
        end = datetime.now()
        start = end - timedelta(hours=3)

        df = reader.read_time_range(start=start, end=end)

        # Should have signals in range
        assert len(df) >= 10

    @pytest.mark.asyncio
    async def test_read_time_range_with_filters(self, signals_table, sample_signals):
        """Test reading time range with symbol and type filters."""
        # Write signals
        writer = SignalWriter(table=signals_table)
        await writer._write_signals(sample_signals)

        # Read with filters
        reader = SignalReader(table=signals_table)
        end = datetime.now()
        start = end - timedelta(hours=3)

        df = reader.read_time_range(start=start, end=end, symbol="SPY", signal_type="entry_long")

        # Should filter correctly
        assert len(df) >= 0
        for row in df.iter_rows(named=True):
            assert row["symbol"] == "SPY"
            assert row["signal_type"] == "entry_long"

    @pytest.mark.asyncio
    async def test_read_latest_signals(self, signals_table, sample_signals):
        """Test reading latest signals."""
        # Write signals
        writer = SignalWriter(table=signals_table)
        await writer._write_signals(sample_signals)

        # Read latest
        reader = SignalReader(table=signals_table)
        df = reader.read_latest_signals(limit=10)

        # Should have 10 signals
        assert len(df) == 10

        # Should be sorted by timestamp descending
        timestamps = df["timestamp"].to_list()
        assert timestamps == sorted(timestamps, reverse=True)

    @pytest.mark.asyncio
    async def test_read_latest_signals_by_symbol(self, signals_table, sample_signals):
        """Test reading latest signals for a symbol."""
        # Write signals
        writer = SignalWriter(table=signals_table)
        await writer._write_signals(sample_signals)

        # Read latest SPY signals
        reader = SignalReader(table=signals_table)
        df = reader.read_latest_signals(symbol="SPY", limit=5)

        # Should have SPY signals
        assert len(df) > 0
        assert len(df) <= 5
        for row in df.iter_rows(named=True):
            assert row["symbol"] == "SPY"

    @pytest.mark.asyncio
    async def test_calculate_signal_distribution(self, signals_table, sample_signals):
        """Test calculating signal distribution."""
        # Write signals
        writer = SignalWriter(table=signals_table)
        await writer._write_signals(sample_signals)

        # Calculate distribution
        reader = SignalReader(table=signals_table)
        df = reader.calculate_signal_distribution(days=30)

        # Should have multiple signal types
        assert len(df) > 0
        assert len(df) <= 4  # At most 4 signal types

        # Sum of counts should equal total signals in range
        total_count = df["len"].sum()
        assert total_count >= 13  # At least 13 signals should be in 30-day range


class TestIntegration:
    """Integration tests for full read-write workflows."""

    @pytest.mark.asyncio
    async def test_write_and_query_workflow(self, signals_table):
        """Test complete write and query workflow."""
        # Create and write signals
        writer = SignalWriter(table=signals_table)
        reader = SignalReader(table=signals_table)

        signals = []
        base_time = datetime.now() - timedelta(hours=1)

        for i in range(10):
            signal = Signal(
                timestamp=base_time + timedelta(minutes=i * 10),
                signal_id=f"workflow_{i}",
                symbol="SPY" if i % 2 == 0 else "QQQ",
                signal_type="entry_long" if i % 2 == 0 else "entry_short",
                strategy_id="test_strategy",
                confidence=0.7 + i * 0.02,
                probability_score=0.65 + i * 0.03,
                regime_context="bullish" if i % 2 == 0 else "neutral",
                futures_lead={"ES": 1.0, "NQ": 1.5, "RTY": 0.8},
                greeks_context={"IV": 0.18, "delta": 0.5, "gamma": 0.1},
                price_action={"support": 450.0, "resistance": 460.0},
                metadata={}
            )
            signals.append(signal)

        await writer._write_signals(signals)

        # Query latest
        latest = reader.read_latest_signals(limit=5)
        assert len(latest) == 5

        # Query by symbol
        spy_signals = reader.read_symbol_signals(symbol="SPY")
        assert len(spy_signals) == 5

        # Query by strategy
        strategy_signals = reader.read_strategy_signals(strategy_id="test_strategy")
        assert len(strategy_signals) == 10

        # Query distribution
        dist = reader.calculate_signal_distribution(days=1)
        assert len(dist) == 2  # entry_long and entry_short

    @pytest.mark.asyncio
    async def test_concurrent_writes(self, signals_table):
        """Test concurrent write operations."""
        writer = SignalWriter(table=signals_table)

        # Create multiple write tasks
        async def write_signals(prefix: int):
            signals = []
            base_time = datetime.now() - timedelta(hours=1)

            for i in range(5):
                signal = Signal(
                    timestamp=base_time + timedelta(minutes=i),
                    signal_id=f"concurrent_{prefix}_{i}",
                    symbol="SPY",
                    signal_type="entry_long",
                    strategy_id=f"strategy_{prefix}",
                    confidence=0.7,
                    probability_score=0.65,
                    regime_context="neutral",
                    futures_lead={},
                    greeks_context={},
                    price_action={},
                    metadata={}
                )
                signals.append(signal)

            await writer._write_signals(signals)

        # Run concurrent writes
        await asyncio.gather(
            write_signals(0),
            write_signals(1),
            write_signals(2)
        )

        # Verify all writes completed
        dt = signals_table.get_table()
        df = pl.from_pandas(dt.to_pandas())

        assert len(df) == 15

    @pytest.mark.asyncio
    async def test_filter_combinations(self, signals_table):
        """Test various filter combinations."""
        writer = SignalWriter(table=signals_table)
        reader = SignalReader(table=signals_table)

        # Create diverse signals
        signals = []
        base_time = datetime.now() - timedelta(hours=1)

        for symbol in ["SPY", "QQQ", "IWM"]:
            for signal_type in ["entry_long", "entry_short", "exit"]:
                signal = Signal(
                    timestamp=base_time,
                    signal_id=f"{symbol}_{signal_type}",
                    symbol=symbol,
                    signal_type=signal_type,
                    strategy_id="test",
                    confidence=0.8,
                    probability_score=0.75,
                    regime_context="neutral",
                    futures_lead={},
                    greeks_context={},
                    price_action={},
                    metadata={}
                )
                signals.append(signal)

        await writer._write_signals(signals)

        # Test various filter combinations
        spy_entry = reader.read_symbol_signals(symbol="SPY", signal_type="entry_long")
        assert len(spy_entry) == 1

        qqq_all = reader.read_symbol_signals(symbol="QQQ")
        assert len(qqq_all) == 3

        all_exit = reader.read_time_range(
            start=base_time - timedelta(minutes=5),
            end=base_time + timedelta(minutes=5),
            signal_type="exit"
        )
        assert len(all_exit) == 3
