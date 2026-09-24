"""
Тесты для слоя application: проверка моделей, репозиториев, менеджера транзакций и DTO.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest

from application.adapters.database.models.wine import Wine
from application.adapters.database.models.user import User
from application.adapters.database.models.cellar import UserCellar
from application.adapters.database.models.pairing import WineFoodPairing
from application.adapters.database.models.scan_history import UserScanHistory
from application.adapters.database.models.preference_history import UserPreferenceHistory
from application.adapters.database.transaction_manager import TransactionManager
from application.adapters.database.repositories.wine_repo import WineRepository
from application.adapters.database.repositories.user_repo import UserRepository
from application.dto.wine import WineDTO, WineDetailDTO, TasteMatrixDTO
from application.dto.user import TasteProfileDTO
from application.services.catalog_service import CatalogService
from application.services.user_service import UserService


def test_wine_model_with_taste_matrix():
    """Проверка инстанцирования модели Wine со всеми полями вкусовой матрицы (Taste Matrix)."""
    wine_id = uuid.uuid4()
    wine = Wine(
        id=wine_id,
        slug="fanagoria-cru-lelerche-2020",
        name="Фанагория Крю Лермонт Каберне Совиньон 2020",
        category="Красное",
        color_desc="Глубокий рубиновый цвет",
        region="Кубань",
        grape_varieties=["Каберне Совиньон"],
        description="Полнотелое вино с тонами черной смородины, вишни, ванили и дуба.",
        winery="Фанагория",
        roskachestvo_score=84.5,
        sugar_type="Сухое",
        vintage_year=2020,
        price_rub=1150.0,
        # Вкусовая матрица (Taste Matrix)
        sweetness=1.2,
        body=4.5,
        acidity=3.2,
        oak=4.0,
        aroma_tags=["черная смородина", "вишня", "ваниль", "дуб"],
        flavor_tags=["слива", "шоколад", "табак"],
        derived_attributes_confidence=0.95,
    )

    assert wine.id == wine_id
    assert wine.slug == "fanagoria-cru-lelerche-2020"
    assert wine.body == 4.5
    assert wine.oak == 4.0
    assert "черная смородина" in wine.aroma_tags
    assert "шоколад" in wine.flavor_tags
    assert wine.derived_attributes_confidence == 0.95


def test_user_model_with_taste_profile():
    """Проверка модели User с агрегированным вкусовым профилем."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="sommelier_fan@example.com",
        first_name="Иван",
        taste_profile={
            "preferred_categories": ["Красное", "Белое"],
            "sweetness_pref": 1.5,
            "body_pref": 4.0,
            "acidity_pref": 3.0,
            "oak_pref": 3.5,
            "favorite_aromas": ["вишня", "дуб"],
            "disliked_aromas": ["петрольные ноты"],
        },
    )

    assert user.id == user_id
    assert user.email == "sommelier_fan@example.com"
    assert user.taste_profile["body_pref"] == 4.0
    assert "вишня" in user.taste_profile["favorite_aromas"]


@pytest.mark.asyncio
async def test_transaction_manager_commits_on_success():
    """Проверка фиксации транзакции при успешном выполнении блока."""
    mock_session = AsyncMock()
    tm = TransactionManager(mock_session)

    async with tm:
        pass

    mock_session.commit.assert_awaited_once()
    mock_session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_transaction_manager_rollbacks_on_error():
    """Проверка отката транзакции при исключении."""
    mock_session = AsyncMock()
    tm = TransactionManager(mock_session)

    with pytest.raises(ValueError):
        async with tm:
            raise ValueError("Test error")

    mock_session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_catalog_service_to_dto():
    """Проверка конвертации модели Wine в WineDTO и WineDetailDTO."""
    mock_session = AsyncMock()
    service = CatalogService(mock_session)

    wine = Wine(
        id=uuid.uuid4(),
        slug="kuban-sauvignon-2023",
        name="Кубань Совиньон Блан",
        category="Белое",
        region="Кубань",
        sweetness=1.1,
        body=2.2,
        acidity=4.5,
        oak=1.0,
        aroma_tags=["цитрус", "зеленое яблоко", "минералы"],
        flavor_tags=["грейпфрут", "лайм"],
    )

    dto = service.to_dto(wine)
    assert isinstance(dto, WineDTO)
    assert dto.slug == "kuban-sauvignon-2023"
    assert dto.acidity == 4.5
    assert dto.body == 2.2

    detail_dto = service.to_detail_dto(wine)
    assert isinstance(detail_dto, WineDetailDTO)
    assert "цитрус" in detail_dto.aroma_tags


