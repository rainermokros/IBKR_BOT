---
phase: 3-decision-rules-engine
plan: 03
type: execute
depends_on: ["3-01", "3-02"]
files_modified: [src/v6/decisions/rules/__init__.py, src/v6/decisions/rules/catastrophe.py, src/v6/decisions/rules/protection_rules.py, src/v6/decisions/rules/exit_rules.py, src/v6/decisions/rules/roll_rules.py, src/v6/decisions/test_rules.py]
domain: quant-options
---

<objective>
Implement 12 priority-based decision rules for automated trading decisions.

Purpose: Create the complete rule set that evaluates positions and triggers actions (CLOSE, ROLL, ADJUST, HEDGE) based on market conditions, Greeks, DTE, IV, and profit/loss.

Output: 12 rule implementations (Priority 1-8), rule registration, integration tests.
</objective>

<execution_context>
~/.claude/get-shit-done/workflows/execute-plan.md
~/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/3-decision-rules-engine/3-01-SUMMARY.md (DecisionEngine foundation)
@.planning/phases/3-decision-rules-engine/3-02-SUMMARY.md (PortfolioRisk calculator)
@../v5/caretaker/decision_engine.py (v5 rules reference)
@src/v6/decisions/models.py (Decision models, Rule protocol)
@src/v6/decisions/engine.py (DecisionEngine)
@src/v6/decisions/portfolio_risk.py (PortfolioRiskCalculator)
@src/v6/models/ib_models.py (PositionSnapshot, Greeks)
@~/.claude/skills/expertise/quant-options/SKILL.md (options domain knowledge)

**12 Decision Rules (Priority Order):**

**Priority 1 - Catastrophe Protection:**
1. Catastrophe Protection: Market crash (>3% drop in 1hr) or IV explosion (>50% spike) → CLOSE IMMEDIATE

**Priority 1.3-1.5 - Single-Leg Protection:**
1.3 Single-Leg Exit: TP ≥80% or SL ≤-50% or DTE ≤21 for LONG/SHORT → CLOSE
1.4 Dynamic Trailing Stop: Peak ≥40% → Trail at 40% of peak → CLOSE
1.5 VIX Exit: VIX >35 or +5 points → CLOSE

**Priority 2-3 - Profit/Loss Management:**
2. Take Profit: UPL ≥80% (or ≥50% → close 50%) → CLOSE
3. Stop Loss: UPL ≤-200% (or ≤-50% if DTE<7) → CLOSE IMMEDIATE

**Priority 4-5 - Greek Risk:**
4. Delta Risk: |net_delta| >0.30 (IC) or >0.40 (spread) → CLOSE
5. IV Crush: IV drop >30% AND profit >20% → CLOSE
5.5 IV Percentile Exit: IV <30th percentile AND profit >20% → CLOSE

**Priority 6-8 - Time & Gamma Risk:**
6. DTE Roll: 21-25 DTE (roll) or ≤21 DTE (force) → ROLL to 45 DTE
7. Gamma Risk: |gamma| >0.10 AND DTE<14 → CLOSE
8. Time Exit: DTE ≤1 → CLOSE

**Tech stack available:**
- DecisionEngine with priority queue (from 3-01)
- PortfolioRiskCalculator (from 3-02)
- Rule protocol for extensibility

**Established patterns:**
- Rule protocol (priority, name, evaluate method)
- First-wins semantics (priority order)
- Async design
- dataclass(slots=True)

**Key decisions from 3-01, 3-02:**
- Protocol-based rules (flexible, testable)
- Priority 1-12 (lower = higher)
- Returns Decision or None
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create catastrophe and protection rules (Priority 1, 1.3-1.5)</name>
  <files>src/v6/decisions/rules/catastrophe.py, src/v6/decisions/rules/__init__.py</files>
  <action>
Create catastrophe and single-leg protection rules:

**File structure:**
- src/v6/decisions/rules/__init__.py - Package exports
- src/v6/decisions/rules/catastrophe.py - CatastropheProtection, SingleLegExit, TrailingStopLoss, VIXExit rules

**CatastropheProtection (Priority 1):**
```python
class CatastropheProtection:
    priority = 1
    name = "catastrophe_protection"

    async def evaluate(self, snapshot, market_data=None) -> Decision | None:
        # Check underlying 1h change
        if market_data and market_data.get("1h_change", 0) < -0.03:  # -3%
            return Decision(
                action=CLOSE, reason="Market crash: {symbol} down {change}%",
                rule="catastrophe_3pct_drop", urgency=IMMEDIATE
            )
        # Check IV spike
        if market_data and market_data.get("iv_change_percent", 0) > 0.50:  # +50%
            return Decision(
                action=CLOSE, reason="IV explosion: +{change}%",
                rule="catastrophe_iv_spike", urgency=IMMEDIATE
            )
        return None
```

