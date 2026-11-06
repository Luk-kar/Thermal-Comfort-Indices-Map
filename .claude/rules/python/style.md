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
- Organize code as a shallow tree of packages, so the structure alone shows what is public and what is private. Keep at most 7 entries (files and subdirectories) per directory, and nest deeper instead of adding more.
- Give each package an `__init__.py` as its only public interface. It contains no logic, only re-exports of the fewest names other packages need. Don't define `__all__`.
- Treat every module in a package other than `__init__.py` as private: code outside the package must not import it.
- Import from another package only through its `__init__.py`. Let each package depend on at most a few sibling packages.
- Treat a package's own `tests/` folder as part of the package: its tests may import the package's private modules.
- Don't name modules or packages after Python keywords or standard-library modules, such as `types`, `logging` or `io`.
- Order a module with its public functions first and `_private` helpers below. Keep the public surface small.
- Keep functions to at most 30 lines of code, not counting the docstring, comments and blank lines. Break longer functions into smaller helpers with one clear purpose each.
- Keep files to at most 200 lines of code, or 300 for test files, not counting docstrings, comments and blank lines. Split larger files by responsibility.
- Do not use global variables: no mutable module-level state and no objects such as clients created at import time. Pass values and dependencies in as arguments. Immutable `UPPER_SNAKE_CASE` constants are allowed.
- Reduce excess complexity or nesting with helper functions, early returns or lookup tables. Group excess parameters into a dataclass.

## Layout

- Separate each logical step inside a function body with a blank line: setup, each action, and the checks or return. Don't pack several steps into one dense block.
- In tests, put blank lines between arrange, act and assert.
- Put a blank line after a docstring that is followed by code, and after a `with` block or loop before unrelated code.
- Assign one value per line. Don't combine unrelated values in one tuple assignment such as `path, cold = make_input(), outputs["cold"]`.

## Naming and data

- Use American English everywhere, including identifiers, docstrings, comments and messages: `color`, `normalize`, `behavior`.
- Give variables, parameters, functions and attributes descriptive names that say what they hold or do. Don't use single letters or abbreviations: write `index`, `left`, `right`, `date_format`, `file_descriptor`, `count` instead of `i`, `a`, `b`, `fmt`, `fd`, `n`. Keep an abbreviation only when it is the standard name in the domain (`utci`, `crs`, `png`), a conventional library alias (`np`, `xr`), or `_` for a value that is deliberately unused.
- Define domain names and thresholds once as constants instead of repeating literals.
- Use frozen dataclasses for structured data, and add `kw_only=True` for options objects.
- Use Pydantic models only where mypy can't help: structured data entering the program from outside at runtime, such as JSON or GeoJSON files, API responses and config files. Turn on strict mode so values are rejected instead of silently converted. Don't use Pydantic for data built by our own code, where mypy already checks the types, or for numpy arrays, whose shape and dtype it can't check.
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
