"""Aggregates run_meta.json, process.json and evaluation.json of all runs into
results/summary.csv and results/report.md.

If results/assessment.md exists, its content is appended to the report as the
qualitative assessment section (written by hand after inspecting the runs).

Usage: python scripts/summarize.py
"""
import csv
import json
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
RUNS_DIR = Path(os.environ.get("TDD_PILOT_RUNS_DIR", PROJECT_DIR / "runs"))
RESULTS_DIR = Path(os.environ.get("TDD_PILOT_RESULTS_DIR", PROJECT_DIR / "results"))

COLUMNS = [
    "run", "condition", "model", "hidden_passed", "hidden_total", "hidden_pass_rate",
    "agent_tests", "agent_tests_all_pass", "line_coverage", "branch_coverage",
    "process_compliant", "violations", "warnings", "tdd_cycles", "tdd_compliant_cycles", "tdd_tests_never_red",
    "commits", "test_runs_logged", "wall_seconds", "duration_ms", "num_turns",
    "total_cost_usd", "result_subtype", "timed_out",
]


def load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def collect():
    rows, details = [], []
    for run_dir in sorted(p for p in RUNS_DIR.iterdir() if p.is_dir()):
        meta, process, evaluation = (load(run_dir / f) for f in
                                     ("run_meta.json", "process.json", "evaluation.json"))
        if not meta:
            continue
        result = meta.get("result") or {}
        hidden = evaluation.get("hidden", {})
        own = evaluation.get("agent_tests", {})
        coverage = own.get("coverage") or {}
        rows.append({
            "run": run_dir.name,
            "condition": meta.get("condition"),
            "model": meta.get("model"),
            "hidden_passed": hidden.get("passed"),
            "hidden_total": hidden.get("total"),
            "hidden_pass_rate": round(hidden["pass_rate"], 3) if "pass_rate" in hidden else None,
            "agent_tests": own.get("num_tests"),
            "agent_tests_all_pass": own.get("all_pass"),
            "line_coverage": round(coverage["line_coverage"], 3) if coverage.get("line_coverage") is not None else None,
            "branch_coverage": round(coverage["branch_coverage"], 3) if coverage.get("branch_coverage") is not None else None,
            "process_compliant": process.get("process_compliant"),
            "violations": len(process.get("violations", [])),
            "warnings": len(process.get("warnings", [])),
            "tdd_cycles": process.get("num_cycles"),
            "tdd_compliant_cycles": process.get("compliant_cycles"),
            "tdd_tests_never_red": process.get("tests_never_red"),
            "commits": process.get("num_commits"),
            "test_runs_logged": process.get("num_test_runs_logged"),
            "wall_seconds": meta.get("wall_seconds"),
            "duration_ms": result.get("duration_ms"),
            "num_turns": result.get("num_turns"),
            "total_cost_usd": result.get("total_cost_usd"),
            "result_subtype": result.get("subtype"),
            "timed_out": meta.get("timed_out"),
        })
        details.append((run_dir.name, meta, process, evaluation))
    return rows, details


def fmt(value):
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".") if value != int(value) else str(int(value))
    return str(value)


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(fmt(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def write_report(rows, details):
    meta_any = details[0][1] if details else {}
    out = ["# Pilot report: TDD vs. Test-After", ""]
    out.append(f"Model: `{meta_any.get('model')}`, effort `{meta_any.get('effort')}`, "
               f"Claude Code `{meta_any.get('claude_version')}`. "
               f"{len(rows)} runs. With 3 runs per condition no statistical conclusions can be drawn; "
               "the numbers only show whether the setup works.")
    out += ["", "## Per-run overview", ""]
    out.append(table(
        ["Run", "Hidden tests", "Pass rate", "Agent tests (all pass)", "Line / branch cov.",
         "Workflow compliant", "Violations", "TDD cycles (compliant)", "TDD tests never red", "Wall time [s]", "Turns", "Cost [USD]"],
        [[r["run"], f"{fmt(r['hidden_passed'])}/{fmt(r['hidden_total'])}", r["hidden_pass_rate"],
          f"{fmt(r['agent_tests'])} ({fmt(r['agent_tests_all_pass'])})",
          f"{fmt(r['line_coverage'])} / {fmt(r['branch_coverage'])}",
          r["process_compliant"], r["violations"],
          f"{fmt(r['tdd_cycles'])} ({fmt(r['tdd_compliant_cycles'])})" if r["condition"] == "tdd" else "-",
          f"{fmt(r['tdd_tests_never_red'])}/{fmt(r['agent_tests'])}" if r["condition"] == "tdd" else "-",
          r["wall_seconds"], r["num_turns"], r["total_cost_usd"]] for r in rows]))

    out += ["", "## Hidden tests per rule", ""]
    rules = sorted({rule for _, _, _, e in details for rule in e.get("hidden", {}).get("per_rule", {})},
                   key=lambda r: int(r[1:]))
    out.append(table(["Run", *rules], [
        [name, *(f"{e['hidden']['per_rule'][r]['passed']}/{e['hidden']['per_rule'][r]['total']}"
                 if r in e.get("hidden", {}).get("per_rule", {}) else "n/a" for r in rules)]
        for name, _, _, e in details]))

    out += ["", "## Violations and warnings per run", ""]
    for name, meta, process, evaluation in details:
        out.append(f"### {name}")
        result = meta.get("result") or {}
        out.append(f"- Agent end state: `{result.get('subtype')}`, exit code {meta.get('agent_exit_code')}, "
                   f"timed out: {meta.get('timed_out')}")
        out.append("- Commits: " + ", ".join(f"`{c['type']}`" for c in process.get("commits", [])[1:]))
        failed = evaluation.get("hidden", {}).get("failed_tests", [])
        if len(failed) > 12:
            out.append(f"- Failed hidden tests: {len(failed)} (see runs/{name}/evaluation.json)")
        else:
            out.append("- Failed hidden tests: " + (", ".join(f"`{t}`" for t in failed) if failed else "none"))
        for label, key in (("Violations", "violations"), ("Warnings", "warnings")):
            items = process.get(key, [])
            out.append(f"- {label} ({len(items)}):" + ("" if items else " none"))
            for item in items[:40]:
                where = f"`{item['commit']}` " if item.get("commit") else ""
                detail = f" ({item['detail']})" if item.get("detail") else ""
                out.append(f"  - {where}{item['rule']}{detail}")
            if len(items) > 40:
                out.append(f"  - ... {len(items) - 40} more, see runs/{name}/process.json")
        out.append("")

    assessment = RESULTS_DIR / "assessment.md"
    out += ["## Assessment", ""]
    out.append(assessment.read_text(encoding="utf-8").strip() if assessment.exists()
               else "_Not written yet (results/assessment.md)._")
    (RESULTS_DIR / "report.md").write_text("\n".join(out) + "\n", encoding="utf-8")


def main():
    RESULTS_DIR.mkdir(exist_ok=True)
    rows, details = collect()
    with open(RESULTS_DIR / "summary.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    write_report(rows, details)
    print(f"Wrote results/summary.csv and results/report.md ({len(rows)} runs)")


if __name__ == "__main__":
    main()
