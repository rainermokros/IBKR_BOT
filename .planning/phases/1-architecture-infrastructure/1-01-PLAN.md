---
phase: 1-architecture-infrastructure
plan: 01
type: execute
depends_on: []
files_modified: [pyproject.toml, .python-version, .gitignore, ruff.toml, pytest.ini, tests/__init__.py]
---

<objective>
Set up v6 project structure with Python 3.11+, development environment, and testing framework.

Purpose: Establish the foundation for all subsequent development with proper packaging, linting, and testing infrastructure.
Output: Working Python project with src/ layout, dependencies installed, and development tools configured.
</objective>

<execution_context>
~/.claude/get-shit-done/workflows/execute-plan.md
./summary.md
</execution_context>

<context>
@v6/.planning/PROJECT.md
@v6/.planning/ROADMAP.md
@v6/.planning/phases/1-architecture-infrastructure/1-RESEARCH.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create src/ layout with pyproject.toml</name>
  <files>pyproject.toml, .python-version, src/v6/__init__.py</files>
  <action>
Create src/ layout with pyproject.toml following 2025 Python packaging standards:

**File structure:**
```
v6/
├── pyproject.toml       # Modern Python packaging (replaces setup.py/setup.cfg)
├── .python-version      # Pin Python version
├── src/v6/              # Package namespace (src layout)
│   └── __init__.py
```

**pyproject.toml content:**
- Build system: hatchling (modern, fast)
- Project metadata: name="v6-trading-system", version="0.1.0", requires-python=">=3.11"
- Core dependencies: deltalake>=0.20.0, ib_async>=0.1.0, pydantic>=2.0.0, polars>=0.20.0, py_vollib_vectorized>=0.1.0, python-dotenv>=1.0.0, loguru>=0.7.0
- Dev dependencies: pytest>=7.0.0, pytest-asyncio>=0.23.0, ruff>=0.8.0
- **Don't use old setup.py** - pyproject.toml is 2025 standard
- **Don't put code in root** - all code in src/v6/ to prevent import conflicts

**Why src/ layout:**
- Prevents import conflicts (tests import from v6, not local directory)
- Better packaging hygiene
- Standard 2025 practice
- Easier testing (pytest can import from installed package)

**.python-version:** Single line "3.11" (pins version for tools like ruff)
  </action>
  <verify>
    pyproject.toml exists and is valid Python 3.11+ config
    src/v6/__init__.py exists
    python --version shows 3.11+
  </verify>
  <done>
    pyproject.toml created with all dependencies
    src/v6/__init__.py created
    .python-version pins to 3.11
  </done>
</task>

<task type="auto">
  <name>Task 2: Configure development tools (ruff, pytest, .gitignore)</name>
  <files>ruff.toml, pytest.ini, .gitignore, tests/__init__.py, tests/conftest.py</files>
  <action>
Configure development tools for linting, formatting, and testing:

**ruff.toml (linter + formatter in one):**
```toml
[target.line-length]
line-length = 100

[format]
quote-style = "double"
indent-style = "space"

[lint]
select = ["E", "F", "I", "N", "W", "B"]
ignore = ["E501"]  # Line length handled by formatter

[per-file-ignores]
"__init__.py" = ["F401"]  # Unused imports OK in __init__.py
```
**Why ruff:** 100x faster than flake8+black, single config, 2025 standard

**pytest.ini (async test support):**
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_default_fixture_loop_scope = function
```
**Why pytest-asyncio:** Auto-detects async tests, no decorators needed

**.gitignore:**
```
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
.eggs/
.eggs-src/
lib64/lib/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
venv/
ENV/
env/
.venv/

# IDEs
.vscode/
.idea/
*.swp
*.swo
*~

# Environment variables
.env
.env.local
.env.*.local

# Delta Lake
data/lake/_delta_log/

# Testing
.pytest_cache/
.coverage
htmlcov/

# Logs
logs/
*.log
```

**tests/conftest.py (shared fixtures):**
```python
import pytest
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
```
**Why conftest:** Makes tests import v6 modules without installation
  </action>
  <verify>
    ruff check passes on empty src/v6/
    pytest --collect-only finds no tests (expected)
    git init .gitignore initialized (if not already)
  </verify>
  <done>
    ruff.toml configured with line-length 100, standard lint rules
    pytest.ini configured with asyncio support
    .gitignore excludes Python artifacts, venv, .env, Delta Lake logs
    tests/conftest.py adds src/ to Python path
  </done>
</task>

</tasks>

<verification>
Before declaring plan complete:
- [ ] `python --version` returns 3.11+
- [ ] `pip list | grep -E "(deltalake|ib_async|pydantic|polars)"` shows all dependencies installed
- [ ] `ruff check src/v6/` passes with no errors
- [ ] `pytest --collect-only` runs without errors (0 tests collected is expected)
- [ ] `git status` shows .gitignore is tracked
</verification>

<success_criteria>
- All tasks completed
- All verification checks pass
- Project structure matches 2025 best practices (src/ layout, pyproject.toml)
- Development tools configured (ruff, pytest-asyncio)
- Ready for next plan (Delta Lake schema)
</success_criteria>

<output>
After completion, create `v6/.planning/phases/1-architecture-infrastructure/1-01-SUMMARY.md`:

# Phase 1 Plan 1: Project Structure & Environment Summary

**Initialized v6 trading system with modern Python packaging and development environment.**

## Accomplishments

- Created src/ layout with pyproject.toml (Python 3.11+)
- Configured all core dependencies (deltalake, ib_async, Pydantic, Polars)
- Set up development tools (ruff for linting/formatting, pytest-asyncio for testing)
- Created .gitignore for Python projects
- Set up tests/conftest.py for easy imports

## Files Created/Modified

- `pyproject.toml` - Modern Python packaging with all dependencies
- `.python-version` - Pins Python to 3.11
- `src/v6/__init__.py` - Package namespace
- `ruff.toml` - Linter and formatter configuration
- `pytest.ini` - Async test configuration
- `.gitignore` - Python-specific ignores
- `tests/__init__.py` - Test package
- `tests/conftest.py` - Shared pytest fixtures

## Decisions Made

- **src/ layout**: Standard 2025 practice, prevents import conflicts
- **pyproject.toml over setup.py**: Modern packaging, unified dependency management
- **ruff over flake8+black**: 100x faster, single configuration
- **pytest-asyncio**: Auto-detects async tests, no decorators needed
- **Python 3.11+**: User requirement, ecosystem maturity

## Issues Encountered

None

## Next Step

Ready for 01-02-PLAN.md (Delta Lake schema)
</output>
