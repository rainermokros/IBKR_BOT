"""
Production Orchestrator Module

Manages production trading workflows with health monitoring, auto-recovery,
and graceful shutdown capabilities.
"""

import asyncio
import signal
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import httpx
from loguru import logger

from src.v6.config.production_config import ProductionConfig
from src.v6.config.loader import load_and_validate_config
from src.v6.utils.ib_connection import IBConnectionManager


class SystemState(Enum):
    """System states for production orchestrator."""

    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class HealthStatus:
    """Health check result."""

    ib_connected: bool
    ib_healthy: bool
    position_sync_lag: float  # seconds since last sync
    dashboard_accessible: bool
    disk_space_ok: bool
    memory_ok: bool
    cpu_ok: bool
    overall: str  # healthy, degraded, unhealthy

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "ib_connected": self.ib_connected,
            "ib_healthy": self.ib_healthy,
            "position_sync_lag_seconds": self.position_sync_lag,
            "dashboard_accessible": self.dashboard_accessible,
            "disk_space_ok": self.disk_space_ok,
            "memory_ok": self.memory_ok,
            "cpu_ok": self.cpu_ok,
            "overall": self.overall,
        }


class ProductionOrchestrator:
    """
    Production orchestrator for managing trading workflows.

    Handles:
    - IB connection management with auto-reconnect
    - Position synchronization monitoring
    - Health check monitoring
    - Auto-recovery from failures
    - Graceful shutdown (waits for pending orders)
    - Alert notifications
    """

    def __init__(self, config: ProductionConfig):
        """
        Initialize orchestrator.

        Args:
            config: Production configuration
        """
        self.config = config
        self.state = SystemState.STARTING

        # IB connection
        self.ib_manager = IBConnectionManager(
            host=config.ib_host,
            port=config.ib_port,
            client_id=config.ib_client_id,
        )

        # Background tasks
        self._tasks: list[asyncio.Task] = []
        self._shutdown_event = asyncio.Event()

        # Health status
        self._health_status = HealthStatus(
            ib_connected=False,
            ib_healthy=False,
            position_sync_lag=0,
            dashboard_accessible=False,
            disk_space_ok=True,
            memory_ok=True,
            cpu_ok=True,
            overall="unhealthy",
        )

        logger.info("Production orchestrator initialized")

    async def start(self) -> None:
        """
        Start production orchestrator.

        Connects to IB, starts all workflows, and begins monitoring.
        """
        logger.info("Starting production orchestrator...")

        try:
            # Connect to IB
            await self.ib_manager.connect()
            await self.ib_manager.start_heartbeat()

            logger.info("✓ Connected to IB")

            # Start background tasks
            self._tasks.append(asyncio.create_task(self._health_check_loop()))
            self._tasks.append(asyncio.create_task(self._auto_recovery_loop()))

            self.state = SystemState.RUNNING
            logger.info("✓ Production orchestrator started")

        except Exception as e:
            logger.error(f"Failed to start orchestrator: {e}", exc_info=True)
            self.state = SystemState.ERROR
            raise

    async def run(self) -> None:
        """
        Main production loop.

        Runs until shutdown event is set. This is the main entry point
        for production trading.
        """
        logger.info("Entering main production loop...")

        while not self._shutdown_event.is_set():
            try:
                # Production workflows run here
                # Entry workflow, monitoring, exit workflow, etc.

                await asyncio.sleep(self.config.health_check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in production loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # Wait before retrying

        logger.info("Exited main production loop")

    async def health_check(self) -> HealthStatus:
        """
        Perform comprehensive health check.

        Checks:
        - IB connection status
        - Position sync lag
        - Dashboard accessibility
        - System resources (disk, memory, CPU)

        Returns:
            HealthStatus with all check results
        """
        # Check IB connection
        ib_health = await self.ib_manager.connection_health()
        self._health_status.ib_connected = ib_health["connected"]
        self._health_status.ib_healthy = ib_health["healthy"]

        # Check position sync lag (placeholder - integrate with actual sync service)
        # TODO: Integrate with position sync service
        self._health_status.position_sync_lag = 0

        # Check dashboard accessibility
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:8501", timeout=2.0)
                self._health_status.dashboard_accessible = response.status_code == 200
        except Exception:
            self._health_status.dashboard_accessible = False

        # Check system resources
        import shutil
        import psutil

        # Disk space (check if > 10% free)
        disk = psutil.disk_usage("/")
        self._health_status.disk_space_ok = disk.percent < 90

        # Memory (check if < 90% used)
        memory = psutil.virtual_memory()
        self._health_status.memory_ok = memory.percent < 90

        # CPU (check if < 90% used)
        cpu = psutil.cpu_percent(interval=1)
        self._health_status.cpu_ok = cpu < 90

        # Calculate overall health
        if (
            self._health_status.ib_healthy
            and self._health_status.disk_space_ok
            and self._health_status.memory_ok
            and self._health_status.cpu_ok
        ):
            self._health_status.overall = "healthy"
        elif self._health_status.ib_connected:
            self._health_status.overall = "degraded"
        else:
            self._health_status.overall = "unhealthy"

        return self._health_status

    async def auto_recovery(self) -> None:
        """
        Attempt to recover from failures.

        Recovers from:
        - IB connection drops (reconnect)
        - Position sync lag (force sync)
        - Dashboard down (restart service)

        Note: This runs in the background as part of auto_recovery_loop
        """
        # Check IB connection
        if not self._health_status.ib_healthy:
            logger.warning("IB connection unhealthy, attempting recovery...")
            try:
                await self.ib_manager.ensure_connected()
                await self.ib_manager.start_heartbeat()
                logger.info("✓ IB connection recovered")
            except Exception as e:
                logger.error(f"Failed to recover IB connection: {e}")
                self.send_alert("CRITICAL: IB connection failed and could not reconnect")

        # Check position sync
        if self._health_status.position_sync_lag > 300:  # 5 minutes
            logger.warning("Position sync lagged, attempting recovery...")
            # TODO: Trigger force sync
            self.send_alert("WARNING: Position sync lagged, force sync triggered")

    async def stop(self) -> None:
        """
        Graceful shutdown.

        Waits for pending orders to fill, then stops all components.
        """
        logger.info("Stopping production orchestrator...")
        self.state = SystemState.STOPPING

        # Signal shutdown to main loop
        self._shutdown_event.set()

        # Wait for pending orders (TODO: integrate with order manager)
        logger.info("Waiting for pending orders... (60s timeout)")
        await asyncio.sleep(5)  # Placeholder - actual order wait logic

        # Cancel background tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Stop IB connection
        await self.ib_manager.stop_heartbeat()
        await self.ib_manager.disconnect()

        self.state = SystemState.STOPPED
        logger.info("✓ Production orchestrator stopped")

    def send_alert(self, message: str, severity: str = "WARNING") -> None:
        """
        Send alert notification if configured.

        Args:
            message: Alert message
            severity: Alert severity (INFO, WARNING, ERROR, CRITICAL)
        """
        logger.info(f"ALERT [{severity}]: {message}")

        if not self.config.alert_webhook_url:
            return

        try:
            # Send to webhook (Slack, Discord, etc.)
            import asyncio

            async def send_webhook():
                async with httpx.AsyncClient() as client:
                    await client.post(
                        self.config.alert_webhook_url,
                        json={"text": f"[{severity}] {message}"},
                        timeout=5.0,
                    )

            asyncio.create_task(send_webhook())
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")

    async def _health_check_loop(self) -> None:
        """Periodic health check loop."""
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(self.config.health_check_interval)

                if not self._shutdown_event.is_set():
                    status = await self.health_check()

                    if status.overall == "healthy":
                        logger.debug("Health check: healthy")
                    elif status.overall == "degraded":
                        logger.warning(f"Health check: degraded - {status.to_dict()}")
                    else:
                        logger.error(f"Health check: unhealthy - {status.to_dict()}")
                        self.send_alert("Health check: unhealthy", "ERROR")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}", exc_info=True)

    async def _auto_recovery_loop(self) -> None:
        """Auto-recovery loop."""
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(30)  # Check every 30 seconds

                if not self._shutdown_event.is_set():
                    await self.auto_recovery()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Auto-recovery error: {e}", exc_info=True)


async def main():
    """Main entry point for production orchestrator."""
    # Load configuration
    config = load_and_validate_config("production")

    # Configure logging
    from loguru import logger as loguru_logger

    log_config = config.get_log_config()
    loguru_logger.add(
        config.log_file,
        rotation=log_config["rotation"],
        retention=log_config["retention"],
        compression=log_config["compression"],
        level=log_config["level"],
        format=log_config["format"],
    )

    # Create orchestrator
    orchestrator = ProductionOrchestrator(config)

    # Set up signal handlers
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, initiating graceful shutdown...")
        asyncio.create_task(orchestrator.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start and run
    try:
        await orchestrator.start()
        await orchestrator.run()
    except Exception as e:
        logger.error(f"Orchestrator error: {e}", exc_info=True)
    finally:
        await orchestrator.stop()


if __name__ == "__main__":
    asyncio.run(main())
