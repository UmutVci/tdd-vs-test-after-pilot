"""Checks whether each run followed its workflow, using git history and test logs.

For every runs/<condition>_<n>/ directory the git history of the copied workspace is
replayed commit by commit: each commit is checked out into a temporary clone and the
agent's own tests are run there. Results go to runs/<name>/process.json.

Usage: python scripts/check_process.py [run_name ...]
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
RUNS_DIR = Path(os.environ.get("TDD_PILOT_RUNS_DIR", PROJECT_DIR / "runs"))
COMMIT_TYPE = re.compile(r"^\s*(red|green|refactor|impl|test|fix|chore)\s*:", re.IGNORECASE)
PYTEST_TIMEOUT_SECONDS = 30


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    ).stdout


def load_commits(repo):
    commits = []
    log = git(repo, "log", "--reverse", "--format=%H%x1f%P%x1f%ct%x1f%s")
    for line in log.splitlines():
        sha, parents, ctime, subject = line.split("\x1f", 3)
        files = git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha).split()
        match = COMMIT_TYPE.match(subject)
        commits.append({
            "sha": sha,
            "parent": parents.split()[0] if parents else None,
            "time": int(ctime),
            "subject": subject,
            "type": match.group(1).lower() if match else "other",
            "files": files,
            "tests_changed": any(f.startswith("tests/") for f in files),
            "test_files_changed": any(f.startswith("tests/") and f != "tests/__init__.py" for f in files),
            "src_changed": any(f.startswith("src/") for f in files),
        })
    return commits


class Replayer:
    """Runs the agent's tests at arbitrary commits in a temporary clone (cached per commit)."""

    def __init__(self, repo, tmp):
        self.clone = Path(tmp) / "clone"
        subprocess.run(["git", "clone", "-q", str(repo), str(self.clone)], check=True)
        self.cache = {}

    def run(self, sha):
        if sha in self.cache:
            return self.cache[sha]
        git(self.clone, "checkout", "-q", "-f", sha)
        git(self.clone, "clean", "-q", "-fdx")
        junit = self.clone.parent / f"junit_{sha}.xml"
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider",
                 f"--junitxml={junit}", f"--timeout={PYTEST_TIMEOUT_SECONDS}"],
                cwd=self.clone, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=600,
            )
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            exit_code = -1
        outcomes = parse_junit(junit) if junit.exists() else {}
        result = {
            "exit_code": exit_code,
            "outcomes": outcomes,
            "passed": sum(o == "passed" for o in outcomes.values()),
            "failing": sum(o in ("failed", "error") for o in outcomes.values()),
        }
        self.cache[sha] = result
        return result


def parse_junit(path):
    outcomes = {}
    for case in ET.parse(path).getroot().iter("testcase"):
        test_id = f"{case.get('classname', '')}::{case.get('name', '')}"
        if case.find("failure") is not None:
            outcomes[test_id] = "failed"
        elif case.find("error") is not None:
            outcomes[test_id] = "error"
        elif case.find("skipped") is not None:
            outcomes[test_id] = "skipped"
        else:
            outcomes[test_id] = "passed"
    return outcomes


def load_testlog(run_dir):
    path = run_dir / "testlog" / "test_runs.jsonl"
    entries = []
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                entry = json.loads(line)
                entry["epoch"] = datetime.fromisoformat(entry["timestamp"]).timestamp()
                entries.append(entry)
            except (json.JSONDecodeError, KeyError, ValueError):
                pass
    return entries


def violation(commit, rule, detail=""):
    return {"commit": commit["sha"][:10] if commit else None,
            "subject": commit["subject"] if commit else None,
            "rule": rule, "detail": detail}


