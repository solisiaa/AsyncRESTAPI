.PHONY: up down migrate seed test lint fmt docs build logs

up:
	docker compose up -d

down:
	docker compose down

down-v:
	docker compose down -v

migrate:
	alembic upgrade head

migrate-down:
	alembic downgrade -1

seed:
	python scripts/seed.py

test:
	pytest -v

test-cov:
	pytest -v --cov=app --cov-report=html --cov-fail-under=85

lint:
	ruff check .
	mypy app

fmt:
	ruff format .
	ruff check --fix .

docs:
	@echo "Open http://localhost:8000/docs"

build:
	docker compose build

logs:
	docker compose logs -f api
