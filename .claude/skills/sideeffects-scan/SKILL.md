---
name: sideeffects-scan
description: Scan a directory for side effects in the code, such as hidden I/O, global or mutable state, import-time work, in-place mutation of arguments and unlogged external calls. Read-only. Use when the user asks for side effects, hidden state or impure functions in a directory.
argument-hint: <directory>
context: fork
agent: Explore
allowed-tools: Read Grep Glob
---

# Side effects scan

Look in `$ARGUMENTS` (a directory relative to the project root) for side effects: anything a function or module does besides computing and returning a value from its arguments. Report only. Never edit, create or delete files, and never run code that uses `os`, `io`, `shutil` or `pathlib`.

## Steps

1. Read the "Structure", "Errors" and "Logging" sections of `.claude/rules/python/style.md`, and the "Pipeline" section of `CLAUDE.md`. Side effects are expected in the I/O stages (extract, load, GeoTIFF, maps) and in the entry point `utci_map/__main__.py`. They are not expected in `computation/`, `contracts/` or in `__init__.py` files.
2. Glob `$ARGUMENTS/**/*.py` (and `*.js` if the directory is under `frontend/`) and read the files. Include `tests/` only to note tests that leave state behind (files outside temporary directories, changed environment variables, unrestored monkeypatches).
3. Look for these categories:
   - **Import-time work:** objects created or code run at module level, for example `cdsapi.Client()` in `thermal_dataset_download.py`, configured loggers, reading files or the environment.
   - **Global state:** mutable module-level values, `global` or `nonlocal`, caches such as `lru_cache` on functions with non-hashable or mutable inputs, singletons.
   - **Hidden I/O:** reads or writes of files, network requests, subprocesses, `print`, logging handler setup, `os.environ` access, current working directory dependence, in functions whose name or signature does not say so.
   - **Argument mutation:** in-place changes to lists, dicts, dataclass fields or numpy arrays passed in (`arr[...] =`, `.append`, `.update`, `np.putmask`, `out=`), and returning a view that aliases an input.
   - **Time and randomness:** `datetime.now`, `time`, `random`, unseeded numpy random, which make results differ between runs.
   - **Process effects:** `sys.exit`, `exit`, warnings filters, `logging.basicConfig` outside `__main__.py`, changes to `sys.path`.
   - **Order dependence:** functions that only work when another function ran first, or output files that later stages read implicitly instead of receiving a path.
4. For each finding, check how many callers depend on it with Grep, so the report can say how risky removing it is.
5. Do not report effects that are the stated job of the function, such as a `write_*` function writing its output file, unless they also do something unrelated (an unexpected second file, a changed global).

## Report

Group by category. For each finding give `path:line`, what the side effect is, whether it is expected for that module, the callers affected, and a suggested fix (pass the dependency in, return a new value instead of mutating, move the effect to the entry point). Rank unexpected effects in pure modules first. If a directory is clean, say so plainly.