def check_tdd(commits, replayer, testlog):
    violations, warnings, cycles = [], [], []
    current = None
    previous = commits[0]
    for commit in commits[1:]:
        own = []
        kind = commit["type"]
        result = replayer.run(commit["sha"])
        if kind == "red":
            current = {"red": commit["sha"][:10], "subject": commit["subject"],
                       "green": None, "refactors": [], "violations": []}
            cycles.append(current)
            if not commit["test_files_changed"]:
                own.append(violation(commit, "red: tests/ not changed"))
            if commit["src_changed"]:
                own.append(violation(commit, "red: src/ changed"))
            if result["failing"] == 0:
                own.append(violation(commit, "red: no failing test at this commit",
                                     f"{result['passed']} passed"))
            parent_ids = set(replayer.run(commit["parent"])["outcomes"]) if commit["parent"] else set()
            new_ids = [t for t in result["outcomes"] if t not in parent_ids]
            new_failing = [t for t in new_ids if result["outcomes"][t] in ("failed", "error")]
            current["new_tests"] = new_ids
            if new_ids and not new_failing:
                own.append(violation(commit, "red: newly added test does not fail", ", ".join(new_ids)))
            if len(new_ids) != 1:
                warnings.append(violation(commit, "red: expected exactly one new test",
                                          f"{len(new_ids)} new test ids"))
            failing_run_logged = any(
                e.get("head") == commit["parent"]
                and e.get("exit_code", 0) != 0
                and e.get("failed", 0) + e.get("errors", 0) > 0
                and e["epoch"] <= commit["time"] + 1
                for e in testlog)
            current["failing_run_logged"] = failing_run_logged
            if not failing_run_logged:
                own.append(violation(commit, "red: no failing ./run_tests.sh run logged before the commit"))
        if kind == "green":
            if previous["type"] != "red":
                own.append(violation(commit, "green: preceding commit is not red",
                                     f"preceded by {previous['type']}"))
            if result["exit_code"] != 0:
                own.append(violation(commit, "green: not all tests pass",
                                     f"{result['failing']} failing, exit code {result['exit_code']}"))
            if not commit["src_changed"]:
                warnings.append(violation(commit, "green: src/ not changed"))
            if commit["test_files_changed"]:
                warnings.append(violation(commit, "green: tests/ changed"))
            if current is not None and current["green"] is None and previous["type"] == "red":
                current["green"] = commit["sha"][:10]
        if kind in ("green", "refactor") and commit["parent"]:
            parent_ids = set(replayer.run(commit["parent"])["outcomes"])
            added = [t for t in result["outcomes"] if t not in parent_ids]
            if added:
                own.append(violation(commit, f"{kind}: adds new tests (they never went through red)",
                                     f"{len(added)} new test ids"))
        if kind == "refactor":
            if result["exit_code"] != 0:
                own.append(violation(commit, "refactor: not all tests pass",
                                     f"{result['failing']} failing, exit code {result['exit_code']}"))
            if previous["type"] not in ("green", "refactor"):
                warnings.append(violation(commit, "refactor: not preceded by green/refactor",
                                          f"preceded by {previous['type']}"))
            if current is not None:
                current["refactors"].append(commit["sha"][:10])
        elif kind not in ("red", "green"):
            own.append(violation(commit, "unexpected commit type for TDD", kind))
        if current is not None and kind in ("red", "green", "refactor"):
            current["violations"].extend(own)
        violations.extend(own)
        previous = commit

    for cycle in cycles:
        if cycle["green"] is None:
            v = {"commit": cycle["red"], "subject": cycle["subject"],
                 "rule": "cycle: red commit not directly followed by a green commit", "detail": ""}
            cycle["violations"].append(v)
            violations.append(v)
        cycle["compliant"] = not cycle["violations"]
    if not cycles:
        violations.append(violation(None, "no red commit / no TDD cycle committed"))

    # Tests in the final commit that never failed at any commit, i.e. never were "red".
    final_ids = replayer.run(commits[-1]["sha"])["outcomes"]
    ever_failed = {t for c in commits for t, o in replayer.run(c["sha"])["outcomes"].items()
                   if o in ("failed", "error")}
    never_red = sorted(t for t in final_ids if t not in ever_failed)

    return {
        "final_tests": len(final_ids),
        "tests_never_red": len(never_red),
        "cycles": cycles,
        "num_cycles": len(cycles),
        "compliant_cycles": sum(c["compliant"] for c in cycles),
        "non_compliant_cycles": sum(not c["compliant"] for c in cycles),
        "violations": violations,
        "warnings": warnings,
    }


