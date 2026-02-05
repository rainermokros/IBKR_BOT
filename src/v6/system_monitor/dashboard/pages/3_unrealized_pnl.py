"""
Unrealized P&L Dashboard Page

Dedicated page for real-time unrealized P&L monitoring with strategy selector,
detailed position breakdown, historical charts, and risk alerts.

Usage:
    streamlit run src/v6/dashboard/pages/3_unrealized_pnl.py
"""

import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

import polars as pl
import streamlit as st

from v6.system_monitor.dashboard.components.pnl_display import UnrealizedPnLCalculator
from v6.system_monitor.dashboard.config import DashboardConfig
from v6.system_monitor.dashboard.data.positions import load_positions


def main():
    """Unrealized P&L dashboard main function."""
    st.set_page_config(
        page_title="Unrealized P&L",
        page_icon="📈",
        layout="wide"
    )

    # Load configuration
    config = DashboardConfig()

    # Initialize P&L calculator
    pnl_calc = UnrealizedPnLCalculator()

    st.markdown("<h2 style='font-size: 1.5rem;'>📈 Strategy Unrealized P&L</h2>", unsafe_allow_html=True)

    # Auto-refresh setup
    if "pnl_auto_refresh" not in st.session_state:
        st.session_state.pnl_auto_refresh = False
    if "selected_strategy_id" not in st.session_state:
        st.session_state.selected_strategy_id = "All Strategies"

    # Sidebar for controls
    with st.sidebar:
        st.markdown("### Controls")

        # Strategy selector
        selected_strategy = display_strategy_selector()

        # Auto-refresh
        auto_refresh = st.checkbox("Auto-Refresh (30s)", value=False)
        st.session_state.pnl_auto_refresh = auto_refresh

        if st.button("🔄 Refresh Now"):
            st.cache_data.clear()
            st.rerun()

        st.markdown("---")
        st.caption("Last refresh: {}".format(datetime.now().strftime("%H:%M:%S")))

    # Load positions
    with st.spinner("Loading P&L data..."):
        positions_df = load_positions(status="OPEN")

    if positions_df.is_empty():
        st.info("No open positions found.")
        return

    # Get current underlying prices
    current_prices = get_current_underlying_prices(positions_df)

    # Convert DataFrame to position dicts
    positions = convert_df_to_positions(positions_df)

    # Filter by strategy if selected
    if selected_strategy != "All Strategies":
        positions = [p for p in positions if p.get('strategy_id') == selected_strategy]

    # Display P&L summary
    display_pnl_summary(selected_strategy, positions, current_prices, pnl_calc)

    st.markdown("---")

    # Display position breakdown
    if selected_strategy != "All Strategies":
        display_position_breakdown(selected_strategy, positions, current_prices, pnl_calc)

    st.markdown("---")

    # Display P&L chart
    display_pnl_chart(selected_strategy, pnl_calc)

    st.markdown("---")

    # Display position P&L charts
    display_position_pnl_charts(positions, current_prices, pnl_calc)

    st.markdown("---")

    # Display risk alerts
    display_risk_alerts(positions, current_prices, pnl_calc)

    # Auto-refresh loop
    if st.session_state.pnl_auto_refresh:
        time.sleep(30)  # 30 seconds
        st.cache_data.clear()
        st.rerun()


def display_strategy_selector() -> str:
    """
    Display strategy selector dropdown.

    Returns:
        Selected strategy ID or "All Strategies"
    """
    # Get available strategies
    try:
        all_positions = load_positions(status="OPEN")

        if not all_positions.is_empty():
            strategy_ids = ["All Strategies"] + all_positions['strategy_id'].unique().to_list()
        else:
            strategy_ids = ["All Strategies"]
    except:
        strategy_ids = ["All Strategies"]

    # Selectbox
    selected = st.selectbox(
        "Select Strategy",
        strategy_ids,
        index=0
    )

    return selected


def get_current_underlying_prices(positions_df: pl.DataFrame) -> Dict[str, float]:
    """
    Get current underlying prices from market_bars table.

    Args:
        positions_df: Positions DataFrame

    Returns:
        {symbol: current_price}
    """
    prices = {}

    for symbol in positions_df['symbol'].unique().to_list():
        try:
            df = pl.read_delta("data/lake/market_bars")
            latest = df.filter(
                (pl.col("symbol") == symbol) &
                (pl.col("interval") == "1d")
            ).sort("timestamp", descending=True).head(1)

            if not latest.is_empty():
                prices[symbol] = latest.select(pl.col("close")).item()
        except Exception as e:
            st.warning(f"Could not load price for {symbol}: {e}")
            prices[symbol] = 0.0

    return prices


