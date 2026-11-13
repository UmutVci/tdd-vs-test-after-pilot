"""Measures functional correctness of each run with the hidden test suite.

For every runs/<condition>_<n>/ directory:
- the final src/duration.py of the workspace is copied into a clean directory and
  hidden_tests/test_hidden.py is run against it;
- the agent's own tests are run on a clean copy of the final workspace, with
  line and branch coverage of src/.
Results go to runs/<name>/evaluation.json.

Usage: python scripts/evaluate.py [run_name ...]
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
RUNS_DIR = Path(os.environ.get("TDD_PILOT_RUNS_DIR", PROJECT_DIR / "runs"))
HIDDEN_TESTS = PROJECT_DIR / "hidden_tests" / "test_hidden.py"
PYTEST_TIMEOUT_SECONDS = 10
RULE_IN_NAME = re.compile(r"test_(r\d+)_")


def run_pytest(args, cwd, env=None):
    junit = Path(cwd) / "junit.xml"
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", *args, "-q", "-p", "no:cacheprovider",
             f"--junitxml={junit}", f"--timeout={PYTEST_TIMEOUT_SECONDS}"],
            cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=900,
        )
        exit_code, output = proc.returncode, proc.stdout + proc.stderr
    except subprocess.TimeoutExpired:
        exit_code, output = -1, "timeout"
    outcomes = {}
    if junit.exists():
        for case in ET.parse(junit).getroot().iter("testcase"):
            if case.find("failure") is not None or case.find("error") is not None:
                outcome = "failed"
            elif case.find("skipped") is not None:
                outcome = "skipped"
            else:
                outcome = "passed"
            outcomes[case.get("name", "")] = outcome
    return exit_code, outcomes, output


def evaluate_hidden(final_src):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        src_dir = Path(tmp) / "src"
        src_dir.mkdir()
        if final_src.exists():
            shutil.copy(final_src, src_dir / "duration.py")
        shutil.copy(HIDDEN_TESTS, Path(tmp) / "test_hidden.py")
        env = dict(os.environ, DURATION_MODULE_PATH=str(src_dir / "duration.py"))
        exit_code, outcomes, output = run_pytest(["test_hidden.py"], tmp, env)

    total = count_hidden_tests()
    passed = sum(o == "passed" for o in outcomes.values())
    per_rule = {}
    for name in hidden_test_names():
        rule = RULE_IN_NAME.match(name).group(1).upper()
        bucket = per_rule.setdefault(rule, {"passed": 0, "total": 0})
        bucket["total"] += 1
        bucket["passed"] += outcomes.get(name) == "passed"
    return {
        "passed": passed,
        "total": total,
        "pass_rate": passed / total if total else 0.0,
        "exit_code": exit_code,
        "per_rule": dict(sorted(per_rule.items(), key=lambda kv: int(kv[0][1:]))),
        "failed_tests": sorted(n for n in hidden_test_names() if outcomes.get(n) != "passed"),
        "output_tail": output[-2000:] if passed < total else "",
    }


def hidden_test_names():
    return re.findall(r"^def (test_\w+)\(", HIDDEN_TESTS.read_text(encoding="utf-8"), re.MULTILINE)


def count_hidden_tests():
    return len(hidden_test_names())


def evaluate_agent_tests(workspace):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        copy = Path(tmp) / "ws"
        shutil.copytree(workspace, copy, ignore=shutil.ignore_patterns(
            ".git", ".testlog", "__pycache__", ".pytest_cache", ".coverage"))
        exit_code, outcomes, output = run_pytest(
            ["tests", "--cov=src", "--cov-branch", "--cov-report=json:coverage.json"], copy)
        coverage = None
        cov_file = copy / "coverage.json"
        if cov_file.exists():
            totals = json.loads(cov_file.read_text(encoding="utf-8"))["totals"]
            statements = totals.get("num_statements", 0)
            branches = totals.get("num_branches", 0)
            coverage = {
                "line_coverage": totals.get("covered_lines", 0) / statements if statements else None,
                "branch_coverage": totals.get("covered_branches", 0) / branches if branches else None,
                "combined_percent": totals.get("percent_covered"),
            }
    return {
        "num_tests": len(outcomes),
        "passed": sum(o == "passed" for o in outcomes.values()),
        "all_pass": exit_code == 0,
        "exit_code": exit_code,
        "coverage": coverage,
        "output_tail": output[-2000:] if exit_code != 0 else "",
    }


def main(names):
    run_dirs = [RUNS_DIR / n for n in names] if names else sorted(
        p for p in RUNS_DIR.iterdir() if (p / "workspace").is_dir())
    for run_dir in run_dirs:
        workspace = run_dir / "workspace"
        report = {
            "run": run_dir.name,
            "hidden": evaluate_hidden(workspace / "src" / "duration.py"),
            "agent_tests": evaluate_agent_tests(workspace),
        }
        (run_dir / "evaluation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        hidden, own = report["hidden"], report["agent_tests"]
        print(f"{run_dir.name}: hidden {hidden['passed']}/{hidden['total']}, "
              f"agent tests {own['passed']}/{own['num_tests']} pass")


if __name__ == "__main__":
    main(sys.argv[1:])
