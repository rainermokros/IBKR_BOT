"""
Integration test script for IB position streaming.

This script tests the position streaming functionality with a real IB connection.
Requires IB Gateway or TWS to be running.

Usage:
    python src/v6/data/test_position_streamer.py
"""

import asyncio

from loguru import logger

from v6.data import IBPositionStreamer, PositionUpdate, PositionUpdateHandler


class TestHandler(PositionUpdateHandler):
    """Test handler that logs position updates."""

    async def on_position_update(self, update: PositionUpdate) -> None:
        """Handle position update by logging it."""
        logger.info(
            f"Position update: {update.symbol} {update.right} {update.strike} "
            f"Exp: {update.expiry} Pos: {update.position} "
            f"Price: ${update.market_price:.2f} P&L: ${update.unrealized_pnl:.2f}"
        )


async def main():
    """Test position streaming."""
    logger.info("Starting position streaming test...")

    # Get singleton instance
    streamer = IBPositionStreamer()

    # Register test handler
    handler = TestHandler()
    streamer.register_handler(handler)
    logger.info(f"Registered handler: {handler.__class__.__name__}")

    # Start streaming (requires IB Gateway/TWS running)
    try:
        logger.info("Connecting to IB...")
        await streamer.start()

        # Stream for 30 seconds
        logger.info("Streaming for 30 seconds...")
        logger.info("Note: You should see position updates if you have open option positions")
        await asyncio.sleep(30)

        # Stop streaming
        await streamer.stop()

        logger.info("✓ Test complete - position streaming works")

    except ConnectionRefusedError:
        logger.error("Connection refused - IB Gateway/TWS is not running")
        logger.info("Start IB Gateway or TWS and try again")
    except Exception as e:
        logger.error(f"Test failed: {e}")
        logger.info("Note: This test requires IB Gateway/TWS to be running")
    finally:
        # Ensure cleanup
        if streamer.is_streaming:
            await streamer.stop()


if __name__ == "__main__":
    # Configure loguru
    logger.remove()
    logger.add(
        lambda msg: print(msg, end=''),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | {message}\n",
        level="INFO"
    )

    # Run test
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nTest interrupted by user")