@pytest.mark.asyncio
async def test_catalog_service_list_wines_with_dto():
    """Проверка работы CatalogService с WineFilterDTO и PaginatedWinesDTO."""
    from application.dto.wine import WineFilterDTO, PaginatedWinesDTO

    mock_session = AsyncMock()
    service = CatalogService(mock_session)

    wine = Wine(
        id=uuid.uuid4(),
        slug="test-wine",
        name="Тестовое вино",
        category="Красное",
        region="Крым",
        sugar_type="Сухое",
    )
    service.repo.list_wines = AsyncMock(return_value=([wine], 1))

    filter_dto = WineFilterDTO(category="Красное", limit=10)
    result = await service.list_wines(filter_dto)

    assert isinstance(result, PaginatedWinesDTO)
    assert result.total == 1
    assert result.limit == 10
    assert len(result.items) == 1
    assert result.items[0].slug == "test-wine"


@pytest.mark.asyncio
async def test_auth_service_security_and_tokens():
    """Тестирование безопасности AuthService: DTO, Token Type Confusion и PBKDF2."""
    from application.services.auth_service import AuthService, hash_password, verify_password
    from application.dto.auth import TokenPayloadDTO, RefreshTokenRequestDTO
    from application.exceptions.domain_exceptions import AuthenticationError

    mock_session = AsyncMock()
    service = AuthService(mock_session)
    user_id = uuid.uuid4()

    # 1. Проверка создания пары токенов и синхронизации expires_in
    tokens = service.create_token_pair(user_id, is_admin=True)
    assert tokens.token_type == "Bearer"
    assert tokens.expires_in == service.access_token_expire_minutes * 60

    # 2. Проверка строгой типизации TokenPayloadDTO
    access_payload = service.decode_token(tokens.access_token)
    assert isinstance(access_payload, TokenPayloadDTO)
    assert access_payload.sub == user_id
    assert access_payload.type == "access"
    assert access_payload.is_admin is True

    refresh_payload = service.decode_token(tokens.refresh_token)
    assert isinstance(refresh_payload, TokenPayloadDTO)
    assert refresh_payload.type == "refresh"

    # 3. Защита от Token Type Confusion
    # decode_access_token должен принимать access_token
    valid_access = service.decode_access_token(tokens.access_token)
    assert valid_access.sub == user_id

    # decode_access_token ДОЛЖЕН отклонять refresh_token
    with pytest.raises(AuthenticationError, match="Недействительный тип токена"):
        service.decode_access_token(tokens.refresh_token)

    # 4. Обновление токенов (refresh_tokens)
    mock_user = User(
        id=user_id,
        email="test@domain.com",
        first_name="Иван",
        is_admin=True,
    )
    service.user_repo.get_by_id = AsyncMock(return_value=mock_user)

    # Успешный refresh
    new_user_dto, new_tokens = await service.refresh_tokens(
        RefreshTokenRequestDTO(refresh_token=tokens.refresh_token)
    )
    assert new_user_dto.id == user_id
    assert new_tokens.access_token != ""

    # Попытка refresh с access токеном должна отклоняться
    with pytest.raises(AuthenticationError, match="Недействительный тип токена"):
        await service.refresh_tokens(RefreshTokenRequestDTO(refresh_token=tokens.access_token))

    # 5. Проверка хеширования паролей: модульный crypt PBKDF2 с уникальной солью на пользователя
    pwd = "superSecretPassword123"
    hash1 = hash_password(pwd)
    hash2 = hash_password(pwd)

    # Уникальная криптографическая соль: одинаковый пароль дает разные хеши
    assert hash1 != hash2
    assert hash1.startswith("pbkdf2_sha256$100000$")
    assert hash2.startswith("pbkdf2_sha256$100000$")

    # Проверка извлечения соли и валидации
    assert verify_password(pwd, hash1) is True
    assert verify_password(pwd, hash2) is True
    assert verify_password("wrongPassword", hash1) is False

    # Невалидный / устаревший хеш без префикса pbkdf2_sha256$ или с неверной структурой должен отклоняться
    assert verify_password(pwd, "someOldSha256OrInvalidHash") is False
    assert verify_password(pwd, "pbkdf2_sha256$invalid_parts") is False
    assert verify_password(pwd, "pbkdf2_sha256$not_a_number$salt$hash") is False


