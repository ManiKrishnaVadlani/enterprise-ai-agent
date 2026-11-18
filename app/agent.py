"""Bounded deterministic orchestration over the explicit tool allowlist."""

from dataclasses import dataclass
import logging
from time import perf_counter
from app.rag import RAGPipeline, Answer
from app.tools import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentRun:
    answer: Answer
    workflow: dict


class AgentOrchestrator:
    """Uses a fixed one-search workflow; this is controlled orchestration, not autonomous reasoning."""

    MAX_STEPS = 2
    MAX_TOOL_CALLS = 1

    def __init__(self, tools: ToolRegistry, rag: RAGPipeline):
        self.tools = tools
        self.rag = rag

    def run(self, question: str, user_id: str, retrieval_query: str | None = None) -> AgentRun:
        tool_started = perf_counter()
        search = self.tools.execute(
            "knowledge_search", {"question": retrieval_query or question, "top_k": 4}, user_id
        )
        tool_duration = perf_counter() - tool_started
        if not search.ok:
            from app.llm import NO_INFORMATION_ANSWER
            logger.info(
                "Agent workflow stopped tool=knowledge_search status=failed steps=1 tool_calls=1 error_code=%s",
                search.error,
            )
            return AgentRun(Answer(NO_INFORMATION_ANSWER, []), {
                "status": "stopped", "steps": 1, "tool_calls": 1,
                "tools": [{"name": "knowledge_search", "status": "failed"}],
                "stop_reason": search.error,
            })
        results = search.data.get("results", [])
        answer_started = perf_counter()
        answer = self.rag.answer(question, owner_id=user_id, retrieval_query=retrieval_query)
        logger.info(
            "Agent workflow completed tool=knowledge_search tool_status=completed steps=2 tool_calls=1 "
            "retrieved_chunks=%d tool_duration_seconds=%.6f answer_pipeline_duration_seconds=%.6f",
            len(results), tool_duration, perf_counter() - answer_started,
        )
        return AgentRun(answer, {
            "status": "completed", "steps": self.MAX_STEPS, "tool_calls": self.MAX_TOOL_CALLS,
            "tools": [{"name": "knowledge_search", "status": "completed", "result_count": len(results)}],
            "stop_reason": "evidence_available" if results else "no_relevant_evidence",
        })
