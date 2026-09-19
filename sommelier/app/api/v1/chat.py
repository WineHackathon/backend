"""
HTTP эндпоинт чата с AI-сомелье (/api/v1/sommelier/chat).
"""
import logging
from fastapi import APIRouter
from application.adapters.database.db_session import create_session
from application.dto.sommelier import SommelierChatRequestDTO, SommelierChatResponseDTO
from application.services.catalog_service import CatalogService
from sommelier.app.services.rag_service import SommelierRAGService
from sommelier.app.services.llm_client import SommelierLLMClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sommelier", tags=["Sommelier HTTP Chat"])


@router.post("/chat", response_model=SommelierChatResponseDTO, summary="Chat with AI Sommelier")
async def chat(request: SommelierChatRequestDTO):
    """Диалог с сомелье с использованием RAG и LLM."""
    rag_service = SommelierRAGService()
    llm_client = SommelierLLMClient()

    # Извлечение последнего сообщения пользователя для подбора релевантных вин
    last_user_msg = next((m.content for m in reversed(request.messages) if m.role == "user"), "")
    recommended_slugs: list[str] = []

    try:
        async with create_session() as session:
            cat_service = CatalogService(session)
            if last_user_msg:
                found = await cat_service.list_wines(query=last_user_msg, limit=3)
                if found.items:
                    recommended_slugs = [w.slug for w in found.items]
            if not recommended_slugs:
                popular = await cat_service.search_by_taste_matrix(limit=3)
                recommended_slugs = [w.slug for w in popular]
    except Exception as exc:
        logger.warning(f"Ошибка при подборе рекомендаций вин в чате сомелье: {exc}")

    system_prompt = rag_service.build_system_prompt()
    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    reply = await llm_client.generate_response(system_prompt, messages)
    return SommelierChatResponseDTO(
        reply=reply,
        recommended_slugs=recommended_slugs,
        food_pairings=[],
    )
