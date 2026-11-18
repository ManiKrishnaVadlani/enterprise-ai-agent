"""Transparent retrieval metrics used by the local evaluation runner."""


def calculate_retrieval_metrics(
    *,
    relevant_results: int,
    expected_evidence: int,
    matched_evidence: int,
    first_relevant_rank: int | None,
    k: int,
) -> dict[str, float | int | None]:
    """Calculate per-case Precision@K, Recall@K, Hit Rate@K, and reciprocal rank.

    Cases without labeled retrieval evidence return ``None`` metrics. They are not
    silently treated as successful retrieval cases.
    """
    if k < 1:
        raise ValueError("k must be positive")
    if expected_evidence < 0 or relevant_results < 0 or matched_evidence < 0:
        raise ValueError("retrieval counts cannot be negative")
    if relevant_results > k or matched_evidence > expected_evidence:
        raise ValueError("retrieval counts exceed their evaluated limits")
    if expected_evidence == 0 and relevant_results:
        raise ValueError("unlabeled retrieval cases cannot claim relevant results")
    if first_relevant_rank is not None and not 1 <= first_relevant_rank <= k:
        raise ValueError("first_relevant_rank must be between 1 and k")
    if (relevant_results == 0) != (first_relevant_rank is None):
        raise ValueError("relevant result count and first rank are inconsistent")

    if expected_evidence == 0:
        return {
            "applicable": False,
            "precision_at_k": None,
            "recall_at_k": None,
            "hit_rate_at_k": None,
            "reciprocal_rank": None,
            "matched_evidence": 0,
            "expected_evidence": 0,
        }
    return {
        "applicable": True,
        "precision_at_k": relevant_results / k,
        "recall_at_k": matched_evidence / expected_evidence,
        "hit_rate_at_k": float(relevant_results > 0),
        "reciprocal_rank": (
            1 / first_relevant_rank if first_relevant_rank is not None else 0.0
        ),
        "matched_evidence": matched_evidence,
        "expected_evidence": expected_evidence,
    }


def aggregate_retrieval_metrics(
    case_metrics: list[dict[str, float | int | None]],
) -> dict[str, float | int | None]:
    """Macro-average applicable per-case retrieval metrics."""
    applicable = [metric for metric in case_metrics if metric["applicable"]]
    names = ("precision_at_k", "recall_at_k", "hit_rate_at_k", "reciprocal_rank")
    result: dict[str, float | int | None] = {"cases": len(applicable)}
    for name in names:
        values = [float(metric[name]) for metric in applicable]
        result[name] = sum(values) / len(values) if values else None
    return result
