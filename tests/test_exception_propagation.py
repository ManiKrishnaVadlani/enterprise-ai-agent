"""Learning examples for exception propagation and re-raising."""


def open_document(document_name: str) -> str:
    """Simulate a missing document in a lower-level function."""
    raise FileNotFoundError(f"Document not found: {document_name}")


def prepare_document(document_name: str) -> str:
    """Pass the work to the lower-level function without catching its error."""
    return open_document(document_name)


def answer_from_document(document_name: str) -> str:
    """Let a missing-document error propagate to the caller."""
    document = prepare_document(document_name)
    return f"Answer based on {document}"


def load_with_logging(document_name: str) -> str:
    """Catch an error briefly, then re-raise the same exception."""
    try:
        return open_document(document_name)
    except FileNotFoundError:
        # A real application could log useful context here before re-raising.
        raise
