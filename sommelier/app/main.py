"""
Главная точка входа специализированного сервиса AI-Сомелье.
Включает HTTP эндпоинты и WebSocket для интерактивного стриминга диалога.
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sommelier.app.config import settings
from sommelier.app.api.v1.chat import router as chat_router
from sommelier.app.api.v1.onboarding import router as onboarding_router
from sommelier.app.websocket.sommelier_ws import router as ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [SommelierService] %(message)s",
)
logger = logging.getLogger("sommelier_service")

app = FastAPI(
    title=settings.app_name,
    description="Специализированный микросервис AI-Сомелье и рекомендаций вин",
    version=settings.app_version,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(onboarding_router)
app.include_router(ws_router)


@app.get("/health", tags=["Health"])
async def health():
    """Healthcheck сервиса сомелье."""
    return JSONResponse(
        status_code=200,
        content={"status": "ok", "service": "sommelier-service"},
    )
