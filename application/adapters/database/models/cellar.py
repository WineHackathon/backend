"""
Сущность позиции в личном погребе пользователя.
"""
import uuid
from typing import TYPE_CHECKING
from sqlalchemy import String, Text, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDMixin, TimestampMixin, GUID

if TYPE_CHECKING:
    from .user import User
    from .wine import Wine


class UserCellar(Base, UUIDMixin, TimestampMixin):
    """
    Запись в личном винном погребе или списке желаний (wishlist) пользователя.
    """
    __tablename__ = "user_cellar"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="Идентификатор пользователя",
    )
    wine_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("wines.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="Идентификатор вина в каталоге",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="in_cellar",
        nullable=False,
        comment="Статус позиции: in_cellar (в погребе), wishlist (желаемое), tasted (дегустировано)",
    )
    bottles_count: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        comment="Количество бутылок в наличии",
    )
    personal_rating: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Персональная оценка от 1 до 5 звезд",
    )
    tasting_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Личные дегустационные заметки и впечатления",
    )

    # Связи
    user: Mapped["User"] = relationship("User", back_populates="cellar_items")
    wine: Mapped["Wine"] = relationship("Wine", back_populates="cellar_entries")

    __table_args__ = (
        UniqueConstraint("user_id", "wine_id", "status", name="uq_user_wine_status"),
    )
