#!/usr/bin/env python3
"""
Verification Script for V6 Data Collection System

This script verifies that all components of the data collection system
are properly created and ready to use.

Usage:
    python verify_data_collection.py
"""

import sys
from pathlib import Path

def check_file_exists(filepath, description):
    """Check if file exists and print status."""
    path = Path(filepath)
    exists = path.exists()
    size = f"{path.stat().st_size / 1024:.1f} KB" if exists else "N/A"

    status = "✓" if exists else "✗"
    print(f"  {status} {description}")
    print(f"     Path: {filepath}")
    print(f"     Size: {size}")
    print()

    return exists

def check_file_syntax(filepath):
    """Check if Python file compiles without syntax errors."""
    import subprocess

    try:
        result = subprocess.run(
            ["python", "-m", "py_compile", filepath],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            print(f"  ✓ Syntax OK")
            return True
        else:
            print(f"  ✗ Syntax Error:")
            print(f"     {result.stderr}")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False

def main():
    """Run verification checks."""
    print("=" * 70)
    print("V6 Data Collection System - Verification")
    print("=" * 70)
    print()

    all_ok = True

    # Check 1: Core market data fetcher
    print("1. OptionDataFetcher (Core Component)")
    print("-" * 70)
    exists = check_file_exists(
        "src/v6/core/market_data_fetcher.py",
        "Market data fetcher with IB API integration"
    )
    if exists:
        if not check_file_syntax("src/v6/core/market_data_fetcher.py"):
            all_ok = False

    # Check 2: Option snapshots table
    print("2. OptionSnapshotsTable (Delta Lake Persistence)")
    print("-" * 70)
    exists = check_file_exists(
        "src/v6/data/option_snapshots.py",
        "Delta Lake table for option snapshots"
    )
    if exists:
        if not check_file_syntax("src/v6/data/option_snapshots.py"):
            all_ok = False

    # Check 3: Data collector
    print("3. DataCollector (Background Service)")
    print("-" * 70)
    exists = check_file_exists(
        "src/v6/scripts/data_collector.py",
        "Continuous data collection service"
    )
    if exists:
        if not check_file_syntax("src/v6/scripts/data_collector.py"):
            all_ok = False

    # Check 4: Test suite
    print("4. Test Suite (Data Collection)")
    print("-" * 70)
    exists = check_file_exists(
        "src/v6/scripts/test_data_collection.py",
        "End-to-end test suite"
    )
    if exists:
        if not check_file_syntax("src/v6/scripts/test_data_collection.py"):
            all_ok = False

    # Check 5: PaperTrader integration
    print("5. PaperTrader Integration")
    print("-" * 70)
    exists = check_file_exists(
        "src/v6/orchestration/paper_trader.py",
        "Paper trading orchestrator with data collector"
    )
    if exists:
        if not check_file_syntax("src/v6/orchestration/paper_trader.py"):
            all_ok = False

        # Check for integration markers
        if exists:
            content = Path("src/v6/orchestration/paper_trader.py").read_text()
            has_import = "from src.v6.scripts.data_collector import DataCollector" in content
            has_init = "self.data_collector = DataCollector(" in content
            has_start = "await self.data_collector.start()" in content
            has_stop = "await self.data_collector.stop()" in content

            print(f"  {'✓' if has_import else '✗'} DataCollector import")
            print(f"  {'✓' if has_init else '✗'} DataCollector initialization")
            print(f"  {'✓' if has_start else '✗'} DataCollector start() call")
            print(f"  {'✓' if has_stop else '✗'} DataCollector stop() call")
            print()

            if not (has_import and has_init and has_start and has_stop):
                all_ok = False

    # Check 6: Documentation
    print("6. Documentation")
    print("-" * 70)
    doc_files = [
        ("DATA_COLLECTION_SYSTEM.md", "Comprehensive technical documentation"),
        ("DATA_COLLECTION_QUICKSTART.md", "Quick start reference guide"),
        ("DATA_COLLECTION_IMPLEMENTATION_SUMMARY.md", "Implementation summary"),
    ]

    for filename, description in doc_files:
        exists = check_file_exists(filename, description)
        if not exists:
            all_ok = False

    # Check 7: Dependencies
    print("7. Dependencies")
    print("-" * 70)
    try:
        import polars as pl
        print(f"  ✓ polars: {pl.__version__}")
    except ImportError:
        print(f"  ✗ polars: Not installed")
        all_ok = False

    try:
        from deltalake import DeltaTable
        print(f"  ✓ deltalake: Installed")
    except ImportError:
        print(f"  ✗ deltalake: Not installed")
        all_ok = False

    try:
        from ib_async import IB
        print(f"  ✓ ib_async: Installed")
    except ImportError:
        print(f"  ✗ ib_async: Not installed")
        all_ok = False

    try:
        from loguru import logger
        print(f"  ✓ loguru: Installed")
    except ImportError:
        print(f"  ✗ loguru: Not installed")
        all_ok = False

    print()

    # Check 8: Directory structure
    print("8. Directory Structure")
    print("-" * 70)
    dirs = [
        ("src/v6/core", "Core components"),
        ("src/v6/data", "Data persistence layer"),
        ("src/v6/scripts", "Scripts and automation"),
        ("src/v6/orchestration", "Orchestration layer"),
        ("data/lake", "Delta Lake storage"),
    ]

    for dirpath, description in dirs:
        path = Path(dirpath)
        exists = path.exists()
        print(f"  {'✓' if exists else '✗'} {description}: {dirpath}")
        if not exists:
            all_ok = False

    print()

    # Final summary
    print("=" * 70)
    if all_ok:
        print("✓ ALL CHECKS PASSED")
        print()
        print("The V6 data collection system is ready!")
        print()
        print("Next steps:")
        print("  1. Start IB Gateway (paper trading account)")
        print("  2. Run test suite:")
        print("     python -m src.v6.scripts.test_data_collection")
        print("  3. Start paper trading system:")
        print("     python -m src.v6.orchestration.paper_trader")
        print()
        return 0
    else:
        print("✗ SOME CHECKS FAILED")
        print()
        print("Please review the errors above and fix them before proceeding.")
        print()
        return 1

if __name__ == "__main__":
    sys.exit(main())
