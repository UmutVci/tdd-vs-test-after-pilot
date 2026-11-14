# Decision log

Chronological record of design decisions, what was observed and why things were changed.
Add new entries at the end of "Log"; update "Open decisions" when one is settled.

## Original brief (from the user, Stage 1)

- Pilot goals: (1) can both workflows be applied reliably with a coding agent, (2) can Red-Green-Refactor
  adherence be checked automatically from logs, (3) can functional correctness be measured with an
  independent test suite. The pilot is not meant to produce results.
- The assistant is the orchestrator: it must not solve the task or place any solution code anywhere.
- Each run is a separate, new headless `claude -p` process; no subagents or Task tool.
- SPEC and the three prompt files are used verbatim.
- CLI flags must be checked with `claude --help` / `--version`, not guessed.
- Python + pytest in a virtualenv. Workspaces outside the project folder. Transcripts and logs are
  copied to `runs/<condition>_<n>/` afterwards.
- Hidden tests: about 25-35 tests, normal cases, boundaries, one per error rule, rule id in the
  docstring, nothing beyond the SPEC.
- Stage 1: build and verify, then stop for approval. Stage 2: 3 runs per condition, analysis, report
  with a modest assessment ("3+3 runs allow no statistical conclusions").
- All code and Markdown in English.

## Log

### 2026-11-13 - Stage 1 setup

- Claude Code 2.1.309 (copy bundled with the desktop app; not on `PATH`). Python 3.13.15 via `uv`.
- Model fixed to `claude-sonnet-5-5`, effort `medium` (the user named no model; chosen as a cheaper,
  representative model; can be overridden).
- `--max-turns` is not listed in `claude --help` of 2.1.309, so it is not used; replaced by
  `--max-budget-usd 10` and `timeout 5400`.
- `--bare` not used: in 2.1.309 it authenticates only with `ANTHROPIC_API_KEY`; the user uses a
  claude.ai login. Isolation instead via `--safe-mode`, `--restricted`, `--strict-mcp-config`,
  `--no-session-persistence`, `--disable-slash-commands`, a scrubbed environment and an empty global
  git config.
