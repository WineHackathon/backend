import enum
import uuid
from typing import TYPE_CHECKING
from sqlalchemy import String, Text, ForeignKey, Index, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDMixin, TimestampMixin, GUID

if TYPE_CHECKING:
    from .wine import Wine


class FoodCategory(str, enum.Enum):
    """
    Категория гастрономического сочетания.
    """
    MEAT = "Мясо"
    FISH = "Рыба"
    SEAFOOD = "Морепродукты"
    POULTRY = "Птица"
    CHEESE = "Сыры"
    DESSERT = "Десерты"
    SNACKS = "Закуски"
    PASTA_PIZZA = "Паста и пицца"
    VEGETABLES = "Овощи"
    OTHER = "Другое"


class WineFoodPairing(Base, UUIDMixin, TimestampMixin):
    """
    Гастрономическое сочетание вина с блюдами и продуктами.
    """
    __tablename__ = "wine_food_pairings"

    wine_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("wines.id", ondelete="CASCADE"),
        nullable=False,
        comment="Идентификатор связанного вина",
    )
    food_category: Mapped[FoodCategory] = mapped_column(
        SQLEnum(FoodCategory, native_enum=False, length=100, values_callable=lambda x: [e.value for e in x]),
        default=FoodCategory.OTHER,
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
        Index("idx_pairing_category_wine", "food_category", "wine_id"),
    )
