# V6 Trading System - clientId Assignment Table

**Last Updated:** 2026-02-04
**IB Gateway Port:** 4002 (all scripts)
**Status:** ✅ All conflicts resolved

## Complete clientId Reference

| clientId | Script | Purpose | Status | Notes |
|----------|--------|---------|--------|-------|
| **999** | `health_check.py` | System health monitoring | ✅ Active | Hourly health checks |
| **9950** | `unified_monitor.py` | **NEW** - Combined monitoring | ✅ Active | Replaces 3 scripts (sync + refresh + monitor) |
| **9960** | `sync_positions.py` | Position sync (pre/post market) | ✅ Active | Now runs 08:00 & 16:15 only |
| **9995** | `simple_monitor.py` | Legacy position monitor | ⚠️ Deprecated | Replaced by unified_monitor |
| **9996** | `verify_positions.py` | Position reconciliation | ✅ Active | On-demand verification |
| **9970** | `execute_all_strategies.py` | Blind strategy execution | ❌ OBSOLETE | Use execute_best_strategies.py instead |
| **9971** | `execute_best_strategies.py` | **NEW** - Proper execution | ✅ Active | Uses v6 infrastructure (StrategySelector + EntryWorkflow) |
| **9972** | `execute_bracket_orders.py` | Bracket order execution | ✅ Active | Manual execution |
| **9973** | `execute_iron_condors.py` | Iron Condor execution | ⚠️ Legacy | Use execute_best_strategies.py instead |
| **9974** | `execute_iron_condors_auto.py` | Auto Iron Condor execution | ✅ Active | Automated execution |
| **9975** | `auto_strategy_builder_execute.py` | Auto strategy execution | ✅ Active | Strategy builder automation |
| **9980** | `collect_option_snapshots.py` | Option data collection | ✅ Active | Every 5min via scheduler (collect_option_data task) |
| **9981** | `run_strategy_builder.py` | Strategy builder runner | ✅ Active | Manual strategy analysis |
| **9982** | `load_historical_data.py` | Historical data loader | ✅ Active | Once daily at 08:00 pre-market |
| **9998** | `execute_iron_condors.py` | Iron Condor execution | ❌ OBSOLETE | Use execute_best_strategies.py instead |
| **9999** | `refresh_option_data.py` | Market data refresh | ⚠️ Deprecated | Replaced by unified_monitor |

## Port Summary

All scripts connect to:
```
Host: 127.0.0.1
Port: 4002
```

## clientId Ranges by Function

| Range | Function | Scripts |
|-------|----------|---------|
| **900-999** | System monitoring | health_check (999) |
| **9900-9999** | Monitoring & data | simple_monitor (9995), verify_positions (9996), refresh_option_data (9999), execute_iron_condors (9998) |
| **9950-9999** | **NEW unified monitoring** | unified_monitor (9950), sync_positions (9960) |
| **9970-9979** | Strategy execution | execute_all_strategies (9970 - obsolete), execute_best_strategies (9971), execute_bracket_orders (9972), execute_iron_condors (9973), execute_iron_condors_auto (9974), auto_strategy_builder_execute (9975) |
| **9980-9994** | Data collection & misc | collect_option_snapshots (9980), run_strategy_builder (9981) |

## Conflicts History

| Date | Conflict | Resolution |
|------|----------|------------|
| 2026-02-04 08:00 | `sync_positions` (9997) vs `execute_all_strategies` (9997) | ✅ Fixed: sync_positions → 9960 |
| 2026-02-04 08:30 | `execute_all_strategies` still using 9997 | ✅ Fixed: execute_all_strategies → 9970 |
| 2026-02-04 08:30 | Created execute_best_strategies | ✅ Assigned: 9971 |

## Script Migration Status

### ✅ COMPLETED Migrations:
| Old Script (Obsolete) | New Script (Proper) | clientId Old → New |
|----------------------|---------------------|---------------------|
| `execute_all_strategies.py` | `execute_best_strategies.py` | 9970 → 9971 |
| `sync_positions.py` (every 5min) | `sync_positions.py` (pre/post only) | 9997 → 9960 |
| `simple_monitor.py` | `unified_monitor.py` | 9995 → 9950 |
| `refresh_option_data.py` | `unified_monitor.py` | 9999 → (included in 9950) |

### ⚠️ PENDING Migrations:
| Old Script | New Script | Status |
|------------|------------|--------|
| `execute_iron_condors.py` | `execute_best_strategies.py` | Ready to deprecate |
| `run_strategy_builder.py` | `run_strategy_analysis.py` | Ready to deprecate |

## Scheduler Integration

Scripts that are **scheduled** (auto-run by scheduler):

| clientId | Script | Schedule | Priority |
|----------|--------|----------|----------|
| 9950 | unified_monitor | Every 5min (market hours) | 32 |
| 9960 | sync_positions | 08:00, 16:15 (pre/post market) | 15 |
| 9971 | execute_best_strategies | 10:00 (daily) | 26 |
| 999 | health_check | Hourly | 100 |

**Manual scripts** (run on-demand):
- `verify_positions.py` (9996) - Run when needed
- `run_strategy_analysis.py` (no IB connection) - Run at 09:45

## clientId Assignment Rules

### ✅ DO:
1. **Use 9900-9999 range** for new monitoring/data scripts
2. **Use 9970-9999 range** for new execution scripts
3. **Document here first** before assigning new clientId
4. **Check for conflicts** before using

### ❌ DO NOT:
1. **Reuse existing clientIds** - always use unique ID
2. **Skip documentation** - update this table when assigning
3. **Use random IDs** - follow the range system above
4. **Assign > 10000** - keep below 5 digits

## clientId Availability

**Available ranges** (as of 2026-02-05):
- 9976-9979 (execution scripts)
- 9983-9994 (miscellaneous)
- 9997 (currently unused)

**Reserved** (do not use):
- 1-998 (IB Gateway/TWS)
- 999 (health_check)
- 1000-9899 (future expansion)

## Troubleshooting

### "Connection refused" on clientId
**Cause:** clientId already in use by another script
**Solution:** Check this table, ensure no other running script uses the same ID

### clientId conflict detection
```bash
# Check what's using a clientId:
grep -r "clientId=9997" /home/bigballs/project/bot/v6/scripts --include="*.py"
```

### Finding next available clientId
1. Check this table for assigned IDs
2. Pick next unused number in appropriate range
3. Update this table
4. Use in script

---

**Generated by:** v6 Trading System
**Auto-generated from:** `/home/bigballs/project/bot/v6/scripts/`
**Questions?** See `SCRIPT_MIGRATION_GUIDE.md`
