"""
Интеграционные тесты многокритериального подбора вин (Multi-Criteria Recommendation).
"""
import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest
from application.adapters.database.models.wine import Wine
from application.adapters.database.models.pairing import WineFoodPairing, FoodCategory
from application.adapters.database.repositories.wine_repo import WineRepository
from application.services.catalog_service import CatalogService
from application.dto.wine_intent import WineSearchIntent
from application.entities.wine_categories import WineCategory, SugarType


@pytest.fixture
def mock_wines():
    # 1. Полнотелое красное к мясу
    wine_red_cabernet = Wine(
        id=uuid.uuid4(),
        slug="fanagoria-100-cabernet",
        name="100 оттенков красного. Каберне",
        category=WineCategory.RED,
        sugar_type=SugarType.DRY,
        region="Кубань",
        grape_varieties=["Каберне Совиньон"],
        description="Мощное танинное вино с ароматом черной смородины и сафьяна. Отлично подходит к стейку рибай и дичи.",
        roskachestvo_score=84.5,
        price_rub=2500.0,
        body=4.8,
        sweetness=1.0,
        acidity=3.5,
        oak=4.0,
    )
    pairing_steak = WineFoodPairing(
        id=uuid.uuid4(),
        wine_id=wine_red_cabernet.id,
        food_category=FoodCategory.MEAT,
        dish_name="Стейк Рибай",
        recommendation_reason="Высокие танины смягчают жирность мраморной говядины.",
    )
    wine_red_cabernet.pairings = [pairing_steak]

    # 2. Еще одно красное к мясу
    wine_red_saperavi = Wine(
        id=uuid.uuid4(),
        slug="fanagoria-saperavi-reserve",
        name="Саперави Резерв",
        category=WineCategory.RED,
        sugar_type=SugarType.DRY,
        region="Кубань",
        grape_varieties=["Саперави"],
        description="Густое экстрактивное вино, идеальная пара к стейку и шашлыку.",
        roskachestvo_score=83.0,
        price_rub=1800.0,
        body=4.5,
        sweetness=1.1,
        acidity=3.2,
        oak=3.5,
    )
    wine_red_saperavi.pairings = []

    # 3. Белое к рыбе с высокой оценкой
    wine_white_chardonnay = Wine(
        id=uuid.uuid4(),
        slug="fanagoria-chardonnay",
        name="100 оттенков. Шардоне",
        category=WineCategory.WHITE,
        sugar_type=SugarType.DRY,
        region="Кубань",
        grape_varieties=["Шардоне"],
        description="Свежее белое вино к морепродуктам и белой рыбе.",
        roskachestvo_score=85.0,
        price_rub=2200.0,
        body=2.8,
        sweetness=1.2,
        acidity=4.0,
        oak=2.0,
    )
    pairing_fish = WineFoodPairing(
        id=uuid.uuid4(),
        wine_id=wine_white_chardonnay.id,
        food_category=FoodCategory.FISH,
        dish_name="Сибас на гриле",
        recommendation_reason="Кислотность подчеркивает нежность рыбы.",
    )
    wine_white_chardonnay.pairings = [pairing_fish]

    return [wine_red_cabernet, wine_red_saperavi, wine_white_chardonnay]


@pytest.mark.asyncio
async def test_smart_recommendation_steak_filters_only_red(mock_wines):
    """
    При запросе к стейку рибай должны подбираться ТОЛЬКО красные вина к мясу.
    """
    mock_session = AsyncMock()
    mock_result = MagicMock()
    # Возвращаем красные вина
    red_wines = [w for w in mock_wines if w.category == WineCategory.RED]
    mock_result.scalars.return_value.all.return_value = red_wines
    mock_session.execute.return_value = mock_result

    repo = WineRepository(mock_session)
    intent = WineSearchIntent(
        category="Красное",
        food_pairing="мясо / стейк",
        target_body=4.5,
        max_price_rub=3000.0,
    )

    recommended = await repo.find_recommended_wines(intent, limit=2)

    assert len(recommended) == 2
    for w in recommended:
        assert w.category == WineCategory.RED
        assert "стейк" in w.description.lower() or any(p.food_category == FoodCategory.MEAT for p in w.pairings)


@pytest.mark.asyncio
async def test_catalog_service_recommend_by_intent(mock_wines):
    """Проверка работы CatalogService.recommend_wines_by_intent и DTO маппинга."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_wines[0]]
    mock_session.execute.return_value = mock_result

    catalog_service = CatalogService(mock_session)
    intent = WineSearchIntent(
        category="Красное",
        food_pairing="мясо / стейк",
        target_body=4.5,
    )

    dtos = await catalog_service.recommend_wines_by_intent(intent, limit=1)

    assert len(dtos) == 1
    assert dtos[0].name == "100 оттенков красного. Каберне"
    assert dtos[0].category == "Красное"
    assert dtos[0].body == 4.8
