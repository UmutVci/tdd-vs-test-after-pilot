# AGENTS.md

Instructions for AI coding assistants (Codex, Claude Code, ...) working on this repository.
Claude Code reads this file through `CLAUDE.md`. The history behind these rules is in
`docs/DECISIONS.md`; read it before changing the experiment design.

## Project

Experiment setup for a Hausarbeit (seminar paper). Research question:

> How does the functional correctness of code produced by an AI coding agent in a TDD workflow differ
> from a Test-After workflow, measured with an independent test suite?

A coding agent (headless Claude Code) implements `parse_duration` (`task/SPEC.md`) under one of two
workflows (`prompts/tdd.md`, `prompts/test_after.md`). The scripts check whether the agent followed its
workflow (git history + test logs) and measure correctness with hidden tests.

Current status: the **pilot is finished** (6 runs, 3 per condition). Results are in
`results/report.md`, `results/v2_rerun_report.md` and `results/assessment.md`. The next phase is
preparing the main experiment (see "Open decisions" in `docs/DECISIONS.md`).

## Your role: orchestrator, not solver (hard rules)

1. **Never solve the task.** Do not write an implementation of `parse_duration`, not even partially,
   as an example, in a test fixture, in a comment or in a scratch file. The only implementation in this
   repository is the stub in `task/template/src/duration.py` (`raise NotImplementedError`).
   To test the analysis scripts, use synthetic histories with unrelated code (e.g. a `VERSION = 1`
   constant) in a temporary directory outside the repository.
2. **Agents under test are separate processes.** Every run is a new headless `claude -p` process
   started by `scripts/run_one.sh`. Never use your own subagents, Task tool or session to produce run
   data.
3. **Verbatim files.** Do not edit `task/SPEC.md`, `task/template/SPEC.md` or `prompts/*.md` unless the
   user explicitly decides to change the experiment design. The two SPEC files must stay identical.
   Prompt = `common_header.md` + blank line + `tdd.md` or `test_after.md`.
4. **Hidden tests stay hidden.** `hidden_tests/` must never be reachable from or mentioned to an agent
   under test. Run workspaces live outside the project folder (`/tmp/tdd-pilot-runs/<run>/` in Git
   Bash = `%LOCALAPPDATA%\Temp\tdd-pilot-runs`). Hidden tests may only test what `task/SPEC.md` states;
   every test names its rule (R1-R10) in its name and docstring.
5. **Do not guess CLI flags.** Before changing the agent invocation, run `claude --version` and
   `claude --help` for the installed version and use only listed flags. Document flags and version in
   `README.md`. (In 2.1.309 `--max-turns` is not listed; `--bare` accepts only `ANTHROPIC_API_KEY`.)
6. **Do not overclaim.** With few runs, report descriptions, not effects. State limitations and every
   change made after seeing data.

## Language and communication

- All code, comments, commit messages and Markdown files: **English**.
- Talk to the user in **Turkish** (they write Turkish).
- Match the existing code style: plain Python 3.13 standard library + pytest, Bash for orchestration,
  short docstrings at the top of each script, few inline comments.

## Environment (Windows)

- Windows 11, scripts run in **Git Bash**. Python: `.venv/Scripts/python` (3.13, created with `uv`;
  packages pinned in `requirements.txt`: pytest, pytest-cov, pytest-timeout).
- Recreate the venv: `uv venv .venv --python 3.13` and `uv pip install --python .venv/Scripts/python.exe -r requirements.txt`.
- Claude Code CLI is not on `PATH`; `scripts/agent_config.sh` finds the copy bundled with the desktop
  app (`%LOCALAPPDATA%\Claude-Data\*\claude-code\<version>\...\claude.exe`) or uses `$CLAUDE_BIN`.
  The standalone CLI must be logged in (`claude auth status` -> `loggedIn: true`).
- When started from inside another Claude session, the parent's `CLAUDE*` env vars must not leak into
  the agent; `agent_config.sh` removes them (keeps only credentials and Git Bash path).

## How to run

```bash
scripts/smoke_test.sh                 # configuration check, task-unrelated prompt (~$0.02)
scripts/run_one.sh tdd 4              # one run -> runs/tdd_4/
scripts/run_pilot.sh 3                # 3 runs per condition, interleaved, then the analysis
.venv/Scripts/python scripts/check_process.py   # workflow compliance -> runs/<run>/process.json
.venv/Scripts/python scripts/evaluate.py        # hidden tests + own tests/coverage -> runs/<run>/evaluation.json
.venv/Scripts/python scripts/summarize.py       # results/summary.csv + results/report.md
```

