"""
Базовые классы и миксины для моделей SQLAlchemy 2.0.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import TypeDecorator, CHAR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class GUID(TypeDecorator):
    """
    Кроссплатформенный тип для UUID (PostgreSQL использует native UUID,
    SQLite использует строковое представление CHAR(36)).
    Автоматически нормализует строки в uuid.UUID для драйвера asyncpg.
    """
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            if isinstance(value, uuid.UUID):
                return value
            try:
                return uuid.UUID(str(value))
            except (ValueError, AttributeError, TypeError):
                return value
        else:
            if isinstance(value, uuid.UUID):
                return str(value)
            try:
                return str(uuid.UUID(str(value)))
            except (ValueError, AttributeError, TypeError):
                return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(str(value))
        except (ValueError, AttributeError, TypeError):
            return value


class Base(DeclarativeBase):
    """Базовый декларативный класс для всех таблиц приложения."""
    pass


class UUIDMixin:
    """Миксин для добавления первичного ключа UUIDv4."""
    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
        sort_order=-10,
        comment="Уникальный идентификатор сущности (UUIDv4)",
    )


class TimestampMixin:
    """Миксин для аудита времени создания и обновления записей (UTC)."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        sort_order=100,
        comment="Метка времени создания записи (UTC)",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        server_onupdate=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        sort_order=101,
        comment="Метка времени последнего обновления записи (UTC)",
    )
