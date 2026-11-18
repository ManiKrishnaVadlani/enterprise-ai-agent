"""Command-line entry point for explicit local RAG evaluation runs."""

import argparse
import json
from pathlib import Path
import sys

from evaluation.runner import (
    CASE_CATEGORIES,
    DEFAULT_DATASET,
    MODES,
    PROVIDERS,
    run_evaluation,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate RAG retrieval and answer behavior on a fictional local dataset."
    )
    parser.add_argument(
        "--provider",
        choices=sorted(PROVIDERS),
        default="extractive",
        help="Answer provider; OpenAI is deliberately excluded.",
    )
    parser.add_argument(
        "--mode",
        choices=sorted(MODES),
        default="all",
        help="Run retrieval checks, answer checks, or both.",
    )
    parser.add_argument(
        "--category",
        choices=sorted(CASE_CATEGORIES),
        action="append",
        help="Limit to one or more categories; can be repeated.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="Path to a schema-version-1 JSON evaluation dataset.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Optional path for a content-free machine-readable report.",
    )
    return parser


def _print_report(report: dict) -> None:
    summary = report["summary"]
    configuration = report["configuration"]
    print(
        f"RAG evaluation: provider={report['provider']} mode={report['mode']} "
        f"cases={summary['total_cases']} passed={summary['passed']} "
        f"failed={summary['failed']} not_applicable={summary['not_applicable']}"
    )
    print(
        "Configuration: "
        f"embeddings={configuration['embedding_model']} "
        f"top_k={configuration['top_k']} "
        f"minimum_score={configuration['minimum_relevance_score']} "
        f"chunk_size={configuration['chunk_size']} "
        f"chunk_overlap={configuration['chunk_overlap']}"
    )
    if report["provider"] == "ollama":
        print(
            f"Ollama model={configuration['answer_model']} "
            f"inference_requests={configuration['ollama_requests']}"
        )
    retrieval = report["retrieval_metrics"]
    if retrieval is not None:
        print(
            "Retrieval (macro average, labeled cases only): "
            f"P@K={retrieval['precision_at_k']} "
            f"R@K={retrieval['recall_at_k']} "
            f"Hit@K={retrieval['hit_rate_at_k']} "
            f"MRR={retrieval['reciprocal_rank']} "
            f"cases={retrieval['cases']}"
        )
    answers = report["answer_metrics"]
    if answers is not None:
        print(
            "Answers: "
            f"fact_rate={answers['answerable_fact_rate']} "
            f"correct_abstention_rate={answers['correct_abstention_rate']} "
            f"citation_validity={answers['citation_validity_rate']} "
            f"expected_source_coverage={answers['expected_source_coverage']}"
        )
    failures = [case for case in report["cases"] if case["status"] == "failed"]
    if failures:
        print("Failing cases:")
        for case in failures:
            print(f"  {case['case_id']} ({case['category']}): {', '.join(case['failures'])}")
    print(
        "No retrieved text or generated answer content is included in this report. "
        "The OpenAI provider is unavailable to this command."
    )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        report = run_evaluation(
            dataset_path=args.dataset,
            provider=args.provider,
            mode=args.mode,
            categories=set(args.category) if args.category else None,
        )
    except ValueError as error:
        print(f"Evaluation could not start: {error}", file=sys.stderr)
        return 2

    _print_report(report)
    if args.json_output:
        try:
            args.json_output.write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError:
            print("Could not write the JSON report.", file=sys.stderr)
            return 2
        print(f"JSON report saved: {args.json_output}")
    return 1 if report["summary"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
