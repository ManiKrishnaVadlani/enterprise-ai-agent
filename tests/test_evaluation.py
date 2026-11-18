"""Regression tests for the standalone local RAG evaluation framework."""

import builtins
import json

import pytest

from app.errors import ProviderError
from evaluation.metrics import (
    aggregate_retrieval_metrics,
    calculate_retrieval_metrics,
)
from evaluation.run import main as evaluation_cli
from evaluation.runner import DEFAULT_DATASET, load_dataset, run_evaluation


def test_controlled_dataset_schema_and_categories_are_valid():
    dataset = load_dataset()

    assert dataset.schema_version == 1
    assert len(dataset.documents) == 4
    assert {case.category for case in dataset.cases} == {
        "answerable", "multi_evidence", "unanswerable", "distractor"
    }
    multi = next(case for case in dataset.cases if case.category == "multi_evidence")
    assert len(multi.retrieval_targets) == 2


def test_dataset_rejects_missing_evidence_labels_and_unknown_sources(tmp_path):
    raw = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))
    raw["cases"][0]["retrieval_targets"][0]["filename"] = "missing.txt"
    dataset_path = tmp_path / "bad-label.json"
    dataset_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="missing or invalid evidence label"):
        load_dataset(dataset_path)


def test_dataset_rejects_facts_not_present_in_expected_source(tmp_path):
    raw = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))
    raw["cases"][0]["expected_facts"] = ["fabricated approval phrase"]
    dataset_path = tmp_path / "bad-fact.json"
    dataset_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="fact absent from its expected sources"):
        load_dataset(dataset_path)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data.update(schema_version=True), "schema_version 1"),
        (lambda data: data["documents"][0].update(filename="../private.txt"), "plain supported filenames"),
    ],
)
def test_dataset_rejects_invalid_version_and_document_names(tmp_path, mutation, message):
    raw = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))
    mutation(raw)
    dataset_path = tmp_path / "invalid-dataset.json"
    dataset_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_dataset(dataset_path)


@pytest.mark.parametrize(
    ("relevant", "expected", "matched", "rank", "k", "precision", "recall", "mrr"),
    [
        (2, 3, 2, 1, 4, 0.5, 2 / 3, 1.0),
        (1, 2, 1, 2, 4, 0.25, 0.5, 0.5),
        (0, 2, 0, None, 4, 0.0, 0.0, 0.0),
    ],
)
def test_retrieval_metric_calculations(
    relevant, expected, matched, rank, k, precision, recall, mrr
):
    metrics = calculate_retrieval_metrics(
        relevant_results=relevant,
        expected_evidence=expected,
        matched_evidence=matched,
        first_relevant_rank=rank,
        k=k,
    )

    assert metrics["precision_at_k"] == pytest.approx(precision)
    assert metrics["recall_at_k"] == pytest.approx(recall)
    assert metrics["hit_rate_at_k"] == float(relevant > 0)
    assert metrics["reciprocal_rank"] == pytest.approx(mrr)


def test_retrieval_metrics_mark_unlabeled_cases_not_applicable():
    metrics = calculate_retrieval_metrics(
        relevant_results=0,
        expected_evidence=0,
        matched_evidence=0,
        first_relevant_rank=None,
        k=4,
    )

    assert metrics["applicable"] is False
    assert metrics["recall_at_k"] is None
    assert aggregate_retrieval_metrics([metrics])["cases"] == 0


def test_aggregate_retrieval_metrics_macro_averages_labeled_cases():
    first = calculate_retrieval_metrics(
        relevant_results=2, expected_evidence=2, matched_evidence=1,
        first_relevant_rank=1, k=4,
    )
    second = calculate_retrieval_metrics(
        relevant_results=1, expected_evidence=2, matched_evidence=2,
        first_relevant_rank=2, k=4,
    )

    aggregate = aggregate_retrieval_metrics([first, second])

    assert aggregate["cases"] == 2
    assert aggregate["precision_at_k"] == pytest.approx(0.375)
    assert aggregate["recall_at_k"] == pytest.approx(0.75)
    assert aggregate["hit_rate_at_k"] == 1.0
    assert aggregate["reciprocal_rank"] == pytest.approx(0.75)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"k": 0},
        {"expected_evidence": -1},
        {"relevant_results": 5},
        {"matched_evidence": 3},
        {"first_relevant_rank": 5},
        {"relevant_results": 1, "first_relevant_rank": None},
    ],
)
def test_retrieval_metrics_reject_invalid_counts(kwargs):
    values = {
        "relevant_results": 1,
        "expected_evidence": 2,
        "matched_evidence": 1,
        "first_relevant_rank": 1,
        "k": 4,
    }
    values.update(kwargs)
    with pytest.raises(ValueError):
        calculate_retrieval_metrics(**values)