def test_all_dtos_validation_and_serialization():
    """Комплексный тест валидации и сериализации всех DTO схем."""
    from application.dto import (
        UserDTO,
        TasteProfileDTO,
        UserPreferenceHistoryDTO,
        PreferenceSessionCreateDTO,
        CellarItemDTO,
        CellarItemCreateDTO,
        ScanResultDTO,
        EvaluationResponseDTO,
        OnboardingAnswerDTO,
    )
    from application.dto.wine_intent import WineSearchIntent
    from application.adapters.database.models.cellar import CellarStatus
    from datetime import datetime, timezone

    # 1. TasteProfileDTO & UserDTO
    profile = TasteProfileDTO(
        preferred_categories=["Красное"],
        sweetness_pref=1.5,
        body_pref=4.5,
        favorite_aromas=["ежевика", "шоколад"],
    )
    assert profile.sweetness_pref == 1.5
    assert "шоколад" in profile.favorite_aromas

    uid = uuid.uuid4()
    user_dto = UserDTO(
        id=uid,
        email="test@user.ru",
        first_name="Тест",
        role="admin",
        taste_profile=profile,
    )
    assert user_dto.role == "admin"
    assert isinstance(user_dto.taste_profile, TasteProfileDTO)
    assert user_dto.taste_profile.body_pref == 4.5

    # 2. PreferenceSessionCreateDTO с произвольными типами в raw_answers (списки, числа)
    session_dto = PreferenceSessionCreateDTO(
        session_id="session-123",
        raw_answers={"step_1": "Красное", "sweetness": 2.0, "aromas": ["ягоды", "дуб"]},
        recommended_slugs=["wine-1", "wine-2"],
    )
    assert session_dto.raw_answers["sweetness"] == 2.0
    assert isinstance(session_dto.raw_answers["aromas"], list)

    # 3. CellarItemDTO & CellarItemCreateDTO
    cellar_create = CellarItemCreateDTO(
        wine_slug="krasnostop-2020",
        status=CellarStatus.IN_CELLAR,
        bottles_count=3,
        personal_rating=5,
    )
    assert cellar_create.bottles_count == 3
    assert cellar_create.status == CellarStatus.IN_CELLAR

    cellar_dto = CellarItemDTO(
        id=uuid.uuid4(),
        user_id=uid,
        wine_id=uuid.uuid4(),
        status=CellarStatus.TASTED,
        bottles_count=1,
        created_at=datetime.now(timezone.utc),
    )
    assert cellar_dto.status == CellarStatus.TASTED

    # 4. ScanResultDTO & EvaluationResponseDTO
    eval_dto = EvaluationResponseDTO(slug="fanagoria-cru-leront-chardonnay")
    assert eval_dto.slug == "fanagoria-cru-leront-chardonnay"

    scan_dto = ScanResultDTO(
        image_id="img_12345",
        slug="fanagoria-cru-leront-chardonnay",
        confidence=0.98,
        latency_ms=120,
    )
    assert scan_dto.confidence == 0.98

    # 5. OnboardingAnswerDTO (плоский и вложенный форматы)
    flat_answer = OnboardingAnswerDTO(
        step=1,
        code="category",
        answer="Белое",
        answers_history={"q0": "init"},
    )
    s, c, a, h = flat_answer.get_parsed_data()
    assert s == 1 and c == "category" and a == "Белое" and h["q0"] == "init"

    nested_answer = OnboardingAnswerDTO(
        answer={"step": 2, "code": "sweetness", "answer": "Сухое"},
        answers_history={"category": "Белое"},
    )
    s2, c2, a2, h2 = nested_answer.get_parsed_data()
    assert s2 == 2 and c2 == "sweetness" and a2 == "Сухое" and h2["category"] == "Белое"

    # 6. WineSearchIntent
    intent = WineSearchIntent(
        category="Красное",
        sugar_type="Сухое",
        target_body=4.0,
        target_sweetness=1.0,
    )
    assert intent.category == "Красное"
    assert intent.target_body == 4.0


