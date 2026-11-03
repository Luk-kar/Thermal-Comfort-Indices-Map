#!/usr/bin/env bash
# PreToolUse hook: ask the user before a tool call that uses Python file I/O libraries.
set -euo pipefail

io_pattern='\b(import|from)[[:space:]]+(os|io|shutil|pathlib)\b|\b(os|io|shutil)\.[a-zA-Z_]+'
delete_pattern='\b(os\.(remove|unlink|rmdir|removedirs)|shutil\.rmtree)\b|\.(unlink|rmdir)\('

text=$(python3 -c 'import json, sys
t = json.load(sys.stdin).get("tool_input", {})
print("\n".join(v for k in ("command", "content", "new_string", "new_source") if isinstance(v := t.get(k), str)))')

if grep -qE "$delete_pattern" <<<"$text"; then
  reason="This removes files through a Python library (os, shutil or pathlib)."
elif grep -qE "$io_pattern" <<<"$text"; then
  reason="This uses a Python file I/O library (os, io, shutil or pathlib)."
else
  exit 0
fi

python3 -c 'import json, sys
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": sys.argv[1]}}))' "$reason"