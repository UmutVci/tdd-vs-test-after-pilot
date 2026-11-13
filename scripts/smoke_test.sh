#!/usr/bin/env bash
# Checks the agent configuration with a trivial, task-unrelated prompt:
# git commits and ./run_tests.sh must work, reading outside the workspace must not,
# and no user-level customizations (MCP servers, plugins, CLAUDE.md, memory) may load.
# Usage: scripts/smoke_test.sh
set -uo pipefail

source "$(dirname "$0")/agent_config.sh"

stamp="$(date +%Y%m%d%H%M%S)"
workspace="$RUNS_ROOT/_smoke_$stamp"
log_dir="$RUNS_ROOT/_smoke_$stamp.logs"
canary_file="$RUNS_ROOT/_smoke_canary_$stamp.txt"
canary_token="CANARY-$RANDOM$RANDOM$RANDOM"

init_workspace "$workspace" || exit 1
mkdir -p "$log_dir"
printf '%s\n' "$canary_token" > "$canary_file"
canary_win="$(cygpath -w "$canary_file" 2>/dev/null || echo "$canary_file")"

prompt="This is a configuration check, not a programming task. Do exactly these steps:
1. Run ./run_tests.sh once (it is expected to report that no tests ran).
2. In ONE Bash call, create notes.txt with a shell heredoc and commit it:
   cat > notes.txt <<'EOF' (content: smoke) followed by && git add notes.txt && git commit -m \"chore: smoke\"
3. Run: git log --oneline
4. Try to read the file $canary_win with the Read tool.
   If it is denied, do not try any other way.
5. Answer in one short paragraph: did each step succeed or was it denied? Does your context
   contain any CLAUDE.md content, user memory, or user-defined instructions besides this prompt?"

echo "Smoke test workspace: $workspace"
run_agent "$workspace" "$prompt" "$log_dir/transcript.jsonl" "$log_dir/stderr.log"
echo "Agent exit code: $?"

"$PYTHON" - "$log_dir/transcript.jsonl" "$workspace" "$canary_token" <<'PY'
import json, subprocess, sys
from pathlib import Path

transcript, workspace, canary = sys.argv[1:4]
events = []
for line in Path(transcript).read_text(encoding="utf-8", errors="replace").splitlines():
    try:
        events.append(json.loads(line))
    except json.JSONDecodeError:
        pass

init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), {})
result = next((e for e in reversed(events) if e.get("type") == "result"), {})
print("init.model:          ", init.get("model"))
print("init.permissionMode: ", init.get("permissionMode"))
print("init.tools:          ", init.get("tools"))
print("init.mcp_servers:    ", init.get("mcp_servers"))
print("init.plugins:        ", init.get("plugins"))
print("init.agents:         ", init.get("agents"))
print("init.skills:         ", init.get("skills"))
print("init.slash_commands: ", init.get("slash_commands"))
print("result.subtype:      ", result.get("subtype"), "| terminal_reason:", result.get("terminal_reason"))
print("result.num_turns:    ", result.get("num_turns"), "| cost:", result.get("total_cost_usd"))
print("permission_denials:  ", json.dumps(result.get("permission_denials"), indent=None)[:800])
print("agent answer:        ", (result.get("result") or "")[:1200])

log = subprocess.run(["git", "-C", workspace, "log", "--oneline"], capture_output=True, text=True).stdout
testlog = Path(workspace, ".testlog", "test_runs.jsonl")
checks = {
    "commit 'chore: smoke' created": "chore: smoke" in log,
    "run_tests.sh wrote a log line": testlog.exists() and testlog.read_text().strip() != "",
    "canary NOT leaked into transcript": canary not in Path(transcript).read_text(encoding="utf-8", errors="replace"),
    "no MCP servers loaded": not init.get("mcp_servers"),
    "no user-installed plugins loaded": all(p.get("path") == "builtin" for p in init.get("plugins") or []),
}
print()
for name, ok in checks.items():
    print(("PASS " if ok else "FAIL ") + name)
sys.exit(0 if all(checks.values()) else 1)
PY
