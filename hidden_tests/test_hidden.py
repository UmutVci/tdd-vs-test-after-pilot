"""Independent evaluation tests for parse_duration (never shown to the agents).

Every test checks exactly one SPEC rule; the rule id (R1..R10) is the first token
of the docstring and is also part of the test name. Invalid inputs always expect
ValueError (R9) and non-str inputs TypeError (R10).

The module under test is loaded from the path in DURATION_MODULE_PATH
(default: ./src/duration.py), so the tests do not depend on how the agent
structured its imports.
"""
import importlib.util
import os

import pytest

_MODULE_PATH = os.environ.get("DURATION_MODULE_PATH", os.path.join("src", "duration.py"))
_spec = importlib.util.spec_from_file_location("duration_under_test", _MODULE_PATH)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
parse_duration = _module.parse_duration


# --- R1: components of non-negative integer + unit h/m/s -------------------

def test_r1_hours_only():
    """R1: "2h" -> 7200 (example from SPEC)."""
    assert parse_duration("2h") == 7200


def test_r1_seconds_only():
    """R1: "45s" -> 45 (example from SPEC)."""
    assert parse_duration("45s") == 45


def test_r1_minutes_only():
    """R1: a single minutes component, "3m" -> 180."""
    assert parse_duration("3m") == 180


def test_r1_hours_and_minutes():
    """R1: "1h30m" -> 5400 (example from SPEC)."""
    assert parse_duration("1h30m") == 5400


def test_r1_hours_and_seconds():
    """R1: "1h5s" -> 3605 (example from SPEC); the minutes component may be skipped."""
    assert parse_duration("1h5s") == 3605


def test_r1_minutes_and_seconds():
    """R1: "2m3s" -> 123; the hours component may be skipped."""
    assert parse_duration("2m3s") == 123


def test_r1_all_three_units():
    """R1: "1h1m1s" -> 3661."""
    assert parse_duration("1h1m1s") == 3661


def test_r1_unknown_unit_is_invalid():
    """R1: only h, m and s are units; "5d" is invalid (ValueError per R9)."""
    with pytest.raises(ValueError):
        parse_duration("5d")


# --- R2: order h, m, s and each unit at most once ---------------------------

def test_r2_minutes_before_hours_invalid():
    """R2: "30m1h" is invalid (example from SPEC)."""
    with pytest.raises(ValueError):
        parse_duration("30m1h")


def test_r2_repeated_hours_invalid():
    """R2: "1h2h" is invalid (example from SPEC)."""
    with pytest.raises(ValueError):
        parse_duration("1h2h")


def test_r2_seconds_before_minutes_invalid():
    """R2: "1s1m" is invalid (s before m)."""
    with pytest.raises(ValueError):
        parse_duration("1s1m")


def test_r2_repeated_minutes_invalid():
    """R2: "1m1m" is invalid (m appears twice)."""
    with pytest.raises(ValueError):
        parse_duration("1m1m")


# --- R3: digits 0-9 only, leading zeros allowed -----------------------------

def test_r3_leading_zero_allowed():
    """R3: "05m" -> 300 (example from SPEC)."""
    assert parse_duration("05m") == 300


def test_r3_negative_sign_invalid():
    """R3: "-5s" is invalid (example from SPEC)."""
    with pytest.raises(ValueError):
        parse_duration("-5s")


def test_r3_plus_sign_invalid():
    """R3: signs are invalid, "+5s"."""
    with pytest.raises(ValueError):
        parse_duration("+5s")


def test_r3_decimal_point_invalid():
    """R3: "1.5h" is invalid (example from SPEC)."""
    with pytest.raises(ValueError):
        parse_duration("1.5h")


def test_r3_underscore_in_number_invalid():
    """R3: other characters are invalid, "1_000s" (Python's int() would accept it)."""
    with pytest.raises(ValueError):
        parse_duration("1_000s")


def test_r3_non_ascii_digit_invalid():
    """R3: only digits 0-9; the Arabic-Indic digit three ("\\u0663s") is invalid."""
    with pytest.raises(ValueError):
        parse_duration("٣s")


# --- R4: values not limited by the next larger unit -------------------------

def test_r4_minutes_above_59():
    """R4: "90m" -> 5400 (example from SPEC)."""
    assert parse_duration("90m") == 5400


def test_r4_seconds_above_59():
    """R4: "100s" -> 100 (example from SPEC)."""
    assert parse_duration("100s") == 100


# --- R5: surrounding whitespace ignored, inner whitespace invalid -----------

def test_r5_surrounding_spaces_ignored():
    """R5: leading and trailing spaces are ignored, "  1h30m  " -> 5400."""
    assert parse_duration("  1h30m  ") == 5400


def test_r5_surrounding_tab_and_newline_ignored():
    """R5: leading tab and trailing newline are ignored, "\\t45s\\n" -> 45."""
    assert parse_duration("\t45s\n") == 45


def test_r5_space_between_components_invalid():
    """R5: "1h 30m" is invalid (example from SPEC)."""
    with pytest.raises(ValueError):
        parse_duration("1h 30m")


def test_r5_space_between_number_and_unit_invalid():
    """R5: whitespace inside the string is invalid, "1 h"."""
    with pytest.raises(ValueError):
        parse_duration("1 h")


# --- R6: lowercase units only -----------------------------------------------

def test_r6_uppercase_hours_invalid():
    """R6: "1H" is invalid (example from SPEC)."""
    with pytest.raises(ValueError):
        parse_duration("1H")


def test_r6_uppercase_unit_in_second_component_invalid():
    """R6: "1h30M" is invalid."""
    with pytest.raises(ValueError):
        parse_duration("1h30M")


# --- R7: zero is valid, empty / whitespace-only is invalid ------------------

def test_r7_zero_seconds():
    """R7: "0s" -> 0 (example from SPEC)."""
    assert parse_duration("0s") == 0


def test_r7_empty_string_invalid():
    """R7: the empty string is invalid."""
    with pytest.raises(ValueError):
        parse_duration("")


def test_r7_whitespace_only_invalid():
    """R7: a string containing only whitespace is invalid."""
    with pytest.raises(ValueError):
        parse_duration("   ")


# --- R8: number without unit / unit without number ----------------------------

def test_r8_number_without_unit_invalid():
    """R8: "30" is invalid (example from SPEC)."""
    with pytest.raises(ValueError):
        parse_duration("30")


def test_r8_unit_without_number_invalid():
    """R8: "h" is invalid (example from SPEC)."""
    with pytest.raises(ValueError):
        parse_duration("h")


def test_r8_trailing_number_without_unit_invalid():
    """R8: "1h30" is invalid (the last number has no unit)."""
    with pytest.raises(ValueError):
        parse_duration("1h30")


def test_r8_unit_without_number_after_component_invalid():
    """R8: "1hm" is invalid (the unit m has no number)."""
    with pytest.raises(ValueError):
        parse_duration("1hm")


# --- R10: non-str input -----------------------------------------------------

def test_r10_none_raises_type_error():
    """R10: None is not a str -> TypeError."""
    with pytest.raises(TypeError):
        parse_duration(None)


def test_r10_int_raises_type_error():
    """R10: an int is not a str -> TypeError."""
    with pytest.raises(TypeError):
        parse_duration(3600)


def test_r10_bytes_raises_type_error():
    """R10: bytes are not a str -> TypeError."""
    with pytest.raises(TypeError):
        parse_duration(b"1h")
