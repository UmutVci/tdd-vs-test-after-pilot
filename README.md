# TDD vs. Test-After pilot

Pilot setup for the research question: *How does the functional correctness of code produced
by an AI coding agent in a TDD workflow differ from a Test-After workflow, measured with an
independent test suite?*

The pilot does not aim at results. It checks whether
1. both workflows can be applied reliably with a coding agent,
2. adherence to Red-Green-Refactor can be checked automatically from git history and test logs,
3. functional correctness can be measured with an independent (hidden) test suite.

## Environment

| Component | Version / value |
|---|---|
| OS | Windows 11, scripts run in Git Bash |
| Claude Code CLI | `2.1.309 (Claude Code)` (copy bundled with the Claude desktop app, see below) |
| Python | 3.13.15 in `.venv` (created with `uv`) |
| Python packages | see `requirements.txt` (pytest 9.2.0, pytest-cov 7.1.0, pytest-timeout 2.4.0) |

The CLI is not on `PATH` on this machine. `scripts/agent_config.sh` resolves it in this order:
`$CLAUDE_BIN`, `claude` on `PATH`, newest `claude.exe` under
`%LOCALAPPDATA%\Claude-Data\*\claude-code\<version>\...`. The desktop app may update that copy;
the version used for each run is stored in `runs/<run>/run_meta.json`.

**Authentication:** the standalone CLI must be logged in (`claude auth status` must report
`loggedIn: true`), or `ANTHROPIC_API_KEY` / `CLAUDE_CODE_OAUTH_TOKEN` must be set. These three
variables are the only `CLAUDE*`/`ANTHROPIC*` variables passed through to the agent.

## Layout

```
task/SPEC.md               task specification (identical to task/template/SPEC.md)
task/template/             start repository copied into every run workspace
hidden_tests/test_hidden.py  independent evaluation tests, never visible to the agents
prompts/                   common_header.md + tdd.md / test_after.md (used verbatim)
scripts/agent_config.sh    shared settings: CLI flags, env scrubbing, workspace init
scripts/run_one.sh         one run: scripts/run_one.sh <tdd|test_after> <n>
scripts/run_pilot.sh       3 runs per condition (interleaved) + analysis
scripts/smoke_test.sh      checks the agent configuration with a task-unrelated prompt
scripts/check_process.py   workflow compliance (git history replay + test logs + transcript scan)
scripts/evaluate.py        hidden tests + agent's own tests with coverage
scripts/summarize.py       results/summary.csv + results/report.md
runs/<condition>_<n>/      artefacts copied from each run (not in the git repository)
results/                   aggregated results: report.md, v2_rerun_report.md, assessment.md, summary.csv
```

The run artefacts (`runs/`, `runs_archive/`: full transcripts, test logs and copied agent
workspaces with their own git histories) are not part of the git repository; they are available
on request.

## Agent invocation

Each run is a new, independent headless process started from `run_one.sh` inside a fresh
workspace `/tmp/tdd-pilot-runs/<condition>_<n>/` (Git Bash `/tmp` =
`%LOCALAPPDATA%\Temp`), i.e. outside the project folder. The prompt is
`common_header.md` + blank line + `tdd.md` or `test_after.md`.

```bash
cd /tmp/tdd-pilot-runs/<condition>_<n>
env -u <every CLAUDE*/ANTHROPIC* variable except credentials> \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/tmp/tdd-pilot-runs/.empty-gitconfig \
    GIT_AUTHOR_NAME=tdd-pilot-agent GIT_AUTHOR_EMAIL=agent@tdd-pilot.invalid \
    GIT_COMMITTER_NAME=tdd-pilot-agent GIT_COMMITTER_EMAIL=agent@tdd-pilot.invalid \
    PATH="<project>/.venv/Scripts:$PATH" \
  timeout 5400 claude -p "<prompt>" \
    --model claude-sonnet-5-5 \
    --effort medium \
    --output-format stream-json \
    --verbose \
    --safe-mode \
    --restricted \
    --strict-mcp-config \
    --no-session-persistence \
    --disable-slash-commands \
    --tools "Bash,Read,Edit,Write,Glob,Grep" \
    --allowedTools "Read" "Edit" "Write" "Glob" "Grep" "Bash" \
    --permission-mode dontAsk \
    --permission-prompts none \
    --max-budget-usd 10 \
  > transcript.jsonl 2> stderr.log < /dev/null
```

All flags were taken from `claude --help` of version 2.1.309. Model, effort, budget and timeout
can be overridden with `TDD_PILOT_MODEL`, `TDD_PILOT_EFFORT`, `TDD_PILOT_MAX_BUDGET_USD`,
`TDD_PILOT_TIMEOUT_SECONDS`.

| Flag | Purpose |
|---|---|
| `--model claude-sonnet-5-5`, `--effort medium` | fixed model (full model id, not an alias) and fixed reasoning effort |
| `--output-format stream-json --verbose` | full transcript, one JSON event per line; the final `result` event carries duration, turns and cost |
| `--tools ...` | only these built-in tools exist (no PowerShell, WebFetch/WebSearch, subagents, ...) |
| `--allowedTools ...` + `--permission-mode dontAsk` + `--permission-prompts none` | file tools and Bash are pre-approved; anything else is denied automatically without a prompt. This is configuration **v2**. Configuration v1 allowed only `Bash(git *)` and `Bash(./run_tests.sh*)`; 3 of 6 pilot runs then stopped after a denied heredoc file write (`cat > file <<'EOF' ...`), so v2 allows Bash in general. Note: even in v1, Claude Code 2.1.309 auto-approved read-only shell commands inside the working directory (`cat SPEC.md`, `ls`) |
| `--max-budget-usd 10` + `timeout 5400` | upper bound per run. **`--max-turns` is not listed in `claude --help` of 2.1.309 and is therefore not used**; the budget and the wall-clock timeout replace it |