@pytest.mark.asyncio
async def test_yandex_oauth_adapter_and_device_utils():
    """Проверка YandexOAuthClient (mock/dev режим) и утилиты parse_device_name."""
    from application.adapters.oauth.yandex import YandexOAuthClient, YandexUserProfile
    from application.common.device_utils import parse_device_name

    # 1. Dev/Mock режим OAuth клиента
    client = YandexOAuthClient()
    profile = await client.get_user_profile("test_sommelier_user")
    assert isinstance(profile, YandexUserProfile)
    assert profile.yandex_id == "yandex_sommelier_user"
    assert profile.email == "yandex_sommelier_user@yandex.ru"
    assert profile.first_name == "Яндекс"

    # 2. Утилита распознавания User-Agent
    ua_mac = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    assert parse_device_name(ua_mac) == "Chrome (macOS)"

    ua_iphone = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"
    assert parse_device_name(ua_iphone) == "Safari (iPhone)"

    # Явное клиентское имя устройства имеет приоритет
    assert parse_device_name(ua_mac, client_device="iPad Pro 12.9") == "iPad Pro 12.9"
    assert parse_device_name(None, None) == "Неизвестное устройство"


@pytest.mark.asyncio
async def test_taste_profile_service_defensive_parsing():
    """Проверка TasteProfileService на устойчивость к спискам ароматов, числам и категориям."""
    from application.services.taste_profile_service import TasteProfileService
    from application.dto.user import PreferenceSessionCreateDTO

    mock_session = AsyncMock()
    service = TasteProfileService(mock_session)

    uid = uuid.uuid4()
    mock_user = User(
        id=uid,
        email="test@taste.ru",
        first_name="Тестер",
        taste_profile={"preferred_categories": ["Белое"], "sweetness_pref": 1.5, "favorite_aromas": ["яблоко"]},
    )
    service.user_repo.get_by_id = AsyncMock(return_value=mock_user)
    service.pref_repo.save = AsyncMock()
    service.user_repo.update_taste_profile = AsyncMock()

    dto = PreferenceSessionCreateDTO(
        user_id=uid,
        session_id="session-defensive-1",
        raw_answers={
            "category": ["Красное", "Розовое"],
            "sweetness": 2.5,  # float вместо строки
            "body": 4.0,       # float вместо строки
            "acidity": "яркая свежесть",
            "oak": 4.5,
            "aromas": ["вишня", "ваниль", "дуб"],  # list вместо str.replace(...)
        },
        recommended_slugs=["wine-1"],
    )

    profile = await service.record_preferences_and_update_profile(dto)
    assert profile is not None
    assert "Белое" in profile.preferred_categories
    assert "Красное" in profile.preferred_categories
    assert "Розовое" in profile.preferred_categories
    assert "вишня" in profile.favorite_aromas
    assert "ваниль" in profile.favorite_aromas
    assert "яблоко" in profile.favorite_aromas
    assert 1.0 <= profile.sweetness_pref <= 5.0
    assert 1.0 <= profile.body_pref <= 5.0


@pytest.mark.asyncio
async def test_scan_service_record_and_lookup():
    """Проверка работы ScanService: сохранение истории и безопасный поиск вина."""
    from application.services.scan_service import ScanService
    from application.adapters.database.models.scan_history import ScanStatus

    mock_session = AsyncMock()
    service = ScanService(mock_session)
    service.scan_repo.save = AsyncMock()

    uid = uuid.uuid4()
    scan_record = await service.record_scan(
        image_id="img-scan-999",
        predicted_slug="fanagoria-cru-leront",
        confidence=0.96,
        latency_ms=180,
        user_id=uid,
        device_fingerprint="fp-device-123",
        ip_address="192.168.1.1",
    )
    assert scan_record.image_id == "img-scan-999"
    assert scan_record.predicted_slug == "fanagoria-cru-leront"
    assert scan_record.status == ScanStatus.SUCCESS
    service.scan_repo.save.assert_awaited_once()

    # Поиск по несуществующему вину не должен падать
    service.catalog_service.get_by_slug = AsyncMock(return_value=None)
    res = await service.get_wine_by_slug_safe("non-existent-wine")
    assert res is None


