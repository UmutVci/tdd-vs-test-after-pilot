# Task: parse_duration

Implement the function `parse_duration(text: str) -> int` in `src/duration.py`.
It converts a duration string into a total number of seconds.

Rules:
- R1: A duration consists of one or more components. Each component is a non-negative
  integer followed by a unit: `h` (hours), `m` (minutes) or `s` (seconds).
  Examples: "2h" -> 7200, "45s" -> 45, "1h30m" -> 5400, "1h5s" -> 3605.
- R2: Units must appear in the order h, m, s. Each unit may appear at most once.
  "30m1h" and "1h2h" are invalid.
- R3: Numbers consist only of digits 0-9. Leading zeros are allowed ("05m" -> 300).
  Signs, decimal points and other characters are invalid ("-5s", "1.5h" are invalid).
- R4: Values are not limited by the next larger unit: "90m" -> 5400, "100s" -> 100.
- R5: Leading and trailing whitespace is ignored. Whitespace inside the string is invalid
  ("1h 30m" is invalid).
- R6: Units are lowercase only. "1H" is invalid.
- R7: "0s" -> 0 is valid. An empty string or a string containing only whitespace is invalid.
- R8: A number without a unit ("30") or a unit without a number ("h") is invalid.
- R9: For any invalid string, raise `ValueError`.
- R10: If `text` is not a `str`, raise `TypeError`.

Do not change the function signature.
