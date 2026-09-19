"""
HTTP эндпоинт чата с AI-сомелье (/api/v1/sommelier/chat).
"""
from fastapi import APIRouter
from application.dto.sommelier import SommelierChatRequestDTO, SommelierChatResponseDTO
from sommelier.app.services.rag_service import SommelierRAGService
from sommelier.app.services.llm_client import SommelierLLMClient

router = APIRouter(prefix="/api/v1/sommelier", tags=["Sommelier HTTP Chat"])


@router.post("/chat", response_model=SommelierChatResponseDTO, summary="Chat with AI Sommelier")
async def chat(request: SommelierChatRequestDTO):
    """Диалог с сомелье с использованием RAG и LLM."""
    rag_service = SommelierRAGService()
    llm_client = SommelierLLMClient()

    system_prompt = rag_service.build_system_prompt()
    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    reply = await llm_client.generate_response(system_prompt, messages)
    return SommelierChatResponseDTO(
        reply=reply,
        recommended_slugs=[],
        food_pairings=[],
    )
