"""Test fixtures for v6 trading system integration tests.

This package provides reusable test fixtures for:
- IB connections and responses
- Market data and option chains
- Strategy configurations
- Portfolio state

Fixtures are auto-discovered by pytest through conftest.py.
"""

from tests.fixtures.ib_fixtures import (
    mock_ib_connection,
    mock_portfolio_response,
    mock_position_data,
    mock_market_data,
)
from tests.fixtures.strategy_fixtures import (
    sample_iron_condor,
    sample_vertical_spread,
    sample_strategy_state,
)
from tests.fixtures.market_fixtures import (
    mock_option_chain,
    mock_greeks_snapshot,
)

__all__ = [
    # IB fixtures
    "mock_ib_connection",
    "mock_portfolio_response",
    "mock_position_data",
    "mock_market_data",
    # Strategy fixtures
    "sample_iron_condor",
    "sample_vertical_spread",
    "sample_strategy_state",
    # Market fixtures
    "mock_option_chain",
    "mock_greeks_snapshot",
]