def check_test_after(commits, replayer, testlog):
    violations, warnings = [], []
    work = commits[1:]
    impl_indices = [i for i, c in enumerate(work) if c["type"] == "impl"]
    test_indices = [i for i, c in enumerate(work) if c["type"] == "test"]
    first_test_files = next((i for i, c in enumerate(work) if c["test_files_changed"]), None)

    if not impl_indices:
        violations.append(violation(None, "no impl commit"))
    else:
        first_impl = impl_indices[0]
        impl = work[first_impl]
        if first_impl != 0:
            violations.append(violation(impl, "impl is not the first commit after the template"))
        if not impl["src_changed"]:
            violations.append(violation(impl, "impl commit does not change src/"))
        if impl["test_files_changed"]:
            violations.append(violation(impl, "impl commit contains tests"))
        if first_test_files is not None and first_test_files < first_impl:
            violations.append(violation(work[first_test_files], "tests committed before the implementation"))
        if len(impl_indices) > 1:
            warnings.append(violation(work[impl_indices[1]], "more than one impl commit"))
        if any(i < first_impl for i in test_indices):
            violations.append(violation(work[min(test_indices)], "test commit before impl commit"))
    if not test_indices:
        violations.append(violation(None, "no test commit"))
    for i, commit in enumerate(work):
        if commit["type"] not in ("impl", "test", "fix"):
            violations.append(violation(commit, "unexpected commit type for Test-After", commit["type"]))
        if commit["type"] == "fix" and (not test_indices or i < test_indices[0]):
            warnings.append(violation(commit, "fix commit before the first test commit"))
        if commit["type"] == "test" and commit["src_changed"]:
            warnings.append(violation(commit, "test commit changes src/"))

    initial = commits[0]["sha"]
    early_runs = [e for e in testlog
                  if e.get("head") == initial and e.get("passed", 0) + e.get("failed", 0) + e.get("errors", 0) > 0]
    if early_runs:
        violations.append(violation(commits[0], "tests were executed before the impl commit",
                                    f"{len(early_runs)} run(s) with collected tests at the template commit"))

    replay = {c["sha"][:10]: {"type": c["type"], **{k: v for k, v in replayer.run(c["sha"]).items()
                                                     if k != "outcomes"}} for c in work}
    return {"replay": replay, "violations": violations, "warnings": warnings}


def scan_transcript(run_dir, workspace_cwd):
    """Flags references to the hidden tests or the project folder and tool calls outside the workspace."""
    transcript = run_dir / "transcript.jsonl"
    text = transcript.read_text(encoding="utf-8", errors="replace") if transcript.exists() else ""
    normalized = text.replace("\\\\", "/").replace("\\", "/").lower()
    project = PROJECT_DIR.as_posix().lower()
    drive_style = project  # e.g. c:/users/.../tdd-pilot
    msys_style = "/" + project[0] + project[2:] if re.match(r"^[a-z]:/", project) else project
    patterns = {"hidden_tests", drive_style, msys_style}

    violations = []
    for pattern in sorted(patterns):
        count = normalized.count(pattern)
        if count:
            violations.append({"commit": None, "subject": None,
                               "rule": "transcript references forbidden location",
                               "detail": f"'{pattern}' x{count}"})

    warnings, tool_counts, denials = [], {}, []
    ws = (workspace_cwd or "").replace("\\", "/").lower().rstrip("/")
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "result":
            denials = event.get("permission_denials") or []
        if event.get("type") != "assistant":
            continue
        for item in event.get("message", {}).get("content", []):
            if item.get("type") != "tool_use":
                continue
            tool_counts[item["name"]] = tool_counts.get(item["name"], 0) + 1
            params = item.get("input", {})
            for key in ("file_path", "path", "notebook_path"):
                value = str(params.get(key, "")).replace("\\", "/").lower()
                if value and (re.match(r"^([a-z]:)?/", value) and not (ws and value.startswith(ws)) or ".." in value):
                    warnings.append({"commit": None, "subject": None,
                                     "rule": "tool call path outside the workspace",
                                     "detail": f"{item['name']}: {params.get(key)}"})
            command = str(params.get("command", ""))
            if "../" in command or "..\\" in command:
                warnings.append({"commit": None, "subject": None,
                                 "rule": "shell command with parent-directory reference",
                                 "detail": command[:200]})
    return {"violations": violations, "warnings": warnings,
            "tool_counts": tool_counts, "permission_denials": denials}


