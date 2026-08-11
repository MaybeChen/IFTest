from browser_ai_test.validator.keyword import KeywordValidator
from browser_ai_test.validator.regex import RegexValidator


def test_keyword_all():
    assert KeywordValidator().validate("东京是日本首都", ["东京", "日本"]).passed


def test_keyword_fail():
    result = KeywordValidator().validate("东京", ["东京", "日本"])
    assert not result.passed and "日本" in result.reason


def test_keyword_any():
    assert KeywordValidator("any").validate("东京", ["大阪", "东京"]).passed


def test_regex_pass():
    assert RegexValidator().validate("答案是 2。", [r"(^|[^0-9])2([^0-9]|$)"]).passed


def test_regex_fail():
    assert not RegexValidator().validate("答案是 20", [r"(^|[^0-9])2([^0-9]|$)"]).passed
