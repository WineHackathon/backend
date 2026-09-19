"""
Типизированные доменные исключения бизнес-логики приложения.
"""


class DomainException(Exception):
    """Базовое исключение доменного слоя."""
    def __init__(self, message: str = "Ошибка бизнес-логики") -> None:
        self.message = message
        super().__init__(self.message)


class WineNotFound(DomainException):
    """Вино не найдено в каталоге."""
    def __init__(self, identifier: str) -> None:
        super().__init__(f"Вино с идентификатором '{identifier}' не найдено.")


class UserNotFound(DomainException):
    """Пользователь не найден."""
    def __init__(self, identifier: str) -> None:
        super().__init__(f"Пользователь '{identifier}' не найден.")


class UserAlreadyExists(DomainException):
    """Пользователь с таким email уже существует."""
    def __init__(self, email: str) -> None:
        super().__init__(f"Пользователь с email '{email}' уже зарегистрирован.")


class AuthenticationError(DomainException):
    """Ошибка аутентификации (неверный пароль или токен)."""
    def __init__(self, message: str = "Неверные учетные данные.") -> None:
        super().__init__(message)


class ScanQuotaExceeded(DomainException):
    """Превышена квота бесплатных сканирований для неавторизованного пользователя."""
    def __init__(self, limit: int = 5) -> None:
        super().__init__(
            f"Вы исчерпали лимит из {limit} бесплатных сканирований. "
            "Пожалуйста, войдите или зарегистрируйтесь, чтобы продолжить!"
        )


class CellarItemNotFound(DomainException):
    """Позиция в винном погребе не найдена."""
    def __init__(self) -> None:
        super().__init__("Позиция в погребе не найдена или не принадлежит текущему пользователю.")
