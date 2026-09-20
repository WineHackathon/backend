"""
Адаптеры внешних OAuth провайдеров.
"""
from .yandex import YandexOAuthClient, YandexUserProfile

__all__ = ["YandexOAuthClient", "YandexUserProfile"]
