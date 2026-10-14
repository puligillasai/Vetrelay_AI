.PHONY: install dev lint typecheck test test-one run-backend run-frontend run-frontend-mvp1 run-frontend-mvp2

install:
	pip install -e ".[dev]"

dev:
	uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

lint:
	ruff check . && ruff format --check .

lint-fix:
	ruff check --fix . && ruff format .

typecheck:
	mypy backend/

test:
	pytest tests/ -v

# Run a single test by name — usage: make test-one T=test_soap_summarise
test-one:
	pytest tests/ -v -k "$(T)"

# Unified app (MVP 1 + MVP 2 with sidebar toggle) — primary entry point
run-frontend:
	streamlit run frontend/app.py --server.port 8501

run-frontend-mvp1:
	streamlit run frontend/mvp1_client.py --server.port 8502

run-frontend-mvp2:
	streamlit run frontend/mvp2_clinic_console.py --server.port 8503
