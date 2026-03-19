# AGENTS.md

Guidance for coding agents working in this repository.

## Project Snapshot

- Language: Python (3.10+; tested on Python 3.12 in this repo).
- App type: PyQt6 Windows tray app.
- Package layout: `src/deskcoach/...`.
- Tests: `pytest` under `tests/`.
- Packaging: setuptools via `pyproject.toml`.
- Optional executable build: PyInstaller with `main.spec`.

## Repository Structure

- `src/deskcoach/main.py`: app entry point and runtime wiring.
- `src/deskcoach/app.py`: QApplication creation/styling setup.
- `src/deskcoach/views/`: UI windows/dialogs.
- `src/deskcoach/services/`: reminders, notifier, session watcher, API client.
- `src/deskcoach/models/store.py`: SQLite persistence and aggregates.
- `src/deskcoach/utils/`: utility helpers (time math, Qt helpers).
- `tests/`: pytest suite.
- `config.toml`: developer/default runtime config in repo root.

## Setup Commands

Use PowerShell on Windows unless you have a reason not to.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e .
```

## Run Commands

- Run app module directly: `python -m deskcoach.main`
- Run installed console entry point: `deskcoach`
- Verify package import: `python -c "import deskcoach; print(deskcoach.__file__)"`

## Test Commands

- Full suite (quiet): `pytest -q`
- Verbose failures: `pytest -q -ra`
- Stop on first failure: `pytest -q -x`
- Run one file: `pytest -q tests/test_config.py`
- Run one test function: `pytest -q tests/test_config.py::test_load_config_from_custom_path`
- Run one test class/function pattern: `pytest -q tests/test_api_client.py -k success`
- Run tests matching keyword globally: `pytest -q -k "day_start and not matrix"`
- Show local variables on failure: `pytest -q -l`

Notes:

- `pytest.ini` sets `addopts = -q` and adds `src` to `pythonpath`.
- `tests/conftest.py` sets `QT_QPA_PLATFORM=offscreen` for headless Qt tests.

## Build Commands

- PyInstaller executable (from repo root): `pyinstaller main.spec`
- Output artifact is expected under `dist/` (for example `dist/DeskCoach.exe`).
- Python package build (optional):

```powershell
python -m pip install build
python -m build
```

## Lint / Static Analysis Commands

This repository currently has no enforced linter/type-check config committed
(no Ruff/Black/Mypy config in `pyproject.toml` as of this writing).

Use these lightweight checks unless a task asks for additional tools:

- Syntax smoke check: `python -m compileall src tests`
- Dead-simple style sweep via tests: `pytest -q`

If your environment already has Ruff/Mypy and the task requests linting,
use them as opt-in checks and report that they are not repo-mandated.

## Code Style Guidelines

Follow existing code patterns over personal preference.

### Imports

- Prefer `from __future__ import annotations` at top of modules.
- Order imports by groups: stdlib, third-party, local package.
- Keep imports explicit; avoid wildcard imports.
- In this codebase, fallback import patterns are common for package vs script runs:
  `try` relative import, `except` absolute import.
- For optional runtime dependencies (especially Qt widgets in tests), use guarded
  imports with safe fallbacks to keep import-time behavior robust.

### Formatting

- Use 4-space indentation.
- Follow PEP 8 style and keep code readable over strict line-length absolutism.
- Preserve existing docstring style (triple double-quotes, concise and practical).
- Prefer small helper methods for non-trivial UI/state logic.
- Do not add decorative comments; add comments only when behavior is non-obvious.

### Types and Annotations

- Add type hints for public functions and important internals.
- Use modern unions (`X | None`) where already used.
- Keep runtime-safe typing pragmas when needed in Qt-heavy code
  (for example `# type: ignore[attr-defined]` on dynamic Qt attributes).
- For config-like objects, this repo often uses `SimpleNamespace`; preserve that
  unless the task explicitly introduces a stronger schema.

### Naming Conventions

- Modules/functions/variables: `snake_case`.
- Classes: `PascalCase`.
- Constants: `UPPER_SNAKE_CASE`.
- Test names: `test_*` with behavior-focused names.
- Keep UI text user-friendly and sentence-cased.

### Error Handling and Logging

- This app is defensive by design: avoid crashing UI/event loops.
- At integration boundaries (Qt signals, Windows APIs, notification APIs,
  filesystem/DB edge paths), graceful `try/except` with fallback is common.
- In core validation paths, raise explicit errors (for example `ValueError`,
  `FileNotFoundError`, or wrapping in `RuntimeError` as appropriate).
- Log through module loggers: `log = logging.getLogger(__name__)`.
- Use structured logging with `%s` formatting (not f-strings in logging calls).

### Data / Persistence Patterns

- Use `pathlib.Path` for filesystem paths.
- Use context managers for SQLite connections.
- Keep SQL statements simple and explicit; preserve current schema assumptions.
- Prefer non-destructive migrations/changes unless task explicitly requires schema changes.

### UI and Runtime Behavior

- Preserve tray-app behavior: app should not quit when main window closes.
- Keep headless-test compatibility for Qt imports and widgets.
- Favor resilient behavior over strict failures for optional Windows-specific APIs.

## Testing Guidelines

- Add/adjust tests in `tests/` alongside behavior changes.
- Prefer deterministic tests with monkeypatch/dummy classes over real network/OS calls.
- Keep tests fast and focused; this suite is intended to run quickly with `pytest -q`.
- For bug fixes, include at least one regression-style assertion.

## Agent Workflow Expectations

- Make minimal, targeted diffs.
- Do not refactor unrelated modules while fixing a specific issue.
- Preserve public interfaces unless task requires a breaking change.
- When changing config keys or persistence behavior, update tests in same change.
- If adding new tooling commands, document them in `README.md` and this file.

## Cursor / Copilot Rule Files

At the time of analysis, no repository-specific rule files were found:

- No `.cursorrules`
- No `.cursor/rules/`
- No `.github/copilot-instructions.md`

If any of these files are added later, treat them as higher-priority constraints
and update this AGENTS.md accordingly.
