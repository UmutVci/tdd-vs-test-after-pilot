#!/usr/bin/env bash
# Runs the test suite with pytest and appends one JSON line per invocation
# to .testlog/test_runs.jsonl. Returns pytest's exit code unchanged.
set -u
cd "$(dirname "$0")"

mkdir -p .testlog
output_file="$(mktemp)"

python -m pytest tests -q "$@" 2>&1 | tee "$output_file"
exit_code=${PIPESTATUS[0]}

head_commit="$(git rev-parse HEAD 2>/dev/null || echo none)"
git status --porcelain > "$output_file.status" 2>/dev/null || true

python - "$output_file" "$output_file.status" "$exit_code" "$head_commit" "$@" >> .testlog/test_runs.jsonl <<'PY'
import json
import re
import sys
from datetime import datetime, timezone

output_path, status_path, exit_code, head = sys.argv[1:5]
extra_args = sys.argv[5:]
with open(output_path, encoding="utf-8", errors="replace") as f:
    output = f.read()
with open(status_path, encoding="utf-8", errors="replace") as f:
    status_lines = [line.rstrip("\n") for line in f if line.strip()]

counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
summary_lines = [l for l in output.splitlines() if re.search(r"\b(passed|failed|error|errors|no tests ran)\b", l)]
if summary_lines:
    for number, kind in re.findall(r"(\d+) (passed|failed|errors?|skipped)", summary_lines[-1]):
        key = "errors" if kind.startswith("error") else kind
        counts[key] = int(number)

print(json.dumps({
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "head": head,
    "git_status": status_lines,
    "dirty_files": len(status_lines),
    "exit_code": int(exit_code),
    "extra_args": extra_args,
    **counts,
}))
PY

rm -f "$output_file" "$output_file.status"
exit "$exit_code"
