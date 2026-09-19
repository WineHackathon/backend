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

