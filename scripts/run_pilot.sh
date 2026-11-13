#!/usr/bin/env bash
# Runs the whole pilot: 3 runs per condition, sequentially and interleaved
# (tdd_1, test_after_1, tdd_2, ...), then the analysis scripts.
# Usage: scripts/run_pilot.sh [runs_per_condition]
set -uo pipefail

scripts_dir="$(cd "$(dirname "$0")" && pwd)"
source "$scripts_dir/agent_config.sh"
runs_per_condition="${1:-3}"

for i in $(seq 1 "$runs_per_condition"); do
    for condition in tdd test_after; do
        "$scripts_dir/run_one.sh" "$condition" "$i" || echo "run ${condition}_$i failed" >&2
    done
done

"$PYTHON" "$scripts_dir/check_process.py"
"$PYTHON" "$scripts_dir/evaluate.py"
"$PYTHON" "$scripts_dir/summarize.py"
