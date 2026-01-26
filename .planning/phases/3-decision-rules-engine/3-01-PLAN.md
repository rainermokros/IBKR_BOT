---
phase: 3-decision-rules-engine
plan: 01
type: execute
depends_on: []
files_modified: [src/v6/decisions/__init__.py, src/v6/decisions/models.py, src/v6/decisions/engine.py, src/v6/decisions/test_engine.py]
domain: quant-options
---

<objective>
Create rule evaluation framework with priority queue execution and state management.

Purpose: Establish the foundation for evaluating decision rules in priority order, enabling the 12 rule-based decision system that drives automated trading decisions.

Output: DecisionEngine class with priority queue, rule execution framework, Decision/Action models, and unit tests.
</objective>

<execution_context>
~/.claude/get-shit-done/workflows/execute-plan.md
~/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/2.1-position-polling/2.1-04-SUMMARY.md
@../v5/caretaker/decision_engine.py (v5 reference for patterns)
@src/v6/models/ib_models.py (existing models)
@src/v6/data/position_streamer.py (position updates)
@~/.claude/skills/expertise/quant-options/SKILL.md (options domain knowledge)

**Tech stack available:**
- Python 3.11+ dataclasses with slots=True
- Delta Lake for persistence (from Phase 2)
- ib_async for IB integration (from Phase 1)
- pytest for testing

**Established patterns:**
- Use dataclasses with slots=True for performance (from Phase 1)
- Delta Lake for all persistence (from Phase 2)
- Singleton pattern for managers (from Phase 2)
- Handler registration protocol for extensibility (from Phase 2)

**Key files from Phase 2:**
- src/v6/models/ib_models.py - PositionSnapshot, Greeks models
- src/v6/data/position_streamer.py - Position updates via handlers
- src/v6/data/repositories/positions.py - Position data access
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create decision models and enums</name>
  <files>src/v6/decisions/models.py</files>
  <action>
Create decision data models and enums:

1. **DecisionAction enum**: HOLD, CLOSE, ROLL, ADJUST, HEDGE, REDUCE
2. **Urgency enum**: IMMEDIATE, HIGH, NORMAL, LOW
3. **Decision dataclass** (slots=True):
   - action: DecisionAction
   - reason: str (what rule triggered)
   - rule: str (rule name/identifier)
   - urgency: Urgency
   - metadata: dict[str, Any] (rule-specific data)
   - timestamp: datetime
4. **RuleResult dataclass** (slots=True):
   - triggered: bool
   - decision: Optional[Decision]
   - priority: int (1-12, lower = higher priority)

Use @dataclass(slots=True) for performance. Add __post_init__ validation. Include type hints for all fields.
  </action>
  <verify>
python -c "from src.v6.decisions.models import Decision, DecisionAction, Urgency; d = Decision(action=DecisionAction.HOLD, reason='test', rule='none', urgency=Urgency.NORMAL); print(d)" executes without errors
  </verify>
  <done>
All enums and models created, type hints complete, __post_init__ validation works, imports succeed
  </done>
</task>

<task type="auto">
  <name>Task 2: Create DecisionEngine with priority queue</name>
  <files>src/v6/decisions/engine.py, src/v6/decisions/__init__.py</files>
  <action>
Create DecisionEngine class with priority queue execution:

**Class structure:**
```python
class DecisionEngine:
    def __init__(self, rules: list[Rule] | None = None)
    async def evaluate(self, snapshot: PositionSnapshot, market_data: dict | None = None) -> Decision
    def register_rule(self, rule: Rule) -> None
    def get_rule_stats(self) -> dict[str, int]
```

**Key features:**
1. **Priority queue**: Rules sorted by priority (1-12), execute in order
2. **First-wins semantics**: Stop at first rule that triggers (returns non-None Decision)
3. **Rule registration**: Register rules dynamically (not hardcoded)
4. **Stats tracking**: Track how often each rule triggers
5. **Async design**: Use async/await for consistency with Phase 2

**Rule protocol:**
```python
class Rule(Protocol):
    priority: int  # 1-12
    name: str
    async def evaluate(self, snapshot: PositionSnapshot, market_data: dict | None = None) -> Decision | None
```

**Implementation:**
- Store rules in list, sort by priority on registration
- In evaluate(): iterate sorted rules, call rule.evaluate(), return first non-None result
- If no rules trigger, return Decision(action=HOLD, reason="No rule triggered", rule="none", urgency=NORMAL)
- Track stats in dict: {rule_name: trigger_count}

