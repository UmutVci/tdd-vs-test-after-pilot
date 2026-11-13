#!/usr/bin/env bash
# Runs one headless agent session.
# Usage: scripts/run_one.sh <tdd|test_after> <run_id>
set -euo pipefail

if [[ $# -ne 2 || ! "$1" =~ ^(tdd|test_after)$ ]]; then
    echo "Usage: $0 <tdd|test_after> <run_id>" >&2
    exit 2
fi
condition="$1"
run_id="$2"
name="${condition}_${run_id}"

source "$(dirname "$0")/agent_config.sh"

workspace="$RUNS_ROOT/$name"
log_dir="$RUNS_ROOT/$name.logs"
out_dir="$PROJECT_DIR/runs/$name"
if [[ -e "$out_dir" ]]; then
    echo "Output directory $out_dir already exists; refusing to overwrite it" >&2
    exit 1
fi

init_workspace "$workspace"
mkdir -p "$log_dir"

prompt="$(cat "$PROJECT_DIR/prompts/common_header.md")

$(cat "$PROJECT_DIR/prompts/$condition.md")"
printf '%s\n' "$prompt" > "$log_dir/prompt.txt"

echo "[$name] workspace: $workspace"
echo "[$name] starting agent ($MODEL, effort $EFFORT, budget \$$MAX_BUDGET_USD, timeout ${TIMEOUT_SECONDS}s)"
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
start_epoch="$(date +%s)"
agent_exit=0
run_agent "$workspace" "$prompt" "$log_dir/transcript.jsonl" "$log_dir/stderr.log" || agent_exit=$?
end_epoch="$(date +%s)"
finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "[$name] agent finished with exit code $agent_exit after $((end_epoch - start_epoch))s"

# Collect artefacts.
mkdir -p "$out_dir"
cp "$log_dir/prompt.txt" "$log_dir/transcript.jsonl" "$log_dir/stderr.log" "$out_dir/"
if [[ -d "$workspace/.testlog" ]]; then
    cp -r "$workspace/.testlog" "$out_dir/testlog"
else
    mkdir -p "$out_dir/testlog"
fi
git -C "$workspace" log --stat > "$out_dir/git_log_stat.txt"
git -C "$workspace" status --porcelain > "$out_dir/git_status_final.txt"
cp -r "$workspace" "$out_dir/workspace"

claude_version="$("$CLAUDE_BIN" --version 2>/dev/null || echo unknown)"
"$PYTHON" - "$out_dir" <<PY
import json, sys
from pathlib import Path

out = Path(sys.argv[1])
result = None
for line in (out / "transcript.jsonl").read_text(encoding="utf-8", errors="replace").splitlines():
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        continue
    if event.get("type") == "result":
        result = event

meta = {
    "condition": "$condition",
    "run_id": "$run_id",
    "workspace": "$workspace",
    "model": "$MODEL",
    "config_version": "$CONFIG_VERSION",
    "effort": "$EFFORT",
    "max_budget_usd": float("$MAX_BUDGET_USD"),
    "timeout_seconds": int("$TIMEOUT_SECONDS"),
    "claude_version": "$claude_version",
    "started_at": "$started_at",
    "finished_at": "$finished_at",
    "wall_seconds": $((end_epoch - start_epoch)),
    "agent_exit_code": $agent_exit,
    "timed_out": $agent_exit == 124,
    "result": None,
}
if result is not None:
    meta["result"] = {k: result.get(k) for k in (
        "subtype", "is_error", "duration_ms", "duration_api_ms", "num_turns",
        "total_cost_usd", "terminal_reason", "stop_reason", "usage", "permission_denials")}
(out / "run_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
PY
echo "[$name] artefacts copied to $out_dir"