def convert_df_to_positions(positions_df: pl.DataFrame) -> List[Dict[str, Any]]:
    """
    Convert positions DataFrame to list of position dicts.

    Args:
        positions_df: Positions DataFrame

    Returns:
        List of position dicts
    """
    positions = []

    for row in positions_df.iter_rows(named=True):
        # Parse legs JSON
        try:
            legs = json.loads(row.get('legs_json', '[]'))
        except:
            legs = []

        # Parse entry params
        try:
            entry_params = json.loads(row.get('entry_params', '{}'))
        except:
            entry_params = {}

        position = {
            'trade_id': row.get('execution_id', ''),
            'strategy_id': row.get('strategy_id', ''),
            'symbol': row.get('symbol', ''),
            'legs': legs,
            'entry_params': entry_params,
            'strategy_type': row.get('strategy_type', ''),
            'entry_time': row.get('entry_time', None)
        }

        positions.append(position)

    return positions


def display_pnl_summary(
    strategy_id: str,
    positions: List[Dict[str, Any]],
    current_prices: Dict[str, float],
    pnl_calc: UnrealizedPnLCalculator
) -> None:
    """
    Display P&L summary metrics cards.

    Args:
        strategy_id: Strategy ID or "All Strategies"
        positions: List of position dicts
        current_prices: Current underlying prices
        pnl_calc: P&L calculator instance
    """
    st.markdown("### 📊 P&L Summary")

    # Calculate total unrealized P&L
    total_unrealized_pnl = 0.0
    total_entry_value = 0.0
    total_realized_pnl = 0.0
    position_count = len(positions)

    for position in positions:
        try:
            result = pnl_calc.calculate_position_unrealized_pnl(position, current_prices)
            total_unrealized_pnl += result['unrealized_pnl']

            # Estimate entry value
            entry_params = position.get('entry_params', {})
            net_premium = entry_params.get('net_credit', entry_params.get('net_premium', 0.0))
            total_entry_value += abs(net_premium) * 100
        except Exception as e:
            st.warning(f"Error calculating P&L: {e}")

    # Calculate P&L percentage
    if total_entry_value > 0:
        total_pnl_pct = (total_unrealized_pnl / total_entry_value) * 100
    else:
        total_pnl_pct = 0.0

    # Get historical realized P&L if specific strategy selected
    if strategy_id != "All Strategies":
        try:
            historical = pnl_calc.get_historical_pnl(strategy_id, days=30)
            total_realized_pnl = historical['realized_pnl']
        except:
            total_realized_pnl = 0.0

    # Total P&L
    total_pnl = total_realized_pnl + total_unrealized_pnl

    # Find best and worst positions
    position_pnls = []
    for position in positions:
        try:
            result = pnl_calc.calculate_position_unrealized_pnl(position, current_prices)
            position_pnls.append(result)
        except:
            pass

    if position_pnls:
        best_position = max(position_pnls, key=lambda x: x['unrealized_pnl'])
        worst_position = min(position_pnls, key=lambda x: x['unrealized_pnl'])
    else:
        best_position = None
        worst_position = None

    # Display metrics cards (3 columns)
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            label="Total Unrealized P&L",
            value=f"${total_unrealized_pnl:,.2f}",
            delta=f"{total_pnl_pct:+.2f}%",
            delta_color="normal" if total_unrealized_pnl >= 0 else "inverse"
        )

    with col2:
        if strategy_id != "All Strategies":
            st.metric(
                label="Realized P&L (30d)",
                value=f"${total_realized_pnl:,.2f}",
                delta_color="normal" if total_realized_pnl >= 0 else "inverse"
            )
        else:
            st.metric(label="Active Positions", value=position_count)

    with col3:
        if strategy_id != "All Strategies":
            st.metric(
                label="Total P&L",
                value=f"${total_pnl:,.2f}",
                delta="Realized + Unrealized",
                delta_color="normal" if total_pnl >= 0 else "inverse"
            )
        else:
            st.metric(label="Active Positions", value=position_count)

    # Best and worst positions
    col1, col2 = st.columns(2)

    with col1:
        if best_position:
            st.success(f"**Best:** {best_position['trade_id'][:20]}... - ${best_position['unrealized_pnl']:,.2f} ({best_position['unrealized_pnl_pct']:+.2f}%)")

    with col2:
        if worst_position:
            st.error(f"**Worst:** {worst_position['trade_id'][:20]}... - ${worst_position['unrealized_pnl']:,.2f} ({worst_position['unrealized_pnl_pct']:+.2f}%)")


