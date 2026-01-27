# Paper Trading Setup Guide

This guide walks you through setting up a paper trading environment for the V6 Trading System to validate strategies without risking real capital.

## Table of Contents

1. [Overview](#overview)
2. [IB Paper Trading Account Setup](#ib-paper-trading-account-setup)
3. [Configuration](#configuration)
4. [Running Paper Trading](#running-paper-trading)
5. [Monitoring Dashboard](#monitoring-dashboard)
6. [Transitioning to Production](#transitioning-to-production)

## Overview

Paper trading allows you to:
- Test strategies in a realistic environment
- Validate entry/exit workflows
- Collect performance metrics
- Compare results against historical backtests
- Build confidence before live trading

**Key Safety Features:**
- `dry_run=True` enforced (no real orders)
- Max positions limited (default: 5)
- Max order size limited (default: 1 contract)
- Symbol whitelist enforced (SPY, QQQ, IWM)
- All trades logged with `[PAPER]` prefix
- Separate Delta Lake tables (no data mixing with production)

## IB Paper Trading Account Setup

### 1. Create IB Paper Trading Account

1. Log in to your IBKR account
2. Navigate to **Account Management** → **Settings** → **Paper Trading Account**
3. Enable paper trading account (if not already enabled)
4. Note your paper trading account ID

### 2. Configure IB Gateway for Paper Trading

1. Download and install IB Gateway:
   - Linux: Download from IBKR website
   - macOS/Windows: Use TWS or Gateway installer

2. Configure IB Gateway:
   ```
   Port: 7497 (paper trading)
   Read-Only API: No (need order placement)
   Master API client ID: 0
   ```
   - For paper trading, the port is typically **7497**
   - Production uses port **7496** (never use in paper trading!)

3. Start IB Gateway:
   ```bash
   # Linux
   /path/to/ibgateway/scripts/ibgateway.sh

   # macOS
   open /Applications/IBGateway.app
   ```

4. Log in with your paper trading account credentials

### 3. Verify IB Connection

Test connection with Python:
```python
import ib_async

ib = ib_async.IB()
ib.connect(host='127.0.0.1', port=7497, clientId=2)

# Should see: "Connected to IB"
print(ib.isConnected())

# Get account summary
account_summary = ib.accountSummary()
print(f"Account: {account_summary}")
```

## Configuration

### 1. Create Configuration File

Copy the example config:
```bash
cp config/paper_trading.yaml.example config/paper_trading.yaml
```

Edit `config/paper_trading.yaml`:
```yaml
# IB Gateway Connection (Paper Trading Account)
ib_host: "127.0.0.1"
ib_port: 7497  # Must be 7497 for paper trading
ib_client_id: 2  # Different from production (use 1)

# Safety Limits (enforced)
dry_run: true  # Always true for paper trading
max_positions: 5  # Maximum concurrent positions
max_order_size: 1  # Maximum contracts per order
allowed_symbols:
  - SPY
  - QQQ
  - IWM

# Paper Trading Tracking
paper_start_date: "2026-01-27T00:00:00"
paper_starting_capital: 100000.0
```

### 2. Set Environment Variables (Optional)

Copy the example env file:
```bash
cp .env.example .env
```

Edit `.env`:
```bash
# Paper Trading Environment Variables
PAPER_TRADING_IB_HOST=127.0.0.1
PAPER_TRADING_IB_PORT=7497
PAPER_TRADING_IB_CLIENT_ID=2

# Safety Limits
PAPER_TRADING_MAX_POSITIONS=5
PAPER_TRADING_MAX_ORDER_SIZE=1
PAPER_TRADING_ALLOWED_SYMBOLS=SPY,QQQ,IWM

# Paper Trading Tracking
PAPER_TRADING_START_DATE=2026-01-27
PAPER_TRADING_STARTING_CAPITAL=100000.0
```

### 3. Validate Configuration

Test configuration loading:
```python
from src.v6.config import PaperTradingConfig

# Load from file
config = PaperTradingConfig.load_from_file("config/paper_trading.yaml")
print(f"dry_run: {config.dry_run}")
print(f"max_positions: {config.max_positions}")
print(f"allowed_symbols: {config.allowed_symbols}")

# Validate symbol
print(f"SPY allowed: {config.validate_symbol('SPY')}")  # True
print(f"AAPL allowed: {config.validate_symbol('AAPL')}")  # False
```

## Running Paper Trading

### 1. Run Paper Trader

Start the paper trading bot:
```bash
python scripts/run_paper_trading.py
```

The bot will:
1. Connect to IB paper trading account
2. Run entry cycle (check market conditions, generate signals)
3. Run monitoring cycle (track positions, evaluate exit decisions)
4. Run exit cycle (close positions when triggered)
5. Log all trades with `[PAPER]` prefix

### 2. Run in Foreground (Testing)

For testing, run in foreground with verbose logging:
```bash
python scripts/run_paper_trading.py --verbose
```

### 3. Run in Background (Production)

For longer-term testing, run as a service:
```bash
# Start service
systemctl --user start v6-paper-trading

# Check status
systemctl --user status v6-paper-trading

# View logs
journalctl --user -u v6-paper-trading -f
```

### 4. Stop Paper Trader

Gracefully stop with Ctrl+C (foreground) or:
```bash
systemctl --user stop v6-paper-trading
```

## Monitoring Dashboard

### 1. Start Dashboard

```bash
streamlit run src/v6/dashboard/app.py --server.port 8501
```

### 2. View Paper Trading Page

Navigate to: http://localhost:8501/pages/5_paper_trading

The page displays:
- **Trade Summary Table**: All completed paper trades
- **Performance Metrics**: Win rate, average P&L, average duration
- **Equity Curve**: P&L trajectory over time
- **Exit Reason Distribution**: Pie chart of exit reasons
- **Comparison**: Paper trading vs historical backtest expectations

### 3. Key Metrics to Monitor

**Win Rate**: Percentage of profitable trades
- Target: >60%
- Warning: <50%

**Average P&L**: Mean profit/loss per trade
- Target: Positive
- Warning: Negative

**Sharpe Ratio**: Risk-adjusted return
- Target: >1.0
- Warning: <0.5

**Max Drawdown**: Largest peak-to-trough decline
- Target: <10%
- Warning: >20%

**Equity Curve**: Should trend upward over time
- Look for consistent growth
- Avoid large swings

### 4. Review Trades

Review individual trades to understand:
- Which strategies are most profitable
- Common exit reasons (stop loss, take profit, time exit)
- Trade duration distribution
- Symbol performance (SPY vs QQQ vs IWM)

## Transitioning to Production

### 1. Pre-Production Checklist

Before transitioning to live trading, ensure:

- [ ] Paper trading runs for at least 1-2 weeks
- [ ] Win rate >60%
- [ ] Sharpe ratio >1.0
- [ ] Max drawdown <10%
- [ ] All safety limits tested (max positions, symbol whitelist)
- [ ] No errors in logs for at least 1 week
- [ ] Dashboard displays all metrics correctly
- [ ] IB connection stable (no disconnects)
- [ ] Position tracking accurate (compare with IB account)

### 2. Reduce Risk Limits

Gradually increase limits:
```yaml
# Week 1-2: Conservative
max_positions: 3
max_order_size: 1

# Week 3-4: Moderate
max_positions: 5
max_order_size: 2

# Week 5+: Production (after validation)
max_positions: 10
max_order_size: 5
```

### 3. Switch to Production

1. Create production config:
   ```bash
   cp config/production.yaml.example config/production.yaml
   ```

2. Update IB connection:
   ```yaml
   ib_port: 7496  # Production port
   ib_client_id: 1  # Different from paper trading
   ```

3. Set dry_run to false:
   ```yaml
   dry_run: false  # ENABLE LIVE TRADING
   ```

4. Start production bot:
   ```bash
   python scripts/run_production_trading.py
   ```

5. Monitor closely for first week:
   - Check dashboard every few hours
   - Review all trades
   - Verify position accuracy
   - Monitor P&L

### 4. Post-Production Monitoring

After transitioning:
- Monitor daily for first month
- Compare production vs paper trading performance
- Adjust strategies if performance differs significantly
- Keep paper trading running in parallel (different account)

## Troubleshooting

### IB Connection Fails

**Error**: "Could not connect to IB"

**Solutions**:
1. Ensure IB Gateway is running
2. Check port (7497 for paper, 7496 for production)
3. Verify client_id is not already in use
4. Check firewall settings

### Dry Run Mode Not Working

**Error**: Real orders being placed

**Solutions**:
1. Verify `dry_run: true` in config
2. Check logs for `[DRY RUN]` prefix
3. Never use port 7496 in paper trading

### Symbol Rejected

**Error**: "Symbol not in whitelist"

**Solutions**:
1. Add symbol to `allowed_symbols` in config
2. Use uppercase symbols (SPY, not spy)
3. Restart paper trader after config change

### Max Positions Exceeded

**Error**: "Max positions limit reached"

**Solutions**:
1. Wait for positions to close
2. Increase `max_positions` in config
3. Close losing positions manually

## Best Practices

1. **Start Conservative**: Use lowest limits initially
2. **Run Long Enough**: Paper trade for 2+ weeks before production
3. **Monitor Daily**: Check dashboard and logs every day
4. **Review Trades**: Understand why each trade was entered/exited
5. **Compare Expectations**: Compare paper trading vs backtest results
6. **Keep Paper Trading**: Run paper trading alongside production
7. **Track Metrics**: Monitor win rate, Sharpe, drawdown weekly
8. **Adjust Gradually**: Increase limits slowly after validation

## Resources

- [IBKR Paper Trading](https://www.interactivebrokers.com/en/trading/ib-paper-trading-account.php)
- [IB API Documentation](https://interactivebrokers.github.io/)
- [V6 Architecture](../.planning/codebase/ARCHITECTURE.md)
- [Strategy Execution Guide](../.planning/phases/4-strategy-execution/4-03-SUMMARY.md)
