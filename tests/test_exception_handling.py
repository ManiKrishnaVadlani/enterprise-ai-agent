def divide_safely(numerator: float, denominator: float) -> tuple[float | None, bool]:
    """Return a division result and whether the attempt finished."""
    completed = False

    try:
        result = numerator / denominator
    except ZeroDivisionError:
        result = None
    finally:
        completed = True

    return result, completed


def test_divide_safely_handles_zero_division():
    result, completed = divide_safely(10, 0)

    assert result is None
    assert completed is True
