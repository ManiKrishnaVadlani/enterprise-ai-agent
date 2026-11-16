import pytest

from iterators_example import (
    CountdownIterator,
    DocumentCollection,
    compare_document_sources,
)


def test_list_is_iterable_and_each_iter_call_makes_a_fresh_iterator():
    documents = ["handbook.pdf", "policy.pdf"]

    first_iterator = iter(documents)
    second_iterator = iter(documents)

    assert first_iterator is not documents
    assert iter(first_iterator) is first_iterator
    assert next(first_iterator) == "handbook.pdf"
    assert next(second_iterator) == "handbook.pdf"


def test_custom_iterable_returns_a_new_iterator_each_time():
    documents = DocumentCollection(["handbook.pdf", "policy.pdf"])

    first_iterator = iter(documents)
    second_iterator = iter(documents)

    assert first_iterator is not second_iterator
    assert next(first_iterator) == "handbook.pdf"
    assert list(second_iterator) == ["handbook.pdf", "policy.pdf"]


def test_custom_iterator_uses_iter_and_next_protocol_methods():
    countdown = CountdownIterator(3)

    assert iter(countdown) is countdown
    assert next(countdown) == 3
    assert next(countdown) == 2
    assert next(countdown) == 1


def test_custom_iterator_raises_stopiteration_after_it_is_exhausted():
    countdown = CountdownIterator(1)

    assert next(countdown) == 1
    with pytest.raises(StopIteration):
        next(countdown)
    with pytest.raises(StopIteration):
        next(countdown)


def test_for_loop_uses_custom_iterator_protocol():
    assert list(CountdownIterator(3)) == [3, 2, 1]


def test_list_iterator_and_generator_have_practical_one_pass_behavior(capsys):
    remaining = compare_document_sources(["handbook.pdf", "policy.pdf"])

    assert remaining == ["policy.pdf"]
    assert capsys.readouterr().out.splitlines() == [
        "List keeps all values: ['handbook.pdf', 'policy.pdf']",
        "Iterator next value: handbook.pdf",
        "List is still reusable: ['handbook.pdf', 'policy.pdf']",
        "Generator next value: handbook.pdf",
        "Generator remaining values: ['policy.pdf']",
    ]
