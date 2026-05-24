from __future__ import annotations

from statistics import mean, pvariance
from typing import Any


def round_metrics(round_id: int, scores: list[int], parse_ok_values: list[bool]) -> dict[str, Any]:
    failures = len([ok for ok in parse_ok_values if not ok])
    return {
        "round": round_id,
        "mean_score": mean(scores) if scores else 0.0,
        "variance_score": pvariance(scores) if len(scores) > 1 else 0.0,
        "min_score": min(scores) if scores else 0,
        "max_score": max(scores) if scores else 0,
        "parse_failure_rate": failures / len(parse_ok_values) if parse_ok_values else 0.0,
    }


def convergence_half_life(metrics: list[dict[str, Any]]) -> int | None:
    if not metrics:
        return None
    initial_variance = metrics[0]["variance_score"]
    if initial_variance <= 0:
        return None
    threshold = initial_variance * 0.5
    for row in metrics:
        if row["variance_score"] <= threshold:
            return int(row["round"])
    return None
