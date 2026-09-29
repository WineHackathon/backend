"""
Тесты сервиса извлечения намерений (IntentExtractor).
"""
import pytest
from sommelier.app.services.intent_extractor import IntentExtractor, intent_extractor
from application.dto.wine_intent import WineSearchIntent


@pytest.mark.asyncio
async def test_heuristic_steak_red_wine():
    text = "Посоветуй полнотелое красное вино к стейку рибай до 3000 рублей"
    intent = intent_extractor.extract_heuristic(text)

    assert intent.category == "Красное"
    assert intent.food_pairing == "мясо / стейк"
    assert intent.target_body == 4.5
    assert intent.max_price_rub == 3000.0
    assert intent.is_recommendation_request is True


@pytest.mark.asyncio
async def test_heuristic_seafood_white_wine():
    text = "Какое белое сухое вино выбрать к морепродуктам?"
    intent = intent_extractor.extract_heuristic(text)

    assert intent.category == "Белое"
    assert intent.sugar_type == "Сухое"
    assert intent.food_pairing == "рыба / морепродукты"
    assert intent.is_recommendation_request is True


@pytest.mark.asyncio
async def test_heuristic_sparkling_brut():
    text = "Посоветуй легкое игристое брют"
    intent = intent_extractor.extract_heuristic(text)

    assert intent.category == "Игристое"
    assert intent.sugar_type == "Сухое" or "брют" in text
    assert intent.target_body == 2.0


@pytest.mark.asyncio
async def test_heuristic_implicit_steak_category():
    # Даже если слово "красное" не указано, стейк рибай должен автоматически классифицироваться как Красное
    text = "Что взять к стейку из мраморной говядины?"
    intent = intent_extractor.extract_heuristic(text)

    assert intent.category == "Красное"
    assert intent.food_pairing == "мясо / стейк"


@pytest.mark.asyncio
async def test_extract_intent_fallback_without_llm():
    text = "Посоветуй плотное красное вино с выдержкой в дубе до 2500 руб"
    intent = await intent_extractor.extract_intent(text, llm_client=None)

    assert intent.category == "Красное"
    assert intent.target_body == 4.5
    assert intent.max_price_rub == 2500.0
    assert intent.is_recommendation_request is True


@pytest.mark.asyncio
async def test_serving_and_pairing_questions_suppress_wine_cards():
    """Вопросы о сервировке и гастропарах к конкретному вину НЕ должны спамить карточками других вин."""
    q1 = "С чем лучше подать вино Массандра Мускат?"
    intent1 = intent_extractor.extract_heuristic(q1)
    assert intent1.is_recommendation_request is False

    q2 = "Какая оптимальная температура подачи у Шардоне?"
    intent2 = intent_extractor.extract_heuristic(q2)
    assert intent2.is_recommendation_request is False

    q3 = "Нужно ли декантировать Саперави?"
    intent3 = intent_extractor.extract_heuristic(q3)
    assert intent3.is_recommendation_request is False

    q4 = "В каких бокалах подавать Пино Нуар?"
    intent4 = intent_extractor.extract_heuristic(q4)
    assert intent4.is_recommendation_request is False


@pytest.mark.asyncio
async def test_explicit_wine_recommendations_enable_wine_cards():
    """Явные просьбы подобрать или посоветовать вино должны активировать карточки вин."""
    q1 = "Посоветуй вино к стейку"
    intent1 = intent_extractor.extract_heuristic(q1)
    assert intent1.is_recommendation_request is True

    q2 = "Какое вино выбрать к морепродуктам?"
    intent2 = intent_extractor.extract_heuristic(q2)
    assert intent2.is_recommendation_request is True

    q3 = "Подбери белое сухое до 2000 рублей"
    intent3 = intent_extractor.extract_heuristic(q3)
    assert intent3.is_recommendation_request is True

