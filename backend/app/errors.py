"""Domain errors raised by the service layer."""


class DomainError(Exception):
    def __init__(self, message: str, code: str = "domain") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class NotFoundError(DomainError):
    def __init__(self, message: str = "Не найдено") -> None:
        super().__init__(message, "not_found")


class DuplicateEmployeeError(DomainError):
    def __init__(self, matches: list[dict]) -> None:
        super().__init__("Найдены дубликаты сотрудника", "duplicate")
        self.matches = matches


class LlmPrivacyError(DomainError):
    def __init__(self, field: str) -> None:
        super().__init__(f"Поле нельзя отправлять в модель: {field}", "llm_privacy")
        self.field = field
