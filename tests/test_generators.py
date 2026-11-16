import pytest

from generators_example import (
    cleanup_generator,
    document_name_generator,
    normal_document_names,
    number_steps,
    square_numbers,
)


def test_normal_function_returns_all_values_immediately():
    assert normal_document_names(3) == [
        "document-0",
        "document-1",
        "document-2",
    ]


def test_generator_function_starts_work_only_when_requested():
    events = []
    names = document_name_generator(2, events)

    assert events == []
    assert next(names) == "document-0"
    assert events == ["generated:document-0"]


def test_next_returns_one_value_at_a_time_and_preserves_position():
    numbers = number_steps()

    assert next(numbers) == 1
    assert next(numbers) == 2
    assert next(numbers) == 3
    with pytest.raises(StopIteration):
        next(numbers)


def test_large_generator_can_be_used_partially_without_building_a_list():
    events = []
    names = document_name_generator(1_000_000, events)

    first_three = [next(names) for _ in range(3)]

    assert first_three == ["document-0", "document-1", "document-2"]
    assert events == [
        "generated:document-0",
        "generated:document-1",
        "generated:document-2",
    ]
    assert not isinstance(names, list)


def test_generator_expression_produces_expected_squares():
    squares = square_numbers(4)

    assert iter(squares) is squares
    assert list(squares) == [0, 1, 4, 9]


def test_generator_cleanup_runs_when_closed_early():
    events = []
    records = cleanup_generator(events)

    assert next(records) == "first record"
    records.close()

    assert events == ["generator cleaned up"]


def test_generator_cleanup_runs_and_error_propagates():
    events = []
    records = cleanup_generator(events)
    assert next(records) == "first record"

    with pytest.raises(ValueError, match="bad record"):
        records.throw(ValueError("bad record"))

    assert events == ["generator cleaned up"]
