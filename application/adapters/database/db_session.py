"""
Модуль подключения к базе данных и управления пулом асинхронных сессий.
"""
from typing import AsyncGenerator
from pydantic_settings import BaseSettings
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
    AsyncEngine,
)

from application.adapters.database.models import Base


class DatabaseSettings(BaseSettings):
    """Настройки подключения к базе данных PostgreSQL."""
    postgres_user: str = "wine_admin"
    postgres_password: str = "change_this_in_production"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "wine_db"
    database_url: str | None = None

    model_config = {"env_file": ".env", "extra": "ignore"}

    def get_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


db_settings = DatabaseSettings()

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
    if any([user, password, host, port, name]):
        u = user or db_settings.postgres_user
        p = password or db_settings.postgres_password
        h = host or db_settings.postgres_host
        prt = port or db_settings.postgres_port
        n = name or db_settings.postgres_db
        return f"postgresql+asyncpg://{u}:{p}@{h}:{prt}/{n}"
    return db_settings.get_url()


def _setup_engine(url: str) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Единая фабрика инициализации движка и сессий (DRY, защита от расхождений)."""
    engine_kwargs = {
        "echo": False,
        "pool_pre_ping": True,
    }
    # Параметры пула QueuePool только для сетевых СУБД (PostgreSQL)
    if not url.startswith("sqlite"):
        engine_kwargs["pool_size"] = 15
        engine_kwargs["max_overflow"] = 10

    engine = create_async_engine(url, **engine_kwargs)
    session_factory = async_sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    return engine, session_factory


async def global_init_db(database_url: str | None = None) -> None:
    """Глобальная инициализация асинхронного движка SQLAlchemy и миграция схемы."""
    global _engine, _sessionmaker

    url = database_url or get_database_url()
    _engine, _sessionmaker = _setup_engine(url)

    # Создание всех зарегистрированных таблиц базы данных при инициализации
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def create_session() -> AsyncSession:
    """Создание отдельного экземпляра сессии (с ленивой инициализацией при необходимости)."""
    global _sessionmaker, _engine
    if _sessionmaker is None:
        url = get_database_url()
        _engine, _sessionmaker = _setup_engine(url)
    return _sessionmaker()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Dependency для внедрения сессии базы данных в эндпоинты."""
    async with create_session() as session:
        yield session


async def close_db() -> None:
    """Корректное закрытие пула соединений и сброс фабрики сессий."""
    global _engine, _sessionmaker
    if _engine:
        await _engine.dispose()
        _engine = None
    _sessionmaker = None
