import pytest

from app.chunking import chunk_text


def test_chunk_text_returns_empty_for_blank_input():
    assert chunk_text(" \n\t ", chunk_size=8, overlap=2) == []


def test_chunk_text_splits_near_word_boundaries_and_overlaps():
    chunks = chunk_text("alpha beta gamma delta", chunk_size=12, overlap=3)

    assert chunks == ["alpha beta", "beta gamma", "gamma delta"]


def test_chunk_text_handles_text_shorter_than_one_chunk():
    assert chunk_text("short text", chunk_size=20, overlap=4) == ["short text"]


def test_chunk_text_prefers_paragraph_and_sentence_boundaries():
    text = "Alpha sentence. Beta sentence. Gamma sentence."

    assert chunk_text(text, chunk_size=24, overlap=0) == [
        "Alpha sentence.", "Beta sentence.", "Gamma sentence."
    ]


def test_chunk_text_preserves_headings_lists_unicode_and_order():
    text = "Policy: 東京\n- café access\n- résumé records"

    chunks = chunk_text(text, chunk_size=18, overlap=0)

    assert "Policy: 東京" in chunks[0]
    assert "café access" in " ".join(chunks)
    assert "résumé records" in " ".join(chunks)
    assert [part for chunk in chunks for part in ("Policy", "café", "résumé") if part in chunk] == [
        "Policy", "café", "résumé"
    ]


def test_chunk_text_bounds_long_words_and_unicode_by_character_count():
    text = "é" * 35 + " end"

    chunks = chunk_text(text, chunk_size=8, overlap=2)

    assert all(0 < len(chunk) <= 8 for chunk in chunks)
    assert "".join(chunk.strip("é ") for chunk in chunks) == "end"
    assert any("é" in chunk for chunk in chunks)


def test_chunk_text_normalizes_crlf_without_erasing_paragraph_separators():
    assert chunk_text("Heading\r\n\r\nBody", chunk_size=50, overlap=0) == [
        "Heading\n\nBody"
    ]


def test_chunk_text_keeps_heading_with_following_content_when_possible():
    chunks = chunk_text(
        "Security Policy\nAccess reviews occur quarterly.",
        chunk_size=28,
        overlap=0,
    )

    assert chunks[0].startswith("Security Policy")
    assert "Access" in chunks[0]


@pytest.mark.parametrize(
    ("chunk_size", "overlap"), [(0, 0), (5, -1), (5, 5)]
)
def test_chunk_text_rejects_invalid_size_or_overlap(chunk_size, overlap):
    with pytest.raises(ValueError):
        chunk_text("some text", chunk_size, overlap)
