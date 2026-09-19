"""
Эндпоинты аутентификации и регистрации (/api/v1/auth).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.db_session import get_session
from application.dto.auth import (
    LoginRequestDTO,
    RegisterRequestDTO,
    TokenPairDTO,
    AuthResponseDTO,
    RefreshTokenRequestDTO,
)
from application.dto.user import UserDTO
from application.exceptions.domain_exceptions import AuthenticationError, UserAlreadyExists
from application.services.auth_service import AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post("/register", response_model=AuthResponseDTO, summary="Register new user")
async def register(
    dto: RegisterRequestDTO,
    session: AsyncSession = Depends(get_session),
):
    """Регистрация нового пользователя с получением JWT токенов."""
    service = AuthService(session)
    try:
        user_dto, tokens = await service.register(dto)
        return AuthResponseDTO(
            user=user_dto,
            tokens=tokens,
        )
    except UserAlreadyExists as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)


@router.post("/login", response_model=AuthResponseDTO, summary="Login with email and password")
async def login(
    dto: LoginRequestDTO,
    session: AsyncSession = Depends(get_session),
):
    """Вход по email и паролю."""
    service = AuthService(session)
    try:
        user_dto, tokens = await service.login(dto)
        return AuthResponseDTO(
            user=user_dto,
            tokens=tokens,
        )
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=e.message)


@router.post("/refresh", response_model=AuthResponseDTO, summary="Refresh access token using refresh token")
async def refresh_tokens(
    dto: RefreshTokenRequestDTO,
    session: AsyncSession = Depends(get_session),
):
    """Обновление пары токенов по валидному refresh-токену."""
    service = AuthService(session)
    try:
        user_dto, tokens = await service.refresh_tokens(dto)
        return AuthResponseDTO(
            user=user_dto,
            tokens=tokens,
        )
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=e.message)


