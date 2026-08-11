import re

from browser_ai_test.models import ValidationResult
from browser_ai_test.validator.base import BaseValidator


class RegexValidator(BaseValidator):
    def validate(self, actual: str, expected: list[str]) -> ValidationResult:
        try:
            missing = [pattern for pattern in expected if re.search(pattern, actual) is None]
        except re.error as exc:
            return ValidationResult(passed=False, reason=f"非法正则表达式: {exc}")
        passed = not missing
        return ValidationResult(passed=passed, reason="正则验证通过" if passed else f"未匹配: {', '.join(missing)}")
