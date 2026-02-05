# V6 Trading System Dashboard

Real-time monitoring dashboard for the V6 automated options trading system.
Built with Streamlit for rapid development and interactive visualizations.

## Features

- **Position Monitor**: View all active positions with Greeks, P&L, and filtering
- **Portfolio Analytics**: Visualize portfolio Greeks, P&L history, and risk metrics
- **Alert Management**: Alert history and active alerts (coming in Plan 2)
- **System Health**: IB connection status and data freshness (coming in Plan 3)

## Installation

### Requirements

```bash
pip install streamlit plotly pandas polars deltalake loguru
```

### Delta Lake Tables

The dashboard reads from Delta Lake tables:
- `data/lake/strategy_executions`: Strategy execution data
- `data/lake/alerts`: Alert history (Plan 2)

## Usage

### Starting the Dashboard

```bash
# Default (port 8501)
python scripts/run_dashboard.py

# Custom port
python scripts/run_dashboard.py --port 8502

# Debug mode
python scripts/run_dashboard.py --debug

# Headless mode (production)
python scripts/run_dashboard.py --headless
```

Or directly with Streamlit:

```bash
streamlit run src/v6/dashboard/app.py
```

### Accessing the Dashboard

Open your browser and navigate to:
- http://localhost:8501 (default)

## Pages

### Home
- Portfolio summary metrics
- Quick access to all pages

### Positions (📈)
- **Filters**: Symbol, Strategy Type, Status
- **Auto-refresh**: Configurable intervals (5s, 30s, 60s, off)
- **Summary metrics**: Total positions, open positions, portfolio delta, unrealized P&L
- **Position cards**: Expandable cards with leg details, execution times, status

### Portfolio (💼)
- **Greeks summary**: Delta, gamma, theta, vega, rho
- **Greeks heatmap**: Strike vs DTE visualization (symbol selector)
- **P&L time series**: Cumulative P&L over time
- **Portfolio metrics**: Position count, symbol count, exposure, concentration

### Alerts (🔔) - Coming in Plan 2
- Active alerts
- Alert history
- Alert acknowledgment

### System Health (🩺) - Coming in Plan 3
- IB connection status
- Data freshness indicators
- System metrics

## Architecture

### Data Flow

```
Delta Lake (strategy_executions, alerts)
    ↓
Dashboard Data Loading (@st.cache_data ttl=30/60s)
    ↓
Streamlit Pages (Positions, Portfolio, Alerts, Health)
    ↓
Interactive Visualizations (Plotly)
```

### Caching Strategy

- **Positions**: 30s TTL (load_positions, get_position_summary)
- **Portfolio Greeks**: 30s TTL (get_portfolio_greeks, get_greeks_by_symbol)
- **P&L History**: 60s TTL (get_portfolio_pnl_history)
- **Alerts**: 60s TTL (load_alerts, get_alert_summary)

Cache is cleared on manual refresh button click.

### Auto-Refresh

- **5s**: Near real-time (higher CPU usage)
- **30s**: Balanced (default)
- **60s**: Low resource usage
- **Off**: Manual refresh only

Auto-refresh uses `st.rerun()` loop with `time.sleep()` interval.

## Configuration

Edit `src/v6/dashboard/config.py`:

```python
@dataclass(slots=True)
class DashboardConfig:
    streamlit_port: int = 8501
    debug_mode: bool = False
    cache_ttl_positions: int = 30  # seconds
    cache_ttl_alerts: int = 60  # seconds
    auto_refresh_options: list[int] = [5, 30, 60, 0]
    default_refresh: int = 30
    delta_lake_base_path: str = "data/lake"
```

## Troubleshooting

### Dashboard Won't Start

**Issue**: Port 8501 already in use
**Solution**: Use `--port` flag to specify different port
```bash
python scripts/run_dashboard.py --port 8502
```

### No Data Showing

**Issue**: Delta Lake tables don't exist or are empty
**Solution**: Run strategy execution workflows first to populate data
```bash
# Check if tables exist
ls data/lake/strategy_executions
```

### Slow Performance

**Issue**: Too much data or cache disabled
**Solution**:
- Reduce auto-refresh interval (use 60s instead of 5s)
- Check cache is enabled (@st.cache_data decorators present)
- Filter positions by symbol/strategy to reduce dataset

### Greeks/P&L Showing Zeros

**Issue**: Greeks not yet tracked in Delta Lake
**Solution**: This is expected for Plan 1. Greeks will be implemented in Plan 2
after option_snapshots table is populated with market data.

### IB API Rate Limits

**Issue**: Dashboard auto-refreshing too fast
**Solution**: Dashboard reads from Delta Lake, not IB API. If you see rate limits:
- Check PositionSync isn't polling too frequently
- Increase cache TTL in config.py
- Reduce auto-refresh interval

## Development

### Project Structure

```
src/v6/dashboard/
├── __init__.py
├── app.py                  # Main Streamlit app
├── config.py               # Configuration
├── README.md               # This file
├── pages/
│   ├── 1_positions.py      # Position monitor
│   ├── 2_portfolio.py      # Portfolio analytics
│   ├── 3_alerts.py         # Alert management (Plan 2)
│   └── 4_health.py         # System health (Plan 3)
├── components/
│   ├── position_card.py    # Position display widget
│   └── greeks_display.py   # Greeks visualization
└── data/
    ├── positions.py        # Position data loading
    ├── portfolio.py        # Portfolio data loading
    └── alerts.py           # Alert data loading (Plan 2)
```

### Adding a New Page

1. Create `pages/N_page_name.py` in `src/v6/dashboard/pages/`
2. Streamlit auto-discovers pages in alphabetical order
3. Add navigation link in `app.py` sidebar

```python
# pages/5_custom.py
import streamlit as st

st.set_page_config(page_title="Custom", page_icon="🔧")
st.title("🔧 Custom Page")

# Your code here
```

### Adding a New Component

1. Create component in `src/v6/dashboard/components/`
2. Import and use in any page

```python
# components/my_component.py
import streamlit as st

def my_component(data):
    st.write(f"Data: {data}")

# Usage in page
from v6.dashboard.components.my_component import my_component
my_component(data)
```

## Future Plans

### Plan 2 (6-02): Alert Management UI
- Active alerts display
- Alert history with filters
- Alert acknowledgment workflow
- Alert configuration UI

### Plan 3 (6-03): System Health Monitoring
- IB connection status
- Data freshness indicators
- System metrics (CPU, memory, disk)
- Active strategy registry

## License

Part of the V6 Automated Trading System.
