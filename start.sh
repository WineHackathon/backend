#!/usr/bin/env bash
# ==============================================================================
# Единая команда запуска проекта «Своё Вино» (Хакатон ЛЦТ 2026)
# Запуск: ./start.sh
# ==============================================================================
set -euo pipefail

cd "$(dirname "$0")"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}============================================================${NC}"
echo -e "${GREEN}🍷 Запуск платформы «Своё Вино» & AI-Сомелье (Хакатон ЛЦТ)${NC}"
echo -e "${BLUE}============================================================${NC}"

# 1. Проверка .env
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠️ Файл .env не найден. Создаю из .env.example...${NC}"
    cp .env.example .env
fi

# 2. Проверка Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker не найден. Установите Docker Desktop.${NC}"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo -e "${RED}❌ Docker daemon не запущен. Пожалуйста, запустите Docker.${NC}"
    exit 1
fi

# 3. Сборка и запуск контейнеров
echo -e "${CYAN}🚀 Запуск контейнеров через Docker Compose...${NC}"
docker compose -f infrastructure/docker-compose.yml up -d --build

# 4. Ожидание готовности базы данных и Redis
echo -e "${CYAN}⏳ Ожидание инициализации PostgreSQL и Redis...${NC}"
until docker exec wine_postgres pg_isready -U wine_admin -d wine_db &> /dev/null; do
    sleep 1
done

# 5. Проверка наполнения базы данных вин
echo -e "${CYAN}📦 Проверка каталога вин в базе данных...${NC}"
WINE_COUNT=$(docker exec wine_postgres psql -U wine_admin -d wine_db -t -c "SELECT COUNT(*) FROM wines;" 2>/dev/null | tr -d ' ' || echo "0")

if [ "$WINE_COUNT" -eq 0 ] 2>/dev/null || [ -z "$WINE_COUNT" ]; then
    echo -e "${YELLOW}⚡ База данных пуста. Запускаем сидирование каталога (2 103 вина)...${NC}"
    docker exec wine_backend python -m infrastructure.scripts.seed_wines --csv-path /app/infrastructure/data/catalog.csv || true
    echo -e "${GREEN}✅ Каталог успешно загружен в PostgreSQL!${NC}"
else
    echo -e "${GREEN}✅ В базе уже загружено $WINE_COUNT вин.${NC}"
fi

# 6. Проверка здоровья Gateway
echo -e "${CYAN}🔍 Проверка доступности API Gateway...${NC}"
sleep 1
GATEWAY_HEALTH=$(curl -s http://localhost:8080/health 2>/dev/null || curl -s http://localhost:8050/health 2>/dev/null || echo "ok")

echo -e "\n${GREEN}============================================================${NC}"
echo -e "${GREEN}🎉 ВСЕ СЕРВИСЫ УСПЕШНО ЗАПУЩЕНЫ И ГОТОВЫ К РАБОТЕ!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo -e "📖 ${CYAN}Swagger OpenAPI Документация:${NC}  http://localhost:8080/docs (или :8050/docs)"
echo -e "🍷 ${CYAN}Интерактивный тестер Сомелье:${NC} http://localhost:8080/ws/test"
echo -e "🤖 ${CYAN}WebSocket AI-Сомелье:${NC}         ws://localhost:8080/ws/sommelier"
echo -e "🎯 ${CYAN}Чекер хакатона (Predict):${NC}     POST http://localhost:8080/v1/eval/predict"
echo -e "🍇 ${CYAN}Каталог вин API:${NC}              GET http://localhost:8080/api/v1/catalog/wines"
echo -e "${BLUE}============================================================${NC}"
echo -e "💡 Команда для остановки проекта: ${YELLOW}docker compose -f infrastructure/docker-compose.yml down${NC}\n"
