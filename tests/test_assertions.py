"""Learning example for Python assertions.

Assertions check assumptions made by the program during development. They are
not a replacement for explicit validation of external or user-provided data.
"""


def confirm_nonempty_answer(answer: str) -> str:
    """Return an answer after checking an internal assumption."""
    assert answer, "The answer should not be empty"
    return answer


def require_nonempty_input(value: str) -> str:
    """Validate external input explicitly, including optimized Python runs."""
    if not value:
        raise ValueError("Input must not be empty")
    return value
