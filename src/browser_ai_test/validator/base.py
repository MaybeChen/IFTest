from abc import ABC, abstractmethod

from browser_ai_test.models import ValidationResult


class BaseValidator(ABC):
    @abstractmethod
    def validate(self, actual: str, expected: list[str]) -> ValidationResult:
        raise NotImplementedError
