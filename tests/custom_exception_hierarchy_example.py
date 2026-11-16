"""Standalone learning example for a small application exception hierarchy."""


class AgentError(Exception):
    """Base class for errors raised by the knowledge agent."""


class DocumentError(AgentError):
    """Base class for errors encountered while working with documents."""


class DocumentNotFoundError(DocumentError):
    """Raised when a requested document does not exist."""


class DocumentLoadError(DocumentError):
    """Raised when an existing document cannot be loaded."""


class RetrievalError(AgentError):
    """Raised when relevant information cannot be retrieved."""


def handle_document_error(error: DocumentError) -> str:
    """Handle a missing document specifically, then other document errors."""
    try:
        raise error
    except DocumentNotFoundError as caught_error:
        return f"Document is missing: {caught_error}"
    except DocumentError as caught_error:
        return f"Could not process document: {caught_error}"


def handle_agent_error(error: AgentError) -> str:
    """Handle any agent-level error through the common parent class."""
    try:
        raise error
    except AgentError as caught_error:
        return f"Agent request failed: {type(caught_error).__name__}: {caught_error}"


if __name__ == "__main__":
    print(handle_document_error(DocumentNotFoundError("handbook.pdf")))
    print(handle_document_error(DocumentLoadError("handbook.pdf is unreadable")))
    print(handle_agent_error(RetrievalError("no matching passages")))
