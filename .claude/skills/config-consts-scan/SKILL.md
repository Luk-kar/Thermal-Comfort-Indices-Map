---
name: config-consts-scan
description: Scan a directory for repeated literals and values that should become named constants in a config or entry module (for example utci_map/source/contracts/config.py). Read-only. Use when the user asks for configuration constants, magic values or repeated settings in a directory.
argument-hint: <directory>
context: fork
agent: Explore
allowed-tools: Read Grep Glob
---

# Config constants scan

Look in `$ARGUMENTS` (a directory relative to the project root) for literals that repeat or that are good candidates for a config or entry-module constant. Report only. Never edit, create or delete files, and never run code that uses `os`, `io`, `shutil` or `pathlib`.

## Steps

1. Read `utci_map/source/contracts/config.py` and `utci_map/source/contracts/schema.py` so you know which constants already exist. Do not propose a constant that is already defined there; report the places that still use the raw literal instead.
2. Read `.claude/rules/python/style.md`: "Define domain names and thresholds once as constants", immutable `UPPER_SNAKE_CASE` is allowed, no mutable module-level state.
3. Glob `$ARGUMENTS/**/*.py` (and `*.js` if the directory is under `frontend/`) and read the files.
4. Collect candidates:
   - Numbers used as thresholds, limits, sizes, tolerances or years, and temperatures such as 9 and 26 °C.
   - Strings that repeat: file names, band names, field names, region names, units, log messages, CRS codes such as `EPSG:4326` and `EPSG:3857`.
   - Values that must match another place, per the "Keeping things in sync" section of `CLAUDE.md`: regions, years, stress brackets, popup labels.
   - Settings that a user might change between runs and that are currently buried in a function body.
5. Use Grep to count each literal across the whole repository, not only `$ARGUMENTS`, so cross-directory duplicates are visible.
6. Skip trivial values (`0`, `1`, empty strings), values that are only meaningful in a single expression, and test data that is intentionally explicit.

## Report

A table with: the literal, number of occurrences, the main locations as `path:line`, a suggested `UPPER_SNAKE_CASE` name, and the target module (existing config or schema module, or the entry module). Mark any entry that duplicates a value across Python and JavaScript, or between `thermal_dataset_download.py` and `config.py`, as a sync risk. Rank by number of occurrences. If nothing qualifies, say so plainly.
