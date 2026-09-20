"""
Эндпоинты профиля пользователя, винного погреба и истории сканирований (/api/v1/users).
"""
import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.db_session import get_session
from application.adapters.database.models.cellar import CellarStatus
from application.dto.user import UserDTO, UserPreferenceHistoryDTO
from application.dto.cellar import CellarItemDTO, CellarItemCreateDTO, CellarDeleteResponseDTO
from application.dto.scan import ScanHistoryItemDTO
from application.dto.session import (
    UserSessionDTO,
    RevokeSessionResponseDTO,
    RevokeAllSessionsResponseDTO,
)
from application.services.user_service import UserService
from application.services.cellar_service import CellarService
from application.services.auth_service import AuthService
from backend.app.dependencies import get_current_user_id, get_current_session_id, get_redis_client
import redis.asyncio as redis

router = APIRouter(prefix="/api/v1/users", tags=["Профиль пользователя и сессии"])


@router.get("/me", response_model=UserDTO, summary="Получить профиль текущего пользователя")
async def get_my_profile(
    user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Получение профиля текущего пользователя, включая вкусовой профиль (taste_profile)."""
    service = UserService(session)
    return await service.get_by_id(user_id)


@router.get("/cellar", response_model=list[CellarItemDTO], summary="Список вин в погребе / вишлисте")
async def get_my_cellar(
    status: CellarStatus | None = Query(None, description="Статус: in_cellar, wishlist, tasted"),
    user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Список вин в личном погребе / вишлисте пользователя."""
    service = CellarService(session)
    return await service.list_items(user_id, status=status)


@router.post("/cellar", response_model=CellarItemDTO, summary="Добавить вино в погреб или вишлист")
async def add_to_my_cellar(
    dto: CellarItemCreateDTO,
    user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Добавление вина в погреб или вишлист."""
    service = CellarService(session)
    return await service.add_item(user_id, dto)


@router.delete("/cellar/{item_id}", response_model=CellarDeleteResponseDTO, summary="Удалить вино из погреба")
async def remove_from_my_cellar(
    item_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Удаление позиции из личного погреба."""
    service = CellarService(session)
    await service.remove_item(user_id, item_id)
    return CellarDeleteResponseDTO(status="deleted", item_id=item_id)


@router.get("/scans", response_model=list[ScanHistoryItemDTO], summary="История сканирований пользователя")
async def get_my_scans(
    limit: int = Query(20, ge=1, le=100),
    user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """История сканирований текущего пользователя."""
    service = UserService(session)
    return await service.get_user_scans(user_id, limit=limit)


@router.get("/preferences", response_model=list[UserPreferenceHistoryDTO], summary="История предпочтений диалогов с сомелье")
async def get_my_preferences(
    limit: int = Query(10, ge=1, le=50),
    user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """История сырых предпочтений и рекомендаций диалогов с сомелье (сырые данные)."""
    service = UserService(session)
    return await service.get_user_preferences(user_id, limit=limit)


# =============================================================================
# Управление сессиями и активными устройствами (Active Sessions & Devices)
# =============================================================================

@router.get("/sessions", response_model=list[UserSessionDTO], summary="Список активных устройств (сессий) пользователя")
async def list_my_sessions(
    user_id: uuid.UUID = Depends(get_current_user_id),
    current_session_id: uuid.UUID | None = Depends(get_current_session_id),
    session: AsyncSession = Depends(get_session),
):
    """
    Список всех активных устройств (сессий) текущего пользователя.
    Флаг is_current=True указывает на сессию, с которой выполняется запрос.
    """
    auth_service = AuthService(session)
    return await auth_service.list_user_sessions(user_id, current_session_id=current_session_id)


@router.delete("/sessions/{session_id}", response_model=RevokeSessionResponseDTO, summary="Завершить конкретную сессию устройства")
async def revoke_my_session(
    session_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    redis_client: redis.Redis | None = Depends(get_redis_client),
    session: AsyncSession = Depends(get_session),
):
    """Удаленное завершение конкретной сессии устройства."""
    auth_service = AuthService(session, redis_client=redis_client)
    revoked = await auth_service.revoke_user_session(user_id, session_id)
    if not revoked:
        return RevokeSessionResponseDTO(
            status="not_found",
            revoked_session_id=session_id,
            message="Сессия не найдена или не принадлежит пользователю",
        )
    return RevokeSessionResponseDTO(
        status="ok",
        revoked_session_id=session_id,
        message="Сессия устройства успешно завершена",
    )


@router.delete("/sessions", response_model=RevokeAllSessionsResponseDTO, summary="Завершить все остальные сессии устройств")
async def revoke_all_my_other_sessions(
    user_id: uuid.UUID = Depends(get_current_user_id),
    current_session_id: uuid.UUID | None = Depends(get_current_session_id),
    session: AsyncSession = Depends(get_session),
):
    """Завершение всех остальных активных сессий пользователя кроме текущей."""
    auth_service = AuthService(session)
    if not current_session_id:
        # Если session_id в токене не найден, завершаем все сессии кроме первой (самой недавней)
        sessions = await auth_service.list_user_sessions(user_id)
        if sessions:
            current_session_id = sessions[0].id

    count = await auth_service.revoke_all_other_sessions(user_id, current_session_id) if current_session_id else 0
    return RevokeAllSessionsResponseDTO(
        status="ok",
        revoked_count=count,
        message=f"Завершено других сессий: {count}",
    )

