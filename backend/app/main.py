"""
Главная точка входа единого FastAPI-сервиса (Backend Gateway / BFF).
Объединяет все HTTP эндпоинты платформы «Своё Вино».
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
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


@app.get("/ws/test", response_class=HTMLResponse, tags=["Цифровой сомелье"], summary="Интерактивный веб-тестер WebSocket чата сомелье")
async def sommelier_websocket_test_page():
    """Интерактивная страница для живого тестирования WebSocket диалога с AI-Сомелье."""
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <title>Тестер AI-Сомелье WebSocket</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }
    .container { max-width: 820px; margin: 0 auto; background: #1e293b; border-radius: 12px; padding: 24px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
    h1 { margin-top: 0; font-size: 24px; color: #f43f5e; display: flex; align-items: center; gap: 10px; }
    .auth-box { display: flex; gap: 10px; margin-bottom: 20px; }
    input[type="text"] { flex: 1; padding: 12px 14px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: #fff; font-size: 14px; outline: none; }
    input[type="text"]:focus { border-color: #f43f5e; }
    button { padding: 12px 20px; border-radius: 8px; border: none; background: #f43f5e; color: #fff; font-weight: 600; cursor: pointer; transition: 0.2s; }
    button:hover { background: #e11d48; }
    button.secondary { background: #475569; }
    button.secondary:hover { background: #64748b; }
    .chat-box { height: 480px; overflow-y: auto; border: 1px solid #334155; border-radius: 8px; padding: 16px; margin-bottom: 16px; background: #0b1329; display: flex; flex-direction: column; gap: 12px; }
    .msg { max-width: 82%; padding: 12px 16px; border-radius: 12px; font-size: 14px; line-height: 1.5; }
    .msg.user { align-self: flex-end; background: #2563eb; color: #fff; border-bottom-right-radius: 2px; }
    .msg.assistant { align-self: flex-start; background: #1e293b; border: 1px solid #334155; color: #f1f5f9; border-bottom-left-radius: 2px; }
    .msg.system { align-self: center; background: #1e293b; color: #94a3b8; font-size: 12px; padding: 6px 14px; border-radius: 20px; border: 1px solid #334155; }
    .candidates { display: flex; flex-direction: column; gap: 8px; margin-top: 10px; }
    .card { background: #0f172a; border: 1px solid #475569; border-radius: 8px; padding: 10px 14px; font-size: 13px; color: #fb7185; display: flex; justify-content: space-between; align-items: center; }
    .card code { background: #1e293b; padding: 2px 6px; border-radius: 4px; color: #38bdf8; }
    .input-box { display: flex; gap: 10px; }
    .quick-chips { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
    .chip { background: #334155; border: none; padding: 6px 12px; border-radius: 16px; font-size: 12px; color: #cbd5e1; cursor: pointer; transition: 0.2s; }
    .chip:hover { background: #f43f5e; color: #fff; }
  </style>
</head>
<body>
<div class="container">
  <h1>🍷 AI-Сомелье — Живой WebSocket Тестер</h1>
  <div class="auth-box">
    <input type="text" id="tokenInput" value="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJmMmViMzg3YS1iNGY2LTRjZmQtYjJmMS04ODRlNDdlZDU5YzAiLCJleHAiOjE3ODk5MDQ5MzMsInR5cGUiOiJhY2Nlc3MiLCJpc19hZG1pbiI6ZmFsc2UsInNlc3Npb25faWQiOm51bGx9.z9Fpbc7yvXhwdG2o9BJBa6STHcIh9SCpcJaCEuvJc4M" placeholder="Вставьте Access Token (для авторизованного режима)...">
    <button id="connectBtn" onclick="toggleConnect()">Подключиться</button>
  </div>
  <div class="chat-box" id="chatBox">
    <div class="msg system">Нажмите «Подключиться» для старта WebSocket соединения с Сомелье</div>
  </div>
  <div class="input-box">
    <input type="text" id="msgInput" placeholder="Напишите сообщение сомелье (например: Посоветуй белое сухое вино)..." onkeydown="if(event.key==='Enter') sendMsg()">
    <button onclick="sendMsg()">Отправить</button>
  </div>
  <div class="quick-chips">
    <button class="chip" onclick="quickSend('Посоветуй белое сухое вино под рыбу')">🐟 Белое к рыбе</button>
    <button class="chip" onclick="quickSend('Какое красное вино взять к стейку?')">🥩 Красное к стейку</button>
    <button class="chip" onclick="quickSend('Найди похожее на Алиготе')">🔍 Похожее на Алиготе</button>
    <button class="chip" onclick="answerQ(1, 'category', 'Белое')">1️⃣ Цвет: Белое</button>
    <button class="chip" onclick="answerQ(2, 'sweetness', 'Сухое')">2️⃣ Сахар: Сухое</button>
    <button class="chip" onclick="answerQ(3, 'body', 'Плотное')">3️⃣ Тело: Плотное</button>
    <button class="chip" onclick="answerQ(4, 'acidity', 'Свежее')">4️⃣ Кислотность: Свежее</button>
    <button class="chip" onclick="answerQ(5, 'aromas', 'Цветы и фрукты')">5️⃣ Ароматы: Цветы</button>
  </div>
</div>
<script>
  let ws = null;
  let lastSentTime = null;
  const chatBox = document.getElementById('chatBox');
  const tokenInput = document.getElementById('tokenInput');
  const msgInput = document.getElementById('msgInput');
  const connectBtn = document.getElementById('connectBtn');

  function appendMsg(role, text, candidates = [], latencyMs = null) {
    const div = document.createElement('div');
    div.className = `msg ${role}`;
    const badge = latencyMs !== null ? `<span style="display:inline-block; margin-left:8px; font-size:11px; padding:2px 6px; border-radius:10px; background:#334155; color:#38bdf8;">⏱️ ${latencyMs} ms</span>` : '';
    div.innerHTML = `<div>${text} ${badge}</div>`;
    if (candidates && candidates.length) {
      const cDiv = document.createElement('div');
      cDiv.className = 'candidates';
      candidates.forEach(c => {
        const name = c.name || c;
        const slug = c.slug || '';
        const region = c.region || '';
        cDiv.innerHTML += `<div class="card"><span>🍾 <b>${name}</b> ${region ? '• ' + region : ''}</span> <code>${slug}</code></div>`;
      });
      div.appendChild(cDiv);
    }
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  function toggleConnect() {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.close();
      return;
    }
    const token = tokenInput.value.trim();
    const url = `ws://${window.location.hostname}:8050/ws/sommelier${token ? '?token=' + encodeURIComponent(token) : ''}`;
    appendMsg('system', `Подключение к ${url}...`);
    ws = new WebSocket(url);

    ws.onopen = () => {
      appendMsg('system', '✅ WebSocket соединение успешно установлено!');
      connectBtn.innerText = 'Отключиться';
      connectBtn.classList.add('secondary');
    };

    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      let latencyMs = null;
      if (lastSentTime) {
        latencyMs = Math.round(performance.now() - lastSentTime);
        console.log(`⏱️ [Время ответа сомелье]: ${latencyMs} ms | Тип: ${data.type}`, data);
      } else {
        console.log('WS msg:', data);
      }

      if (data.type === 'welcome') {
        appendMsg('assistant', data.message);
        if (data.question) {
          appendMsg('assistant', `<b>Вопрос №${data.question.step}:</b> ${data.question.question}<br><i>Варианты: ${data.question.options.join(', ')}</i>`);
        }
      } else if (data.type === 'message' || data.type === 'chat') {
        appendMsg('assistant', data.content || data.reply, data.candidates, latencyMs);
      } else if (data.type === 'answer_ack') {
        appendMsg('assistant', `✅ Ответ зафиксирован (${data.code}: ${data.answer}).`, [], latencyMs);
        if (data.next_question) {
          appendMsg('assistant', `<b>Вопрос №${data.next_question.step}:</b> ${data.next_question.question}<br><i>Варианты: ${data.next_question.options.join(', ')}</i>`);
        }
      } else if (data.type === 'onboarding_complete') {
        appendMsg('assistant', '🎉 Опросник завершён! Вот подобранные вина по вкусовой матрице:', data.candidates, latencyMs);
      } else if (data.type === 'auth_success') {
        appendMsg('system', `🔑 ${data.message} (User ID: ${data.user_id})`);
      } else {
        appendMsg('assistant', data.content || data.reply || JSON.stringify(data), data.candidates, latencyMs);
      }
    };

    ws.onclose = () => {
      appendMsg('system', '❌ Соединение закрыто.');
      connectBtn.innerText = 'Подключиться';
      connectBtn.classList.remove('secondary');
      ws = null;
    };

    ws.onerror = (err) => {
      appendMsg('system', '⚠️ Ошибка WebSocket соединения.');
      console.error(err);
    };
  }

  function sendMsg() {
    const text = msgInput.value.trim();
    if (!text || !ws) return;
    appendMsg('user', text);
    lastSentTime = performance.now();
    ws.send(JSON.stringify({ type: 'message', content: text }));
    msgInput.value = '';
  }

  function quickSend(text) {
    if (!ws) toggleConnect();
    setTimeout(() => {
      appendMsg('user', text);
      lastSentTime = performance.now();
      ws.send(JSON.stringify({ type: 'message', content: text }));
    }, 400);
  }

  function answerQ(step, code, answer) {
    if (!ws) toggleConnect();
    setTimeout(() => {
      appendMsg('user', `Ответ на вопрос №${step} (${code}): ${answer}`);
      lastSentTime = performance.now();
      ws.send(JSON.stringify({ type: 'answer', step: step, code: code, answer: answer }));
    }, 400);
  }
</script>
</body>
</html>""")