def display_position_breakdown(
    strategy_id: str,
    positions: List[Dict[str, Any]],
    current_prices: Dict[str, float],
    pnl_calc: UnrealizedPnLCalculator
) -> None:
    """
    Display position breakdown table with leg details.

    Args:
        strategy_id: Strategy ID
        positions: List of position dicts
        current_prices: Current underlying prices
        pnl_calc: P&L calculator instance
    """
    st.markdown("### 📋 Position Breakdown")

    # Calculate P&L for each position
    position_data = []

    for position in positions:
        try:
            result = pnl_calc.calculate_position_unrealized_pnl(position, current_prices)

            # Get leg details
            legs = position.get('legs', [])
            leg_summary = ", ".join([
                f"{leg.get('action', '')} {leg.get('right', '')} {leg.get('strike', 0)}"
                for leg in legs
            ])

            position_data.append({
                'Trade ID': result['trade_id'],
                'Symbol': position.get('symbol', ''),
                'Strategy': position.get('strategy_type', ''),
                'Legs': leg_summary,
                'Unrealized P&L': result['unrealized_pnl'],
                'Unrealized P&L %': result['unrealized_pnl_pct'],
                'Leg Count': len(result['legs'])
            })
        except Exception as e:
            st.warning(f"Error calculating P&L for {position.get('trade_id', 'unknown')}: {e}")

    if not position_data:
        st.info("No positions to display.")
        return

    # Sort by Unrealized P&L (descending, worst at top)
    position_data.sort(key=lambda x: x['Unrealized P&L'])

    # Display table
    for pos in position_data:
        # Color code by profitability
        pnl_color = "🟢" if pos['Unrealized P&L'] >= 0 else "🔴"

        # Expandable row
        with st.expander(f"{pnl_color} {pos['Trade ID']} - ${pos['Unrealized P&L']:,.2f} ({pos['Unrealized P&L %']:+.2f}%)"):
            col1, col2, col3, col4 = st.columns(4)

            col1.write(f"**Symbol:** {pos['Symbol']}")
            col2.write(f"**Strategy:** {pos['Strategy']}")
            col3.write(f"**Legs:** {pos['Legs']}")
            col4.write(f"**Leg Count:** {pos['Leg Count']}")


def display_pnl_chart(
    strategy_id: str,
    pnl_calc: UnrealizedPnLCalculator
) -> None:
    """
    Display P&L chart showing historical time series.

    Args:
        strategy_id: Strategy ID or "All Strategies"
        pnl_calc: P&L calculator instance
    """
    st.markdown("### 📈 P&L Chart (30 Days)")

    if strategy_id == "All Strategies":
        st.info("Select a specific strategy to view historical P&L chart.")
        return

    try:
        # Get historical P&L
        result = pnl_calc.get_historical_pnl(strategy_id, days=30)

        if not result['daily_pnl_series']:
            st.info("No historical P&L data available.")
            return

        # Prepare chart data
        dates = [d['date'] for d in result['daily_pnl_series']]
        cumulative_pnl = [d['cumulative_pnl'] for d in result['daily_pnl_series']]
        unrealized_pnl = [d['unrealized_pnl'] for d in result['daily_pnl_series']]

        # Create chart data
        chart_data = {
            'date': dates,
            'cumulative_pnl': cumulative_pnl,
            'unrealized_pnl': unrealized_pnl
        }

        # Display line chart
        st.line_chart(
            data=chart_data,
            x='date',
            y='cumulative_pnl',
            use_container_width=True,
            color="#00cc00" if cumulative_pnl[-1] >= 0 else "#ff4444"
        )

        # Show unrealized P&L as area chart
        st.area_chart(
            data=chart_data,
            x='date',
            y='unrealized_pnl',
            use_container_width=True
        )

    except Exception as e:
        st.error(f"Error loading P&L chart: {e}")
        st.info("Historical P&L requires performance_metrics table data.")


