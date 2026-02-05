"""
Strategy Builder Factory

Maps StrategyType to the appropriate builder instance.

This allows EntryWorkflow to dynamically select the right builder
based on the strategy type being executed.
"""

from typing import Dict, Type

from v6.strategy_builder.builders import (
    StrategyBuilder,
    IronCondorBuilder,
    VerticalSpreadBuilder,
)
from v6.strategy_builder.models import StrategyType


class StrategyBuilderFactory:
    """
    Factory that returns the appropriate builder for a given StrategyType.

    This allows dynamic builder selection based on strategy type,
    rather than hardcoding a single builder in EntryWorkflow.
    """

    # Registry of strategy type to builder class
    _builders: Dict[StrategyType, Type[StrategyBuilder]] = {
        StrategyType.IRON_CONDOR: IronCondorBuilder,
        StrategyType.VERTICAL_SPREAD: VerticalSpreadBuilder,
        # Add more builders here as needed
        # StrategyType.CUSTOM: CustomStrategyBuilder,
    }

    @classmethod
    def get_builder(cls, strategy_type: StrategyType) -> StrategyBuilder:
        """
        Get the appropriate builder instance for a strategy type.

        Args:
            strategy_type: The type of strategy to build

        Returns:
            StrategyBuilder: Builder instance for this strategy type

        Raises:
            ValueError: If strategy_type is not supported
        """
        builder_class = cls._builders.get(strategy_type)

        if builder_class is None:
            raise ValueError(
                f"No builder registered for strategy type: {strategy_type}. "
                f"Supported types: {list(cls._builders.keys())}"
            )

        return builder_class()

    @classmethod
    def register_builder(
        cls,
        strategy_type: StrategyType,
        builder_class: Type[StrategyBuilder]
    ) -> None:
        """
        Register a new builder for a strategy type.

        Args:
            strategy_type: The strategy type this builder handles
            builder_class: The builder class to register
        """
        cls._builders[strategy_type] = builder_class

    @classmethod
    def supported_types(cls) -> list[StrategyType]:
        """Return list of supported strategy types."""
        return list(cls._builders.keys())
