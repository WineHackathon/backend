"""
Сервис RAG (Retrieval-Augmented Generation) по базе знаний российских вин и Роскачества.
"""
from typing import Any


class SommelierRAGService:
    """Формирование контекста знаний эксперта-сомелье."""

    @staticmethod
    def build_system_prompt(context_wine: dict[str, Any] | None = None) -> str:
        """Построение системного промпта сомелье с контекстом вина."""
        base_prompt = (
            "Вы — ведущий цифровой AI-сомелье платформы «Своё Вино» и эксперт «Винного гида России» Роскачества.\n"
            "Ваша цель — профессионально, дружелюбно и понятно помогать пользователям в выборе российских вин,\n"
            "описании их органолептических свойств (Вкусовой матрицы: сладость, тело, кислотность, дуб),\n"
            "и подборе идеальных гастрономических пар."
        )

        if context_wine:
            wine_info = (
                f"\n\nТекущий контекст выбранного вина:\n"
                f"- Наименование: {context_wine.get('name')}\n"
                f"- Категория: {context_wine.get('category')}\n"
                f"- Регион: {context_wine.get('region')}\n"
                f"- Сорта винограда: {', '.join(context_wine.get('grape_varieties', []))}\n"
                f"- Оценка Роскачества: {context_wine.get('roskachestvo_score')}\n"
                f"- Вкусовая матрица: Сладость={context_wine.get('sweetness')}, Тело={context_wine.get('body')}, "
                f"Кислотность={context_wine.get('acidity')}, Дуб={context_wine.get('oak')}\n"
                f"- Ароматы: {', '.join(context_wine.get('aroma_tags', []))}\n"
                f"- Описание: {context_wine.get('description')}\n"
            )
            return base_prompt + wine_info

        return base_prompt