- Hidden tests: 36 tests (R1-R8, R10; R9 is covered by every invalid-input test). Two deliberate
  interpretations to keep in mind: `1_000s` and the Arabic-Indic digit `٣s` are invalid under R3
  (Python's `int()` would accept them); `"\t45s\n"` treats tab/newline as whitespace under R5.
- Verified: the stub fails all 36 hidden tests with `NotImplementedError`; the checkers detect planted
  violations in a synthetic (task-unrelated) git history.
- The user approved Stage 1.

### 2026-11-13 - Stage 2, configuration v1

- Smoke test passed (commit and `./run_tests.sh` work; reading outside the workspace denied; no MCP
  servers). The only plugins loaded are Claude Code's built-in ones, which `--safe-mode` does not
  remove; accepted.
- First pilot attempt produced no data because of an orchestration bug (a `name` loop variable in the
  sourced `agent_config.sh` overwrote the run name). Fixed; no agent had run.
- Result: 3 of 6 runs (tdd_2, tdd_3, test_after_3) stopped after 3-4 turns without a commit. Cause:
  the agent wrote files with a Bash heredoc chained with test run and commit; v1 allowed only
  `Bash(git *)` and `Bash(./run_tests.sh*)`, so `dontAsk` denied the whole call and the agent gave up.
  The other 3 runs switched to the Write tool and finished (36/36 hidden tests).
- tdd_1 ended with `refactor: add tests covering remaining SPEC rules` adding 17 tests that never
  went through red. The checker did not flag this; rules "green/refactor adds new tests" and metric
  `tests_never_red` were added (post hoc).

### 2026-11-13 - Configuration v2 and re-runs

- Decision (user): widen the permission and re-run the 3 failed runs. v2 = `--allowedTools ... Bash`
  (Bash in general); everything else unchanged. `CONFIG_VERSION` is recorded in `run_meta.json`.
- Trade-off accepted: Bash is not confined to the workspace; access outside is only detected
  afterwards by the transcript scan. File tools remain confined by `--restricted`.
- Smoke test v2 passed, including a heredoc write + commit in one Bash call.
- Failed v1 runs moved to `runs_archive/v1-bash-restricted/` (kept, not summarised).
- All 3 re-runs completed with 0 permission denials and 36/36 hidden tests.
- All 3 TDD runs end with a `refactor:` commit that adds tests (17, 14, 5); 57-68 % of the final TDD
  tests never failed. The agents' own final messages explain it: earlier green steps implemented far
  more than required (one anchored regex), so remaining rules already passed and no red step was
  possible. tdd_2 also amended a broken commit; rule "history rewritten" was added (post hoc).
- The pilot therefore mixes v1 (tdd_1, test_after_1, test_after_2) and v2 (tdd_2, tdd_3,
  test_after_3); stated in the reports.

### 2026-11-13 - Publication

- Public repository `UmutVci/tdd-vs-test-after-pilot`, first commit `17d72d3`: setup code and
  `results/` (reports, assessment, summary.csv). Not included: `runs/`, `runs_archive/`, `.venv`,
  console logs (local paths, personal data in transcripts).
- Commit identity for this repository: `UmutVci` with the GitHub noreply address (the global git
  identity is a work account and must not appear in this public repository).

### 2026-11-14 - Research question and commitments to the supervisor

- Official research question (German, agreed with the supervisor): "Inwieweit unterscheidet sich die
  funktionale Korrektheit von Code, den ein KI-Coding-Agent in einem TDD-Workflow erzeugt, von der eines
  Test-After-Workflows, gemessen an einer unabhängigen, vorab definierten Testsuite?" README and
  AGENTS.md updated.
- Plan communicated to the supervisor before the pilot: same agent, model and settings for both
  workflows; identical requirements and fixed interface; hidden evaluation tests run after each run;
  one commit per TDD phase and logged test runs; check whether hooks can enforce the order; every run
  in a new session with a fresh repository copy (possibly in a container); then several tasks of
  different complexity and requirement detail, with repeated runs; methodology after Wohlin et al.
  (2024).
- Not yet done in the pilot (stated in the e-mail with the pilot results): enforcing the TDD order
  with hooks, running in a container.

## Open decisions (before the main experiment)

1. **Agent configuration:** keep v2 for all runs of the main experiment (recommended); no mixing.
2. **Ceiling effect:** all 6 pilot runs reached 36/36. Options: a harder task with more interacting
   rules, harder hidden tests, or several tasks. Without this, correctness differences cannot appear.
3. **"Refactor adds tests" / non-minimal green steps (3/3 TDD runs):**
   (a) keep the prompts and treat TDD fidelity (`tests_never_red`, compliant cycles) as a measured
   covariate, or (b) clarify in `prompts/tdd.md` that green must be minimal and refactor must not add
   tests. (b) changes a verbatim prompt and must be decided before data collection.
4. **Number of runs / tasks per condition:** runs cost $0.04-0.17 and take 19-86 s, so many more runs
   are affordable.
5. **Freeze the checker rules** (pre-registration) and decide whether non-compliant TDD runs stay in
   the analysis (intention-to-treat) or are analysed separately.
6. Optional: check "minimal green" more strictly (e.g. mutation testing per cycle).
7. **Hooks:** evaluate whether Claude Code hooks can enforce the TDD order (e.g. block edits to `src/`
   until a failing test is logged). Note: `--safe-mode` disables hooks, so enforcing hooks would need
   a different isolation setup. Enforcing the order changes the treatment (process is forced instead
   of measured) and must be decided before data collection.
8. **Container:** decide whether runs move into a container (stronger isolation than v2, where Bash
   is not confined to the workspace).
9. **Task set:** several tasks of different complexity and requirement detail, as promised to the
   supervisor; each needs its own SPEC, template stub and hidden tests.
