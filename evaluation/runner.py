"""Run the fictional RAG evaluation corpus against isolated local storage."""

from dataclasses import dataclass
import json
from pathlib import Path
import tempfile
from typing import Any

from app.config import Settings
from app.document_service import DocumentService
from app.embeddings import LocalEmbeddingProvider
from app.errors import InvalidDocumentError, ProviderError
from app.llm import (
    NO_INFORMATION_ANSWER,
    ExtractiveAnswerProvider,
    OllamaLanguageModel,
)
from app.rag import NO_DOCUMENTS_ANSWER, RAGPipeline
from app.text_extraction import validate_filename
from app.vector_store import SQLiteVectorStore
from evaluation.metrics import aggregate_retrieval_metrics, calculate_retrieval_metrics


DEFAULT_DATASET = Path(__file__).with_name("dataset.json")
CASE_CATEGORIES = {"answerable", "multi_evidence", "unanswerable", "distractor"}
PROVIDERS = {"extractive", "ollama"}
MODES = {"all", "retrieval", "answers"}


@dataclass(frozen=True)
class DocumentSpec:
    filename: str
    text: str


@dataclass(frozen=True)
class RetrievalTarget:
    filename: str
    text_contains: str


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    question: str
    category: str
    answerable: bool
    expected_behavior: str
    expected_facts: tuple[str, ...]
    retrieval_targets: tuple[RetrievalTarget, ...]
    expected_source_files: tuple[str, ...]


