import pytest

from test_assertions import confirm_nonempty_answer, require_nonempty_input


def test_assertion_succeeds_when_condition_is_true():
    assert confirm_nonempty_answer("Here is the answer") == "Here is the answer"


def test_assertion_failure_raises_assertion_error_with_message():
    with pytest.raises(AssertionError, match="The answer should not be empty"):
        confirm_nonempty_answer("")


def test_explicit_raise_validates_empty_external_input():
    with pytest.raises(ValueError, match="Input must not be empty"):
        require_nonempty_input("")


def test_explicit_input_validation_returns_valid_value():
    assert require_nonempty_input("customer question") == "customer question"
