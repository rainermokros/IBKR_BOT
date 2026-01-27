"""
Test that all fixtures work correctly.
"""


def test_ib_fixtures(mock_ib_connection, mock_portfolio_response, mock_position_data, mock_market_data):
    """Test IB fixtures are created correctly."""
    assert mock_ib_connection is not None
    assert mock_ib_connection.ib is not None
    assert len(mock_portfolio_response) > 0
    assert mock_position_data is not None
    assert mock_market_data is not None


def test_strategy_fixtures(sample_iron_condor, sample_vertical_spread, sample_strategy_state):
    """Test strategy fixtures are created correctly."""
    assert sample_iron_condor is not None
    assert sample_iron_condor.strategy_type.value == "iron_condor"
    assert len(sample_iron_condor.legs) == 4
    assert sample_vertical_spread is not None
    assert len(sample_vertical_spread.legs) == 2
    assert sample_strategy_state is not None
    assert sample_strategy_state["status"] == "filled"


def test_market_fixtures(mock_option_chain, mock_greeks_snapshot):
    """Test market fixtures are created correctly."""
    assert mock_option_chain is not None
    assert mock_option_chain["symbol"] == "SPY"
    assert len(mock_option_chain["calls"]) > 0
    assert len(mock_option_chain["puts"]) > 0
    assert mock_greeks_snapshot is not None
    assert "portfolio_greeks" in mock_greeks_snapshot
