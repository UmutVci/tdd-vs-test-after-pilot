Development method: strict Test-Driven Development (Red-Green-Refactor).
Repeat the following cycle until every rule in SPEC.md is covered by tests and implemented:
1. RED: Add exactly one new small test for the next piece of behavior to tests/test_duration.py.
   Do not change src/ in this step. Run ./run_tests.sh and confirm that the new test fails.
   Commit with the message "red: <short description of the behavior>".
2. GREEN: Write the minimal code in src/duration.py needed to make all tests pass.
   Run ./run_tests.sh and confirm that all tests pass.
   Commit with the message "green: <short description>".
3. REFACTOR (optional): Improve the code or the tests without changing behavior.
   Run ./run_tests.sh and confirm that all tests pass.
   Commit with the message "refactor: <short description>".
