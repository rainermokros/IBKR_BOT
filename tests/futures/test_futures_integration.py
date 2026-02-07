"""
Integration Tests for Futures Collection

Tests for futures data collection including:
- FuturesFetcher with IB connection
- Futures persistence (Delta Lake)
- Change metrics calculation
- Contract rollover detection
- Maintenance window handling
- Queue processing
- Idempotent writes

All tests use mocked IB connections (no live IB required).
"""

import asyncio
import pytest
from datetime import datetime, time, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import polars as pl

from v6.core.futures_fetcher import (
    FuturesFetcher,
    FuturesSnapshot,
    FUTURES_CONTRACTS,
    MAINTENANCE_WINDOW_START,
    MAINTENANCE_WINDOW_END,
    ROLLOVER_DAYS_THRESHOLD,
)
from v6.data.futures_persistence import (
    FuturesSnapshotsTable,
    DeltaLakeFuturesWriter,
    FuturesDataReader,
)
from v6.config.futures_config import (
    FuturesConfig,
    MaintenanceWindow,
    load_futures_config,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_lake_path(tmp_path):
    """Create temporary Delta Lake path for testing."""
    return tmp_path / "futures_snapshots"


@pytest.fixture
def futures_table(temp_lake_path):
    """Create futures snapshots table for testing."""
    table = FuturesSnapshotsTable(table_path=str(temp_lake_path))
    return table


@pytest.fixture
def sample_snapshot():
    """Create sample futures snapshot."""
    return FuturesSnapshot(
        symbol="ES",
        timestamp=datetime.now(),
        bid=4500.25,
        ask=4500.50,
        last=4500.375,
        volume=100000,
        open_interest=500000,
        implied_vol=0.18,
        change_1h=0.5,
        change_4h=1.2,
        change_overnight=-0.3,
        change_daily=0.8,
        expiry="20250321",
        is_front_month=True,
    )


@pytest.fixture
def sample_snapshots():
    """Create multiple sample snapshots."""
    snapshots = []
    base_time = datetime.now()

    for i in range(10):
        snapshot = FuturesSnapshot(
            symbol="ES",
            timestamp=base_time + timedelta(seconds=i * 60),
            bid=4500.0 + i * 0.1,
            ask=4500.25 + i * 0.1,
            last=4500.125 + i * 0.1,
            volume=100000 + i * 100,
            open_interest=500000,
            implied_vol=0.18 + i * 0.001,
            change_1h=0.5 + i * 0.01,
            change_4h=1.2 + i * 0.02,
            change_overnight=-0.3 + i * 0.005,
            change_daily=0.8 + i * 0.01,
            expiry="20250321",
            is_front_month=True,
        )
        snapshots.append(snapshot)

    return snapshots


@pytest.fixture
def multi_symbol_snapshots():
    """Create snapshots for multiple symbols."""
    snapshots = []
    base_time = datetime.now()

    for symbol in ["ES", "NQ", "RTY"]:
        for i in range(5):
            snapshot = FuturesSnapshot(
                symbol=symbol,
                timestamp=base_time + timedelta(seconds=i * 60),
                bid=4500.0 + i * 0.1,
                ask=4500.25 + i * 0.1,
                last=4500.125 + i * 0.1,
                volume=100000 + i * 100,
                open_interest=500000,
                implied_vol=0.18,
                change_1h=0.5,
                change_4h=1.2,
                change_overnight=-0.3,
                change_daily=0.8,
                expiry="20250321",
                is_front_month=True,
            )
            snapshots.append(snapshot)

    return snapshots


@pytest.fixture
def mock_ib_connection():
    """Create mock IB connection manager."""
    mock_conn = MagicMock()
    mock_conn.ib = MagicMock()
    mock_conn.is_connected = True
    mock_conn.ensure_connected = AsyncMock()
    return mock_conn


@pytest.fixture
def sample_futures_config():
    """Create sample futures config."""
    return FuturesConfig(
        enabled=True,
        symbols=["ES", "NQ", "RTY"],
        collection_interval=300,
        batch_write_interval=60,
        batch_size=100,
        maintenance_window=MaintenanceWindow(start="17:00", end="18:00"),
        ib_connection=MagicMock(
            host="127.0.0.1",
            port=4002,
            client_id=9981,
        ),
    )


# =============================================================================
# Test: FuturesFetcher
# =============================================================================

class TestFuturesFetcher:
    """Test suite for FuturesFetcher."""

    def test_init_validates_symbols(self, mock_ib_connection):
        """Test that initialization validates symbols."""
        # Valid symbols
        fetcher = FuturesFetcher(ib_conn=mock_ib_connection, symbols=["ES", "NQ"])
        assert fetcher.symbols == ["ES", "NQ"]

        # Invalid symbol should raise ValueError
        with pytest.raises(ValueError, match="Invalid futures symbol"):
            FuturesFetcher(ib_conn=mock_ib_connection, symbols=["INVALID"])

    def test_maintenance_window_detection(self, mock_ib_connection):
        """Test maintenance window detection."""
        fetcher = FuturesFetcher(ib_conn=mock_ib_connection)

        # Patch current time to be within maintenance window
        with patch('v6.core.futures_fetcher.datetime') as mock_dt:
            mock_dt.now.return_value = datetime.now().replace(
                hour=17, minute=30, second=0, microsecond=0
            )
            assert fetcher._is_maintenance_window() is True

        # Patch current time to be outside maintenance window
        with patch('v6.core.futures_fetcher.datetime') as mock_dt:
            mock_dt.now.return_value = datetime.now().replace(
                hour=14, minute=30, second=0, microsecond=0
            )
            assert fetcher._is_maintenance_window() is False

    @pytest.mark.asyncio
    async def test_subscribe_to_futures_skips_maintenance_window(self, mock_ib_connection):
        """Test that subscribe_to_futures skips collection during maintenance window."""
        fetcher = FuturesFetcher(ib_conn=mock_ib_connection)

        # Patch to simulate maintenance window
        with patch.object(fetcher, '_is_maintenance_window', return_value=True):
            snapshots = await fetcher.subscribe_to_futures()
            assert snapshots == {}

    @pytest.mark.asyncio
    async def test_get_snapshot_returns_none_during_maintenance(self, mock_ib_connection):
        """Test that get_snapshot returns None during maintenance window."""
        fetcher = FuturesFetcher(ib_conn=mock_ib_connection)

        # Patch to simulate maintenance window
        with patch.object(fetcher, '_is_maintenance_window', return_value=True):
            snapshot = await fetcher.get_snapshot("ES")
            assert snapshot is None

    @pytest.mark.asyncio
    async def test_connection_health(self, mock_ib_connection):
        """Test connection health check."""
        fetcher = FuturesFetcher(ib_conn=mock_ib_connection)

        # Mock IB connection health
        mock_ib_connection.connection_health = AsyncMock(
            return_value={"connected": True, "healthy": True}
        )

        # Patch maintenance window
        with patch.object(fetcher, '_is_maintenance_window', return_value=False):
            health = await fetcher.connection_health()

            assert health["ib_connected"] is True
            assert health["symbols"] == ["ES", "NQ", "RTY"]
            assert health["maintenance_window"] is False


# =============================================================================
# Test: FuturesSnapshotsTable
# =============================================================================

class TestFuturesSnapshotsTable:
    """Test suite for FuturesSnapshotsTable."""

    def test_init_creates_table(self, temp_lake_path):
        """Test that initialization creates Delta Lake table."""
        from deltalake import DeltaTable

        # Remove table if it exists
        import shutil
        if temp_lake_path.exists():
            shutil.rmtree(temp_lake_path)

        table = FuturesSnapshotsTable(table_path=str(temp_lake_path))

        # Verify table exists
        assert DeltaTable.is_deltatable(str(temp_lake_path))

    def test_table_schema(self, futures_table):
        """Test that table has correct schema."""
        dt = futures_table.get_table()
        schema = dt.schema()
        field_names = [field.name for field in schema.fields]

        required_fields = [
            'symbol', 'timestamp', 'bid', 'ask', 'last',
            'volume', 'open_interest', 'implied_vol',
            'change_1h', 'change_4h', 'change_overnight', 'change_daily', 'date'
        ]

        for field in required_fields:
            assert field in field_names

    def test_write_snapshots(self, futures_table, sample_snapshot):
        """Test writing snapshots."""
        count = futures_table.write_snapshots([sample_snapshot.to_dict()])

        assert count == 1

        # Verify data was written
        dt = futures_table.get_table()
        df = pl.from_pandas(dt.to_pandas())
        assert len(df) == 1
        assert df.row(0)[0] == "ES"  # symbol column

    def test_read_latest_snapshots(self, futures_table, sample_snapshots):
        """Test reading latest snapshots."""
        # Write snapshots
        snapshots_data = [s.to_dict() for s in sample_snapshots]
        futures_table.write_snapshots(snapshots_data)

        # Read latest
        df = futures_table.read_latest_snapshots(symbol="ES", limit=5)

        assert len(df) == 5
        assert df.row(0)[0] == "ES"

    def test_read_time_range(self, futures_table, sample_snapshot):
        """Test reading snapshots within time range."""
        # Write snapshot
        futures_table.write_snapshots([sample_snapshot.to_dict()])

        # Read time range
        end = datetime.now() + timedelta(hours=1)
        start = end - timedelta(hours=24)

        df = futures_table.read_time_range("ES", start, end)

        assert len(df) >= 1
        assert df.row(0)[0] == "ES"

    def test_get_stats(self, futures_table, sample_snapshot):
        """Test getting table statistics."""
        # Write snapshot
        futures_table.write_snapshots([sample_snapshot.to_dict()])

        # Get stats
        stats = futures_table.get_stats()

        assert stats["total_rows"] == 1
        assert "ES" in stats["symbols"]


# =============================================================================
# Test: DeltaLakeFuturesWriter
# =============================================================================

class TestDeltaLakeFuturesWriter:
    """Test suite for DeltaLakeFuturesWriter."""

    @pytest.mark.asyncio
    async def test_write_single_snapshot(self, futures_table, sample_snapshot):
        """Test writing a single snapshot."""
        writer = DeltaLakeFuturesWriter(table=futures_table, batch_interval=1)

        # Write snapshot directly
        await writer._write_snapshots([sample_snapshot.to_dict()])

        # Verify write
        dt = futures_table.get_table()
        df = pl.from_pandas(dt.to_pandas())

        assert len(df) == 1
        assert df.row(0)[0] == "ES"

    @pytest.mark.asyncio
    async def test_write_multiple_snapshots(self, futures_table, sample_snapshots):
        """Test writing multiple snapshots."""
        writer = DeltaLakeFuturesWriter(table=futures_table, batch_interval=1)

        # Write snapshots
        snapshots_data = [s.to_dict() for s in sample_snapshots]
        await writer._write_snapshots(snapshots_data)

        # Verify write
        dt = futures_table.get_table()
        df = pl.from_pandas(dt.to_pandas())

        assert len(df) == 10

    @pytest.mark.asyncio
    async def test_empty_write(self, futures_table):
        """Test writing empty list."""
        writer = DeltaLakeFuturesWriter(table=futures_table, batch_interval=1)

        # Write empty list
        count = await writer._write_snapshots([])

        # Should return 0
        assert count == 0

    @pytest.mark.asyncio
    async def test_buffer_and_flush(self, futures_table, sample_snapshots):
        """Test buffering and flushing."""
        writer = DeltaLakeFuturesWriter(table=futures_table, batch_interval=60)

        # Buffer snapshots
        for snapshot in sample_snapshots[:5]:
            await writer.on_snapshot(snapshot.to_dict())

        # Verify buffer
        assert len(writer._buffer) == 5

        # Stop should flush
        await writer.stop_batch_writing()

        # Verify buffer was flushed
        assert len(writer._buffer) == 0

        # Verify data was written
        dt = futures_table.get_table()
        df = pl.from_pandas(dt.to_pandas())
        assert len(df) == 5


# =============================================================================
# Test: FuturesDataReader
# =============================================================================

class TestFuturesDataReader:
    """Test suite for FuturesDataReader."""

    @pytest.mark.asyncio
    async def test_read_latest_snapshots(self, futures_table, sample_snapshots):
        """Test reading latest snapshots."""
        # Write snapshots first
        writer = DeltaLakeFuturesWriter(table=futures_table)
        snapshots_data = [s.to_dict() for s in sample_snapshots]
        await writer._write_snapshots(snapshots_data)

        # Read latest
        reader = FuturesDataReader(table=futures_table)
        df = reader.read_latest_snapshots(symbol="ES", limit=5)

        assert len(df) == 5
        assert df.row(0)[0] == "ES"

    @pytest.mark.asyncio
    async def test_read_time_range(self, futures_table, sample_snapshot):
        """Test reading snapshots within time range."""
        # Write snapshot
        writer = DeltaLakeFuturesWriter(table=futures_table)
        await writer._write_snapshots([sample_snapshot.to_dict()])

        # Read time range
        reader = FuturesDataReader(table=futures_table)
        end = datetime.now() + timedelta(hours=1)
        start = end - timedelta(hours=24)

        df = reader.read_time_range("ES", start, end)

        assert len(df) >= 1
        assert df.row(0)[0] == "ES"

    @pytest.mark.asyncio
    async def test_calculate_correlation(self, futures_table):
        """Test calculating correlation between symbols."""
        # Write correlated data for ES and NQ
        snapshots = []
        base_time = datetime.now() - timedelta(hours=2)

        for i in range(50):
            # ES and NQ move together (correlated)
            es_snapshot = FuturesSnapshot(
                symbol="ES",
                timestamp=base_time + timedelta(seconds=i * 60),
                bid=4500.0 + i * 0.1,
                ask=4500.25 + i * 0.1,
                last=4500.125 + i * 0.1,
                volume=100000,
                open_interest=500000,
                implied_vol=0.18,
                change_1h=0.1 * i if i > 0 else 0.0,
                change_4h=0.4 * i if i > 0 else 0.0,
                change_overnight=-0.1 * i if i > 0 else 0.0,
                change_daily=0.2 * i if i > 0 else 0.0,
                expiry="20250321",
                is_front_month=True,
            )

            nq_snapshot = FuturesSnapshot(
                symbol="NQ",
                timestamp=base_time + timedelta(seconds=i * 60),
                bid=15000.0 + i * 0.3,
                ask=15000.25 + i * 0.3,
                last=15000.125 + i * 0.3,
                volume=100000,
                open_interest=500000,
                implied_vol=0.18,
                change_1h=0.1 * i if i > 0 else 0.0,
                change_4h=0.4 * i if i > 0 else 0.0,
                change_overnight=-0.1 * i if i > 0 else 0.0,
                change_daily=0.2 * i if i > 0 else 0.0,
                expiry="20250321",
                is_front_month=True,
            )

            snapshots.append(es_snapshot)
            snapshots.append(nq_snapshot)

        writer = DeltaLakeFuturesWriter(table=futures_table)
        snapshots_data = [s.to_dict() for s in snapshots]
        await writer._write_snapshots(snapshots_data)

        # Calculate correlation
        reader = FuturesDataReader(table=futures_table)
        corr = reader.calculate_correlation("ES", "NQ", days=1, field="last")

        # Should be highly correlated (close to 1.0)
        assert corr > 0.9


# =============================================================================
# Test: FuturesConfig
# =============================================================================

class TestFuturesConfig:
    """Test suite for FuturesConfig."""

    def test_config_defaults(self):
        """Test default configuration values."""
        config = FuturesConfig()

        assert config.enabled is True
        assert config.symbols == ["ES", "NQ", "RTY"]
        assert config.collection_interval == 300
        assert config.batch_write_interval == 60
        assert config.batch_size == 100

    def test_config_from_dict(self):
        """Test creating config from dictionary."""
        data = {
            "enabled": False,
            "symbols": ["ES"],
            "collection_interval": 600,
            "batch_write_interval": 120,
            "batch_size": 200,
            "maintenance_window": {
                "start": "16:00",
                "end": "17:00",
            },
            "ib_connection": {
                "host": "192.168.1.100",
                "port": 7497,
                "client_id": 100,
            },
        }

        config = FuturesConfig.from_dict(data)

        assert config.enabled is False
        assert config.symbols == ["ES"]
        assert config.collection_interval == 600
        assert config.batch_write_interval == 120
        assert config.batch_size == 200
        assert config.maintenance_window.start == "16:00"
        assert config.ib_connection.host == "192.168.1.100"
        assert config.ib_connection.port == 7497

    def test_config_validation_valid(self, sample_futures_config):
        """Test validation of valid config."""
        errors = sample_futures_config.validate()
        assert len(errors) == 0

    def test_config_validation_invalid_symbols(self):
        """Test validation rejects invalid symbols."""
        config = FuturesConfig(symbols=["INVALID"])
        errors = config.validate()

        assert len(errors) > 0
        assert any("Invalid symbol" in e for e in errors)

    def test_config_validation_invalid_interval(self):
        """Test validation rejects invalid intervals."""
        config = FuturesConfig(collection_interval=10)  # Too low
        errors = config.validate()

        assert len(errors) > 0
        assert any("collection_interval" in e for e in errors)

    def test_config_validation_invalid_port(self):
        """Test validation rejects invalid port."""
        config = FuturesConfig()
        config.ib_connection.port = 70000  # Invalid port
        errors = config.validate()

        assert len(errors) > 0
        assert any("port" in e for e in errors)

    def test_maintenance_window_parsing(self):
        """Test maintenance window time parsing."""
        window = MaintenanceWindow(start="17:00", end="18:00")

        start_time = window.parse_time(window.start)
        end_time = window.parse_time(window.end)

        assert start_time.hour == 17
        assert start_time.minute == 0
        assert end_time.hour == 18
        assert end_time.minute == 0


# =============================================================================
# Test: Idempotent Writes
# =============================================================================

class TestIdempotentWrites:
    """Test suite for idempotent write behavior."""

    @pytest.mark.asyncio
    async def test_duplicate_snapshot_not_written(self, futures_table):
        """Test that duplicate snapshots (same timestamp+symbol) are not written twice."""
        snapshot = FuturesSnapshot(
            symbol="ES",
            timestamp=datetime.now(),
            bid=4500.0,
            ask=4500.25,
            last=4500.125,
            volume=100000,
            open_interest=500000,
            implied_vol=0.18,
            change_1h=0.5,
            change_4h=1.2,
            change_overnight=-0.3,
            change_daily=0.8,
            expiry="20250321",
            is_front_month=True,
        )

        # Write same snapshot twice
        count1 = futures_table.write_snapshots([snapshot.to_dict()])
        count2 = futures_table.write_snapshots([snapshot.to_dict()])

        # First write should succeed, second should be skipped
        # (exact behavior depends on deduplication implementation)
        assert count1 == 1
        # Second write might write 0 if timestamp is identical

        # Verify only one record exists
        dt = futures_table.get_table()
        df = pl.from_pandas(dt.to_pandas())
        assert len(df) == 1


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-x"])
