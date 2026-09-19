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

    # 5. Проверка хеширования паролей: чистый PBKDF2 (без устаревшего SHA-256)
    pwd = "superSecretPassword123"
    new_hash = hash_password(pwd)
    assert new_hash.startswith("pbkdf2_sha256$")
    assert verify_password(pwd, new_hash) is True
    assert verify_password("wrongPassword", new_hash) is False

    # Невалидный / устаревший хеш без префикса pbkdf2_sha256$ должен отклоняться
    legacy_hash = "someOldSha256OrInvalidHash"
    assert verify_password(pwd, legacy_hash) is False


