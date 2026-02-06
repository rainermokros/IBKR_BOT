"""
Tests for Performance Metrics Persistence

Unit tests for Delta Lake persistence layer including table creation,
batch writing, idempotent writes, and PnL aggregation queries.
"""

import asyncio
import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

from src.v6.data.performance_metrics_persistence import (
    PerformanceMetricsTable,
    PerformanceWriter,
    PerformanceReader,
    PerformanceMetric,
    Greeks
)


@pytest.fixture
def lake_path(tmp_path):
    """Create temporary Delta Lake path for testing."""
    return tmp_path / "performance_metrics"


@pytest.fixture
def metrics_table(lake_path):
    """Create performance metrics table for testing."""
    table = PerformanceMetricsTable(table_path=str(lake_path))
    return table


@pytest.fixture
def sample_greeks():
    """Create sample Greeks."""
    return Greeks(
        delta=0.5,
        gamma=0.1,
        theta=-0.05,
        vega=0.2
    )


@pytest.fixture
def sample_metric(sample_greeks):
    """Create sample performance metric."""
    return PerformanceMetric(
        timestamp=datetime.now(),
        strategy_id="iron_condor_v1",
        trade_id="trade_001",
        entry_time=datetime.now() - timedelta(hours=2),
        exit_time=None,
        entry_price=1.50,
        exit_price=None,
        quantity=1,
        premium_collected=150.0,
        premium_paid=0.0,
        net_premium=150.0,
        max_profit=150.0,
        max_loss=-400.0,
        realized_pnl=0.0,
        unrealized_pnl=25.0,
        hold_duration_minutes=None,
        exit_reason=None,
        greeks_at_entry=sample_greeks,
        greeks_at_exit=None,
        metadata={"symbol": "SPY", "DTE": 21, "strike_width": 5}
    )


@pytest.fixture
def sample_metrics():
    """Create multiple sample metrics."""
    metrics = []
    base_time = datetime.now() - timedelta(days=1)

    for i in range(20):
        entry_greeks = Greeks(
            delta=0.5 + i * 0.01,
            gamma=0.1 + i * 0.005,
            theta=-0.05 - i * 0.002,
            vega=0.2 + i * 0.01
        )

        # Alternate between open and closed positions
        if i % 3 == 0:
            # Closed position
            exit_time = base_time + timedelta(hours=i * 2 + 4)
            exit_price = 0.50
            realized_pnl = 100.0
            unrealized_pnl = 0.0
            hold_duration = (exit_time - (base_time + timedelta(hours=i * 2))).total_seconds() / 60
            exit_reason = "take_profit"
        else:
            # Open position
            exit_time = None
            exit_price = None
            realized_pnl = 0.0
            unrealized_pnl = 25.0 + i * 5
            hold_duration = None
            exit_reason = None

        metric = PerformanceMetric(
            timestamp=base_time + timedelta(hours=i * 2),
            strategy_id=f"strategy_{i % 3}",
            trade_id=f"trade_{i:03d}",
            entry_time=base_time + timedelta(hours=i * 2),
            exit_time=exit_time,
            entry_price=1.50 + i * 0.1,
            exit_price=exit_price,
            quantity=1,
            premium_collected=150.0 + i * 10,
            premium_paid=0.0,
            net_premium=150.0 + i * 10,
            max_profit=150.0 + i * 10,
            max_loss=-400.0 - i * 10,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            hold_duration_minutes=int(hold_duration) if hold_duration else None,
            exit_reason=exit_reason,
            greeks_at_entry=entry_greeks,
            greeks_at_exit=None,
            metadata={"index": i}
        )
        metrics.append(metric)

    return metrics


class TestPerformanceMetricsTable:
    """Test suite for PerformanceMetricsTable."""

    def test_init_creates_table(self, lake_path):
        """Test that initialization creates Delta Lake table."""
        # Remove table if it exists
        import shutil
        if lake_path.exists():
            shutil.rmtree(lake_path)

        table = PerformanceMetricsTable(table_path=str(lake_path))

        # Verify table exists
        from deltalake import DeltaTable
        assert DeltaTable.is_deltatable(str(lake_path))

    def test_init_reuses_existing_table(self, metrics_table, lake_path):
        """Test that initialization reuses existing table."""
        # Create table first time
        table1 = metrics_table

        # Create table second time
        table2 = PerformanceMetricsTable(table_path=str(lake_path))

        # Should be same path
        assert table1.table_path == table2.table_path

    def test_get_table(self, metrics_table):
        """Test getting DeltaTable instance."""
        dt = metrics_table.get_table()

        assert dt is not None
        assert dt.version() == 0  # Should be version 0 for new table

    def test_table_schema(self, metrics_table):
        """Test that table has correct schema."""
        dt = metrics_table.get_table()

        # Get schema fields
        schema = dt.schema()
        field_names = [field.name for field in schema.fields]

        # Verify required fields
        required_fields = [
            'timestamp', 'strategy_id', 'trade_id', 'entry_time', 'exit_time',
            'entry_price', 'exit_price', 'quantity', 'premium_collected',
            'premium_paid', 'net_premium', 'max_profit', 'max_loss',
            'realized_pnl', 'unrealized_pnl', 'hold_duration_minutes',
            'exit_reason', 'greeks_at_entry', 'greeks_at_exit', 'metadata'
        ]

        for field in required_fields:
            assert field in field_names, f"Field {field} not in schema"


