from __future__ import annotations

from collections import Counter
from statistics import fmean
from typing import Any, Iterable, Sequence

from browser_ai_test.models import CaseResult


def percentile(values: Sequence[float], percent: float) -> float | None:
    """Linear interpolation between closest ranks (NumPy's default method)."""
    if not values:
        return None
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * percent / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def calculate_statistics(results: Iterable[CaseResult]) -> dict[str, Any]:
    items = list(results)
    total = len(items)
    rate = lambda count: count / total * 100 if total else 0.0
    passed = sum(item.passed for item in items)
    ttft = [item.ttft_ms for item in items if item.ttft_ms is not None]
    stream = [item.stream_total_ms for item in items if item.stream_total_ms is not None]
    output: dict[str, Any] = {
        "total": total, "passed": passed, "failed": total - passed,
        "success_rate": rate(passed),
        "ui_success_rate": rate(sum(item.ui_ok for item in items)),
        "network_success_rate": rate(sum(item.network_ok for item in items)),
        "answer_success_rate": rate(sum(item.answer_ok for item in items)),
        "ttft_avg": fmean(ttft) if ttft else None,
        "stream_avg": fmean(stream) if stream else None,
        "errors": Counter(item.error_type.value for item in items if item.error_type),
    }
    for label, values in (("ttft", ttft), ("stream", stream)):
        for p in (50, 90, 95, 99):
            output[f"{label}_p{p}"] = percentile(values, p)
    return output
