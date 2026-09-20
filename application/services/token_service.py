"""
Прикладной сервис создания, подписи и верификации JWT токенов.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from application.dto.auth import TokenPairDTO, TokenPayloadDTO
from application.exceptions.domain_exceptions import AuthenticationError


class TokenService:
    """Сервис создания, подписи и верификации JWT токенов (не требует сессии БД)."""

    def __init__(
        self,
        jwt_secret: str | None = None,
        jwt_algorithm: str | None = None,
        access_token_expire_minutes: int | None = None,
        refresh_token_expire_days: int | None = None,
    ) -> None:
        self.jwt_secret: str = jwt_secret or os.getenv(
            "JWT_SECRET_KEY", "wine_hackathon_super_secret_jwt_key_32_chars"
        )
        self.jwt_algorithm: str = jwt_algorithm or os.getenv("JWT_ALGORITHM", "HS256")
        self.access_token_expire_minutes: int = int(
            access_token_expire_minutes
            or os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60")
        )
        self.refresh_token_expire_days: int = int(
            refresh_token_expire_days
            or os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "30")
        )

    def create_token_pair(
        self,
        user_id: uuid.UUID,
        is_admin: bool = False,
        session_id: uuid.UUID | None = None,
    ) -> TokenPairDTO:
        """Создание пары токенов (access и refresh) с валидацией через TokenPayloadDTO."""
        now = datetime.now(timezone.utc)
        access_exp = int((now + timedelta(minutes=self.access_token_expire_minutes)).timestamp())
        refresh_exp = int((now + timedelta(days=self.refresh_token_expire_days)).timestamp())

        access_payload = TokenPayloadDTO(
            sub=user_id,
            is_admin=is_admin,
            exp=access_exp,
            type="access",
            session_id=session_id,
        )
        refresh_payload = TokenPayloadDTO(
            sub=user_id,
            exp=refresh_exp,
            type="refresh",
            session_id=session_id,
        )

        access_token = jwt.encode(
            access_payload.model_dump(mode="json"),
            self.jwt_secret,
            algorithm=self.jwt_algorithm,
        )
        refresh_token = jwt.encode(
            refresh_payload.model_dump(mode="json"),
            self.jwt_secret,
            algorithm=self.jwt_algorithm,
        )

        return TokenPairDTO(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="Bearer",
            expires_in=int(self.access_token_expire_minutes * 60),
        )

    def decode_token(self, token: str) -> TokenPayloadDTO:
        """Декодирование и верификация JWT токена в строгий TokenPayloadDTO."""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            return TokenPayloadDTO.model_validate(payload)
        except (jwt.PyJWTError, Exception) as e:
            raise AuthenticationError(f"Недействительный токен: {str(e)}")

    def decode_access_token(self, token: str) -> TokenPayloadDTO:
        """Декодирование access-токена с защитой от подмены типа (Token Type Confusion)."""
        payload = self.decode_token(token)
        if payload.type != "access":
            raise AuthenticationError("Недействительный тип токена. Ожидается access токен.")
        return payload
