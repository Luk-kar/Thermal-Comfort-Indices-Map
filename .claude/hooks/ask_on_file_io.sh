#!/usr/bin/env bash
# PreToolUse hook: ask the user before a tool call that uses Python file I/O libraries.
set -euo pipefail

io_pattern='\b(import|from)[[:space:]]+(os|io|shutil|pathlib)\b|\b(os|io|shutil)\.[a-zA-Z_]+'
delete_pattern='\b(os\.(remove|unlink|rmdir|removedirs)|shutil\.rmtree)\b|\.(unlink|rmdir)\('

text=$(jq -r '[.tool_input.command, .tool_input.content, .tool_input.new_string, .tool_input.new_source]
  | map(select(. != null)) | join("\n")')

if grep -qE "$delete_pattern" <<<"$text"; then
  reason="This removes files through a Python library (os, shutil or pathlib)."
elif grep -qE "$io_pattern" <<<"$text"; then
  reason="This uses a Python file I/O library (os, io, shutil or pathlib)."
else
  exit 0
fi

jq -n --arg reason "$reason" '{hookSpecificOutput: {
  hookEventName: "PreToolUse",
  permissionDecision: "ask",
  permissionDecisionReason: $reason
}}'
