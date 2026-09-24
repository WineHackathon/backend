"""
Сущность вина каталога «Своё Вино» с поддержкой Вкусовой матрицы (Taste Matrix).
"""
import uuid
from typing import TYPE_CHECKING
from sqlalchemy import String, Text, Float, Integer, Index, JSON, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from application.entities.wine_categories import WineCategory, SugarType
from .base import Base, UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from .pairing import WineFoodPairing
    from .cellar import UserCellar


class Wine(Base, UUIDMixin, TimestampMixin):
    """
    Модель вина каталога «Своё Вино».
    Включает базовые метаданные, оценку Роскачества и Вкусовую матрицу (Taste Matrix).
    """
    __tablename__ = "wines"

    slug: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        comment="Уникальный слаг вина для чекера и ссылок",
    )
    name: Mapped[str] = mapped_column(
        String(500),
        index=True,
        nullable=False,
        comment="Коммерческое наименование вина",
    )
    category: Mapped[WineCategory] = mapped_column(
        SQLEnum(WineCategory, native_enum=False, length=100, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=WineCategory.STILL,
        comment="Категория вина (Белое, Красное, Розовое, Игристое, Тихое)",
    )
    color_desc: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Органолептическое описание визуального цвета",
    )
    region: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Винодельческий регион (Крым, Кубань, Долина Дона и др.)",
    )
    grape_varieties: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=list,
        nullable=False,
        comment="Список сортов винограда (JSONB)",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Дегустационные заметки и описание сомелье",
    )
    winery: Mapped[str | None] = mapped_column(
        String(255),
        index=True,
        nullable=True,
        comment="Наименование производителя / винодельни",
    )
    roskachestvo_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Оценка качества «Винного гида России» Роскачества",
    )
    sugar_type: Mapped[SugarType | None] = mapped_column(
        SQLEnum(SugarType, native_enum=False, length=50, values_callable=lambda x: [e.value for e in x]),
        nullable=True,
        comment="Тип по содержанию сахара (Сухое, Полусухое, Полусладкое, Сладкое, Брют, Экстра брют)",
    )
    vintage_year: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Год урожая (винтаж)",
    )
    price_rub: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Ориентировочная розничная цена в рублях",
    )
    image_filename: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Оригинальное имя файла фотографии в датасете Strapi",
    )
    image_s3_key: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Ключ объекта фотографии в S3-хранилище (wine-catalog)",
    )
    image_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Прямая подписанная ссылка на фотографию в S3",
    )

    # =========================================================================
    # Вкусовая матрица (Taste Matrix)
    # =========================================================================
    sweetness: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Сладость вина по шкале от 1.0 (очень сухое) до 5.0 (десертное)",
    )
    body: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Тело / плотность вина по шкале от 1.0 (лёгкое) до 5.0 (полнотелое)",
    )
    acidity: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Кислотность / свежесть по шкале от 1.0 (мягкая) до 5.0 (хрустящая)",
    )
    oak: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Выдержка в дубе по шкале от 1.0 (без дуба/сталь) до 5.0 (мощный дуб)",
    )
    aroma_tags: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=list,
        nullable=False,
        comment="Теги ароматического профиля (JSONB)",
    )
    flavor_tags: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=list,
        nullable=False,
        comment="Теги вкусового профиля (JSONB)",
    )
    derived_attributes_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        default=1.0,
        comment="Уверенность извлечения признаков вкусовой матрицы (от 0.0 до 1.0)",
    )

    # Связи с другими сущностями
    pairings: Mapped[list["WineFoodPairing"]] = relationship(
        "WineFoodPairing",
        back_populates="wine",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    cellar_entries: Mapped[list["UserCellar"]] = relationship(
        "UserCellar",
        back_populates="wine",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_wine_region_category", "region", "category"),
        Index("idx_wine_score", "roskachestvo_score"),
        Index("idx_wine_sweetness_body", "sweetness", "body"),
    )
