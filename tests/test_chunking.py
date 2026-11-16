import pytest

from app.chunking import chunk_text


def test_chunk_text_returns_empty_for_blank_input():
    assert chunk_text(" \n\t ", chunk_size=8, overlap=2) == []


def test_chunk_text_splits_near_word_boundaries_and_overlaps():
    chunks = chunk_text("alpha beta gamma delta", chunk_size=12, overlap=3)

    assert chunks == ["alpha beta", "beta gamma", "gamma delta"]


def test_chunk_text_handles_text_shorter_than_one_chunk():
    assert chunk_text("short text", chunk_size=20, overlap=4) == ["short text"]


@pytest.mark.parametrize(
    ("chunk_size", "overlap"), [(0, 0), (5, -1), (5, 5)]
)
def test_chunk_text_rejects_invalid_size_or_overlap(chunk_size, overlap):
    with pytest.raises(ValueError):
        chunk_text("some text", chunk_size, overlap)