@pytest.mark.asyncio
async def test_ml_and_redis_adapters():
    """Проверка работы MLDispatcher и ScanRateLimiter в слое application/adapters/."""
    from application.adapters.ml.ml_dispatcher import MLDispatcher
    from application.adapters.redis.rate_limiter import ScanRateLimiter

    # 1. MLDispatcher в автономном/mock режиме
    dispatcher = MLDispatcher(redis_client=None, mock_mode=True)
    slug, conf, latency = await dispatcher.predict(b"dummy_bytes")
    assert slug is not None
    assert conf == 0.94
    assert latency >= 0

    # 2. ScanRateLimiter без Redis (graceful fallback)
    limiter = ScanRateLimiter(redis_client=None, limit=5, ttl=3600)
    allowed, remaining = await limiter.check_and_increment(fingerprint="fp_test")
    assert allowed is True
    assert remaining == 5

    # 3. ScanRateLimiter с моком Redis
    mock_redis = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock(return_value=True)
    limiter_redis = ScanRateLimiter(redis_client=mock_redis, limit=5, ttl=3600)
    allowed, remaining = await limiter_redis.check_and_increment(fingerprint="fp_test_2")
    assert allowed is True
    assert remaining == 4
    mock_redis.incr.assert_awaited_once_with("anon:scan:fp_test_2")
    mock_redis.expire.assert_awaited_once_with("anon:scan:fp_test_2", 3600)


@pytest.mark.asyncio
async def test_cellar_service_update_item():
    """Проверка обновления и слияния позиций погреба в CellarService.update_item."""
    from application.services.cellar_service import CellarService
    from application.dto.cellar import CellarItemUpdateDTO
    from application.adapters.database.models.cellar import UserCellar, CellarStatus
    from application.exceptions.domain_exceptions import CellarItemNotFound

    mock_session = AsyncMock()
    service = CellarService(mock_session)

    user_id = uuid.uuid4()
    item_id = uuid.uuid4()
    wine_id = uuid.uuid4()

    item = UserCellar(
        id=item_id,
        user_id=user_id,
        wine_id=wine_id,
        status=CellarStatus.IN_CELLAR,
        bottles_count=2,
    )

    # 1. Позиция не найдена
    service.cellar_repo.get_by_id = AsyncMock(return_value=None)
    with pytest.raises(CellarItemNotFound):
        await service.update_item(user_id, item_id, CellarItemUpdateDTO(status=CellarStatus.TASTED))

    # 2. Успешное простое обновление
    service.cellar_repo.get_by_id = AsyncMock(return_value=item)
    service.cellar_repo.get_by_user_and_wine = AsyncMock(return_value=None)
    service.cellar_repo.save = AsyncMock()

    dto = CellarItemUpdateDTO(
        status=CellarStatus.TASTED,
        bottles_count=1,
        personal_rating=4,
        tasting_notes="Мягкое послевкусие",
    )
    res = await service.update_item(user_id, item_id, dto)
    assert res.status == CellarStatus.TASTED
    assert res.bottles_count == 1
    assert res.personal_rating == 4
    assert res.tasting_notes == "Мягкое послевкусие"

    # 3. Слияние при наличии существующей записи со статусом tasted
    item_in_cellar = UserCellar(
        id=item_id,
        user_id=user_id,
        wine_id=wine_id,
        status=CellarStatus.IN_CELLAR,
        bottles_count=2,
    )
    existing_tasted = UserCellar(
        id=uuid.uuid4(),
        user_id=user_id,
        wine_id=wine_id,
        status=CellarStatus.TASTED,
        bottles_count=1,
        personal_rating=5,
    )
    service.cellar_repo.get_by_id = AsyncMock(return_value=item_in_cellar)
    service.cellar_repo.get_by_user_and_wine = AsyncMock(return_value=existing_tasted)
    service.cellar_repo.delete_item = AsyncMock(return_value=True)

    res_merged = await service.update_item(user_id, item_id, CellarItemUpdateDTO(status=CellarStatus.TASTED))
    assert res_merged.id == existing_tasted.id
    assert res_merged.status == CellarStatus.TASTED
    service.cellar_repo.delete_item.assert_awaited_once_with(user_id, item_in_cellar.id)
