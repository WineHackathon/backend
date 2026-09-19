"""
Тесты эвристического анализатора и разметчика вкусовой матрицы (Taste Matrix).
"""
import pytest
from infrastructure.scripts.enrich_taste_matrix import extract_taste_matrix


def test_extract_taste_matrix_for_red_oaked_wine():
    """Проверка извлечения вкусовой матрицы для красного выдержанного вина."""
    description = (
        "Вино глубокого рубинового цвета. В аромате выразительные тона спелой вишни, "
        "черной смородины, ванили и благородного дуба. Вкус полнотелый, с бархатистыми "
        "танинами, нотами шоколада, сливы и долгой выдержки в барриках."
    )
    matrix = extract_taste_matrix(
        category="Красное",
        sugar_type="Сухое",
        description=description,
    )

    assert matrix["sweetness"] == 1.2
    assert matrix["body"] >= 4.0  # Полнотелое
    assert matrix["oak"] >= 3.5   # Дуб, ваниль, баррики
    assert "вишня" in matrix["aroma_tags"]
    assert "черная смородина" in matrix["aroma_tags"]
    assert "ваниль" in matrix["aroma_tags"]
    assert "шоколад" in matrix["flavor_tags"]
    assert matrix["derived_attributes_confidence"] >= 0.85


def test_extract_taste_matrix_for_crisp_white_wine():
    """Проверка извлечения вкусовой матрицы для свежего белого вина без дуба."""
    description = (
        "Светло-соломенный цвет с зеленоватыми бликами. Яркий освежающий аромат с нотами "
        "зеленого яблока, лайма, белых цветов и мокрого камня (минералы). "
        "Хрустящая высокая кислотность, легкое тело, выдержка исключительно в нейтральных стальных емкостях."
    )
    matrix = extract_taste_matrix(
        category="Белое",
        sugar_type="Сухое",
        description=description,
    )

    assert matrix["sweetness"] == 1.2
    assert matrix["body"] <= 2.5   # Легкое тело
    assert matrix["acidity"] >= 4.0 # Хрустящая кислотность
    assert matrix["oak"] <= 1.5    # Сталь / без дуба
    assert "зеленое яблоко" in matrix["aroma_tags"]
    assert "лайм" in matrix["aroma_tags"]
    assert "минералы" in matrix["aroma_tags"] or "минералы" in matrix["flavor_tags"]
    assert matrix["derived_attributes_confidence"] >= 0.85


def test_extract_taste_matrix_sweet_wine():
    """Проверка определения сладости для десертного/сладкого вина."""
    description = "Аромат кураги, меда и цукатов. Насыщенный сладкий вкус."
    matrix = extract_taste_matrix(
        category="Белое",
        sugar_type="Сладкое",
        description=description,
    )
    assert matrix["sweetness"] >= 4.0
    assert "мед" in matrix["aroma_tags"] or "цукаты" in matrix["aroma_tags"]