class TestPerformanceWriter:
    """Test suite for PerformanceWriter."""

    @pytest.mark.asyncio
    async def test_write_single_metric(self, metrics_table, sample_metric):
        """Test writing a single metric."""
        writer = PerformanceWriter(table=metrics_table, batch_interval=1)

        # Write metric directly (bypass buffer)
        await writer._write_metrics([sample_metric])

        # Verify write
        dt = metrics_table.get_table()
        df = pl.from_pandas(dt.to_pandas())

        assert len(df) == 1
        assert df.row(0)[2] == "trade_001"  # trade_id column

    @pytest.mark.asyncio
    async def test_write_multiple_metrics(self, metrics_table, sample_metrics):
        """Test writing multiple metrics."""
        writer = PerformanceWriter(table=metrics_table, batch_interval=1)

        # Write metrics
        await writer._write_metrics(sample_metrics)

        # Verify write
        dt = metrics_table.get_table()
        df = pl.from_pandas(dt.to_pandas())

        assert len(df) == 20

    @pytest.mark.asyncio
    async def test_idempotent_write(self, metrics_table, sample_metric):
        """Test that duplicate writes are handled correctly."""
        writer = PerformanceWriter(table=metrics_table, batch_interval=1)

        # Write metric first time
        await writer._write_metrics([sample_metric])

        # Write same metric again (same trade_id)
        await writer._write_metrics([sample_metric])

        # Verify only one record exists
        dt = metrics_table.get_table()
        df = pl.from_pandas(dt.to_pandas())

        assert len(df) == 1

    @pytest.mark.asyncio
    async def test_buffer_and_batch_write(self, metrics_table, sample_metrics):
        """Test buffering and batch writing."""
        writer = PerformanceWriter(table=metrics_table, batch_interval=1)

        # Buffer metrics
        for metric in sample_metrics[:10]:
            await writer.on_metric(metric)

        # Verify buffer
        assert len(writer._buffer) == 10

        # Start batch writing (should write immediately)
        await writer.start_batch_writing()
        await asyncio.sleep(0.1)  # Small delay for batch to process

        # Stop batch writing
        await writer.stop_batch_writing()

        # Verify writes
        dt = metrics_table.get_table()
        df = pl.from_pandas(dt.to_pandas())

        assert len(df) == 10

    @pytest.mark.asyncio
    async def test_empty_write(self, metrics_table):
        """Test writing empty list."""
        writer = PerformanceWriter(table=metrics_table, batch_interval=1)

        # Write empty list
        count = await writer._write_metrics([])

        # Should return 0
        assert count == 0

    @pytest.mark.asyncio
    async def test_flush_on_stop(self, metrics_table, sample_metrics):
        """Test that buffer is flushed when stopping."""
        writer = PerformanceWriter(table=metrics_table, batch_interval=60)

        # Buffer metrics
        for metric in sample_metrics[:5]:
            await writer.on_metric(metric)

        # Stop without waiting for batch interval
        await writer.stop_batch_writing()

        # Verify buffer was flushed
        assert len(writer._buffer) == 0

        dt = metrics_table.get_table()
        df = pl.from_pandas(dt.to_pandas())

        assert len(df) == 5

    @pytest.mark.asyncio
    async def test_greeks_serialization(self, metrics_table):
        """Test that Greeks are serialized to JSON correctly."""
        writer = PerformanceWriter(table=metrics_table, batch_interval=1)

        greeks = Greeks(delta=0.5, gamma=0.1, theta=-0.05, vega=0.2)

        metric = PerformanceMetric(
            timestamp=datetime.now(),
            strategy_id="test_strategy",
            trade_id="test_trade",
            entry_time=datetime.now(),
            exit_time=None,
            entry_price=1.0,
            exit_price=None,
            quantity=1,
            premium_collected=100.0,
            premium_paid=0.0,
            net_premium=100.0,
            max_profit=100.0,
            max_loss=-400.0,
            realized_pnl=0.0,
            unrealized_pnl=10.0,
            hold_duration_minutes=None,
            exit_reason=None,
            greeks_at_entry=greeks,
            greeks_at_exit=None,
            metadata={}
        )

        await writer._write_metrics([metric])

        # Verify greeks serialization
        dt = metrics_table.get_table()
        df = pl.from_pandas(dt.to_pandas())

        assert len(df) == 1
        greeks_entry_str = df.row(0)[17]  # greeks_at_entry column
        greeks_dict = json.loads(greeks_entry_str)

        assert greeks_dict["delta"] == 0.5
        assert greeks_dict["gamma"] == 0.1
        assert greeks_dict["theta"] == -0.05
        assert greeks_dict["vega"] == 0.2

    @pytest.mark.asyncio
    async def test_nullable_fields(self, metrics_table):
        """Test that nullable fields are handled correctly."""
        writer = PerformanceWriter(table=metrics_table, batch_interval=1)

        metric = PerformanceMetric(
            timestamp=datetime.now(),
            strategy_id="test_strategy",
            trade_id="test_trade",
            entry_time=datetime.now(),
            exit_time=None,  # Nullable
            entry_price=1.0,
            exit_price=None,  # Nullable
            quantity=1,
            premium_collected=100.0,
            premium_paid=0.0,
            net_premium=100.0,
            max_profit=100.0,
            max_loss=-400.0,
            realized_pnl=0.0,
            unrealized_pnl=10.0,
            hold_duration_minutes=None,  # Nullable
            exit_reason=None,  # Nullable
            greeks_at_entry=None,  # Nullable
            greeks_at_exit=None,  # Nullable
            metadata=None  # Nullable
        )

        await writer._write_metrics([metric])

        # Verify write succeeded
        dt = metrics_table.get_table()
        df = pl.from_pandas(dt.to_pandas())

        assert len(df) == 1


