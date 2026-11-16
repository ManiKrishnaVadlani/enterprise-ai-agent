import pytest

from context_manager_example import ManagedDocument, read_document


def test_with_block_opens_then_closes_the_document():
    document = ManagedDocument("handbook.pdf")

    with document as opened_document:
        assert opened_document is document
        assert document.is_open is True

    assert document.is_open is False


def test_context_manager_closes_document_when_an_exception_occurs():
    document = ManagedDocument("handbook.pdf")

    with pytest.raises(ValueError, match="bad document"):
        with document:
            raise ValueError("bad document")

    assert document.is_open is False


def test_read_document_returns_a_description():
    assert read_document("handbook.pdf") == "Reading handbook.pdf"