`TDD_PILOT_RUNS_DIR` / `TDD_PILOT_RESULTS_DIR` redirect the analysis scripts (useful for synthetic test
fixtures). Settings can be overridden with `TDD_PILOT_MODEL`, `TDD_PILOT_EFFORT`,
`TDD_PILOT_MAX_BUDGET_USD`, `TDD_PILOT_TIMEOUT_SECONDS`, `TDD_PILOT_RUNS_ROOT`.

Run the smoke test after any change to `scripts/agent_config.sh` and before any data collection.

## Agent configuration (current: v2)

Defined only in `scripts/agent_config.sh` (`CONFIG_VERSION="v2-bash-allowed"`):
model `claude-sonnet-5-5`, effort `medium`, `--output-format stream-json --verbose`, `--safe-mode`,
`--restricted`, `--strict-mcp-config`, `--no-session-persistence`, `--disable-slash-commands`,
`--tools "Bash,Read,Edit,Write,Glob,Grep"`, `--allowedTools Read Edit Write Glob Grep Bash`,
`--permission-mode dontAsk`, `--permission-prompts none`, `--max-budget-usd 10`, `timeout 5400`.

- If you change the configuration, bump `CONFIG_VERSION`; it is written to every `run_meta.json`.
- Never mix configurations within one data collection. Known trade-off of v2: Bash is not confined to
  the workspace, so access outside it is only detected afterwards by the transcript scan.
- Pass the prompt before the variadic `--tools` / `--allowedTools` options.

## Run data

- `runs/` and `runs_archive/` are **not** in git (full transcripts with local paths and the user's
  email in the agent context; copied workspaces with their own `.git`). Never commit or publish them.
- Never overwrite or delete a run. `run_one.sh` refuses existing workspaces/output folders. Failed or
  superseded runs go to `runs_archive/<reason>/` (on Windows: copy, verify with `diff -rq`, then
  delete; `mv` of these folders fails because of file locks).

## Analysis rules (`scripts/check_process.py`)

TDD violations: red commit must change only `tests/`, have a failing test, the newly added test must
fail, and a failing `./run_tests.sh` run on the parent commit must be logged before it; green must
directly follow red and pass; refactor must pass; green/refactor must not add new tests; other commit
types; red without green; no cycle. Metric: `tests_never_red`. Warnings: not exactly one new test per
red, green without `src/` change or with `tests/` change, refactor not after green/refactor.
Test-After violations: missing/late `impl:`, `impl:` without `src/` or with tests, tests before
`impl:`, no `test:` commit, other commit types, tests executed before `impl:`.
Both: `hidden_tests` or project path in the transcript (violation), tool paths outside the workspace,
uncommitted changes, rewritten history (test log HEADs missing from the final history) (warnings).

The rules "green/refactor adds new tests", `tests_never_red` and "history rewritten" were added after
seeing pilot data. **Freeze the rule set before the main experiment** and record any later change in
`docs/DECISIONS.md`.

## Git and GitHub

- Public repository: https://github.com/UmutVci/tdd-vs-test-after-pilot (branch `main`).
- Repo-local identity (already set in `.git/config`): `UmutVci <36034903+UmutVci@users.noreply.github.com>`.
  Do not use the global git identity (work account) for this repository.
- `gh` has two accounts: `UmutVci` (this repo) and a second (work) account. Check with
  `gh auth status`. Pushing needs `UmutVci` active (`gh auth switch --hostname github.com --user UmutVci`);
  switch back afterwards if the user asks.
- Commit or push only when the user asks. Publishing is public: check that no run artefacts, local
  paths or personal data are included.
- `.gitattributes` forces LF for `*.sh`, `*.py`, `*.md`; executable bit is set in git for all `*.sh`.

## Known pitfalls

- Bash scripts that are `source`d must not use common variable names in loops (a `name` loop variable
  once overwrote the run name in `run_one.sh`).
- In Git Bash, `ls` may append `*` to executables; use globs instead of parsing `ls`.
- Inline Python in Bash heredocs: watch backslashes/quoting; prefer small script files or the Edit tool.
- `gh auth login --web`: the device code flow only completes after pressing Enter in the terminal; use
  a private browser window so the right GitHub account approves it.
- Claude Code may append a `Co-Authored-By` trailer to the agents' commits; the checker reads only the
  subject line.
