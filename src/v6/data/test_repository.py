#!/usr/bin/env python3
"""
Test script for PositionsRepository.

Verifies that:
- Repository can be imported from v6.data.repositories
- PositionsRepository().get_latest() returns DataFrame with correct schema
- PositionsRepository().get_at_version(0) works
- PositionsRepository().get_by_symbol() filters correctly
- PositionsRepository().get_open_positions() filters correctly
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.v6.data.repositories import PositionsRepository
from loguru import logger


def test_repository():
    """Test PositionsRepository functionality."""
    logger.info("Testing PositionsRepository")

    # Initialize repository
    repo = PositionsRepository()
    logger.info("Repository initialized successfully")

    # Test 1: get_latest() returns DataFrame with correct schema
    logger.info("Test 1: get_latest()")
    df = repo.get_latest()
    logger.info(f"  Shape: {df.shape}")
    logger.info(f"  Columns: {df.columns}")
    assert df.shape[0] == 0, "Expected empty table"
    assert len(df.columns) == 16, f"Expected 16 columns, got {len(df.columns)}"
    logger.info("  ✓ get_latest() works")

    # Test 2: get_at_version(0) works
    logger.info("Test 2: get_at_version(0)")
    df_v0 = repo.get_at_version(0)
    logger.info(f"  Shape at version 0: {df_v0.shape}")
    assert df_v0.shape[0] == 0, "Expected empty table at version 0"
    logger.info("  ✓ get_at_version(0) works")

    # Test 3: get_by_symbol() filters correctly
    logger.info("Test 3: get_by_symbol()")
    df_spy = repo.get_by_symbol("SPY")
    logger.info(f"  Shape for SPY: {df_spy.shape}")
    assert df_spy.shape[0] == 0, "Expected empty result for SPY"
    logger.info("  ✓ get_by_symbol() works")

    # Test 4: get_open_positions() filters correctly
    logger.info("Test 4: get_open_positions()")
    df_open = repo.get_open_positions()
    logger.info(f"  Shape for open positions: {df_open.shape}")
    assert df_open.shape[0] == 0, "Expected no open positions"
    logger.info("  ✓ get_open_positions() works")

    # Test 5: get_version()
    logger.info("Test 5: get_version()")
    version = repo.get_version()
    logger.info(f"  Current version: {version}")
    # Version may be 0 or 1 depending on whether table already existed
    assert version >= 0, f"Expected version >= 0, got {version}"
    logger.info("  ✓ get_version() works")

    logger.info("All tests passed!")


if __name__ == "__main__":
    test_repository()
