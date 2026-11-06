---
name: refactor-scan
description: Scan a directory for duplicated or near-duplicated logic that could become a generalized shared module reused by other sub-modules. Read-only; proposes, does not edit. Use when the user asks for refactor candidates, shared helpers or deduplication in a directory.
argument-hint: <directory>
context: fork
agent: Explore
allowed-tools: Read Grep Glob
---

# Refactor scan

Look in `$ARGUMENTS` (a directory relative to the project root) for logic that appears in more than one place and could be generalized into a shared module. Report only. Never edit, create or delete files, and never run code that uses `os`, `io`, `shutil` or `pathlib`.

## Steps

1. Read the "Structure" section of `.claude/rules/python/style.md` and the "Repository notes" in `CLAUDE.md` about package interfaces. Any proposal must respect them: each package exposes only `__init__.py` re-exports, other modules are private, and a package depends on at most a few siblings.
2. Glob `$ARGUMENTS/**/*.py` and read the files. Skip `tests/` unless the duplicated code is in test helpers, where the proposal is a `conftest.py` fixture or a shared helper.
3. Find candidates:
   - Functions or blocks with the same steps and only different names, constants or array fields.
   - The same validation, conversion, logging or error-message pattern repeated across modules.
   - Several functions that differ by one parameter and could take it as an argument or a lookup table.
   - Helpers that live in one package but are imported or re-implemented by its siblings.
4. For each candidate, decide where the shared code should live. Prefer an existing package such as `utci_map/source/contracts/` for shared types and settings, otherwise a new package with its own `__init__.py`. Check that the new location does not create an import cycle or break the 7-entries-per-directory limit.
5. Ignore similarities that are only coincidental, such as two short unrelated loops. A candidate needs at least two real occurrences and a clear single purpose.

## Report

For each candidate give: a short name, the occurrences as `path:line`, the proposed module path and function signature, which callers change, and the risk (behavior differences between the copies, tests that would need updating). Rank by value: more occurrences and more lines saved first. If nothing qualifies, say so plainly.
