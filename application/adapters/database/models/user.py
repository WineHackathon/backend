"""
Сущность пользователя платформы с поддержкой вкусового профиля (Taste Profile).
"""
import uuid
from typing import TYPE_CHECKING
from sqlalchemy import String, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from .cellar import UserCellar
    from .scan_history import UserScanHistory
    from .preference_history import UserPreferenceHistory


class User(Base, UUIDMixin, TimestampMixin):
    """
    Модель пользователя платформы.
    Поддерживает аутентификацию по паролю и через Яндекс ID OAuth.
    Хранит агрегированный вкусовой профиль пользователя (taste_profile).
    """
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
        comment="Email пользователя для входа и уведомлений",
    )
    password_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Хеш пароля Argon2id (null для пользователей через Яндекс OAuth)",
    )
    yandex_id: Mapped[str | None] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=True,
        comment="Уникальный идентификатор Яндекс ID",
    )
    first_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        default="Пользователь",
        comment="Имя пользователя",
    )
    last_name: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
        comment="Фамилия пользователя",
    )
    avatar_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Ссылка на аватар пользователя",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Флаг активности учетной записи",
    )
    is_admin: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Флаг роли администратора",
    )

    # =========================================================================
    # Вкусовой профиль пользователя (Taste Profile)
    # =========================================================================
    taste_profile: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        comment="Агрегированные вкусовые предпочтения пользователя (JSON)",
    )

    # Связи
    cellar_items: Mapped[list["UserCellar"]] = relationship(
        "UserCellar",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    scan_history: Mapped[list["UserScanHistory"]] = relationship(
        "UserScanHistory",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    preference_history: Mapped[list["UserPreferenceHistory"]] = relationship(
        "UserPreferenceHistory",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
