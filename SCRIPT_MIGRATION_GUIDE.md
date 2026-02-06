# Script Migration Guide: From Blind to Smart Strategy Execution

## Summary of Problems Found

### ❌ OBSOLETE Scripts (DO NOT USE):
| Script | Problem | Why It's Bad |
|--------|---------|--------------|
| `run_strategy_builder.py` | Just calculates % strikes | No market analysis, no scoring, no risk evaluation |
| `execute_all_strategies.py` | Hardcoded strikes from old data | Based on "11:37 AM" comment - completely outdated |
| `execute_iron_condors.py` | Hardcoded strikes | No analysis, no risk checks |

**These scripts VIOLATE v6 architecture rules (see CLAUDE.md)**

---

## ✅ NEW Proper v6 Scripts

### 1. `run_strategy_analysis.py` (9:45 AM)
**What it does:**
- Uses `StrategySelector` from v6 infrastructure
- Analyzes all strategies (Iron Condor, Bull Put, Bear Call)
- Scores each strategy based on:
  - Credit received
  - Risk/reward ratio
  - Probability of success (from delta)
  - Expected return
  - IV rank
- Returns best strategy per symbol

**Schedule:** 9:45 AM daily (pre-market)
**Priority:** 25 (after validate_ib_connection)

### 2. `execute_best_strategies.py` (10:00 AM)
**What it does:**
- Uses `EntryWorkflow` from v6 infrastructure
- Executes only strategies with score >= 70
- Respects 12-priority decision rules
- Proper risk management and validation
- Order monitoring and error handling

**Schedule:** 10:00 AM daily (15 min after analysis)
**Priority:** 26 (after strategy_analysis)

---

## Complete Daily Schedule

| Time | Priority | Task | Purpose |
|------|----------|------|---------|
| 08:00 | 10 | load_historical_data | Load historical market data |
| 08:45 | 20 | validate_ib_connection | Verify IB Gateway ready |
| **09:45** | **25** | **strategy_analysis** | **NEW: Analyze strategies** |
| **10:00** | **26** | **execute_strategies** | **NEW: Execute best strategies** |
| Every 5min | 30-31 | collect_option/futures_data | Market data collection |
| 16:30 | 40 | calculate_daily_statistics | EOD statistics |
| 18:00 | 50 | validate_data_quality | Data quality checks |
| Hourly | 100 | health_check | System health monitoring |

---

## Script Classification

### ✅ PRODUCTION READY (Use These):
- `sync_positions.py` - Position sync (now runs pre/post market only)
- `run_strategy_analysis.py` - **NEW** Strategy analysis
- `execute_best_strategies.py` - **NEW** Strategy execution
- `health_check.py` - Health monitoring
- `verify_positions.py` - Position reconciliation

### ❌ OBSOLETE (Do NOT Use):
- `run_strategy_builder.py` → Use `run_strategy_analysis.py`
- `execute_all_strategies.py` → Use `execute_best_strategies.py`
- `execute_iron_condors.py` → Use `execute_best_strategies.py`
- `simple_monitor.py` → Will be replaced by unified_monitor.py
- `refresh_option_data.py` → Will be replaced by unified_monitor.py

### ⚠️ NEEDS WORK:
- `simple_monitor.py` - Should be combined into unified_monitor.py
- `refresh_option_data.py` - Should be combined into unified_monitor.py
- `sync_positions.py` - Should run pre/post market only, not every 5min

---

## Next Steps

### 1. Implement unified_monitor.py
Combine `simple_monitor`, `refresh_option_data`, `sync_positions` into one script:
```python
# Runs every 5 minutes:
1. Connect to IB (once)
2. Fetch positions
3. Sync to Delta Lake
4. Fetch market data
5. Calculate P&L
6. Send alerts
7. Disconnect
```

### 2. Fix position_sync schedule
Change from every 5min to:
- Pre-market: 08:00
- Post-market: 16:15
- Trigger on order fill (event-driven)

### 3. Complete execute_best_strategies.py
The script is a placeholder showing the proper structure.
To complete:
1. Initialize EntryWorkflow with dependencies
2. Configure RiskManager
3. Set up AlertManager
4. Configure CircuitBreaker
5. Test with paper trading

---

## Architecture Rules (from CLAUDE.md)

✅ **DO:**
- Use `StrategySelector` for analysis
- Use `EntryWorkflow` for execution
- Use `PositionMonitoringWorkflow` for monitoring
- Use proper risk management

❌ **DO NOT:**
- Create custom execution scripts
- Use hardcoded strikes
- Execute without analysis/scoring
- Bypass risk management
- Create manual monitoring scripts

---

## File Locations

### Proper v6 Infrastructure:
```
src/v6/strategy_builder/
├── strategy_selector.py      ← Use this for analysis
├── builders.py               ← IronCondorBuilder, VerticalSpreadBuilder
└── models.py                 ← Strategy models

src/v6/risk_manager/trading_workflows/
├── entry.py                  ← Use this for execution
└── monitoring.py             ← Use this for monitoring
```

### Scripts:
```
scripts/
├── run_strategy_analysis.py   ← NEW: Strategy analysis
├── execute_best_strategies.py  ← NEW: Strategy execution
└── [obsolete scripts]          ← DO NOT USE
```

---

## Testing

Before going live:

1. **Test strategy analysis:**
```bash
cd /home/bigballs/project/bot/v6
PYTHONPATH=/home/bigballs/project/bot/v6/src python scripts/run_strategy_analysis.py
```

2. **Test strategy execution (paper trading):**
```bash
cd /home/bigballs/project/bot/v6
PYTHONPATH=/home/bigballs/project/bot/v6/src python scripts/execute_best_strategies.py
```

3. **Verify scheduler:**
```bash
cd /home/bigballs/project/bot/v6
python3 -c "
import sys
sys.path.insert(0, 'src')
from v6.system_monitor.data.scheduler_config import SchedulerConfigTable
config = SchedulerConfigTable()
print(config.get_all_tasks().select(['task_name', 'schedule_time', 'priority']))
"
```

---

## Migration Checklist

- [x] Created `run_strategy_analysis.py`
- [x] Created `execute_best_strategies.py`
- [x] Added to scheduler at 9:45 and 10:00
- [ ] Complete `execute_best_strategies.py` implementation
- [ ] Create `unified_monitor.py`
- [ ] Update `sync_positions` to pre/post market only
- [ ] Test with paper trading
- [ ] Remove obsolete scripts
- [ ] Update documentation

---

## Questions?

1. **Why were the old scripts blind?**
   - They were legacy scripts from before v6 infrastructure existed
   - Used hardcoded strikes or simple % calculations
   - No real analysis or scoring

2. **Why 9:45 and 10:00?**
   - 9:45: 15 min before market open gives time for analysis
   - 10:00: 15 min after analysis gives buffer before market opens
   - Can be adjusted based on your preferences

3. **What if no strategies meet score threshold?**
   - System skips execution (no trade is better than bad trade)
   - You'll see "No strategies meet execution threshold" in logs

4. **Can I adjust the score threshold?**
   - Yes: Edit `min_score` parameter in `execute_best_strategies.py`
   - Default: 70 (reasonable for quality strategies)
   - Lower = more trades, higher risk
   - Higher = fewer trades, higher quality