Reference ../v5/caretaker/decision_engine.py for patterns (priority-based evaluation, first-wins), but adapt to v6 architecture (async, protocol-based).
  </action>
  <verify>
python -c "
from src.v6.decisions.engine import DecisionEngine
from src.v6.decisions.models import Decision, DecisionAction, Urgency
from src.v6.models.ib_models import PositionSnapshot
engine = DecisionEngine()
print('Rules:', len(engine._rules))
print('Engine created successfully')
" executes and shows 0 rules (empty by default)
  </verify>
  <done>
DecisionEngine class created, priority queue works, rule registration works, evaluate() returns HOLD with no rules, stats tracking functional
  </done>
</task>

<task type="auto">
  <name>Task 3: Create unit tests for DecisionEngine</name>
  <files>src/v6/decisions/test_engine.py</files>
  <action>
Create comprehensive unit tests for DecisionEngine:

**Test cases:**
1. **test_empty_engine_returns_hold**: Engine with 0 rules returns HOLD decision
2. **test_priority_order**: Create 3 mock rules (priorities 1, 2, 3), verify rule 1 executes first even if rule 2 would trigger
3. **test_first_wins_semantics**: If rule 1 triggers, rules 2-3 never execute
4. **test_rule_registration**: Register rules dynamically, verify they're sorted by priority
5. **test_stats_tracking**: Call evaluate multiple times, verify stats track trigger counts
6. **test_no_trigger_returns_hold**: Create rule that returns None, verify HOLD decision
7. **test_market_data_passing**: Verify market_data dict passed to rule.evaluate()

**Mock rule for testing:**
```python
class MockRule:
    def __init__(self, priority: int, name: str, should_trigger: bool = False):
        self.priority = priority
        self.name = name
        self.should_trigger = should_trigger
        self.call_count = 0

    async def evaluate(self, snapshot, market_data=None):
        self.call_count += 1
        if self.should_trigger:
            return Decision(action=CLOSE, reason=f"Triggered {self.name}", rule=self.name, urgency=IMMEDIATE)
        return None
```

Use pytest with async tests (pytest-asyncio). Create test fixtures for PositionSnapshot. Run tests with: `conda run -n ib pytest src/v6/decisions/test_engine.py -v`
  </action>
  <verify>
conda run -n ib pytest src/v6/decisions/test_engine.py -v shows all tests passing (7 passed)
  </verify>
  <done>
All 7 tests pass, code coverage >90% for engine.py, async tests work correctly
  </done>
</task>

</tasks>

<verification>
Before declaring plan complete:
- [ ] `conda run -n ib pytest src/v6/decisions/test_engine.py -v` - all tests pass
- [ ] `python -c "from src.v6.decisions import DecisionEngine; print('Import success')"` - imports work
- [ ] DecisionEngine has 0 rules by default (extensible design)
- [ ] Rules sorted by priority when registered
- [ ] First-wins semantics verified by tests
- [ ] Stats tracking functional
</verification>

<success_criteria>

- Decision models created with all enums and dataclasses
- DecisionEngine implements priority queue execution
- Rule registration protocol working (Protocol-based, extensible)
- First-wins semantics verified (priority 1 executes before priority 2)
- All unit tests passing (7+ tests)
- No linting errors (ruff check passes)
  </success_criteria>

<output>
After completion, create `.planning/phases/3-decision-rules-engine/3-01-SUMMARY.md`:

# Phase 3 Plan 1: Rule Evaluation Framework Summary

**Created DecisionEngine with priority queue execution and rule registration protocol.**

## Accomplishments

- Decision models and enums (DecisionAction, Urgency, Decision, RuleResult)
- DecisionEngine class with priority queue (first-wins semantics)
- Rule registration protocol (Protocol-based, extensible)
- Unit tests (7 tests, all passing)
- Foundation for 12-rule decision system

## Files Created/Modified

- `src/v6/decisions/models.py` - Decision data models
- `src/v6/decisions/engine.py` - DecisionEngine with priority queue
- `src/v6/decisions/__init__.py` - Package exports
- `src/v6/decisions/test_engine.py` - Unit tests

## Decisions Made

- Used Protocol for Rule interface (duck-typing, flexible)
- Priority 1-12 (lower = higher priority, matches v5)
- First-wins semantics (stop at first triggered rule)
- Stats tracking for rule analysis
- Async design for consistency with Phase 2

## Deviations from Plan

None - plan executed as specified.

## Next Step

Ready for 3-02-PLAN.md (Portfolio-level risk calculations)
</output>
