---
name: style-check
description: Check the Python files in a directory against .claude/rules/python/style.md and report violations that Ruff, mypy and radon cannot catch. Read-only. Use when the user asks to check, audit or review a directory for style.
argument-hint: <directory>
context: fork
agent: Explore
allowed-tools: Read Grep Glob
---

# Style check

Audit `$ARGUMENTS` (a directory relative to the project root) against the project's Python style rules. Report only. Never edit, create or delete files, and never run code that uses `os`, `io`, `shutil` or `pathlib`.

## Steps

1. Read `.claude/rules/python/style.md` in full. It is the single source of truth, so do not rely on a remembered copy of the rules.
2. Glob `$ARGUMENTS/**/*.py` and read each file. If the directory does not exist or has no Python files, say so and stop.
3. Check every file against each rule in the style file that a linter cannot check. Ruff and mypy already cover formatting, imports, naming, type hints and the complexity, parameter and nesting limits, so skip those.
   - **Structure:** function length (30 code lines, not counting docstring, comments and blank lines), file length (200 code lines, 300 for tests), at most 7 entries per directory, `__init__.py` contains only `from x import name as name` re-exports (no logic, no `__all__`), imports from another package go only through its `__init__.py`, no stdlib or keyword names for modules and packages, public functions before `_private` helpers, no mutable module-level state or import-time objects.
   - **Layout:** blank lines between logical steps, after a docstring followed by code, and after `with` blocks and loops; one value per assignment line.
   - **Naming and data:** American English in identifiers, docstrings, comments and messages; repeated domain literals instead of constants; frozen dataclasses with `kw_only=True` for options; Pydantic only for external runtime data, in strict mode; NaN for missing numbers; documented array shapes; keyword arguments for similar-meaning values.
   - **Docstrings and comments:** module purpose docstring followed by a blank line, "E.g." examples for non-obvious transformations, comments that explain why.
   - **Errors:** early validation with specific built-in exceptions, actionable messages naming the file or value, `else: raise` ending `if`/`elif` chains over known cases, no broad `except`.
   - **Logging:** one stdlib logger per entry point, log path in the config module, start and outcome logged, I/O with sizes, a `WARNING` when a threshold in the config is crossed.
   - **Tests:** `tests/test_<module>.py` naming, module docstring of at most 3 sentences, plain functions up to 10 tests and `Test<Subject>` classes above that, behavior-based names, arrange/act/assert blank lines, `.unit.test.py` files with the "not a behavior contract" docstring, `parametrize` and `conftest.py` use, mocks only for external services.
4. Count lines by hand for the length limits. Say "approximately" when a count is within 3 lines of a limit.

## Report

Group findings by rule. For each one give `path:line`, the rule violated, and a one-line fix. Finish with a count per rule and the files that are clean. Do not invent findings: if a rule cannot be judged from the code, list it under "Not checked" with the reason.
