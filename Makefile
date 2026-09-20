# ==============================================================================
# Makefile платформы «Своё Вино» & AI-Сомелье (Хакатон ЛЦТ 2026)
# ==============================================================================

.PHONY: help up start down restart test seed logs clean

help:
	@echo "Команды платформы «Своё Вино»:"
	@echo "  make up       - Запуск проекта в один клик (сборка, запуск, БД, чеки)"
	@echo "  make down     - Остановка всех контейнеров"
	@echo "  make restart  - Перезапуск сервисов"
	@echo "  make test     - Запуск полного набора автотестов (pytest)"
	@echo "  make seed     - Наполнение базы данных 2 103 российскими винами"
	@echo "  make logs     - Просмотр логов всех контейнеров в реальном времени"

up: start

start:
	@./start.sh

down:
	@docker compose -f infrastructure/docker-compose.yml down

restart:
	@docker compose -f infrastructure/docker-compose.yml restart

test:
	@PYTHONPATH=. pytest -v

seed:
	@docker exec wine_backend python -m infrastructure.scripts.seed_wines --csv-path /app/infrastructure/data/catalog.csv

logs:
	@docker compose -f infrastructure/docker-compose.yml logs -f
