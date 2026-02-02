# Strategy Selector Migration

## What Changed

### Old Script: `run_strategist.py` (OBSOLETE)
- **DEPRECATED** - Marked as obsolete
- Only builds Iron Condors (hardcoded)
- No strategy evaluation or comparison
- Kept for reference only

### New Script: `run_strategy_selector.py` (ACTIVE)
- **ACTIVE** - Use this for all strategy execution
- Evaluates ALL available strategies using StrategySelector
- Scores and ranks strategies based on multiple factors
- Selects and executes the best strategy per symbol

## Strategies Evaluated

The new `StrategySelector` evaluates:

1. **Iron Condor** (neutral market outlook)
   - Best for range-bound markets
   - Profits from time decay
   - Delta-neutral positioning

2. **Bull Put Spread** (bullish outlook)
   - Best when expecting upward movement
   - Credit received reduces basis
   - Limited risk

3. **Bear Call Spread** (bearish outlook)
   - Best when expecting downward movement
   - Credit received reduces basis
   - Limited risk
   - **Note**: Not yet implemented with smart lookup

## Scoring Factors

The `StrategySelector` scores each strategy (0-100) based on:

1. **Risk/Reward Ratio** (30% weight)
   - Lower is better
   - Ideal R/R < 3: 100 points
   - R/R >= 10: 0 points

2. **Probability of Success** (30% weight)
   - Higher is better
   - Derived from delta (POS ≈ 100 - (|delta| × 100))
   - POS >= 80%: 100 points
   - POS < 50%: 0 points

3. **Expected Return %** (25% weight)
   - Higher is better
   - ER = Credit × POS% - Risk × (1-POS%)
   - ER >= 20%: 100 points
   - ER <= 0%: 0 points

4. **IV Rank Context** (15% weight)
   - Moderate IV (25-75): Best for sellers (100 points)
   - Very high IV (75-100): Good but expensive (75 points)
   - Low IV (0-25): Bad for credit strategies (25 points)

## Scheduler Configuration

Both scheduler tasks now use the new script:

```
task_name          | script_path                      | schedule_time
-------------------|----------------------------------|--------------
run_daily_strategy | scripts/run_strategy_selector.py  | 09:35
fallback_strategy  | scripts/run_strategy_selector.py  | 09:45
```

## Usage Examples

### Dry Run (Testing)
```bash
python scripts/run_strategy_selector.py --dry-run
```

### Live Trading
```bash
python scripts/run_strategy_selector.py --live
```

### Custom DTE
```bash
python scripts/run_strategy_selector.py --dte 30
```

### Specific Symbols
```bash
python scripts/run_strategy_selector.py --symbols SPY QQQ
```

## Output

The selector will:

1. **Analyze all strategies** for each symbol
2. **Score each strategy** based on the factors above
3. **Rank strategies** by composite score
4. **Select the best strategy** per symbol
5. **Execute the selected strategy** (or dry run)
6. **Save execution to Delta Lake** for tracking

Example output:
```
STRATEGY SELECTOR: Analyzing all strategies for SPY

Building Iron Condor...
Building Bull Put Spread...

RANKING STRATEGIES

🥇 #1 - Iron Condor
   Score: 78.5/100
   R/R: 2.8:1 | POS: 81.2%
   Exp Return: $152.00 (15.2%)

✅ RECOMMENDED: Iron Condor
   Score: 78.5/100
   Risk/Reward: $1000 risk for $152 credit
   Probability of Success: 81.2%
```

## Migration Checklist

- [x] Create `run_strategy_selector.py`
- [x] Mark `run_strategist.py` as obsolete
- [x] Update scheduler config for `run_daily_strategy`
- [x] Update scheduler config for `fallback_strategy`
- [x] Verify all imports work
- [x] Test scheduler config update

## Future Improvements

1. **Implement Bear Call Spread** with smart lookup
2. **Add Wheel strategy** to evaluation
3. **Add regime-based selection** (use Regime Classifier predictions)
4. **Add ML-based scoring** (train on historical performance)
5. **Add backtesting** for each strategy before selection

## Questions?

See `src/v6/strategies/strategy_selector.py` for scoring logic.
See `scripts/run_strategy_selector.py` for execution logic.