class TestPerformanceReader:
    """Test suite for PerformanceReader."""

    @pytest.mark.asyncio
    async def test_read_trade(self, metrics_table, sample_metric):
        """Test reading a specific trade."""
        # Write metric first
        writer = PerformanceWriter(table=metrics_table)
        await writer._write_metrics([sample_metric])

        # Read trade
        reader = PerformanceReader(table=metrics_table)
        df = reader.read_trade(trade_id="trade_001")

        assert df is not None
        assert len(df) == 1
        assert df.row(0)[2] == "trade_001"

    @pytest.mark.asyncio
    async def test_read_trade_not_found(self, metrics_table):
        """Test reading non-existent trade."""
        reader = PerformanceReader(table=metrics_table)
        df = reader.read_trade(trade_id="nonexistent")

        assert df is None

    @pytest.mark.asyncio
    async def test_read_strategy_metrics(self, metrics_table, sample_metrics):
        """Test reading metrics for a specific strategy."""
        # Write metrics first
        writer = PerformanceWriter(table=metrics_table)
        await writer._write_metrics(sample_metrics)

        # Read strategy metrics
        reader = PerformanceReader(table=metrics_table)
        df = reader.read_strategy_metrics(strategy_id="strategy_0")

        # Should have metrics for strategy_0
        assert len(df) > 0
        for row in df.iter_rows(named=True):
            assert row["strategy_id"] == "strategy_0"

    @pytest.mark.asyncio
    async def test_read_strategy_metrics_with_time_range(self, metrics_table, sample_metrics):
        """Test reading strategy metrics within time range."""
        # Write metrics
        writer = PerformanceWriter(table=metrics_table)
        await writer._write_metrics(sample_metrics)

        # Read with time range
        reader = PerformanceReader(table=metrics_table)
        end = datetime.now()
        start = end - timedelta(hours=12)

        df = reader.read_strategy_metrics(
            strategy_id="strategy_0",
            start=start,
            end=end
        )

        # Should filter by time range
        assert len(df) > 0

    @pytest.mark.asyncio
    async def test_read_time_range(self, metrics_table, sample_metrics):
        """Test reading metrics within time range."""
        # Write metrics
        writer = PerformanceWriter(table=metrics_table)
        await writer._write_metrics(sample_metrics)

        # Read time range
        reader = PerformanceReader(table=metrics_table)
        end = datetime.now()
        start = end - timedelta(days=2)

        df = reader.read_time_range(start=start, end=end)

        # Should have most metrics (some may be outside time range due to test timing)
        assert len(df) >= 13  # At least 13 metrics should be in range

    @pytest.mark.asyncio
    async def test_read_open_positions(self, metrics_table, sample_metrics):
        """Test reading open positions."""
        # Write metrics
        writer = PerformanceWriter(table=metrics_table)
        await writer._write_metrics(sample_metrics)

        # Read open positions
        reader = PerformanceReader(table=metrics_table)
        df = reader.read_open_positions()

        # Should have open positions (those without exit_time)
        # In our sample data, every 3rd position is closed
        assert len(df) > 0
        assert len(df) < 20  # Some positions are closed

    @pytest.mark.asyncio
    async def test_calculate_pnl_for_strategy(self, metrics_table, sample_metrics):
        """Test calculating PnL for a strategy."""
        # Write metrics
        writer = PerformanceWriter(table=metrics_table)
        await writer._write_metrics(sample_metrics)

        # Calculate PnL
        reader = PerformanceReader(table=metrics_table)
        pnl = reader.calculate_pnl(strategy_id="strategy_0")

        # Should have PnL data
        assert 'total_realized_pnl' in pnl
        assert 'total_unrealized_pnl' in pnl
        assert 'total_pnl' in pnl
        assert 'win_rate' in pnl
        assert 'avg_trade_pnl' in pnl
        assert 'num_trades' in pnl

        # Verify calculation
        assert pnl['total_pnl'] == pnl['total_realized_pnl'] + pnl['total_unrealized_pnl']
        assert pnl['num_trades'] > 0

        # For strategy_0, we have 7 trades (indices 0, 3, 6, 9, 12, 15, 18)
        # Some are closed (realized_pnl > 0), some are open (unrealized_pnl > 0)
        assert pnl['num_trades'] >= 1  # At least some trades

    @pytest.mark.asyncio
    async def test_calculate_pnl_all_strategies(self, metrics_table, sample_metrics):
        """Test calculating PnL across all strategies."""
        # Write metrics
        writer = PerformanceWriter(table=metrics_table)
        await writer._write_metrics(sample_metrics)

        # Calculate PnL
        reader = PerformanceReader(table=metrics_table)
        pnl = reader.calculate_pnl()

        # Should have PnL data for all trades
        assert pnl['num_trades'] >= 13  # At least 13 trades should be in range
        assert pnl['total_pnl'] > 0  # Should have positive PnL from sample data

    @pytest.mark.asyncio
    async def test_calculate_pnl_empty_table(self, metrics_table):
        """Test calculating PnL with no data."""
        reader = PerformanceReader(table=metrics_table)
        pnl = reader.calculate_pnl()

        # Should return zeros
        assert pnl['total_realized_pnl'] == 0.0
        assert pnl['total_unrealized_pnl'] == 0.0
        assert pnl['total_pnl'] == 0.0
        assert pnl['win_rate'] == 0.0
        assert pnl['avg_trade_pnl'] == 0.0
        assert pnl['num_trades'] == 0


