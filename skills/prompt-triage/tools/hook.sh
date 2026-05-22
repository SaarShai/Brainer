#!/bin/bash
# agents-triage UserPromptSubmit hook.
#
# stdin:  {session_id, transcript_path, prompt, ...}  (from Claude Code)
# stdout: a directive block that gets injected into the main model's context.
#         Strong nudge to delegate via Task tool to a cheaper subagent/model.
#
# Opus sees the directive + user prompt. Ideal path: opus emits a Task() call
# with the suggested args and does NO deep reasoning. Actual task runs on the
# lesser subagent's context budget.
#
# Override: user types "NO TRIAGE" anywhere in prompt → hook exits silently.

set -e
INPUT=$(cat)

# extract prompt via python one-liner
PROMPT=$(printf '%s' "$INPUT" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('prompt') or d.get('user_prompt') or '')
except Exception: pass
" 2>/dev/null)

# bypass flag
if printf '%s' "$PROMPT" | grep -qiE "NO[ _-]?TRIAGE|/opus"; then
    exit 0
fi

# classify
HERE="$(cd "$(dirname "$0")" && pwd)"
CLASSIFIER="$HERE/classify.py"
[ -f "$CLASSIFIER" ] || exit 0   # skill not installed properly; don't break hook

CLS=$(printf '%s' "$PROMPT" | python3 "$CLASSIFIER" 2>/dev/null)
[ -z "$CLS" ] && exit 0

# If main-model required (tier=hard or agent=none), emit nothing.
TIER=$(echo "$CLS" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tier',''))" 2>/dev/null)
AGENT=$(echo "$CLS" | python3 -c "import json,sys; print(json.load(sys.stdin).get('agent',''))" 2>/dev/null)
[ "$TIER" = "hard" ] && exit 0
[ "$AGENT" = "none" ] && exit 0

# Build directive
cat <<EOF
⚡ [agents-triage] Task classified:
$CLS

**Strong recommendation:** dispatch this task via the \`Task\` tool using the suggested subagent + model, then return its result. Do NOT engage deep-thinking or load full context yourself. The subagent will load only what it needs.

If classification seems wrong, user can re-send with "NO TRIAGE" to bypass.
EOF

exit 0
