# Report: configuration v2 (re-run of tdd_2, tdd_3, test_after_3)

Date: 2026-11-13. Model `claude-sonnet-5-5`, effort `medium`, Claude Code `2.1.309`.
Prompts, task, template and hidden tests are identical to configuration v1.

## Why a v2 was necessary

In configuration v1 the agent was allowed to run only `git *` and `./run_tests.sh` in Bash. In all six
v1 runs the agent's first attempt to write a file was a shell heredoc chained with the test run and the
commit, e.g.

```
cat > tests/test_duration.py <<'EOF' ... EOF
./run_tests.sh | tail -3; git add tests && git commit -qm "red: parse seconds only"
```

This command was denied as a whole (`dontAsk` mode). Three runs (tdd_1, test_after_1, test_after_2)
switched to the Write tool and finished. Three runs (tdd_2, tdd_3, test_after_3) stopped after 3-4 turns
and asked for more permissions, without any commit and with the stub unchanged (0/36 hidden tests).
These attempts are kept in `runs_archive/v1-bash-restricted/`.

## What was changed

Only one setting, in `scripts/agent_config.sh`:

| | v1 | v2 |
|---|---|---|
| `--allowedTools` | `Read Edit Write Glob Grep "Bash(git *)" "Bash(./run_tests.sh)" "Bash(./run_tests.sh *)"` | `Read Edit Write Glob Grep Bash` |

All other flags (`--safe-mode`, `--restricted`, `--strict-mcp-config`, `--no-session-persistence`,
`--tools`, `--permission-mode dontAsk`, budget, timeout) stayed the same. `run_meta.json` of the v2 runs
records `config_version: v2-bash-allowed`.

Consequence for isolation: the file tools (Read/Edit/Write/Glob/Grep) remain confined to the workspace
by `--restricted`, but Bash is no longer confined. Reading a file outside the workspace via the shell
is therefore not prevented any more; it is only detected afterwards by the transcript scan in
`check_process.py`.

## Smoke test with v2

`scripts/smoke_test.sh` was changed to reproduce the failing pattern: one Bash call that creates a file
with a heredoc and commits it. Result (5 turns, $0.02):

| Check | Result |
|---|---|
| `./run_tests.sh` runs and writes a log line | PASS |
| heredoc file write + `git add` + `git commit` in one Bash call | PASS |
| Read tool on a canary file outside the workspace is denied | PASS (denied, canary not in transcript) |
| no MCP servers, no user-installed plugins | PASS (only Claude Code's 4 built-in plugins) |
| no CLAUDE.md / user memory in context | PASS (agent's own statement) |

Observed side effect: Claude Code adds a `Co-Authored-By: Claude ...` line to commit messages (the agent
reported a "commit attribution reminder" in its context). The checker uses only the commit subject, so
this has no effect on the analysis.

## Results of the three v2 runs

| Run | Hidden tests | Own tests (all pass) | Line / branch cov. | Commits | Cycles compliant | Own tests never red | Wall time | Turns | Cost | Permission denials |
|---|---|---|---|---|---|---|---|---|---|---|
| tdd_2 | 36/36 | 23 (yes) | 100 % / 100 % | 9 red, 8 green, 1 refactor | 7/9 | 15/23 | 76 s | 15 | $0.096 | 0 |
| tdd_3 | 36/36 | 23 (yes) | 100 % / 100 % | 7 red, 7 green, 1 refactor | 6/7 | 13/23 | 54 s | 11 | $0.075 | 0 |
| test_after_3 | 36/36 | 43 (yes) | 100 % / 100 % | 1 impl, 1 test | - (protocol followed) | - | 19 s | 6 | $0.036 | 0 |

All three runs finished with `success` and without any permission denial. No transcript referenced
`hidden_tests`, the project folder or a path outside the workspace.

### tdd_2

- Test log: 20 runs, alternating failing (red) and passing (green) runs, as expected for TDD.
- Violations found by `check_process.py`:
  - `red: duplicate unit` (`a7b3561b27`): the new test already passed when committed (the behaviour had
    been implemented by an earlier green step); no failing run was logged before the commit, and the
    next commit was another `red:` instead of a `green:`.
  - `refactor: add regression tests for remaining spec rules` (`79029da258`): adds 14 tests that never
    went through red.
- Warning (new check, see below): the test log contains runs on two commits that are not part of the
  final history, i.e. the history was rewritten.
- The agent's own final report matches the checker and explains it: "`1h2h` already passed when I
  wrote its test", a broken green commit was fixed with `git commit --amend`, and the remaining rules
  "were already satisfied", so they were added "as regression tests in one commit labelled
  refactor, since no further red step was possible".

### tdd_3

- Test log: 15 runs, alternating red/green.
- Violation: `refactor: cover remaining spec examples` (`2e0df2eec2`) adds 5 tests that never went
  through red.
- Warnings: three red commits added a parametrised test with 2, 8 and 4 cases instead of exactly one
  new test.
- The agent's final report again states this itself: the last commit "only adds tests ... Those
  passed on first run, so they have no red step", and "some red commits add a parametrized test with
  several inputs rather than exactly one".

### test_after_3

- Commits `impl: initial implementation` (only `src/`) and `test: cover all parse_duration spec rules`
  (only `tests/`), 43 tests, one `./run_tests.sh` run with 43 passed, no `fix:` necessary. Fully
  compliant.

## Interpretation (pilot level only)

- **v2 removes the drop-outs.** 3/3 runs completed, compared with 0/3 for the same run slots in v1.
  With so few runs this shows only that the blocking cause was removed, not a reliability rate.
- **The TDD deviation is systematic and explainable.** Together with tdd_1 (v1), all three TDD runs end
  with a `refactor:` commit that adds tests (17, 14, 5), and 57-68 % of the final TDD tests never
  failed. The agents' explanation is consistent: their green steps implemented much more than the
  current test required (the final implementations are one anchored regex), so the remaining rules
  already passed and could no longer produce a red step. The non-minimal green steps are the actual
  deviation; adding tests in refactor is the consequence.
- **Agent self-reports agree with the automatic check.** In both v2 TDD runs, every deviation the
  checker flagged was also mentioned by the agent in its final message. This supports the validity of
  the checker, but self-reports must not replace it: the agent reported an amend that the replay alone
  could not see.
- **Correctness ceiling.** All v2 runs reached 36/36 hidden tests, like the v1 runs that completed.

## Changes to the analysis made after this re-run

- New warning in `check_process.py`: "history rewritten (test runs on commits missing from the final
  history)". It compares the HEAD hashes in `.testlog/test_runs.jsonl` with the final git history. It
  fires for tdd_2 only (2 orphaned commits) and confirms the amend reported by the agent.
- As before: these rules were added after seeing the data and should be frozen before the main
  experiment.
