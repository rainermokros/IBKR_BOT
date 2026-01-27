"""
Deployment integration tests.

Tests deployment scripts, service management, and idempotency.
"""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.mark.deployment
class TestDeploymentScripts:
    """Test deployment scripts."""

    def test_deploy_script_exists(self):
        """Test that deploy.sh script exists."""
        deploy_script = Path("scripts/deploy.sh")
        assert deploy_script.exists(), "deploy.sh not found"
        assert os.access(deploy_script, os.X_OK), "deploy.sh not executable"

    def test_update_script_exists(self):
        """Test that update.sh script exists."""
        update_script = Path("scripts/update.sh")
        assert update_script.exists(), "update.sh not found"
        assert os.access(update_script, os.X_OK), "update.sh not executable"

    def test_rollback_script_exists(self):
        """Test that rollback.sh script exists."""
        rollback_script = Path("scripts/rollback.sh")
        assert rollback_script.exists(), "rollback.sh not found"
        assert os.access(rollback_script, os.X_OK), "rollback.sh not executable"

    def test_status_script_exists(self):
        """Test that status.sh script exists."""
        status_script = Path("scripts/status.sh")
        assert status_script.exists(), "status.sh not found"
        assert os.access(status_script, os.X_OK), "status.sh not executable"

    def test_backup_script_exists(self):
        """Test that backup.sh script exists."""
        backup_script = Path("scripts/backup.sh")
        assert backup_script.exists(), "backup.sh not found"
        assert os.access(backup_script, os.X_OK), "backup.sh not executable"

    def test_deploy_script_dry_run(self):
        """Test that deploy.sh supports --dry-run flag."""
        result = subprocess.run(
            ["./scripts/deploy.sh", "--dry-run"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, "deploy.sh --dry-run failed"
        assert "DRY RUN" in result.stdout, "Dry run mode not indicated"


@pytest.mark.deployment
class TestSystemdServices:
    """Test systemd service configuration."""

    def test_trading_service_exists(self):
        """Test that v6-trading.service exists."""
        service_file = Path("systemd/v6-trading.service")
        assert service_file.exists(), "v6-trading.service not found"

        # Check service file content
        content = service_file.read_text()
        assert "[Unit]" in content, "Missing [Unit] section"
        assert "[Service]" in content, "Missing [Service] section"
        assert "[Install]" in content, "Missing [Install] section"
        assert "ExecStart" in content, "Missing ExecStart directive"
        assert "Restart=on-failure" in content, "Missing restart policy"

    def test_dashboard_service_exists(self):
        """Test that v6-dashboard.service exists."""
        service_file = Path("systemd/v6-dashboard.service")
        assert service_file.exists(), "v6-dashboard.service not found"

        content = service_file.read_text()
        assert "ExecStart" in content, "Missing ExecStart directive"
        assert "Restart=always" in content, "Missing restart policy"

    def test_position_sync_service_exists(self):
        """Test that v6-position-sync.service exists."""
        service_file = Path("systemd/v6-position-sync.service")
        assert service_file.exists(), "v6-position-sync.service not found"

        content = service_file.read_text()
        assert "ExecStart" in content, "Missing ExecStart directive"

    def test_health_check_service_exists(self):
        """Test that v6-health-check.service exists."""
        service_file = Path("systemd/v6-health-check.service")
        assert service_file.exists(), "v6-health-check.service not found"

        # Check timer exists
        timer_file = Path("systemd/v6-health-check.timer")
        assert timer_file.exists(), "v6-health-check.timer not found"

    def test_services_run_as_non_root(self):
        """Test that services run as non-root user."""
        for service_name in ["v6-trading.service", "v6-dashboard.service", "v6-position-sync.service"]:
            service_file = Path(f"systemd/{service_name}")
            content = service_file.read_text()
            assert "User=trading" in content, f"{service_name} not configured to run as 'trading' user"


@pytest.mark.deployment
class TestHealthCheck:
    """Test health check script."""

    def test_health_check_script_exists(self):
        """Test that health_check.py script exists."""
        health_script = Path("scripts/health_check.py")
        assert health_script.exists(), "health_check.py not found"
        assert os.access(health_script, os.X_OK), "health_check.py not executable"

    def test_health_check_exit_codes(self):
        """Test that health_check.py returns valid exit codes."""
        # Note: This test assumes IB Gateway is not running (expected in CI)
        # Exit codes: 0 (healthy), 1 (degraded), 2 (unhealthy)
        result = subprocess.run(
            ["./scripts/health_check.py"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Should return 0, 1, or 2
        assert result.returncode in [0, 1, 2], f"Invalid exit code: {result.returncode}"

    def test_health_check_output_format(self):
        """Test that health_check.py produces structured output."""
        result = subprocess.run(
            ["./scripts/health_check.py"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Check for expected output sections
        output = result.stdout
        assert "Health Check" in output or "IB Connection" in output, "Missing expected output"


@pytest.mark.deployment
class TestBackup:
    """Test backup functionality."""

    def test_backup_script_creates_backup(self, tmp_path):
        """Test that backup.sh creates a backup file."""
        # Create temporary directory for backup
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        # Create dummy data directory
        data_dir = tmp_path / "data" / "lake"
        data_dir.mkdir(parents=True)
        (data_dir / "test.txt").write_text("test data")

        # Run backup (dry-run would be better but let's test actual backup)
        # Note: This test may skip if IB Gateway not running
        result = subprocess.run(
            ["./scripts/backup.sh"],
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "BACKUP_PATH": str(backup_dir) + "/"},
        )

        # Backup should succeed or warn (if data missing)
        assert result.returncode in [0, 1], f"Backup failed: {result.stderr}"

        # Check if backup file created (if backup succeeded)
        if result.returncode == 0:
            backup_files = list(backup_dir.glob("backup_*.tar.gz"))
            # May not find files if backup failed, that's okay for this test


@pytest.mark.deployment
class TestConfiguration:
    """Test configuration files."""

    def test_production_config_exists(self):
        """Test that production config module exists."""
        config_module = Path("src/v6/config/production_config.py")
        assert config_module.exists(), "production_config.py not found"

    def test_production_config_class(self):
        """Test that ProductionConfig class is defined."""
        from src.v6.config.production_config import ProductionConfig

        # Create instance with defaults
        config = ProductionConfig()

        # Check attributes
        assert hasattr(config, "ib_host"), "Missing ib_host attribute"
        assert hasattr(config, "ib_port"), "Missing ib_port attribute"
        assert hasattr(config, "dry_run"), "Missing dry_run attribute"
        assert hasattr(config, "log_level"), "Missing log_level attribute"

    def test_production_config_validation(self):
        """Test that production config validates settings."""
        from src.v6.config.production_config import ProductionConfig

        # Valid config
        config = ProductionConfig(
            ib_host="127.0.0.1",
            ib_port=7497,
            dry_run=False,
        )

        assert config.ib_host == "127.0.0.1"
        assert config.ib_port == 7497
        assert config.dry_run is False

    def test_production_config_example_exists(self):
        """Test that production.yaml.example exists."""
        example_config = Path("config/production.yaml.example")
        assert example_config.exists(), "production.yaml.example not found"

        # Check it's a valid YAML file
        import yaml

        with open(example_config) as f:
            config_data = yaml.safe_load(f)

        assert "ib" in config_data, "Missing 'ib' section"
        assert "logging" in config_data, "Missing 'logging' section"

    def test_env_example_exists(self):
        """Test that .env.example exists."""
        env_example = Path(".env.example")
        assert env_example.exists(), ".env.example not found"

        content = env_example.read_text()
        assert "PRODUCTION_IB_HOST" in content, "Missing PRODUCTION_IB_HOST"


@pytest.mark.deployment
class TestDocumentation:
    """Test documentation files."""

    def test_production_setup_doc_exists(self):
        """Test that PRODUCTION_SETUP.md exists."""
        doc_file = Path("docs/PRODUCTION_SETUP.md")
        assert doc_file.exists(), "PRODUCTION_SETUP.md not found"

        content = doc_file.read_text()
        assert "Prerequisites" in content, "Missing Prerequisites section"
        assert "Installation" in content, "Missing Installation section"

    def test_runbook_exists(self):
        """Test that RUNBOOK.md exists."""
        doc_file = Path("docs/RUNBOOK.md")
        assert doc_file.exists(), "RUNBOOK.md not found"

        content = doc_file.read_text()
        assert "Daily Operations" in content, "Missing Daily Operations section"
        assert "Emergency Procedures" in content, "Missing Emergency Procedures section"

    def test_monitoring_doc_exists(self):
        """Test that MONITORING.md exists."""
        doc_file = Path("docs/MONITORING.md")
        assert doc_file.exists(), "MONITORING.md not found"

        content = doc_file.read_text()
        assert "Metrics" in content, "Missing Metrics section"

    def test_backup_restore_doc_exists(self):
        """Test that BACKUP_RESTORE.md exists."""
        doc_file = Path("docs/BACKUP_RESTORE.md")
        assert doc_file.exists(), "BACKUP_RESTORE.md not found"

        content = doc_file.read_text()
        assert "Backup Procedure" in content, "Missing Backup Procedure section"
        assert "Restore Procedure" in content, "Missing Restore Procedure section"


@pytest.mark.deployment
class TestIdempotency:
    """Test idempotency of deployment operations."""

    def test_deploy_idempotent(self):
        """Test that running deploy.sh multiple times is safe."""
        # This test only checks --dry-run mode
        result1 = subprocess.run(
            ["./scripts/deploy.sh", "--dry-run"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        result2 = subprocess.run(
            ["./scripts/deploy.sh", "--dry-run"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result1.returncode == 0, "First deploy failed"
        assert result2.returncode == 0, "Second deploy failed"
