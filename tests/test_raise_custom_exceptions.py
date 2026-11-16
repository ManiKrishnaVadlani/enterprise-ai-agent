class InvalidAgeError(ValueError):
    """Raised when an age is outside the allowed range."""


def validate_age(age: int) -> int:
    """Return an age from 0 to 120, or raise InvalidAgeError."""
    if not 0 <= age <= 120:
        raise InvalidAgeError("Age must be between 0 and 120.")

    return age


def test_validate_age_returns_a_valid_age():
    assert validate_age(30) == 30


def test_validate_age_raises_custom_exception_for_negative_age():
    import pytest

    with pytest.raises(InvalidAgeError, match="Age must be between 0 and 120"):
        validate_age(-1)
