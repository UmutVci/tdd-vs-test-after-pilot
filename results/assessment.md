The pilot contains 6 runs (3 per condition) and therefore allows no statements about differences in
correctness between TDD and Test-After. The assessment below concerns only the three questions of the
pilot: can the workflows be applied, can compliance be checked, can correctness be measured.

**Two agent configurations.** tdd_1, test_after_1 and test_after_2 ran with configuration v1 (Bash
allowed only for `git *` and `./run_tests.sh`). In v1, the other three runs stopped after 3-4 turns
without a commit (see below); they are kept in `runs_archive/v1-bash-restricted/` and were repeated with
configuration v2 (Bash allowed in general, everything else unchanged). `run_meta.json` of the
repeated runs records `config_version: v2-bash-allowed`. Prompts, model, task and hidden tests were
identical in all runs.

### (1) Can both workflows be applied reliably with a coding agent? - Yes, after fixing the permissions

- **v1:** 3 of 6 runs stopped without a commit. In all six runs the agent's first write was a shell
  heredoc (`cat > file <<'EOF' ... && ./run_tests.sh && git commit ...`), which the v1 allow rules
  denied as a whole. Three runs switched to the Write tool, three stopped and asked for more
  permissions. The drop-outs were an artefact of the permission configuration.
- **v2:** all three repeated runs completed (0 permission denials). Together with the three v1 runs
  that completed, all 6 runs produced a full git history, test log and transcript.
- Trade-off of v2: Bash is no longer confined to the workspace. The file tools still are
  (`--restricted`, verified by the smoke test), but reading outside the workspace via `cat` would now
  only be detected afterwards by the transcript scan, not prevented. No run referenced
  `hidden_tests`, the project folder or any path outside its workspace.
- Read-only shell commands (`cat SPEC.md`, `ls`) were executed even in v1, because Claude Code 2.1.309
  auto-approves read-only commands inside the working directory.

### (2) Can Red-Green-Refactor adherence be checked automatically? - Yes, and it shows a systematic deviation

- Replaying the git history commit by commit plus the test log produced explainable results for every
  run. The checker found:
  - **All three TDD runs** end with a `refactor:` commit that adds 17, 14 and 5 new tests. Together
    with red commits that add several (parametrised) test cases at once, 17/25, 15/23 and 13/23 of the
    final tests (57-68 %) never failed at any commit. In other words, a large part of the TDD test
    suites was written test-after. The agent used the optional REFACTOR step to "complete the tests".
  - tdd_2 committed a `red:` commit whose new test already passed (the behaviour had been implemented
    in an earlier green step), and then went on directly to the next `red:` commit without a green.
    The test log shows no failing run before that commit, which matches.
  - tdd_3 added 2, 8 and 4 test cases in three red commits (parametrised tests); recorded as warnings.
  - Apart from that, red commits changed only `tests/`, had a failing new test and a logged failing
    run before the commit; all green commits passed. Cycle compliance: 7/8, 7/9, 6/7.
- All three Test-After runs followed their protocol exactly (`impl`, then one `test` commit; no
  `fix` was necessary). Each ran `./run_tests.sh` exactly once.
- Limitations: the rules "refactor/green adds new tests" and "tests never red" were added after
  seeing tdd_1, i.e. after data collection. Whether green steps were really "minimal" is not checked
  (several cycles covered more rules than their single test; 7-9 cycles sufficed for 10 rules).

### (3) Can functional correctness be measured with an independent test suite? - Technically yes, but with a ceiling effect

- `evaluate.py` worked for all runs (final `src/duration.py` against 36 hidden tests, the agent's own
  tests with coverage).
- **All 6 runs reached 36/36**, with 100 % line and branch coverage of their own tests. For this model
  the task is too easy; the hidden suite cannot separate the conditions if both reach the maximum.
- Process differences are visible: TDD runs took longer (54-86 s vs. 19-25 s), more turns (11-39 vs.
  6-9) and cost more ($0.08-0.17 vs. $0.04-0.06), and produced fewer own tests (23-25 vs. 43-47).
  With 3 runs per condition these are descriptions, not findings.

### What should be changed before the main experiment

1. **Keep configuration v2** (general Bash permission) and use it for all runs, so the main
   experiment does not mix configurations. Re-run the smoke test before data collection.
2. **Harder task or harder hidden tests:** a task with more interacting rules and edge cases (or
   several tasks), so that pass rates are not all 100 %. Otherwise only process differences, not
   correctness differences, can become visible.
3. **Decide how to deal with the "refactor adds tests" pattern.** It is systematic (3/3 TDD runs) and
   dilutes the treatment. Options: (a) keep the prompts and treat TDD fidelity ("tests never red",
   compliant cycles) as a measured covariate; (b) clarify in `tdd.md` that REFACTOR must not add
   tests. (b) changes the prompt and must therefore be decided before the main experiment, not
   during it.
4. **More runs and/or more tasks per condition:** runs took 19-86 s and $0.04-0.17 each, so many more
   runs are affordable.
5. **Freeze the checker rules before data collection** (pre-registration), and decide in advance
   whether non-compliant TDD runs stay in the analysis (intention-to-treat) or are analysed separately.
