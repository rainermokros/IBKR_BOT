#!/usr/bin/env python3
"""
Position Sync Script - Sync IB positions to Delta Lake

Fetches current positions from IB Gateway and writes to Delta Lake.
This should run on a schedule (e.g., every 5 minutes) to keep position
data current for health checks and monitoring.

Usage:
    python scripts/sync_positions.py

The script will:
1. Connect to IB Gateway
2. Fetch all current option positions
3. Write to data/lake/position_updates Delta Lake table
4. Log summary of synced positions
"""

import asyncio
import sys
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict

import numpy as np
import polars as pl
from deltalake import DeltaTable, write_deltalake
from ib_async import IB
from loguru import logger

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

DELTA_PATH = "data/lake/position_updates"


async def fetch_ib_positions() -> List[Dict]:
    """
    Fetch current option positions from IB Gateway.

    Returns:
        List of position dictionaries
    """
    ib = IB()
    try:
        logger.info("Connecting to IB Gateway...")
        await ib.connectAsync(
            host='127.0.0.1',
            port=4002,
            clientId=9960,  # Unique clientId for position sync
            timeout=10
        )
        logger.success("✓ Connected to IB Gateway")

        # Wait for positions to be loaded
        await asyncio.sleep(0.5)

        # Get all positions directly
        positions = list(ib.positions())

        if not positions:
            logger.info("No positions found in IB account")
            ib.disconnect()
            return []

        # Filter and format option positions
        option_positions = []
        for position in positions:
            if position.position == 0:
                continue  # Skip closed positions

            contract = position.contract
            if not hasattr(contract, 'right'):
                continue  # Skip non-options

            # Note: marketPrice, marketValue, unrealizedPNL are not directly available
            # They need to be fetched via tickers or calculated
            # For now, we'll sync the basic position data with NaN for missing values
            option_positions.append({
                'conid': contract.conId,
                'symbol': contract.symbol,
                'right': contract.right,
                'strike': contract.strike,
                'expiry': contract.lastTradeDateOrContractMonth,
                'position': position.position,
                'market_price': np.nan,
                'market_value': np.nan,
                'average_cost': position.avgCost if position.avgCost else np.nan,
                'unrealized_pnl': np.nan,
                'timestamp': datetime.now(),
                'date': date.today(),
            })

        ib.disconnect()
        logger.success(f"✓ Fetched {len(option_positions)} positions from IB")
        return option_positions

    except Exception as e:
        logger.error(f"Failed to fetch positions from IB: {e}")
        raise


def write_positions_to_delta_lake(positions: List[Dict]) -> None:
    """
    Write positions to Delta Lake table.

    Args:
        positions: List of position dictionaries
    """
    if not positions:
        logger.info("No positions to write to Delta Lake")
        return

    # Create DataFrame
    df = pl.DataFrame(positions)

    # Write to Delta Lake (overwrite mode - we want current state)
    try:
        write_deltalake(
            DELTA_PATH,
            df,
            mode="overwrite",
        )
        logger.success(f"✓ Wrote {len(positions)} positions to {DELTA_PATH}")
    except Exception as e:
        logger.error(f"Failed to write positions to Delta Lake: {e}")
        raise


async def main():
    """
    Main entry point for position sync.
    """
    logger.info("=" * 80)
    logger.info("POSITION SYNC - IB Gateway → Delta Lake")
    logger.info("=" * 80)
    logger.info(f"Time: {datetime.now()}")
    logger.info("")

    try:
        # Fetch positions from IB
        positions = await fetch_ib_positions()

        # Write to Delta Lake
        write_positions_to_delta_lake(positions)

        # Summary
        logger.info("")
        logger.info("=" * 80)
        logger.info("POSITION SYNC SUMMARY")
        logger.info("=" * 80)

        if positions:
            # Group by symbol
            by_symbol = {}
            for pos in positions:
                symbol = pos['symbol']
                if symbol not in by_symbol:
                    by_symbol[symbol] = []
                by_symbol[symbol].append(pos)

            for symbol, pos_list in by_symbol.items():
                logger.info(f"  {symbol}: {len(pos_list)} leg(s)")

            logger.success(f"✓ Successfully synced {len(positions)} positions")
        else:
            logger.info("  No positions to sync")

        return 0

    except Exception as e:
        logger.error(f"Position sync failed: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
