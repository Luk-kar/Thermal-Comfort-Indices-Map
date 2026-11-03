---
paths:
  - "**/*.py"
---

# Python style

Ruff and mypy enforce formatting, imports, naming, type hints, and the complexity, parameter and nesting limits, using the settings in `pyproject.toml`. This file covers what they cannot check.

## Structure

- Separate reading and validating data, computing results, and writing outputs into distinct modules. Keep orchestration in the entry point.
- Keep shared data contracts, domain constants and run settings in their own modules, separate from the logic that uses them.
- Use absolute imports from the project root.
- Order a module with its public functions first and `_private` helpers below. Keep the public surface small.
- Keep functions to at most 30 lines of code, not counting the docstring, comments and blank lines. Break longer functions into smaller helpers with one clear purpose each.
- Keep files to at most 200 lines of code, or 300 for test files, not counting docstrings, comments and blank lines. Split larger files by responsibility.
- Do not use global variables: no mutable module-level state and no objects such as clients created at import time. Pass values and dependencies in as arguments. Immutable `UPPER_SNAKE_CASE` constants are allowed.
- Reduce excess complexity or nesting with helper functions, early returns or lookup tables. Group excess parameters into a dataclass.

## Naming and data

- Use American English everywhere, including identifiers, docstrings, comments and messages: `color`, `normalize`, `behavior`.
- Define domain names and thresholds once as constants instead of repeating literals.
- Use frozen dataclasses for structured data, and add `kw_only=True` for options objects.
- Represent missing numeric values explicitly, using NaN in arrays and NaN-aware functions. Document array shapes.
- Use keyword arguments when a call passes several values of similar meaning.

## Docstrings and comments

- State each module's purpose in its docstring. Use one line for simple helpers and add detail for public functions.
- Show non-obvious transformations with a concrete example ("E.g. ...").
- Use comments to explain why, not to restate the code.
- After each module's docstring is a new line

## Errors

- Validate inputs and fail early with a specific built-in exception.
- Make messages actionable: include the file name, offending value or field.
- When an `if`/`elif` chain checks a value against a known set of cases, end it with an `else` that raises an error, so an unexpected value cannot pass silently.
- Catch only exceptions you can handle.

## Logging

- Give each program (each entry point listed under Commands in `CLAUDE.md`) its own logger, built with the standard library `logging` module only.
- State the log file path in the program's config module, not hardcoded in the logging setup.
- Log at least the program's start and its outcome: completion, or the error that stopped it.
- Where practical, log filesystem and network I/O: the files a program reads and writes, with their sizes, and any network requests it makes.
- Log a `WARNING` or higher when I/O volume, count or duration crosses a threshold defined in the program's config, so an abnormal run is visible without reading every line.

## Tests

- Put tests in a `tests/` directory beside the module, named `test_<module>.py`.
- Start each test file with a module docstring of at most 3 sentences stating the intent of its tests.
- Write plain test functions when a test file has 10 or fewer test functions, counting each parametrized function once. Above 10, group them into `Test<Subject>` classes by the function or behavior under test.
- Name tests after the behavior they check.
- Test through public entry points, using small synthetic inputs and real temporary files. Mock only external services.
- When a test needs to reach into private internals to guard against unintended side effects during a refactor, put it in `<module>.unit.test.py` beside `test_<module>.py`, not inside it. Start that file with a module docstring stating plainly that it pins current internal behavior and is not a behavior contract. It does not need to follow the public-entry-points rule above, and may be rewritten freely whenever the internals change on purpose.
- Add explicit contract tests when the interface itself matters, such as checking that an endpoint exists or that an API request has the correct URL, parameters and payload.
- Use `pytest.mark.parametrize` for input variations and share fixtures through `conftest.py`.
- Add a docstring when a test's scenario isn't obvious from its name.