**SingleLegExit (Priority 1.3):**
For LONG/SHORT strategies (not spreads):
- Check if UPL ≥80% → CLOSE
- Check if UPL ≤-50% → CLOSE
- Check if DTE ≤21 → CLOSE

**TrailingStopLoss (Priority 1.4):**
- Track peak UPL for each position (need state management)
- If peak ≥40%, set trailing stop at 40% of peak
- If current UPL ≤ trailing_stop → CLOSE

**VIXExit (Priority 1.5):**
- If VIX >35 → CLOSE
- If VIX +5 points from entry → CLOSE

Use Rule protocol (priority, name, evaluate). Reference ../v5/caretaker/decision_engine.py for logic, adapt to v6.
  </action>
  <verify>
python -c "
from src.v6.decisions.rules.catastrophe import CatastropheProtection
rule = CatastropheProtection()
print(f'Priority: {rule.priority}, Name: {rule.name}')
" prints "Priority: 1, Name: catastrophe_protection"
  </verify>
  <done>
All 4 rules created (CatastropheProtection, SingleLegExit, TrailingStopLoss, VIXExit), priorities correct, logic matches v5
  </done>
</task>

<task type="auto">
  <name>Task 2: Create profit/loss and Greek risk rules (Priority 2-5.5)</name>
  <files>src/v6/decisions/rules/protection_rules.py</files>
  <action>
Create profit/loss and Greek risk rules:

**TakeProfit (Priority 2):**
- If UPL ≥80% → CLOSE (take profit)
- If UPL ≥50% → CLOSE 50% of position (partial exit)

**StopLoss (Priority 3):**
- If UPL ≤-200% → CLOSE IMMEDIATE (stop loss)
- If DTE<7 AND UPL ≤-50% → CLOSE IMMEDIATE (accelerated stop)

**DeltaRisk (Priority 4):**
- Use PortfolioRiskCalculator to get portfolio delta
- If |portfolio_delta| >0.30 for Iron Condors → CLOSE
- If |portfolio_delta| >0.40 for vertical spreads → CLOSE
- Return decision with list of symbols causing delta risk

**IVCrush (Priority 5):**
- If IV drop >30% AND current_profit >20% → CLOSE
- Prevents IV crush from eroding gains

**IVPercentileExit (Priority 5.5):**
- If IV <30th percentile AND current_profit >20% → CLOSE
- Low IV environment with profits = exit signal

All rules follow Rule protocol. Use snapshot.upl_pct for profit/loss checks. Use PortfolioRiskCalculator from 3-02 for delta checks.
  </action>
  <verify>
python -c "
from src.v6.decisions.rules.protection_rules import TakeProfit, StopLoss, DeltaRisk, IVCrush, IVPercentileExit
for rule in [TakeProfit(), StopLoss(), DeltaRisk(), IVCrush(), IVPercentileExit()]:
    print(f'{rule.name}: priority={rule.priority}')
" shows all priorities 2-5.5
  </verify>
  <done>
All 5 rules created, priorities 2-5.5 correct, profit/loss checks work, delta risk checks work, IV rules work
  </done>
</task>

<task type="auto">
  <name>Task 3: Create time and gamma rules (Priority 6-8)</name>
  <files>src/v6/decisions/rules/roll_rules.py</files>
  <action>
Create time-based and gamma risk rules:

**DTERoll (Priority 6):**
- If 21 ≤ DTE ≤ 25 → ROLL (recommend roll to 45 DTE)
- If DTE ≤21 → ROLL (force roll to 45 DTE)
- Returns Decision(action=ROLL, reason=f"DTE={dte}, roll to 45 DTE")

**GammaRisk (Priority 7):**
- If |gamma| >0.10 AND DTE<14 → CLOSE
- High gamma near expiration is dangerous
- Returns Decision(action=CLOSE, urgency=HIGH)

**TimeExit (Priority 8):**
- If DTE ≤1 → CLOSE
- Last day before expiration, exit to avoid assignment risk

**ROLL action note:**
- ROLL means "close current position, open same strategy with 45 DTE"
- Decision should include metadata: {'roll_to_dte': 45}
- Execution layer (Phase 4) handles the actual roll

All rules follow Rule protocol. Use snapshot.dte for DTE checks. Use snapshot.greeks.gamma for gamma checks.
  </action>
  <verify>
python -c "
from src.v6.decisions.rules.roll_rules import DTERoll, GammaRisk, TimeExit
for rule in [DTERoll(), GammaRisk(), TimeExit()]:
    print(f'{rule.name}: priority={rule.priority}')
