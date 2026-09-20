import enum
import uuid
from typing import TYPE_CHECKING
from sqlalchemy import String, Text, Float, Integer, ForeignKey, Index, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDMixin, TimestampMixin, GUID

if TYPE_CHECKING:
    from .user import User


class ScanStatus(str, enum.Enum):
    """
    Статус обработки распознавания этикетки вина.
    """
    SUCCESS = "success"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"


class UserScanHistory(Base, UUIDMixin, TimestampMixin):
    """
    Журнал распознавания этикеток для авторизованных и анонимных пользователей.
    Сохраняет информацию о попытках распознавания, фингерпринте устройства и результате.
    """
    __tablename__ = "user_scan_history"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Идентификатор пользователя (если авторизован)",
    )
    image_id: Mapped[str] = mapped_column(
        String(100),
        index=True,
        nullable=False,
        comment="Уникальный идентификатор изображения",
    )
    image_s3_key: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Ключ загруженного изображения в S3 (wine-scans)",
    )
    predicted_slug: Mapped[str | None] = mapped_column(
        String(255),
        index=True,
        nullable=True,
        comment="Распознанный слаг вина в каталоге",
    )
    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Уверенность распознавания модели от 0.0 до 1.0",
    )
    latency_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Время инференса модели в миллисекундах",
    )
    device_fingerprint: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Фингерпринт устройства анонимного пользователя",
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="IP адрес клиента для защиты от злоупотреблений",
    )
    status: Mapped[ScanStatus] = mapped_column(
        SQLEnum(ScanStatus, native_enum=False, length=50, values_callable=lambda x: [e.value for e in x]),
        default=ScanStatus.SUCCESS,
        nullable=False,
        comment="Статус обработки: success, failed, rate_limited",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Текст ошибки при неудачном распознавании",
    )

    user: Mapped["User | None"] = relationship("User", back_populates="scan_history")

    __table_args__ = (
        Index("idx_scan_user_created", "user_id", "created_at"),
        Index("idx_scan_fingerprint_created", "device_fingerprint", "created_at"),
    )
