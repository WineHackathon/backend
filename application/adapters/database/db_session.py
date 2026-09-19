"""
Модуль подключения к базе данных и управления пулом асинхронных сессий.
"""
import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine

from application.adapters.database.models import Base

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_database_url(
    user: str | None = None,
    password: str | None = None,
    host: str | None = None,
    port: int | str | None = None,
    name: str | None = None,
) -> str:
    """Формирование URL подключения к PostgreSQL с драйвером asyncpg."""
    db_user = user or os.getenv("POSTGRES_USER", "wine_admin")
    db_pass = password or os.getenv("POSTGRES_PASSWORD", "change_this_in_production")
    db_host = host or os.getenv("POSTGRES_HOST", "localhost")
    db_port = port or os.getenv("POSTGRES_PORT", "5432")
    db_name = name or os.getenv("POSTGRES_DB", "wine_db")
    return f"postgresql+asyncpg://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"


async def global_init_db(database_url: str | None = None) -> None:
    """Глобальная инициализация асинхронного движка SQLAlchemy и фабрики сессий."""
    global _engine, _sessionmaker

    url = database_url or get_database_url()
    _engine = create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        pool_size=15,
        max_overflow=10,
    )
    _sessionmaker = async_sessionmaker(
        bind=_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    # Создание всех зарегистрированных таблиц базы данных при инициализации
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def create_session() -> AsyncSession:
    """Создание отдельного экземпляра сессии."""
    global _sessionmaker
    if _sessionmaker is None:
        # Автоматическая ленивая инициализация при отсутствии вызова global_init_db
        url = get_database_url()
        _engine = create_async_engine(url, pool_pre_ping=True)
        _sessionmaker = async_sessionmaker(bind=_engine, expire_on_commit=False)
    return _sessionmaker()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Dependency для внедрения сессии базы данных в эндпоинты."""
    async with create_session() as session:
        yield session


async def close_db() -> None:
    """Корректное закрытие пула соединений при остановке сервиса."""
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