def test_default_evaluation_covers_answers_abstentions_citations_and_sources():
    report = run_evaluation()

    assert report["provider"] == "extractive"
    assert report["summary"] == {
        "total_cases": 5,
        "passed": 5,
        "failed": 0,
        "not_applicable": 0,
    }
    assert report["retrieval_metrics"]["cases"] == 4
    assert report["retrieval_metrics"]["recall_at_k"] == 1.0
    assert report["answer_metrics"]["answerable_fact_rate"] == 1.0
    assert report["answer_metrics"]["correct_abstention_rate"] == 1.0
    assert report["answer_metrics"]["citation_validity_rate"] == 1.0
    assert report["answer_metrics"]["expected_source_coverage"] == 1.0
    assert report["configuration"]["openai_api_calls"] is False


def test_retrieval_and_answer_modes_can_run_independently():
    retrieval = run_evaluation(mode="retrieval")
    answers = run_evaluation(mode="answers")

    assert retrieval["retrieval_metrics"] is not None
    assert retrieval["answer_metrics"] is None
    assert answers["retrieval_metrics"] is None
    assert answers["answer_metrics"]["cases"] == 5


def test_optional_ollama_selection_does_not_connect_in_retrieval_only_mode():
    report = run_evaluation(provider="ollama", mode="retrieval")

    assert report["provider"] == "ollama"
    assert report["configuration"]["openai_api_calls"] is False
    assert report["answer_metrics"] is None
    assert report["summary"]["failed"] == 0


def test_provider_failures_are_reported_without_error_text(monkeypatch):
    import evaluation.runner as runner

    class BrokenProvider:
        def generate_answer(self, _question, _context):
            raise ProviderError("private provider response")

    monkeypatch.setattr(
        runner, "_build_answer_provider", lambda *_args: BrokenProvider()
    )
    report = run_evaluation(mode="answers")
    serialized = json.dumps(report)

    assert report["summary"]["failed"] == 4
    assert sum("provider_error" in case["failures"] for case in report["cases"]) == 4
    assert "private provider response" not in serialized
    assert report["answer_metrics"]["correct_abstention_rate"] == 0.5


def test_category_filter_and_unknown_category():
    report = run_evaluation(categories={"unanswerable", "distractor"})

    assert report["summary"]["total_cases"] == 2
    with pytest.raises(ValueError, match="Unknown evaluation categories"):
        run_evaluation(categories={"not-a-category"})


def test_cli_writes_content_free_json_report(tmp_path, capsys):
    output = tmp_path / "report.json"

    exit_code = evaluation_cli(
        ["--mode", "retrieval", "--json-output", str(output)]
    )

    assert exit_code == 0
    report_text = output.read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert report["summary"]["failed"] == 0
    assert "Access reviews happen quarterly" not in report_text
    assert "Security owners record access reviews" not in report_text
    assert '"answer_text"' not in report_text
    assert "JSON report saved" in capsys.readouterr().out


def test_openai_is_not_an_evaluation_provider():
    with pytest.raises(ValueError, match="OpenAI is excluded"):
        run_evaluation(provider="openai")


def test_default_evaluation_does_not_import_openai(monkeypatch):
    original_import = builtins.__import__

    def reject_openai(name, *args, **kwargs):
        if name == "openai" or name.startswith("openai."):
            raise AssertionError("The evaluation must never import OpenAI.")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_openai)
    report = run_evaluation()

    assert report["configuration"]["openai_api_calls"] is False
    assert report["summary"]["failed"] == 0
