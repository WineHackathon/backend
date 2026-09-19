"""
Менеджер транзакций для атомарных операций с базой данных.
Обеспечивает корректное управление транзакцией через контекстный менеджер (async with).
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class TransactionManager:
    """
    Менеджер транзакций базы данных.
    
    Пример использования:
    ```python
    async with TransactionManager(session) as tm:
        await user_repo.save(user)
        await cellar_repo.save(item)
        # При возникновении ошибки автоматически произойдет rollback.
        # При успешном завершении блока автоматически выполнится commit.
    ```
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        """Явная фиксация текущей транзакции."""
        await self._session.commit()

    async def rollback(self) -> None:
        """Откат текущей транзакции."""
        await self._session.rollback()

    async def __aenter__(self) -> "TransactionManager":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type:
            logger.warning(f"Ошибка в транзакции: {exc_val}. Выполняется откат (rollback)...")
            await self.rollback()
            return  # Пробрасываем исключение дальше
        await self.commit()
