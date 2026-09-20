import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import String, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDMixin, TimestampMixin, GUID

if TYPE_CHECKING:
    from .user import User


class UserSession(Base, UUIDMixin, TimestampMixin):
    """
    Модель активной сессии устройства пользователя.
    Используется для отслеживания подключенных устройств, ограничения их количества (FIFO)
    и удаленного завершения сессий.
    """
    __tablename__ = "user_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="ID пользователя-владельца сессии",
    )
    refresh_token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        comment="SHA-256 хэш текущего refresh токена сессии",
    )
    device_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        default="Неизвестное устройство",
        comment="Понятное название устройства/браузера (например, 'Chrome на macOS', 'iPhone 15')",
    )
    device_fingerprint: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="Клиентский фингерпринт устройства (если передан)",
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="IP-адрес клиента при последней активности",
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Сырой заголовок User-Agent",
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        comment="Время последней активности (обращения по refresh токену)",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Срок истечения сессии (соответствует exp refresh токена)",
    )

    # Связь с пользователем
    user: Mapped["User"] = relationship(
        "User",
        back_populates="sessions",
    )

    __table_args__ = (
        Index("ix_user_sessions_user_last_active", "user_id", "last_active_at"),
    )
