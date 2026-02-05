"""
Alert Routing System

This module provides alert management with routing to Slack, email, and logging.
Implements rate limiting to prevent alert spam while ensuring critical alerts get through.

Key features:
- Multi-channel alerts: Slack webhook, email, logging
- Severity levels: critical, warning, info
- Rate limiting: max 1 alert/hour per source (critical bypasses limit)
- Color-coded Slack messages
- SMTP email support
"""

import dataclasses
import os
import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path
from typing import Literal

import requests
from loguru import logger

# Import pandas for type hints (actual import in methods to avoid circular dependency)
import pandas as pd


@dataclass
class Alert:
    """
    Alert data structure.

    Attributes:
        severity: Alert severity level ('critical', 'warning', 'info')
        source: Alert source identifier (e.g., 'data_quality', 'correlation')
        message: Human-readable alert message
        metadata: Additional context about the alert
    """
    severity: Literal["critical", "warning", "info"]
    source: str
    message: str
    metadata: dict


class AlertManager:
    """
    Manage alert routing to multiple channels with rate limiting.

    Sends alerts to Slack, email, and logs based on severity and configuration.
    Implements rate limiting to prevent spam while ensuring critical alerts get through.
    """

    # Color codes for Slack messages
    SLACK_COLORS = {
        "critical": "#ff0000",  # Red
        "warning": "#ff9900",  # Orange
        "info": "#36a64f",  # Green
    }

    def __init__(
        self,
        enabled_channels: list[str] | None = None,
        slack_webhook_url: str | None = None,
        email_config: dict | None = None,
        rate_limit_minutes: int = 60,
    ):
        """
        Initialize alert manager.

        Args:
            enabled_channels: List of channels to enable ('slack', 'email', 'log')
            slack_webhook_url: Slack webhook URL (reads from SLACK_WEBHOOK_URL env var if not provided)
            email_config: Email configuration dict with 'smtp_server', 'smtp_port', 'sender', 'password'
            rate_limit_minutes: Minutes between alerts for same source (critical bypasses)
        """
        self.enabled_channels = enabled_channels or ["log"]
        self.slack_webhook_url = slack_webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        self.email_config = email_config or {}
        self.rate_limit_minutes = rate_limit_minutes

        # Rate limiting: track last alert time per source
        self._last_alert_times: dict[str, datetime] = {}

        logger.info(
            f"AlertManager initialized: channels={self.enabled_channels}, "
            f"rate_limit={rate_limit_minutes}min"
        )

    def _should_send_alert(self, alert: Alert) -> bool:
        """
        Check if alert should be sent based on rate limiting.

        Args:
            alert: Alert to check

        Returns:
            True if alert should be sent, False otherwise
        """
        # Critical alerts always bypass rate limiting
        if alert.severity == "critical":
            return True

        # Check if same source alerted recently
        last_alert_time = self._last_alert_times.get(alert.source)

        if last_alert_time is None:
            return True

        time_since_last = datetime.now() - last_alert_time

        if time_since_last < timedelta(minutes=self.rate_limit_minutes):
            logger.debug(
                f"Alert from {alert.source} rate limited "
                f"({time_since_total_seconds := time_since_last.total_seconds() / 60:.1f}min ago)"
            )
            return False

        return True

    def _update_last_alert_time(self, alert: Alert) -> None:
        """
        Update last alert time for source.

        Args:
            alert: Alert that was sent
        """
        self._last_alert_times[alert.source] = datetime.now()

    def _send_slack(self, alert: Alert) -> bool:
        """
        Send alert to Slack via webhook.

        Args:
            alert: Alert to send

        Returns:
            True if sent successfully, False otherwise
        """
        if "slack" not in self.enabled_channels:
            return False

        if not self.slack_webhook_url:
            logger.warning("Slack webhook URL not configured, skipping Slack alert")
            return False

        try:
            # Build Slack message
            color = self.SLACK_COLORS.get(alert.severity, "#36a64f")

            # Format metadata fields
            fields = []
            for key, value in alert.metadata.items():
                fields.append({
                    "title": key,
                    "value": str(value),
                    "short": True,
                })

            payload = {
                "attachments": [
                    {
                        "color": color,
                        "title": f"[{alert.severity.upper()}] {alert.source}",
                        "text": alert.message,
                        "fields": fields,
                        "footer": "V6 Trading System",
                        "ts": int(datetime.now().timestamp()),
                    }
                ]
            }

            # Send to Slack
            response = requests.post(
                self.slack_webhook_url,
                json=payload,
                timeout=10,
            )

            response.raise_for_status()

            logger.info(f"✓ Slack alert sent: {alert.source} - {alert.message[:50]}...")
            return True

        except requests.RequestException as e:
            logger.error(f"Failed to send Slack alert: {e}")
            return False

    def _send_email(self, alert: Alert) -> bool:
        """
        Send alert via email.

        Args:
            alert: Alert to send

        Returns:
            True if sent successfully, False otherwise
        """
        if "email" not in self.enabled_channels:
            return False

        # Check email configuration
        required_keys = ["smtp_server", "smtp_port", "sender", "password", "recipients"]
        if not all(key in self.email_config for key in required_keys):
            logger.warning("Email configuration incomplete, skipping email alert")
            return False

        try:
            # Build email message
            subject = f"[{alert.severity.upper()}] {alert.source}: {alert.message[:50]}"

            # Format metadata as text
            metadata_text = "\n".join(
                f"{key}: {value}" for key, value in alert.metadata.items()
            )

            body = f"""
Alert Details:
-------------
Severity: {alert.severity}
Source: {alert.source}
Message: {alert.message}

Metadata:
{metadata_text}

Timestamp: {datetime.now().isoformat()}
"""

            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = self.email_config["sender"]
            msg["To"] = ", ".join(self.email_config["recipients"])

            # Send email
            with smtplib.SMTP(
                self.email_config["smtp_server"],
                self.email_config["smtp_port"],
            ) as server:
                server.starttls()
                server.login(
                    self.email_config["sender"],
                    self.email_config["password"],
                )
                server.send_message(msg)

            logger.info(f"✓ Email alert sent: {alert.source} - {alert.message[:50]}...")
            return True

        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
            return False

    def _log_alert(self, alert: Alert) -> None:
        """
        Log alert with appropriate severity level.

        Args:
            alert: Alert to log
        """
        message = f"[{alert.source}] {alert.message}"

        if alert.metadata:
            message += f" | Metadata: {alert.metadata}"

        if alert.severity == "critical":
            logger.error(message)
        elif alert.severity == "warning":
            logger.warning(message)
        else:
            logger.info(message)

    def send_alert(self, alert: Alert) -> bool:
        """
        Send alert to all enabled channels.

        Args:
            alert: Alert to send

        Returns:
            True if alert was sent to at least one channel, False otherwise
        """
        # Check rate limiting
        if not self._should_send_alert(alert):
            logger.debug(f"Alert rate limited: {alert.source}")
            return False

        # Send to all enabled channels
        sent = False

        # Log all alerts (always enabled)
        self._log_alert(alert)
        sent = True

        # Send to Slack
        if self._send_slack(alert):
            sent = True

        # Send email
        if self._send_email(alert):
            sent = True

        # Update last alert time
        if sent:
            self._update_last_alert_time(alert)

        return sent

    def send_data_quality_alert(
        self,
        health_score: int,
        anomaly_count: int,
        metadata: dict | None = None,
    ) -> bool:
        """
        Send data quality alert based on health score and anomalies.

        Args:
            health_score: Data quality health score (0-100)
            anomaly_count: Number of anomalies detected
            metadata: Additional metadata

        Returns:
            True if alert was sent, False otherwise
        """
        # Determine severity
        if health_score < 50 or anomaly_count > 10:
            severity: Literal["critical", "warning", "info"] = "critical"
            message = (
                f"Critical data quality issue detected. "
                f"Health score: {health_score}/100, Anomalies: {anomaly_count}"
            )
        elif health_score < 80 or anomaly_count > 5:
            severity = "warning"
            message = (
                f"Data quality degradation detected. "
                f"Health score: {health_score}/100, Anomalies: {anomaly_count}"
            )
        else:
            severity = "info"
            message = (
                f"Data quality monitoring update. "
                f"Health score: {health_score}/100, Anomalies: {anomaly_count}"
            )

        # Build alert
        alert = Alert(
            severity=severity,
            source="data_quality",
            message=message,
            metadata={
                "health_score": health_score,
                "anomaly_count": anomaly_count,
                **(metadata or {}),
            },
        )

        return self.send_alert(alert)

    def send_correlation_alert(
        self,
        divergence_score: float,
        correlated_symbols: list[str],
        metadata: dict | None = None,
    ) -> bool:
        """
        Send correlation divergence alert.

        Args:
            divergence_score: Correlation divergence score
            correlated_symbols: List of symbols with correlation issues
            metadata: Additional metadata

        Returns:
            True if alert was sent, False otherwise
        """
        # Determine severity
        if divergence_score > 0.8:
            severity: Literal["critical", "warning", "info"] = "critical"
            message = (
                f"Critical correlation divergence detected. "
                f"Divergence score: {divergence_score:.2f}, Symbols: {correlated_symbols}"
            )
        elif divergence_score > 0.5:
            severity = "warning"
            message = (
                f"Correlation divergence detected. "
                f"Divergence score: {divergence_score:.2f}, Symbols: {correlated_symbols}"
            )
        else:
            severity = "info"
            message = (
                f"Correlation monitoring update. "
                f"Divergence score: {divergence_score:.2f}"
            )

        # Build alert
        alert = Alert(
            severity=severity,
            source="correlation",
            message=message,
            metadata={
                "divergence_score": divergence_score,
                "correlated_symbols": ", ".join(correlated_symbols),
                **(metadata or {}),
            },
        )

        return self.send_alert(alert)


