Development method: Test-After.
1. IMPLEMENT: First implement the complete functionality in src/duration.py based on SPEC.md.
   Do not write any tests in this step.
   Commit with the message "impl: initial implementation".
2. TEST: Then write tests in tests/test_duration.py that cover every rule in SPEC.md.
   Run ./run_tests.sh. Commit with the message "test: <short description>".
3. FIX: If tests fail, find out whether the code or the test is wrong and fix it.
   Run ./run_tests.sh until all tests pass. Commit each fix with the message
   "fix: <short description>".
