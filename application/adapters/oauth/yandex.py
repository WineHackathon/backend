"""
Адаптер интеграции с Яндекс ID OAuth 2.0.
"""
import logging
from dataclasses import dataclass
import httpx

from application.exceptions.domain_exceptions import AuthenticationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class YandexUserProfile:
    """Нормализованный профиль пользователя из Яндекс ID."""
    yandex_id: str
    email: str
    first_name: str
    last_name: str | None
    avatar_url: str | None


class YandexOAuthClient:
    """Клиент для взаимодействия с OAuth 2.0 API Яндекса."""

    TOKEN_URL = "https://oauth.yandex.ru/token"
    INFO_URL = "https://login.yandex.ru/info?format=json"

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.timeout = timeout

    async def get_user_profile(
        self,
        code: str,
        client_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str | None = None,
    ) -> YandexUserProfile:
        """
        Обмен кода авторизации на токен и получение профиля пользователя.
        Поддерживает dev/mock режим для локальной разработки и автотестов.
        """
        c_id = client_id or self.client_id
        c_secret = client_secret or self.client_secret
        r_uri = redirect_uri or self.redirect_uri

        # Dev / Mock режим
        if not c_id or not c_secret or code.startswith("test_") or code.startswith("mock_"):
            logger.info("Использование dev-режима Яндекс OAuth (mock профиль).")
            mock_id = code.replace("test_", "").replace("mock_", "") or "dev_user"
            return YandexUserProfile(
                yandex_id=f"yandex_{mock_id}",
                email=f"yandex_{mock_id}@yandex.ru",
                first_name="Яндекс",
                last_name="Пользователь",
                avatar_url=None,
            )

        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": c_id,
            "client_secret": c_secret,
        }
        if r_uri:
            token_data["redirect_uri"] = r_uri

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                token_resp = await client.post(self.TOKEN_URL, data=token_data)
                if token_resp.status_code != 200:
                    logger.error(
                        "Ошибка Яндекс OAuth token exchange: status=%d, body=%s",
                        token_resp.status_code,
                        token_resp.text,
                    )
                    raise AuthenticationError("Не удалось авторизоваться через Яндекс ID: неверный код авторизации.")

                token_json = token_resp.json()
                access_token = token_json.get("access_token")

                headers = {"Authorization": f"OAuth {access_token}"}
                info_resp = await client.get(self.INFO_URL, headers=headers)
                if info_resp.status_code != 200:
                    logger.error(
                        "Ошибка получения профиля Яндекс: status=%d, body=%s",
                        info_resp.status_code,
                        info_resp.text,
                    )
                    raise AuthenticationError("Не удалось получить профиль пользователя от Яндекс ID.")

                data = info_resp.json()
        except httpx.RequestError as exc:
            logger.error("Сетевая ошибка при обращении к Яндекс OAuth: %s", exc)
            raise AuthenticationError(f"Сетевая ошибка при обращении к Яндекс ID: {exc}") from exc

        yandex_id = str(data.get("id"))
        email = data.get("default_email") or f"yandex_{yandex_id}@yandex.ru"
        first_name = data.get("first_name") or "Пользователь"
        last_name = data.get("last_name")
        avatar_id = data.get("default_avatar_id")
        avatar_url = f"https://avatars.yandex.net/get-yapic/{avatar_id}/islands-200" if avatar_id else None

        return YandexUserProfile(
            yandex_id=yandex_id,
            email=email,
            first_name=first_name,
            last_name=last_name,
            avatar_url=avatar_url,
        )
