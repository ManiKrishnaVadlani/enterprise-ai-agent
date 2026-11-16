"""Learning example for translating a storage error into an application error."""


class DocumentLoadError(RuntimeError):
    """Raised when the application cannot load a requested document."""


def read_document(document_name: str) -> str:
    """Simulate a lower-level storage lookup that cannot find a document."""
    raise FileNotFoundError(f"Document not found: {document_name}")


def load_document(document_name: str) -> str:
    """Wrap a storage error with a clearer application-level error."""
    try:
        return read_document(document_name)
    except FileNotFoundError as original_error:
        raise DocumentLoadError(
            f"Could not load document: {document_name}"
        ) from original_error
