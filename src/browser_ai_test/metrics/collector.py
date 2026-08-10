from browser_ai_test.metrics.statistics import calculate_statistics
from browser_ai_test.models import CaseResult


class MetricsCollector:
    def __init__(self) -> None:
        self.results: list[CaseResult] = []

    def add(self, result: CaseResult) -> None:
        self.results.append(result)

    def statistics(self) -> dict[str, object]:
        return calculate_statistics(self.results)
