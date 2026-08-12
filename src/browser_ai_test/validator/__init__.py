"""Answer validation strategies."""

from browser_ai_test.validator.base import BaseValidator
from browser_ai_test.validator.keyword import KeywordValidator
from browser_ai_test.validator.regex import RegexValidator


def get_validator(kind: str, match_mode: str = "all") -> BaseValidator:
    if kind == "keyword":
        return KeywordValidator(match_mode)
    if kind == "regex":
        return RegexValidator()
    raise ValueError(f"尚未实现的验证类型: {kind}")

__all__ = ["BaseValidator", "KeywordValidator", "RegexValidator", "get_validator"]
