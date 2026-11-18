"""Small allowlisted tools for authenticated knowledge-base workflows."""

from dataclasses import dataclass
from typing import Any, Callable, TYPE_CHECKING
from pydantic import BaseModel, Field, ValidationError
from pydantic import ConfigDict

if TYPE_CHECKING:
    from app.services import ApplicationServices


class SearchArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=4, ge=1, le=10)


class DocumentArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: str = Field(min_length=1, max_length=64)


class EmptyArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    data: dict[str, Any]
    error: str | None = None


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: type[BaseModel]
    handler: Callable[[BaseModel, str], dict[str, Any]]


class ToolRegistry:
    """Explicit registry; no dynamic imports, shell, SQL, or filesystem tools."""

    def __init__(self, services: "ApplicationServices"):
        self._services = services
        self._tools = {
            "knowledge_search": Tool(
                "knowledge_search", "Search the authenticated user's documents.", SearchArguments, self._search
            ),
            "document_list": Tool(
                "document_list", "List metadata for the authenticated user's documents.", EmptyArguments, self._list
            ),
            "document_info": Tool(
                "document_info", "Get metadata for one owned document without its contents.", DocumentArguments, self._info
            ),
        }

    @property
    def descriptions(self) -> list[dict[str, Any]]:
        return [{"name": t.name, "description": t.description, "input_schema": t.schema.model_json_schema()} for t in self._tools.values()]

    def execute(self, name: str, arguments: dict[str, Any], user_id: str) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(False, {}, "unknown_tool")
        try:
            parsed = tool.schema.model_validate(arguments)
            return ToolResult(True, tool.handler(parsed, user_id))
        except ValidationError:
            return ToolResult(False, {}, "invalid_arguments")
        except Exception:
            # Keep provider/storage internals and user data out of tool errors.
            return ToolResult(False, {}, "tool_execution_failed")

    def _search(self, args: BaseModel, user_id: str) -> dict[str, Any]:
        parsed = SearchArguments.model_validate(args)
        vectors = self._services.rag.embeddings.embed([parsed.question])
        matches = self._services.store.search(
            vectors[0], min(parsed.top_k, 10), owner_id=user_id,
            min_score=self._services.rag.min_relevance_score,
        )
        return {"results": [
            {"document_id": m.chunk.document_id, "filename": m.chunk.filename,
             "chunk_id": m.chunk.chunk_id, "page_number": m.chunk.page_number,
             "score": round(m.score, 4), "text": m.chunk.text[:2000]}
            for m in matches
        ]}

    def _list(self, _args: BaseModel, user_id: str) -> dict[str, Any]:
        documents = self._services.documents.list_documents(owner_id=user_id, limit=100)
        return {"documents": [
            {"document_id": d.document_id, "filename": d.filename,
             "ingested_at": d.ingested_at.isoformat(), "chunk_count": d.chunk_count}
            for d in documents
        ]}

    def _info(self, args: BaseModel, user_id: str) -> dict[str, Any]:
        parsed = DocumentArguments.model_validate(args)
        try:
            from uuid import UUID
            document_id = str(UUID(parsed.document_id))
        except ValueError:
            return {"found": False}
        document = self._services.store.get_document_summary(document_id, user_id)
        if document is None:
            return {"found": False}
        return {"found": True, "document_id": document.document_id, "filename": document.filename,
                "ingested_at": document.ingested_at.isoformat(), "chunk_count": document.chunk_count}
