import pytest

from custom_exception_hierarchy_example import (
    AgentError,
    DocumentError,
    DocumentLoadError,
    DocumentNotFoundError,
    RetrievalError,
    handle_agent_error,
    handle_document_error,
)


@pytest.mark.parametrize(
    ("child", "parent"),
    [
        (DocumentError, AgentError),
        (DocumentNotFoundError, DocumentError),
        (DocumentLoadError, DocumentError),
        (RetrievalError, AgentError),
    ],
)
def test_custom_errors_inherit_from_the_expected_parent(child, parent):
    assert issubclass(child, parent)


def test_document_handler_catches_specific_missing_document_error_first():
    assert handle_document_error(DocumentNotFoundError("handbook.pdf")) == (
        "Document is missing: handbook.pdf"
    )


def test_document_parent_handler_catches_other_document_errors():
    assert handle_document_error(DocumentLoadError("unreadable")) == (
        "Could not process document: unreadable"
    )


def test_agent_parent_handler_catches_child_retrieval_error():
    assert handle_agent_error(RetrievalError("no matching passages")) == (
        "Agent request failed: RetrievalError: no matching passages"
    )
