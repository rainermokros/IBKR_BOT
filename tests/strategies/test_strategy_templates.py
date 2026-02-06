"""
Tests for Strategy Template base class and registry.
"""

import pytest
from datetime import date, datetime

from v6.strategies.models import (
    LegAction,
    LegSpec,
    OptionRight,
    Strategy,
    StrategyType,
)
from v6.strategies.strategy_templates import (
    Greeks,
    StrategyTemplate,
    StrategyTemplateRegistry,
    get_registry,
    register_template,
)


class DummyTemplate(StrategyTemplate):
    """Dummy template for testing."""

    def generate_legs(self, symbol: str, direction: str, params: dict):
        """Generate dummy legs."""
        from datetime import timedelta
        return [
            LegSpec(
                right=OptionRight.CALL,
                strike=100.0,
                quantity=1,
                action=LegAction.BUY,
                expiration=date.today() + timedelta(days=30),
                price=1.0
            )
        ]

    def calculate_greeks(self, legs):
        """Calculate dummy greeks."""
        return Greeks(delta=0.5, gamma=0.1, theta=-0.05, vega=0.2)

    def validate_params(self, params):
        """Validate dummy params."""
        return True

    def get_default_params(self):
        """Get default params."""
        return {"quantity": 1}

    def estimate_risk_reward(self, params):
        """Estimate dummy risk/reward."""
        return (100.0, 50.0)

    def get_strategy_type(self):
        """Get strategy type."""
        return StrategyType.CUSTOM


class TestGreeks:
    """Tests for Greeks dataclass."""

    def test_greeks_addition(self):
        """Test adding two Greeks objects."""
        g1 = Greeks(delta=0.5, gamma=0.1, theta=-0.05, vega=0.2)
        g2 = Greeks(delta=0.3, gamma=0.05, theta=-0.03, vega=0.1)

        result = g1 + g2

        assert result.delta == 0.8
        assert result.gamma == pytest.approx(0.15, rel=1e-10)
        assert result.theta == -0.08
        assert result.vega == pytest.approx(0.3, rel=1e-10)

    def test_greeks_repr(self):
        """Test Greeks string representation."""
        g = Greeks(delta=0.5, gamma=0.1, theta=-0.05, vega=0.2)
        repr_str = repr(g)

        assert "Δ=0.500" in repr_str
        assert "Γ=0.100" in repr_str
        assert "Θ=-0.050" in repr_str
        assert "ν=0.200" in repr_str


class TestStrategyTemplateRegistry:
    """Tests for StrategyTemplateRegistry."""

    def test_register_template(self):
        """Test registering a template."""
        registry = StrategyTemplateRegistry()

        registry.register_template("dummy", DummyTemplate)

        assert "dummy" in registry.list_templates()

    def test_register_duplicate_raises_error(self):
        """Test registering duplicate template raises error."""
        registry = StrategyTemplateRegistry()
        registry.register_template("dummy", DummyTemplate)

        with pytest.raises(ValueError, match="already registered"):
            registry.register_template("dummy", DummyTemplate)

    def test_register_invalid_class_raises_error(self):
        """Test registering non-StrategyTemplate class raises error."""
        registry = StrategyTemplateRegistry()

        class NotATemplate:
            pass

        with pytest.raises(ValueError, match="must inherit from StrategyTemplate"):
            registry.register_template("invalid", NotATemplate)

    def test_get_template(self):
        """Test getting a template instance."""
        registry = StrategyTemplateRegistry()
        registry.register_template("dummy", DummyTemplate)

        template = registry.get_template("dummy")

        assert isinstance(template, DummyTemplate)
        assert isinstance(template, StrategyTemplate)

    def test_get_nonexistent_template_raises_error(self):
        """Test getting nonexistent template raises error."""
        registry = StrategyTemplateRegistry()

        with pytest.raises(ValueError, match="not found"):
            registry.get_template("nonexistent")

    def test_list_templates(self):
        """Test listing all templates."""
        registry = StrategyTemplateRegistry()
        registry.register_template("dummy1", DummyTemplate)
        registry.register_template("dummy2", DummyTemplate)

        templates = registry.list_templates()

        assert len(templates) == 2
        assert "dummy1" in templates
        assert "dummy2" in templates

    def test_create_strategy_from_template(self):
        """Test creating strategy from registered template."""
        registry = StrategyTemplateRegistry()
        registry.register_template("dummy", DummyTemplate)

        strategy = registry.create_strategy(
            template_name="dummy",
            symbol="SPY",
            direction="bullish",
            params={"quantity": 2}
        )

        assert isinstance(strategy, Strategy)
        assert strategy.symbol == "SPY"
        assert len(strategy.legs) == 1
        assert strategy.metadata["template"] == "DummyTemplate"


class TestGlobalRegistry:
    """Tests for global registry functions."""

    def test_get_registry_singleton(self):
        """Test that get_registry returns same instance."""
        registry1 = get_registry()
        registry2 = get_registry()

        assert registry1 is registry2

    def test_register_template_global(self):
        """Test registering template via global function."""
        registry = get_registry()

        # Clear any existing templates
        registry._templates.clear()

        register_template("global_dummy", DummyTemplate)

        assert "global_dummy" in registry.list_templates()


class TestStrategyTemplateBase:
    """Tests for StrategyTemplate base class."""

    def test_create_strategy(self):
        """Test creating strategy from template."""
        template = DummyTemplate()

        strategy = template.create_strategy(
            symbol="SPY",
            direction="bullish"
        )

        assert isinstance(strategy, Strategy)
        assert strategy.symbol == "SPY"
        assert strategy.strategy_type == StrategyType.CUSTOM
        assert len(strategy.legs) == 1
        assert strategy.legs[0].action == LegAction.BUY
        assert strategy.legs[0].right == OptionRight.CALL

    def test_create_strategy_with_custom_params(self):
        """Test creating strategy with custom params."""
        template = DummyTemplate()

        strategy = template.create_strategy(
            symbol="QQQ",
            direction="bearish",
            params={"quantity": 5}
        )

        assert strategy.symbol == "QQQ"
        assert strategy.metadata["params"]["quantity"] == 5

    def test_create_strategy_invalid_params_raises_error(self):
        """Test that invalid params raise error."""

        class StrictTemplate(StrategyTemplate):
            def generate_legs(self, symbol, direction, params):
                return []

            def calculate_greeks(self, legs):
                return Greeks(0, 0, 0, 0)

            def validate_params(self, params):
                if params.get("quantity", 0) < 1:
                    raise ValueError("Quantity must be >= 1")
                return True

            def get_default_params(self):
                return {"quantity": 1}

            def estimate_risk_reward(self, params):
                return (100, 50)

            def get_strategy_type(self):
                return StrategyType.CUSTOM

        template = StrictTemplate()

        with pytest.raises(ValueError, match="Quantity must be >= 1"):
            template.create_strategy(
                symbol="SPY",
                direction="bullish",
                params={"quantity": 0}
            )
