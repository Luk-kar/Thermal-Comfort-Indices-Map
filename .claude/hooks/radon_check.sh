#!/usr/bin/env bash
file=$(jq -r '.tool_input.file_path // empty')
[[ "$file" == *.py ]] || exit 0

out=$(uv run radon cc -s -n C "$file"; uv run radon mi -s -n B "$file")
[ -z "$out" ] && exit 0   # fine: say nothing, cost nothing

{
  echo "Radon flagged this file (complexity C or worse, or MI below A):"
  echo "$out"
  echo "Read docs/refactoring-examples.md, then simplify."
} >&2
exit 2   # exit code 2 feeds stderr back to Claude
