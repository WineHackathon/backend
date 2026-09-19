"""
Тесты специализированного ML-слоя:
- Векторный индекс и косинусный поиск Top-1
- Проверка криптографической HMAC подписи целостности индекса
"""
import numpy as np
import pytest
from ml.app.model.vector_index import VectorIndex


def test_vector_index_add_and_search():
    """Проверка добавления эмбеддингов и Top-1 поиска по косинусному сходству."""
    index = VectorIndex()

    v1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    v2 = np.array([0.0, 1.0, 0.0], dtype=np.float32)

    index.add("wine-a", v1)
    index.add("wine-b", v2)

    assert not index.is_empty()

    # Запрос совпадает с v1 -> должен найтись wine-a с уверенностью ~1.0
    query = np.array([0.9, 0.1, 0.0], dtype=np.float32)
    query = query / np.linalg.norm(query)

    slug, conf = index.search_top1(query)
    assert slug == "wine-a"
    assert conf > 0.85


def test_vector_index_hmac_integrity(tmp_path):
    """Проверка сохранения и криптографической верификации целостности HMAC-SHA256."""
    index = VectorIndex(hmac_secret="test_secret_key_123")
    v1 = np.array([0.5, 0.5, 0.7], dtype=np.float32)
    v1 = v1 / np.linalg.norm(v1)
    index.add("shiraz-2023", v1)

    file_path = str(tmp_path / "test_index.npz")
    index.save(file_path)

    # Успешная загрузка с правильным ключом
    loaded_index = VectorIndex(hmac_secret="test_secret_key_123")
    success = loaded_index.load(file_path, verify_checksum=True)
    assert success is True
    assert "shiraz-2023" in loaded_index.slugs

    # Ошибка верификации при неверном секрете
    wrong_key_index = VectorIndex(hmac_secret="wrong_secret")
    tampered_success = wrong_key_index.load(file_path, verify_checksum=True)
    assert tampered_success is False