@dataclass(frozen=True)
class EvaluationDataset:
    schema_version: int
    documents: tuple[DocumentSpec, ...]
    cases: tuple[EvaluationCase, ...]


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def load_dataset(path: str | Path = DEFAULT_DATASET) -> EvaluationDataset:
    """Load and validate dataset structure and every evidence label."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Could not read the evaluation dataset.") from error
    if (
        not isinstance(raw, dict)
        or type(raw.get("schema_version")) is not int
        or raw["schema_version"] != 1
    ):
        raise ValueError("The evaluation dataset must use schema_version 1.")
    if not isinstance(raw.get("documents"), list) or not raw["documents"]:
        raise ValueError("The evaluation dataset must contain documents.")
    if not isinstance(raw.get("cases"), list) or not raw["cases"]:
        raise ValueError("The evaluation dataset must contain cases.")

    documents: list[DocumentSpec] = []
    filenames: set[str] = set()
    for index, item in enumerate(raw["documents"]):
        if not isinstance(item, dict):
            raise ValueError(f"documents[{index}] must be an object")
        filename = _require_string(item.get("filename"), "filename")
        try:
            validate_filename(filename)
        except InvalidDocumentError as error:
            raise ValueError("Evaluation documents need plain supported filenames.") from error
        if not filename.lower().endswith(".txt"):
            raise ValueError("Evaluation documents must be fictional UTF-8 TXT files.")
        document = DocumentSpec(
            filename=filename,
            text=_require_string(item.get("text"), "document text"),
        )
        if document.filename in filenames:
            raise ValueError("Evaluation document filenames must be unique.")
        documents.append(document)
        filenames.add(document.filename)

    docs_by_name = {document.filename: document for document in documents}
    cases: list[EvaluationCase] = []
    case_ids: set[str] = set()
    for index, item in enumerate(raw["cases"]):
        if not isinstance(item, dict):
            raise ValueError(f"cases[{index}] must be an object")
        case_id = _require_string(item.get("case_id"), "case_id")
        if case_id in case_ids:
            raise ValueError("Evaluation case IDs must be unique.")
        case_ids.add(case_id)
        category = _require_string(item.get("category"), "category")
        if category not in CASE_CATEGORIES:
            raise ValueError(f"Unsupported evaluation category: {category}")
        answerable = item.get("answerable")
        if not isinstance(answerable, bool):
            raise ValueError(f"Case {case_id} answerable must be a boolean")
        behavior = _require_string(item.get("expected_behavior"), "expected_behavior")
        if behavior not in {"answer", "abstain"}:
            raise ValueError(f"Case {case_id} has an unsupported expected behavior")
        if answerable != (behavior == "answer"):
            raise ValueError(f"Case {case_id} answerability conflicts with expected behavior")
        if (category in {"unanswerable", "distractor"}) == answerable:
            raise ValueError(f"Case {case_id} category conflicts with answerability")

        facts_value = item.get("expected_facts")
        targets_value = item.get("retrieval_targets")
        sources_value = item.get("expected_source_files")
        if not isinstance(facts_value, list) or not isinstance(targets_value, list):
            raise ValueError(f"Case {case_id} facts and retrieval targets must be lists")
        if not isinstance(sources_value, list):
            raise ValueError(f"Case {case_id} expected_source_files must be a list")
        facts = tuple(_require_string(value, "expected fact") for value in facts_value)
        if answerable and (not facts or not targets_value or not sources_value):
            raise ValueError(f"Answerable case {case_id} needs facts, targets, and sources")
        if not answerable and facts:
            raise ValueError(f"Abstention case {case_id} cannot list expected answer facts")

        targets: list[RetrievalTarget] = []
        for target_value in targets_value:
            if not isinstance(target_value, dict):
                raise ValueError(f"Case {case_id} retrieval targets must be objects")
            filename = _require_string(target_value.get("filename"), "target filename")
            marker = _require_string(target_value.get("text_contains"), "target evidence")
            document = docs_by_name.get(filename)
            if document is None or marker.casefold() not in document.text.casefold():
                raise ValueError(f"Case {case_id} has a missing or invalid evidence label")
            targets.append(RetrievalTarget(filename, marker))
        if len({(target.filename, target.text_contains) for target in targets}) != len(targets):
            raise ValueError(f"Case {case_id} contains duplicate retrieval targets")
        if category == "multi_evidence" and len(targets) < 2:
            raise ValueError(f"Multi-evidence case {case_id} needs at least two targets")
        if category == "unanswerable" and targets:
            raise ValueError(f"Unanswerable case {case_id} cannot have retrieval targets")
        if category == "distractor" and not targets:
            raise ValueError(f"Distractor case {case_id} needs a related retrieval target")

        source_files = tuple(
            _require_string(value, "expected source filename") for value in sources_value
        )
        if len(set(source_files)) != len(source_files) or any(
            filename not in docs_by_name for filename in source_files
        ):
            raise ValueError(f"Case {case_id} has invalid expected source files")
        if not answerable and source_files:
            raise ValueError(f"Abstention case {case_id} cannot expect answer sources")
        if answerable and any(
            not any(
                fact.casefold() in docs_by_name[filename].text.casefold()
                for filename in source_files
            )
            for fact in facts
        ):
            raise ValueError(f"Case {case_id} has a fact absent from its expected sources")
        if answerable and not set(source_files).issubset(
            {target.filename for target in targets}
        ):
            raise ValueError(f"Case {case_id} expects a source without a retrieval target")
        cases.append(
            EvaluationCase(
                case_id=case_id,
                question=_require_string(item.get("question"), "question"),
                category=category,
                answerable=answerable,
                expected_behavior=behavior,
                expected_facts=facts,
                retrieval_targets=tuple(targets),
                expected_source_files=source_files,
            )
        )
    return EvaluationDataset(1, tuple(documents), tuple(cases))


def _build_answer_provider(provider: str, settings: Settings):
    if provider == "extractive":
        return ExtractiveAnswerProvider()
    if provider == "ollama":
        return OllamaLanguageModel(
            settings.ollama_base_url,
            settings.ollama_model,
            timeout_seconds=settings.ollama_timeout_seconds,
            temperature=settings.ollama_temperature,
            think=settings.ollama_think,
            num_predict=settings.ollama_num_predict,
            context_length=settings.ollama_context_length,
            max_prompt_chars=settings.ollama_max_prompt_chars,
        )
    raise ValueError("Evaluation provider must be extractive or ollama.")


def run_evaluation(
    *,
    dataset: EvaluationDataset | None = None,
    dataset_path: str | Path = DEFAULT_DATASET,
    provider: str = "extractive",
    mode: str = "all",
    categories: set[str] | None = None,
) -> dict[str, Any]:
    """Evaluate local providers in a temporary database and return safe metrics."""
    if provider not in PROVIDERS:
        raise ValueError("OpenAI is excluded; provider must be extractive or ollama.")
    if mode not in MODES:
        raise ValueError("mode must be all, retrieval, or answers")
    selected_dataset = dataset or load_dataset(dataset_path)
    if categories:
        unknown = categories - CASE_CATEGORIES
        if unknown:
            raise ValueError(f"Unknown evaluation categories: {', '.join(sorted(unknown))}")
        cases = tuple(case for case in selected_dataset.cases if case.category in categories)
    else:
        cases = selected_dataset.cases
    if not cases:
        raise ValueError("No evaluation cases match the selected categories.")

    retrieval_enabled = mode in {"all", "retrieval"}
    answers_enabled = mode in {"all", "answers"}
    embeddings = LocalEmbeddingProvider()
    case_reports: list[dict[str, Any]] = []
    per_case_retrieval: list[dict[str, float | int | None]] = []
    answer_case_passes = answer_case_count = 0
    answerable_case_passes = answerable_case_count = 0
    fact_hits = fact_count = 0
    expected_source_hits = expected_source_count = 0
    citation_valid_count = abstention_count = abstention_case_count = 0

    with tempfile.TemporaryDirectory(prefix="enterprise-rag-eval-") as temp_directory:
        settings = Settings(
            ai_mode="local",
            llm_provider="extractive" if provider == "extractive" else "ollama",
            database_path=Path(temp_directory) / "evaluation.sqlite3",
        )
        store = SQLiteVectorStore(
            settings.database_path, embedding_model=embeddings.model_id
        )
        user = store.create_user("Temporary evaluation user")
        document_service = DocumentService(
            store=store,
            embeddings=embeddings,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            max_upload_bytes=settings.max_upload_bytes,
            max_pdf_pages=settings.max_pdf_pages,
            max_extracted_text_chars=settings.max_extracted_text_chars,
            max_document_chunks=settings.max_document_chunks,
        )
        filename_to_document_id: dict[str, str] = {}
        for document in selected_dataset.documents:
            summary = document_service.ingest(
                document.filename,
                document.text.encode("utf-8"),
                owner_id=user.user_id,
            )
            filename_to_document_id[document.filename] = summary.document_id
        pipeline = RAGPipeline(
            store=store,
            embeddings=embeddings,
            language_model=_build_answer_provider(provider, settings),
            top_k=settings.top_k,
            min_relevance_score=settings.relevance_threshold_for("local"),
        )

        for case in cases:
            vector = embeddings.embed([case.question])[0]
            retrieved = store.search(
                vector,
                settings.top_k,
                owner_id=user.user_id,
                min_score=settings.relevance_threshold_for("local"),
            )
            hits: set[int] = set()
            result_targets: list[list[int]] = []
            relevant_ranks: list[int] = []
            for rank, result in enumerate(retrieved, start=1):
                matched = [
                    target_index
                    for target_index, target in enumerate(case.retrieval_targets)
                    if result.chunk.filename == target.filename
                    and target.text_contains.casefold() in result.chunk.text.casefold()
                ]
                result_targets.append(matched)
                if matched:
                    relevant_ranks.append(rank)
                    hits.update(matched)
            retrieval_metrics = calculate_retrieval_metrics(
                relevant_results=len(relevant_ranks),
                expected_evidence=len(case.retrieval_targets),
                matched_evidence=len(hits),
                first_relevant_rank=relevant_ranks[0] if relevant_ranks else None,
                k=settings.top_k,
            )
            per_case_retrieval.append(retrieval_metrics)

            failures: list[str] = []
            answer_report = None
            answer_pass: bool | None = None
            if answers_enabled:
                if case.answerable:
                    answerable_case_count += 1
                    fact_count += len(case.expected_facts)
                    expected_source_count += len(case.expected_source_files)
                else:
                    abstention_case_count += 1
                try:
                    answer = pipeline.answer(case.question, owner_id=user.user_id)
                    citation_map = {
                        result.chunk.chunk_id: result.chunk for result in retrieved
                    }
                    citations_valid = all(
                        source.chunk_id in citation_map
                        and source.document_id == citation_map[source.chunk_id].document_id
                        and source.filename == citation_map[source.chunk_id].filename
                        and source.filename in filename_to_document_id
                        and source.document_id == filename_to_document_id[source.filename]
                        for source in answer.sources
                    )
                    cited_files = {source.filename for source in answer.sources}
                    is_abstention = answer.answer in {
                        NO_INFORMATION_ANSWER,
                        NO_DOCUMENTS_ANSWER,
                    }
                    matched_facts = [
                        fact for fact in case.expected_facts
                        if fact.casefold() in answer.answer.casefold()
                    ]
                    source_hits = set(case.expected_source_files) & cited_files
                    fact_hits += len(matched_facts)
                    expected_source_hits += len(source_hits)
                    citation_valid_count += int(citations_valid)
                    if case.expected_behavior == "answer":
                        answer_pass = (
                            not is_abstention
                            and len(matched_facts) == len(case.expected_facts)
                            and citations_valid
                            and set(case.expected_source_files).issubset(cited_files)
                        )
                        if is_abstention:
                            failures.append("unexpected_abstention")
                        if len(matched_facts) < len(case.expected_facts):
                            failures.append("expected_fact_missing")
                        if not citations_valid:
                            failures.append("citation_invalid")
                        if not set(case.expected_source_files).issubset(cited_files):
                            failures.append("expected_source_missing")
                    else:
                        abstained = is_abstention and not answer.sources
                        abstention_count += int(abstained)
                        answer_pass = abstained and citations_valid
                        if not is_abstention:
                            failures.append("expected_abstention")
                        if answer.sources:
                            failures.append("unexpected_citation")
                        if not citations_valid:
                            failures.append("citation_invalid")
                    if case.answerable:
                        answerable_case_passes += int(bool(answer_pass))
                    answer_report = {
                        "expected_behavior": case.expected_behavior,
                        "facts_matched": len(matched_facts),
                        "facts_expected": len(case.expected_facts),
                        "citation_valid": citations_valid,
                        "expected_sources_covered": len(source_hits),
                        "expected_sources": len(case.expected_source_files),
                        "abstained": is_abstention,
                    }
                except ProviderError:
                    answer_pass = False
                    failures.append("provider_error")

            if answers_enabled:
                answer_case_count += 1
                answer_case_passes += int(bool(answer_pass))
            retrieval_pass: bool | None = None
            if retrieval_enabled and case.retrieval_targets:
                retrieval_pass = len(hits) == len(case.retrieval_targets)
                if not retrieval_pass:
                    failures.append("retrieval_target_missing")
            applicable_checks = [
                check for check in (retrieval_pass, answer_pass) if check is not None
            ]
            if not applicable_checks:
                case_status = "not_applicable"
            elif all(applicable_checks):
                case_status = "passed"
            else:
                case_status = "failed"

            retrieval_report = None
            if retrieval_enabled:
                retrieval_report = {
                    **retrieval_metrics,
                    "targets_found": len(hits),
                    "retrieved": [
                        {
                            "rank": rank,
                            "filename": result.chunk.filename,
                            "score": round(result.score, 4),
                            "matched_target_indexes": result_targets[rank - 1],
                        }
                        for rank, result in enumerate(retrieved, start=1)
                    ],
                }
            case_reports.append(
                {
                    "case_id": case.case_id,
                    "category": case.category,
                    "status": case_status,
                    "failures": failures,
                    "retrieval": retrieval_report,
                    "answer": answer_report,
                }
            )

    summary = {
        "total_cases": len(case_reports),
        "passed": sum(case["status"] == "passed" for case in case_reports),
        "failed": sum(case["status"] == "failed" for case in case_reports),
        "not_applicable": sum(
            case["status"] == "not_applicable" for case in case_reports
        ),
    }
    answer_metrics = None
    if answers_enabled:
        answer_metrics = {
            "cases": answer_case_count,
            "passed_cases": answer_case_passes,
            "answerable_cases": answerable_case_count,
            "answerable_case_pass_rate": (
                answerable_case_passes / answerable_case_count
                if answerable_case_count else None
            ),
            "answerable_fact_rate": fact_hits / fact_count if fact_count else None,
            "correct_abstention_rate": (
                abstention_count / abstention_case_count
                if abstention_case_count else None
            ),
            "citation_validity_rate": (
                citation_valid_count / answer_case_count if answer_case_count else None
            ),
            "expected_source_coverage": (
                expected_source_hits / expected_source_count
                if expected_source_count else None
            ),
        }
    return {
        "dataset_schema_version": selected_dataset.schema_version,
        "provider": provider,
        "mode": mode,
        "configuration": {
            "embedding_provider": "local-feature-hash",
            "embedding_model": embeddings.model_id,
            "answer_model": settings.ollama_model if provider == "ollama" else "extractive",
            "top_k": settings.top_k,
            "minimum_relevance_score": settings.relevance_threshold_for("local"),
            "chunk_size": settings.chunk_size,
            "chunk_overlap": settings.chunk_overlap,
            "maximum_document_chunks": settings.max_document_chunks,
            "ollama_requests": provider == "ollama" and answers_enabled,
            "openai_api_calls": False,
            "model_downloads": False,
        },
        "summary": summary,
        "retrieval_metrics": (
            aggregate_retrieval_metrics(per_case_retrieval) if retrieval_enabled else None
        ),
        "answer_metrics": answer_metrics,
        "cases": case_reports,
    }
