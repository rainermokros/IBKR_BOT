"""
Tests for Paper Trading Configuration

Tests configuration validation and safety limit enforcement.
"""

import pytest
from datetime import datetime

from src.v6.config import PaperTradingConfig


class TestPaperTradingConfig:
    """Test PaperTradingConfig validation and safety limits."""

    def test_default_config_enforces_dry_run(self):
        """Test that default config enforces dry_run=True."""
        config = PaperTradingConfig()
        assert config.dry_run is True

    def test_config_validates_required_fields(self):
        """Test that config validates required fields."""
        # Should not raise with valid config
        config = PaperTradingConfig(
            ib_host="127.0.0.1",
            ib_port=7497,
            ib_client_id=2,
        )
        assert config.ib_host == "127.0.0.1"
        assert config.ib_port == 7497
        assert config.ib_client_id == 2

    def test_config_rejects_production_port(self):
        """Test that config rejects port 7496 (production)."""
        with pytest.raises(ValueError, match="Port 7496 is for production"):
            PaperTradingConfig(ib_port=7496)

    def test_config_enforces_max_positions_limit(self):
        """Test that config enforces max_positions <= 10."""
        with pytest.raises(ValueError, match="max_positions.*too high"):
            PaperTradingConfig(max_positions=11)

    def test_config_allows_reasonable_max_positions(self):
        """Test that config allows reasonable max_positions."""
        config = PaperTradingConfig(max_positions=10)
        assert config.max_positions == 10

    def test_config_enforces_max_order_size_limit(self):
        """Test that config enforces max_order_size <= 5."""
        with pytest.raises(ValueError, match="max_order_size.*too high"):
            PaperTradingConfig(max_order_size=6)

    def test_config_rejects_empty_allowed_symbols(self):
        """Test that config rejects empty symbol whitelist."""
        with pytest.raises(ValueError, match="allowed_symbols cannot be empty"):
            PaperTradingConfig(allowed_symbols=[])

    def test_config_uppercases_symbols(self):
        """Test that config converts symbols to uppercase."""
        config = PaperTradingConfig(allowed_symbols=["spy", "qqq", "iwm"])
        assert config.allowed_symbols == ["SPY", "QQQ", "IWM"]

    def test_validate_symbol_whitelist(self):
        """Test symbol whitelist validation."""
        config = PaperTradingConfig(allowed_symbols=["SPY", "QQQ", "IWM"])

        assert config.validate_symbol("SPY") is True
        assert config.validate_symbol("QQQ") is True
        assert config.validate_symbol("AAPL") is False

    def test_validate_position_count(self):
        """Test position count validation."""
        config = PaperTradingConfig(max_positions=5)

        assert config.validate_position_count(0) is True  # Can add first
        assert config.validate_position_count(4) is True  # Can add 5th
        assert config.validate_position_count(5) is False  # At limit

    def test_validate_order_size(self):
        """Test order size validation."""
        config = PaperTradingConfig(max_order_size=3)

        assert config.validate_order_size(1) is True
        assert config.validate_order_size(3) is True
        assert config.validate_order_size(4) is False

    def test_load_from_env(self):
        """Test loading config from environment variables."""
        import os
        from unittest.mock import patch

        env_vars = {
            "PAPER_TRADING_IB_HOST": "192.168.1.1",
            "PAPER_TRADING_IB_PORT": "7497",
            "PAPER_TRADING_IB_CLIENT_ID": "5",
            "PAPER_TRADING_MAX_POSITIONS": "10",
            "PAPER_TRADING_MAX_ORDER_SIZE": "2",
            "PAPER_TRADING_ALLOWED_SYMBOLS": "SPY,QQQ,IWM",
            "PAPER_TRADING_START_DATE": "2026-01-27",
            "PAPER_TRADING_STARTING_CAPITAL": "50000.0",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            config = PaperTradingConfig.load_from_env()

        assert config.ib_host == "192.168.1.1"
        assert config.ib_port == 7497
        assert config.ib_client_id == 5
        assert config.max_positions == 10
        assert config.max_order_size == 2
        assert config.allowed_symbols == ["SPY", "QQQ", "IWM"]
        assert config.paper_starting_capital == 50000.0

    def test_save_and_load_from_file(self, tmp_path):
        """Test saving and loading config from YAML file."""
        config_path = tmp_path / "paper_config.yaml"

        # Save config
        config = PaperTradingConfig(
            ib_host="127.0.0.1",
            ib_port=7497,
            ib_client_id=2,
            max_positions=5,
            max_order_size=1,
            allowed_symbols=["SPY", "QQQ"],
            paper_starting_capital=100000.0,
        )
        config.save_to_file(str(config_path))

        # Load config
        loaded_config = PaperTradingConfig.load_from_file(str(config_path))

        assert loaded_config.ib_host == config.ib_host
        assert loaded_config.ib_port == config.ib_port
        assert loaded_config.max_positions == config.max_positions
        assert loaded_config.allowed_symbols == config.allowed_symbols

    def test_load_from_nonexistent_file_raises_error(self):
        """Test loading from nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            PaperTradingConfig.load_from_file("nonexistent_config.yaml")
