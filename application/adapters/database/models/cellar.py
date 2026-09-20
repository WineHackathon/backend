import enum
import uuid
from typing import TYPE_CHECKING
from sqlalchemy import String, Text, Integer, ForeignKey, UniqueConstraint, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDMixin, TimestampMixin, GUID

if TYPE_CHECKING:
    from .user import User
    from .wine import Wine


from application.entities.user_modes import CellarStatus


class UserCellar(Base, UUIDMixin, TimestampMixin):
    """
    Запись в личном винном погребе или списке желаний (wishlist) пользователя.
    """
    __tablename__ = "user_cellar"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
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
    status: Mapped[CellarStatus] = mapped_column(
        SQLEnum(CellarStatus, native_enum=False, length=50, values_callable=lambda x: [e.value for e in x]),
        default=CellarStatus.IN_CELLAR,
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