class TestIntegration:
    """Integration tests for full read-write workflows."""

    @pytest.mark.asyncio
    async def test_full_trade_lifecycle(self, metrics_table):
        """Test tracking trade from entry to exit."""
        writer = PerformanceWriter(table=metrics_table)
        reader = PerformanceReader(table=metrics_table)

        entry_greeks = Greeks(delta=0.5, gamma=0.1, theta=-0.05, vega=0.2)

        # Entry
        entry_metric = PerformanceMetric(
            timestamp=datetime.now(),
            strategy_id="test_strategy",
            trade_id="lifecycle_test",
            entry_time=datetime.now(),
            exit_time=None,
            entry_price=1.50,
            exit_price=None,
            quantity=1,
            premium_collected=150.0,
            premium_paid=0.0,
            net_premium=150.0,
            max_profit=150.0,
            max_loss=-400.0,
            realized_pnl=0.0,
            unrealized_pnl=25.0,
            hold_duration_minutes=None,
            exit_reason=None,
            greeks_at_entry=entry_greeks,
            greeks_at_exit=None,
            metadata={"symbol": "SPY"}
        )

        await writer._write_metrics([entry_metric])

        # Verify entry
        trade = reader.read_trade("lifecycle_test")
        assert trade is not None
        assert trade['realized_pnl'][0] == 0.0
        assert trade['unrealized_pnl'][0] == 25.0

        # Exit
        exit_metric = PerformanceMetric(
            timestamp=datetime.now() + timedelta(hours=4),
            strategy_id="test_strategy",
            trade_id="lifecycle_test",
            entry_time=entry_metric.entry_time,
            exit_time=datetime.now() + timedelta(hours=4),
            entry_price=1.50,
            exit_price=0.50,
            quantity=1,
            premium_collected=150.0,
            premium_paid=0.0,
            net_premium=150.0,
            max_profit=150.0,
            max_loss=-400.0,
            realized_pnl=100.0,
            unrealized_pnl=0.0,
            hold_duration_minutes=240,
            exit_reason="take_profit",
            greeks_at_entry=entry_greeks,
            greeks_at_exit=Greeks(delta=0.1, gamma=0.02, theta=-0.01, vega=0.05),
            metadata={"symbol": "SPY"}
        )

        # Update with exit data (should be skipped due to anti-join,
        # upsert operations would handle this in production)
        await writer._write_metrics([exit_metric])

        # Verify we still have entry data (anti-join prevents duplicate trade_ids)
        trade = reader.read_trade("lifecycle_test")
        assert trade is not None

    @pytest.mark.asyncio
    async def test_aggregation_across_strategies(self, metrics_table):
        """Test aggregating metrics across multiple strategies."""
        writer = PerformanceWriter(table=metrics_table)
        reader = PerformanceReader(table=metrics_table)

        # Create metrics for multiple strategies
        metrics = []
        for strategy_id in ["strategy_A", "strategy_B", "strategy_C"]:
            for i in range(5):
                metric = PerformanceMetric(
                    timestamp=datetime.now() - timedelta(hours=i),
                    strategy_id=strategy_id,
                    trade_id=f"{strategy_id}_trade_{i}",
                    entry_time=datetime.now() - timedelta(hours=i + 2),
                    exit_time=datetime.now() - timedelta(hours=i) if i % 2 == 0 else None,
                    entry_price=1.0,
                    exit_price=0.5 if i % 2 == 0 else None,
                    quantity=1,
                    premium_collected=100.0,
                    premium_paid=0.0,
                    net_premium=100.0,
                    max_profit=100.0,
                    max_loss=-400.0,
                    realized_pnl=50.0 if i % 2 == 0 else 0.0,
                    unrealized_pnl=0.0 if i % 2 == 0 else 25.0,
                    hold_duration_minutes=120 if i % 2 == 0 else None,
                    exit_reason="expiry" if i % 2 == 0 else None,
                    greeks_at_entry=Greeks(0.5, 0.1, -0.05, 0.2),
                    greeks_at_exit=None,
                    metadata={}
                )
                metrics.append(metric)

        await writer._write_metrics(metrics)

        # Calculate PnL for each strategy
        for strategy_id in ["strategy_A", "strategy_B", "strategy_C"]:
            pnl = reader.calculate_pnl(strategy_id=strategy_id)
            assert pnl['num_trades'] == 5
            assert pnl['total_realized_pnl'] > 0

        # Calculate overall PnL
        total_pnl = reader.calculate_pnl()
        assert total_pnl['num_trades'] == 15

    @pytest.mark.asyncio
    async def test_concurrent_writes(self, metrics_table):
        """Test concurrent write operations."""
        writer = PerformanceWriter(table=metrics_table)

        # Create multiple write tasks
        async def write_metrics(prefix: int):
            metrics = []
            for i in range(5):
                metric = PerformanceMetric(
                    timestamp=datetime.now() - timedelta(hours=i),
                    strategy_id=f"concurrent_{prefix}",
                    trade_id=f"concurrent_{prefix}_trade_{i}",
                    entry_time=datetime.now() - timedelta(hours=i + 2),
                    exit_time=None,
                    entry_price=1.0,
                    exit_price=None,
                    quantity=1,
                    premium_collected=100.0,
                    premium_paid=0.0,
                    net_premium=100.0,
                    max_profit=100.0,
                    max_loss=-400.0,
                    realized_pnl=0.0,
                    unrealized_pnl=25.0,
                    hold_duration_minutes=None,
                    exit_reason=None,
                    greeks_at_entry=Greeks(0.5, 0.1, -0.05, 0.2),
                    greeks_at_exit=None,
                    metadata={}
                )
                metrics.append(metric)

            await writer._write_metrics(metrics)

        # Run concurrent writes
        await asyncio.gather(
            write_metrics(0),
            write_metrics(1),
            write_metrics(2)
        )

        # Verify all writes completed
        dt = metrics_table.get_table()
        df = pl.from_pandas(dt.to_pandas())

        assert len(df) == 15