def transcript_cwd(run_dir):
    transcript = run_dir / "transcript.jsonl"
    if not transcript.exists():
        return None
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            return event.get("cwd")
    return None


def check_run(run_dir):
    condition = "test_after" if run_dir.name.startswith("test_after_") else "tdd"
    repo = run_dir / "workspace"
    commits = load_commits(repo)
    testlog = load_testlog(run_dir)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        replayer = Replayer(repo, tmp)
        workflow = (check_tdd if condition == "tdd" else check_test_after)(commits, replayer, testlog)
        final = replayer.run(commits[-1]["sha"])
    transcript = scan_transcript(run_dir, transcript_cwd(run_dir))
    status_file = run_dir / "git_status_final.txt"
    uncommitted = status_file.read_text().split("\n") if status_file.exists() else []
    uncommitted = [line for line in uncommitted if line.strip()]

    warnings = workflow.pop("warnings") + transcript["warnings"]
    if uncommitted:
        warnings.append({"commit": None, "subject": None, "rule": "uncommitted changes at the end",
                         "detail": "; ".join(uncommitted)})
    # Test runs on a HEAD that is not part of the final history mean that commits were
    # rewritten (e.g. git commit --amend), so the replay does not see the original state.
    known = {c["sha"] for c in commits}
    orphaned = sorted({e["head"] for e in testlog if e.get("head") not in known | {"none"}})
    if orphaned:
        warnings.append({"commit": None, "subject": None,
                         "rule": "history rewritten (test runs on commits missing from the final history)",
                         "detail": ", ".join(h[:10] for h in orphaned)})
    violations = workflow.pop("violations") + transcript["violations"]
    return {
        "run": run_dir.name,
        "condition": condition,
        "num_commits": len(commits),
        "commits": [{"sha": c["sha"][:10], "type": c["type"], "subject": c["subject"], "files": c["files"]}
                    for c in commits],
        "num_test_runs_logged": len(testlog),
        "final_commit_tests": {k: v for k, v in final.items() if k != "outcomes"},
        **workflow,
        "violations": violations,
        "warnings": warnings,
        "process_compliant": not violations,
        "tool_counts": transcript["tool_counts"],
        "permission_denials": transcript["permission_denials"],
    }


def main(names):
    run_dirs = [RUNS_DIR / n for n in names] if names else sorted(
        p for p in RUNS_DIR.iterdir() if (p / "workspace" / ".git").exists())
    for run_dir in run_dirs:
        report = check_run(run_dir)
        (run_dir / "process.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        extra = (f", cycles {report['compliant_cycles']}/{report['num_cycles']} compliant"
                 if report["condition"] == "tdd" else "")
        print(f"{run_dir.name}: {len(report['violations'])} violation(s), "
              f"{len(report['warnings'])} warning(s){extra}")


if __name__ == "__main__":
    main(sys.argv[1:])
