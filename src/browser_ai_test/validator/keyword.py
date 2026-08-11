from browser_ai_test.models import ValidationResult
from browser_ai_test.validator.base import BaseValidator


class KeywordValidator(BaseValidator):
    def __init__(self, match_mode: str = "all") -> None:
        if match_mode not in {"all", "any"}:
            raise ValueError("match_mode must be all or any")
        self.match_mode = match_mode

    def validate(self, actual: str, expected: list[str]) -> ValidationResult:
        hits = [item in actual for item in expected]
        passed = all(hits) if self.match_mode == "all" else any(hits)
        missing = [item for item, hit in zip(expected, hits, strict=True) if not hit]
        reason = "关键词验证通过" if passed else f"缺少关键词: {', '.join(missing)}"
        return ValidationResult(passed=passed, reason=reason)