class CorrelationDivergenceMonitor:
    """
    Monitor correlation divergences for all futures-ETF pairs.

    Checks all 9 pairs (ES/NQ/RTY vs SPY/QQQ/IWM) for divergence using z-score analysis.
    Implements rate limiting (1 alert/day per pair) and market hours filtering.
    Logs divergences to Delta Lake for historical tracking.
    """

    # Market hours: 8am-5pm ET
    MARKET_HOUR_START = 8
    MARKET_HOUR_END = 17

    def __init__(
        self,
        alert_manager: AlertManager,
        rate_limit_hours: int = 24,  # 1 alert per day per pair
        divergence_table_path: str = "data/lake/correlation_divergences",
    ):
        """
        Initialize correlation divergence monitor.

        Args:
            alert_manager: AlertManager instance for sending alerts
            rate_limit_hours: Hours between alerts for same pair (default 24)
            divergence_table_path: Path to Delta Lake table for logging divergences
        """
        self.alert_manager = alert_manager
        self.rate_limit_hours = rate_limit_hours
        self.divergence_table_path = Path(divergence_table_path)

        # Track last alert time per pair
        self._last_alert_times: dict[str, datetime] = {}

        # Ensure divergence table exists
        self._ensure_divergence_table()

        logger.info(
            f"CorrelationDivergenceMonitor initialized: "
            f"rate_limit={rate_limit_hours}h"
        )

    def _ensure_divergence_table(self) -> None:
        """Create Delta Lake table for correlation divergences if it doesn't exist."""
        from deltalake import DeltaTable, write_deltalake
        import pandas as pd

        if DeltaTable.is_deltatable(str(self.divergence_table_path)):
            return

        # Create empty DataFrame with schema
        schema_df = pd.DataFrame(
            {
                "timestamp": [],
                "pair_name": [],
                "correlation": [],
                "z_score": [],
                "resolved": [],
            }
        )

        # Write to Delta Lake
        write_deltalake(
            str(self.divergence_table_path),
            schema_df,
            mode="overwrite",
        )

        logger.info(f"Created correlation divergences table: {self.divergence_table_path}")

    def is_market_hours(self, timestamp: datetime) -> bool:
        """
        Check if timestamp is during market hours (8am-5pm ET, weekdays only).

        Args:
            timestamp: Timestamp to check

        Returns:
            True if during market hours, False otherwise
        """
        # Check if weekday (Monday=0, Friday=5)
        if timestamp.weekday() > 4:
            return False

        # Market hours: 8am-5pm ET
        hour = timestamp.hour
        return self.MARKET_HOUR_START <= hour < self.MARKET_HOUR_END

    def _should_alert_pair(self, pair_name: str) -> bool:
        """
        Check if pair should alert based on rate limiting.

        Args:
            pair_name: Pair name to check

        Returns:
            True if alert should be sent, False otherwise
        """
        last_alert_time = self._last_alert_times.get(pair_name)

        if last_alert_time is None:
            return True

        time_since_last = datetime.now() - last_alert_time

        if time_since_last < timedelta(hours=self.rate_limit_hours):
            logger.debug(
                f"Correlation alert for {pair_name} rate limited "
                f"({time_since_last.total_seconds() / 3600:.1f}h ago)"
            )
            return False

        return True

    def _update_last_alert_time(self, pair_name: str) -> None:
        """
        Update last alert time for pair.

        Args:
            pair_name: Pair name
        """
        self._last_alert_times[pair_name] = datetime.now()

    def _log_divergence(
        self,
        result: "DivergenceResult",
    ) -> None:
        """
        Log divergence to Delta Lake for historical tracking.

        Args:
            result: DivergenceResult to log
        """
        from deltalake import write_deltalake
        import pandas as pd

        try:
            divergence_df = pd.DataFrame(
                {
                    "timestamp": [result.timestamp],
                    "pair_name": [result.pair_name],
                    "correlation": [result.current_correlation],
                    "z_score": [result.z_score],
                    "resolved": [False],  # Will be updated when correlation normalizes
                }
            )

            write_deltalake(
                str(self.divergence_table_path),
                divergence_df,
                mode="append",
            )

            logger.info(f"Logged divergence to Delta Lake: {result.pair_name}")

        except Exception as e:
            logger.error(f"Failed to log divergence to Delta Lake: {e}")

    def monitor_all_pairs(
        self,
        hours_back: int = 2,
    ) -> list:
        """
        Monitor all futures-ETF pairs for divergence.

        Args:
            hours_back: Hours to look back for correlation data

        Returns:
            List of divergence results (empty if no divergences)
        """
        from v6.monitoring.correlation_tracker import CorrelationTracker

        divergences = []

        # Check all pairs
        for futures_symbol, etf_symbol in CorrelationTracker.ALL_PAIRS:
            # Skip if not during market hours
            if not self.is_market_hours(datetime.now()):
                logger.debug("Outside market hours, skipping correlation check")
                continue

            # Create tracker
            tracker = CorrelationTracker(
                futures_symbol=futures_symbol,
                etf_symbol=etf_symbol,
            )

            # Get current divergence status
            result = tracker.get_current_divergence_status()

            # Check if divergence detected
            if result.divergence_detected:
                # Check rate limiting
                if not self._should_alert_pair(result.pair_name):
                    logger.debug(
                        f"Correlation divergence for {result.pair_name} rate limited"
                    )
                    continue

                # Send alert
                self.alert_manager.send_correlation_alert(
                    divergence_score=abs(result.z_score) / 2.0,  # Normalize to 0-1
                    correlated_symbols=[result.pair_name],
                    metadata={
                        "pair": result.pair_name,
                        "correlation": result.current_correlation,
                        "z_score": result.z_score,
                        "mean_correlation": result.mean_correlation,
                        "std_correlation": result.std_correlation,
                    },
                )

                # Log to Delta Lake
                self._log_divergence(result)

                # Update last alert time
                self._update_last_alert_time(result.pair_name)

                divergences.append(result)

                logger.warning(
                    f"Correlation divergence alert sent: {result.pair_name} "
                    f"(z-score: {result.z_score:.2f})"
                )

        return divergences

    def get_recent_divergences(
        self,
        hours_back: int = 24,
    ) -> pd.DataFrame:
        """
        Get recent divergences from Delta Lake.

        Args:
            hours_back: Hours to look back

        Returns:
            DataFrame of recent divergences
        """
        from deltalake import DeltaTable
        import pandas as pd

        try:
            if not DeltaTable.is_deltatable(str(self.divergence_table_path)):
                return pd.DataFrame()

            table = DeltaTable(str(self.divergence_table_path))

            # Load all data and filter in Python (avoid Delta Lake type issues)
            df = table.to_pandas()

            if df.empty:
                return pd.DataFrame()

            # Filter by timestamp in Python
            cutoff_time = datetime.now() - timedelta(hours=hours_back)
            df = df[df["timestamp"] >= cutoff_time]

            return df.sort_values("timestamp", ascending=False)

        except Exception as e:
            logger.error(f"Failed to load recent divergences: {e}")
            return pd.DataFrame()