def display_position_pnl_charts(
    positions: List[Dict[str, Any]],
    current_prices: Dict[str, float],
    pnl_calc: UnrealizedPnLCalculator
) -> None:
    """
    Display small multiples of P&L charts for each position.

    Args:
        positions: List of position dicts
        current_prices: Current underlying prices
        pnl_calc: P&L calculator instance
    """
    st.markdown("### 📊 Position P&L (7 Days)")

    # Limit to 9 positions for display (3x3 grid)
    display_positions = positions[:9]

    if not display_positions:
        st.info("No positions to display.")
        return

    # Calculate P&L for each position
    position_pnls = []

    for position in display_positions:
        try:
            result = pnl_calc.calculate_position_unrealized_pnl(position, current_prices)
            position_pnls.append(result)
        except:
            pass

    # Display in 3-column grid
    cols = st.columns(3)

    for i, pnl_data in enumerate(position_pnls):
        col = cols[i % 3]

        with col:
            # Color code by profitability
            pnl_color = "🟢" if pnl_data['unrealized_pnl'] >= 0 else "🔴"

            st.markdown(f"**{pnl_color} {pnl_data['trade_id'][:10]}...**")
            st.write(f"${pnl_data['unrealized_pnl']:,.2f}")
            st.write(f"({pnl_data['unrealized_pnl_pct']:+.2f}%)")

            # Mini progress bar
            st.progress(
                min(1.0, max(0.0, (pnl_data['unrealized_pnl'] + 1000) / 2000)),
                text=f"{pnl_data['unrealized_pnl_pct']:+.1f}%"
            )


def display_risk_alerts(
    positions: List[Dict[str, Any]],
    current_prices: Dict[str, float],
    pnl_calc: UnrealizedPnLCalculator
) -> None:
    """
    Display risk alerts for positions approaching thresholds.

    Args:
        positions: List of position dicts
        current_prices: Current underlying prices
        pnl_calc: P&L calculator instance
    """
    st.markdown("### ⚠️ Risk Alerts")

    alerts = []

    for position in positions:
        try:
            result = pnl_calc.calculate_position_unrealized_pnl(position, current_prices)

            # Check risk thresholds

            # Alert 1: Unrealized P&L < -50%
            if result['unrealized_pnl_pct'] < -50:
                alerts.append({
                    'level': 'danger',
                    'message': f"**{result['trade_id']}** is down {result['unrealized_pnl_pct']:.1f}%",
                    'action': 'Approaching stop-loss - consider rolling or closing'
                })

            # Alert 2: Unrealized P&L < -max_loss * 0.5
            entry_params = position.get('entry_params', {})
            max_loss = entry_params.get('max_loss', 0.0)

            if max_loss > 0 and result['unrealized_pnl'] < -max_loss * 0.5:
                alerts.append({
                    'level': 'warning',
                    'message': f"**{result['trade_id']}** approaching max loss (${result['unrealized_pnl']:,.2f} / ${max_loss:,.2f})",
                    'action': 'Consider rolling position'
                })

            # Alert 3: Check gamma risk (if available in Greeks)
            # This is a placeholder - actual gamma calculation requires option_snapshots
            # For now, we'll alert on large position sizes
            leg_count = len(result['legs'])
            if leg_count > 4:
                alerts.append({
                    'level': 'info',
                    'message': f"**{result['trade_id']}** has {leg_count} legs - high complexity",
                    'action': 'Monitor closely for Greeks risk'
                })

        except Exception as e:
            pass

    # Display alerts
    if not alerts:
        st.success("✅ No risk alerts - all positions within normal thresholds.")
        return

    # Sort by severity
    severity_order = {'danger': 0, 'warning': 1, 'info': 2}
    alerts.sort(key=lambda x: severity_order.get(x['level'], 3))

    # Display alerts
    for alert in alerts:
        if alert['level'] == 'danger':
            st.error(f"🚨 {alert['message']}\n\n💡 {alert['action']}")
        elif alert['level'] == 'warning':
            st.warning(f"⚠️ {alert['message']}\n\n💡 {alert['action']}")
        else:
            st.info(f"ℹ️ {alert['message']}\n\n💡 {alert['action']}")


if __name__ == "__main__":
    main()
