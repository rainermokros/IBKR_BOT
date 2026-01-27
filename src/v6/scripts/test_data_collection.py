"""
Test Data Collection System

This script tests the market data collection system:
1. Create option snapshots table
2. Connect to IB
3. Fetch option chain for one symbol
4. Calculate IV Rank
5. Store snapshots to Delta Lake
6. Read back and verify

Usage:
    python -m src.v6.scripts.test_data_collection
"""

import asyncio
from datetime import datetime

from loguru import logger

from src.v6.config.paper_config import PaperTradingConfig
from src.v6.core.market_data_fetcher import OptionDataFetcher
from src.v6.data.option_snapshots import OptionSnapshotsTable
from src.v6.utils.ib_connection import IBConnectionManager


async def test_data_collection():
    """Test data collection system end-to-end."""

    logger.info("=" * 60)
    logger.info("Testing Data Collection System")
    logger.info("=" * 60)

    # Load config
    try:
        config = PaperTradingConfig.load_from_file("config/paper_trading.yaml")
        logger.info(f"✓ Loaded config: symbols={config.allowed_symbols}")
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        logger.info("Using default config")
        config = PaperTradingConfig(
            ib_host="127.0.0.1",
            ib_port=7497,
            ib_client_id=1,
            allowed_symbols=["SPY"],
            data_dir="data/lake",
        )

    # Create option snapshots table
    logger.info("\n1. Creating OptionSnapshotsTable...")
    option_snapshots_table = OptionSnapshotsTable(
        table_path=f"{config.data_dir}/option_snapshots",
    )
    logger.info("✓ OptionSnapshotsTable created")

    # Create IB connection
    logger.info("\n2. Connecting to IB...")
    ib_conn = IBConnectionManager(
        host=config.ib_host,
        port=config.ib_port,
        client_id=config.ib_client_id,
    )

    try:
        await ib_conn.connect()
        logger.info(f"✓ Connected to IB at {config.ib_host}:{config.ib_port}")

        # Create option fetcher
        logger.info("\n3. Creating OptionDataFetcher...")
        option_fetcher = OptionDataFetcher(
            ib_conn=ib_conn,
            option_snapshots_table=option_snapshots_table,
            symbols=[config.allowed_symbols[0]],  # Test with first symbol only
        )
        logger.info(f"✓ OptionDataFetcher created for {config.allowed_symbols[0]}")

        # Test 1: Fetch VIX
        logger.info("\n4. Testing VIX fetch...")
        vix = await option_fetcher.get_vix()
        logger.info(f"✓ VIX: {vix:.2f}")

        # Test 2: Fetch underlying trend
        logger.info("\n5. Testing underlying trend...")
        symbol = config.allowed_symbols[0]
        trend = await option_fetcher.get_underlying_trend(symbol)
        logger.info(f"✓ {symbol} trend: {trend}")

        # Test 3: Calculate IV Rank (will use default if no data)
        logger.info("\n6. Testing IV Rank calculation...")
        iv_rank = await option_fetcher.calculate_iv_rank(symbol)
        logger.info(f"✓ {symbol} IV Rank: {iv_rank:.1f}")

        # Test 4: Fetch option chain
        logger.info(f"\n7. Fetching option chain for {symbol}...")
        logger.info("   This may take 30-60 seconds...")
        contracts = await option_fetcher.fetch_option_chain(symbol)
        logger.info(f"✓ Fetched {len(contracts)} contracts")

        # Test 5: Write snapshots to Delta Lake
        if contracts:
            logger.info(f"\n8. Writing {len(contracts)} snapshots to Delta Lake...")
            written = option_snapshots_table.write_snapshots(contracts)
            logger.info(f"✓ Wrote {written} snapshots to Delta Lake")

            # Test 6: Read back snapshots
            logger.info(f"\n9. Reading back latest chain for {symbol}...")
            latest_chain = option_snapshots_table.read_latest_chain(symbol)
            logger.info(f"✓ Read {len(latest_chain)} contracts from Delta Lake")

            # Display sample data
            if len(latest_chain) > 0:
                logger.info("\n10. Sample contract data:")
                sample = latest_chain.row(0, named=True)
                logger.info(f"   Symbol: {sample['symbol']}")
                logger.info(f"   Strike: {sample['strike']}")
                logger.info(f"   Expiry: {sample['expiry']}")
                logger.info(f"   Right: {sample['right']}")
                logger.info(f"   Bid/Ask: {sample['bid']}/{sample['ask']}")
                logger.info(f"   IV: {sample['iv']:.2%}" if sample['iv'] else "   IV: N/A")
                logger.info(f"   Delta: {sample['delta']:.3f}" if sample['delta'] else "   Delta: N/A")

            # Test 7: Get table stats
            logger.info("\n11. Getting table statistics...")
            stats = option_snapshots_table.get_snapshot_stats()
            logger.info(f"✓ Total rows: {stats['total_rows']}")
            logger.info(f"✓ Symbols: {stats['symbols']}")
            if stats['date_range']:
                logger.info(f"✓ Date range: {stats['date_range']['start']} to {stats['date_range']['end']}")
        else:
            logger.warning("No contracts to write - skipping write/read tests")

        # Test 8: Connection health
        logger.info("\n12. Testing connection health...")
        health = await option_fetcher.connection_health()
        logger.info(f"✓ IB connected: {health['ib_connected']}")
        logger.info(f"✓ Circuit breaker: {health['circuit_breaker_state']}")
        logger.info(f"✓ Healthy: {health['healthy']}")

        logger.info("\n" + "=" * 60)
        logger.info("All tests completed successfully!")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        raise
    finally:
        # Disconnect
        logger.info("\nDisconnecting from IB...")
        await ib_conn.disconnect()
        logger.info("✓ Disconnected")


if __name__ == "__main__":
    logger.info("Starting data collection test...")
    logger.info(f"Test time: {datetime.now()}")
    logger.info("")

    try:
        asyncio.run(test_data_collection())
    except KeyboardInterrupt:
        logger.info("\nTest interrupted by user")
    except Exception as e:
        logger.error(f"\nTest failed with error: {e}")
        exit(1)
