"""Application errors safe to translate into useful API responses."""


class AgentError(Exception):
    """Base class for expected application failures."""


class InvalidDocumentError(AgentError):
    """The uploaded document is unsupported or cannot be read safely."""


class DocumentNotFoundError(AgentError):
    """The requested document does not exist in the vector store."""


class ProviderConfigurationError(AgentError):
    """A provider is not configured with the credentials it needs."""


class ProviderError(AgentError):
    """An embedding or language model provider failed."""


class StorageError(AgentError):
    """Persistent document or vector storage failed."""
