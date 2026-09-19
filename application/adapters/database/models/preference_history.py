"""
Сущность истории диалогов и сырых предпочтений пользователя с сомелье.
"""
import uuid
from typing import TYPE_CHECKING
from sqlalchemy import String, ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDMixin, TimestampMixin, GUID

if TYPE_CHECKING:
    from .user import User


class UserPreferenceHistory(Base, UUIDMixin, TimestampMixin):
    """
    Журнал сырых ответов пользователя на вопросы сомелье и выданных рекомендаций.
    Используется фоновым процессом для агрегации вкусового профиля (taste_profile).
    """
    __tablename__ = "user_preference_history"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
        comment="Идентификатор пользователя (nullable для сессий гостей)",
    )
    session_id: Mapped[str] = mapped_column(
        String(100),
        index=True,
        nullable=False,
        comment="Идентификатор сессии диалога с сомелье",
    )
    raw_answers: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        comment="Сырые ответы пользователя на вопросы онбординга (JSON)",
    )
    recommended_slugs: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
        comment="Список слагов рекомендованных вин",
    )

    user: Mapped["User"] = relationship("User", back_populates="preference_history")

    __table_args__ = (
        Index("idx_pref_user_created", "user_id", "created_at"),
        Index("idx_pref_session", "session_id"),
    )