" shows priorities 6-8
  </verify>
  <done>
All 3 rules created, priorities 6-8 correct, DTE checks work, gamma risk check works, time exit works
  </done>
</task>

<task type="auto">
  <name>Task 4: Create rule registration and integration tests</name>
  <files>src/v6/decisions/rules/__init__.py, src/v6/decisions/test_rules.py</files>
  <action>
Create rule registration helper and integration tests:

**Rule registration (src/v6/decisions/rules/__init__.py):**
```python
from src.v6.decisions.rules.catastrophe import CatastropheProtection, SingleLegExit, TrailingStopLoss, VIXExit
from src.v6.decisions.rules.protection_rules import TakeProfit, StopLoss, DeltaRisk, IVCrush, IVPercentileExit
from src.v6.decisions.rules.roll_rules import DTERoll, GammaRisk, TimeExit

def register_all_rules(engine: DecisionEngine) -> None:
    """Register all 12 rules with DecisionEngine."""
    rules = [
        CatastropheProtection(),
        SingleLegExit(),
        TrailingStopLoss(),
        VIXExit(),
        TakeProfit(),
        StopLoss(),
        DeltaRisk(),
        IVCrush(),
        IVPercentileExit(),
        DTERoll(),
        GammaRisk(),
        TimeExit(),
    ]
    for rule in rules:
        engine.register_rule(rule)
```

**Integration tests (src/v6/decisions/test_rules.py):**
1. **test_all_rules_registered**: Register rules, verify engine has 12 rules
2. **test_priority_order**: Verify rules sorted by priority (1 → 8)
3. **test_catastrophe_triggers_first**: Create scenario with catastrophe + TP, catastrophe wins
4. **test_take_profit_triggers**: Position with UPL=85% → TP triggers
5. **test_stop_loss_triggers**: Position with UPL=-250% → SL triggers
6. **test_dte_roll_triggers**: Position with DTE=22 → ROLL triggers
7. **test_gamma_risk_triggers**: Position with gamma=0.15, DTE=10 → Gamma risk triggers
8. **test_no_trigger_returns_hold**: Healthy position (UPL=30%, DTE=30, normal Greeks) → HOLD

Use pytest with async tests. Mock PositionSnapshot with test data. Mock market_data for catastrophe/VIX rules. Run with: `conda run -n ib pytest src/v6/decisions/test_rules.py -v`
  </action>
  <verify>
conda run -n ib pytest src/v6/decisions/test_rules.py -v shows all tests passing (8+ passed)
  </verify>
  <done>
register_all_rules() works, all 12 rules registered, priority order verified, 8 integration tests pass, end-to-end flow works
  </done>
</task>

</tasks>

<verification>
Before declaring plan complete:
- [ ] `conda run -n ib pytest src/v6/decisions/test_rules.py -v` - all integration tests pass
- [ ] `python -c "from src.v6.decisions.rules import register_all_rules; print('OK')"` - imports work
- [ ] All 12 rules created and registered
- [ ] Priority order verified (1-8)
- [ ] Catastrophe rule triggers before TP/SL rules
- [ ] DTE roll returns ROLL action with metadata
- [ ] All rule actions (CLOSE, ROLL, HOLD) work correctly
</verification>

<success_criteria>

- 12 decision rules implemented (Priority 1-8)
- Rule registration helper created
- All rules follow Rule protocol
- Priority order verified (catastrophe first)
- Integration tests passing (8+ tests)
- ROLL action includes metadata (roll_to_dte)
- End-to-end flow works (DecisionEngine + rules)
  </success_criteria>

<output>
After completion, create `.planning/phases/3-decision-rules-engine/3-03-SUMMARY.md`:

# Phase 3 Plan 3: Decision Rules Implementation Summary

**Implemented 12 priority-based decision rules for automated trading decisions.**

## Accomplishments

- 12 decision rules created (Priority 1-8)
- Catastrophe and protection rules (Priority 1, 1.3-1.5)
- Profit/loss management rules (Priority 2-3)
- Greek risk rules (Priority 4-5.5)
- Time and gamma rules (Priority 6-8)
- Rule registration helper
- Integration tests (8 tests, all passing)

## Files Created/Modified

- `src/v6/decisions/rules/catastrophe.py` - Catastrophe and protection rules
- `src/v6/decisions/rules/protection_rules.py` - P/L and Greek risk rules
- `src/v6/decisions/rules/roll_rules.py` - Time and gamma rules
- `src/v6/decisions/rules/__init__.py` - Package exports and registration
- `src/v6/decisions/test_rules.py` - Integration tests

## Deviations from Plan

None - plan executed as specified.

## Next Step

Ready for 3-04-PLAN.md (Alert generation and management)
</output>
