import pytest

from test_exception_chaining import DocumentLoadError, load_document


def test_load_document_wraps_missing_document_with_explicit_cause():
    with pytest.raises(DocumentLoadError, match="Could not load document: handbook.pdf") as error:
        load_document("handbook.pdf")

    assert isinstance(error.value.__cause__, FileNotFoundError)
    assert str(error.value.__cause__) == "Document not found: handbook.pdf"