### Isolation

- **No `--bare`:** `--bare` would be the most complete isolation, but in 2.1.309 it accepts only
  `ANTHROPIC_API_KEY` (OAuth/keychain are never read). With subscription login it cannot
  authenticate. If an API key is used, `--bare` can be added to `AGENT_FLAGS`.
- **Instead:** `--safe-mode` (disables CLAUDE.md, skills, installed plugins, hooks, MCP servers,
  custom commands/agents, output styles; auth and built-in tools keep working),
  `--restricted` (ignores user/project/local settings files and confines the file tools to the
  working directory), `--strict-mcp-config` (no MCP servers), `--no-session-persistence`
  (nothing written to the user's session history), `--disable-slash-commands`.
- **Environment:** all `CLAUDE*` / `ANTHROPIC*` variables inherited from the orchestrating
  session are removed except `ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`,
  `CLAUDE_CODE_GIT_BASH_PATH`, `CLAUDE_CONFIG_DIR`. Git uses an empty global config and a fixed
  identity, so user-level git hooks/aliases/signing do not apply.
- **File system:** the workspace is outside the project folder, so `hidden_tests/` is not
  reachable by relative path; `--restricted` confines Read/Edit/Write/Glob/Grep to the workspace;
  Bash is not confined (v2), so shell access outside the workspace is not prevented but only
  detected afterwards: `check_process.py` scans every
  transcript for `hidden_tests` and the project path (violation) and for tool calls with paths
  outside the workspace (warning).
- **Check before the real runs:** `scripts/smoke_test.sh` starts the agent with the same
  configuration and a task-unrelated prompt and verifies that `git commit` and `./run_tests.sh`
  work, that a canary file outside the workspace cannot be read, and that no MCP servers or
  plugins are loaded. It also prints the `init` event (tools, permission mode, model).

## Test logging (`task/template/run_tests.sh`)

Runs `python -m pytest tests -q` (extra arguments are passed through and logged), prints the
output, appends one JSON line to `.testlog/test_runs.jsonl` (UTC timestamp, HEAD hash,
`git status --porcelain` lines, exit code, passed/failed/errors/skipped) and returns pytest's
exit code. `.testlog/` is in `.gitignore`. Note: the agent could in principle edit this file
with the Write tool; the transcript shows whether it did.

## Workflow compliance (`check_process.py`)

Every commit is checked out into a temporary clone and the agent's own tests are run there
(pytest + junit XML, 30 s timeout per test).

TDD (violations):
- `red:` changes `tests/`, does not change `src/`, at least one failing test at that commit,
  the newly added test ids (compared with the parent commit) fail, and the test log contains a
  failing `./run_tests.sh` run on the parent commit (HEAD = parent) before the commit time.
- `green:` directly preceded by a `red:` commit, all tests pass.
- `refactor:` all tests pass.
- Any other commit type; a red commit without a directly following green; no cycle at all.
- `green:` / `refactor:` commits that add new test ids (these tests never went through red).
- Metric `tests_never_red`: tests of the final commit that never failed at any commit.
- Warnings: not exactly one new test in a red commit, green without `src/` change or with
  `tests/` change, refactor not after green/refactor.
- A cycle (red + green + optional refactors) is compliant if none of its commits has a violation.

Test-After (violations): no `impl:` commit, `impl:` not the first commit, `impl:` without `src/`
change or containing tests, tests committed before `impl:`, no `test:` commit, other commit
types, tests executed (log) on the template commit before `impl:`.

Both: references to `hidden_tests` or the project path in the transcript are violations;
uncommitted changes at the end are warnings.

## Evaluation (`evaluate.py`)

- The final `src/duration.py` of the workspace is copied into a clean temporary folder and
  `hidden_tests/test_hidden.py` is run against it (10 s timeout per test). The hidden tests load
  the module from a file path, independent of the agent's import style.
- The agent's own tests are run on a clean copy of the final workspace with line and branch
  coverage of `src/`.

## Hidden tests

36 tests, each tagged with exactly one rule (R1-R10) in its name and docstring. R9 (ValueError
for invalid input) has no dedicated test; it is checked by every invalid-input test.

## Running

```bash
scripts/smoke_test.sh           # configuration check (costs a few cents)
scripts/run_pilot.sh            # 3 runs per condition + analysis
scripts/run_one.sh tdd 4        # a single additional run
```

The analysis scripts can be re-run at any time:
`.venv/Scripts/python scripts/check_process.py && .venv/Scripts/python scripts/evaluate.py && .venv/Scripts/python scripts/summarize.py`.

## Pilot findings

See `results/report.md`. tdd_1, test_after_1 and test_after_2 ran with configuration v1; tdd_2, tdd_3
and test_after_3 were repeated with v2 after their v1 attempts stopped without a commit. The failed v1
attempts are kept in `runs_archive/v1-bash-restricted/`; `run_meta.json` records `config_version` for
v2 runs.
