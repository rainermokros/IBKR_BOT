"""Shared pytest fixtures for v6 trading system tests."""

import pytest
import sys
import tempfile
import shutil
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Import all fixtures for global availability
from tests.fixtures.ib_fixtures import *
from tests.fixtures.strategy_fixtures import *
from tests.fixtures.market_fixtures import *


@pytest.fixture(scope="session")
def test_lake_path():
    """
    Create a temporary Delta Lake directory for testing.

    This fixture creates a temporary directory for Delta Lake tables
    that will be automatically cleaned up after all tests complete.

    Returns:
        Path: Path to temporary Delta Lake directory

    Example:
        def test_delta_lake(test_lake_path):
            lake_path = test_lake_path / "positions"
            # Use lake_path for Delta Lake operations
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="v6_test_lake_"))
    yield temp_dir
    # Cleanup after all tests
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def lake_path(test_lake_path, tmp_path):
    """
    Create a fresh Delta Lake directory for each test.

    This fixture creates a temporary directory for Delta Lake tables
    that will be automatically cleaned up after each test.

    Returns:
        Path: Path to temporary Delta Lake directory

    Example:
        def test_with_lake(lake_path):
            positions_path = lake_path / "positions"
            # Use positions_path for Delta Lake operations
    """
    return tmp_path / "lake"
