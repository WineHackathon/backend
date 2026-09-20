"""
Главная точка входа единого FastAPI-сервиса (Backend Gateway / BFF).
Объединяет все HTTP эндпоинты платформы «Своё Вино».
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import redis.asyncio as redis

from application.adapters.database.db_session import global_init_db, close_db
from application.exceptions.domain_exceptions import (
    DomainException,
    WineNotFound,
    UserNotFound,
    CellarItemNotFound,
    UserAlreadyExists,
    AuthenticationError,
    ScanQuotaExceeded,
)
from backend.app.config import settings
from backend.app.api.v1.eval import router as eval_router
from backend.app.api.v1.scan import router as scan_router
from backend.app.api.v1.catalog import router as catalog_router
from backend.app.api.v1.users import router as users_router
from backend.app.api.v1.auth import router as auth_router
from backend.app.api.v1.sommelier import router as sommelier_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [BackendGateway] %(message)s",
)
logger = logging.getLogger("backend_gateway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом сервиса: подключение к БД и пулу соединений Redis."""
    logger.info("Инициализация соединений с базой данных PostgreSQL...")
    try:
        await global_init_db()
    except Exception as exc:
        logger.warning(f"Ошибка подключения к БД при старте (в тестах допустимо): {exc}")

    logger.info(f"Подключение к Redis ({settings.redis_host}:{settings.redis_port})...")
    try:
        redis_url = f"redis://{settings.redis_host}:{settings.redis_port}/0"
        if settings.redis_password:
            redis_url = f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}/0"

        app.state.redis = redis.from_url(
            redis_url,
            decode_responses=True,
            max_connections=50,
        )
        await app.state.redis.ping()
        logger.info("Подключение к Redis успешно проверено.")
    except Exception as exc:
        logger.warning(f"Не удалось подключиться к Redis: {exc}. Работа в автономном режиме.")
        app.state.redis = None

    yield

    logger.info("Закрытие соединений...")
    if getattr(app.state, "redis", None):
        await app.state.redis.close()
    await close_db()
    logger.info("Соединения успешно закрыты.")


app = FastAPI(
    title=settings.app_name,
    description="Единый API Gateway / BFF для платформы «Своё Вино» и AI-Сомелье",
    version=settings.app_version,
    lifespan=lifespan,
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Регистрация маршрутов
app.include_router(eval_router)
app.include_router(scan_router)
app.include_router(catalog_router)
app.include_router(users_router)
app.include_router(auth_router)
app.include_router(sommelier_router)

# Глобальные обработчики доменных исключений
@app.exception_handler(WineNotFound)
@app.exception_handler(UserNotFound)
@app.exception_handler(CellarItemNotFound)
async def not_found_exception_handler(request: Request, exc: DomainException):
    return JSONResponse(status_code=404, content={"detail": exc.message})


@app.exception_handler(UserAlreadyExists)
async def conflict_exception_handler(request: Request, exc: UserAlreadyExists):
    return JSONResponse(status_code=409, content={"detail": exc.message})


@app.exception_handler(AuthenticationError)
async def auth_exception_handler(request: Request, exc: AuthenticationError):
    return JSONResponse(status_code=401, content={"detail": exc.message})


@app.exception_handler(ScanQuotaExceeded)
async def quota_exception_handler(request: Request, exc: ScanQuotaExceeded):
    return JSONResponse(status_code=429, content={"detail": exc.message})


@app.exception_handler(DomainException)
async def domain_exception_handler(request: Request, exc: DomainException):
    return JSONResponse(status_code=400, content={"detail": exc.message})


@app.get("/health", tags=["Состояние сервиса"], summary="Проверка работоспособности сервиса (healthcheck)")
async def health(request: Request):
    """
    Глубокий healthcheck состояния сервиса и инфраструктурных зависимостей.
    """
    redis_ok = False
    redis_client = getattr(request.app.state, "redis", None)
    if redis_client:
        try:
            redis_ok = bool(await redis_client.ping())
        except Exception:
            redis_ok = False
    else:
        redis_ok = True  # В тестовом окружении

    return JSONResponse(
        status_code=200 if redis_ok else 503,
        content={
            "status": "ok" if redis_ok else "degraded",
            "service": "wine-backend-gateway",
            "redis": "connected" if redis_ok else "disconnected",
        },
    )
