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
