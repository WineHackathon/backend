"""
Сущность гастрономических пар для вина.
"""
import uuid
from typing import TYPE_CHECKING
from sqlalchemy import String, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDMixin, TimestampMixin, GUID

if TYPE_CHECKING:
    from .wine import Wine


class WineFoodPairing(Base, UUIDMixin, TimestampMixin):
    """
    Гастрономическое сочетание вина с блюдами и продуктами.
    """
    __tablename__ = "wine_food_pairings"

    wine_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("wines.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="Идентификатор связанного вина",
    )
    food_category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Категория блюда (Мясо, Рыба, Сыры, Десерты и др.)",
    )
    dish_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Наименование рекомендуемого блюда или продукта",
    )
    recommendation_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Обоснование эногастрономической гармонии",
    )

    wine: Mapped["Wine"] = relationship("Wine", back_populates="pairings")

    __table_args__ = (
        Index("idx_pairing_wine_category", "wine_id", "food_category"),
    )
