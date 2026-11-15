PY ?= .venv/Scripts/python
ifeq ($(OS),)
PY = .venv/bin/python
endif

.PHONY: install seed dev test eval lint demo api web worker gigsim mcp contract e2e client

install:
	$(PY) -m pip install -e ".[dev]"
	cd apps/web && npm install

seed:            ## download Kaggle data, generate synthetic data, build indexes
	$(PY) -m scripts.prepare_kaggle
	$(PY) -m scripts.generate_synthetic
	$(PY) -m rag.ingest.build

gigsim:
	$(PY) -m uvicorn gigsim.app:app --port 8081

mcp:
	$(PY) -m scripts.run_mcp_servers

api:
	$(PY) -m uvicorn apps.api.main:app --port 8000

worker:
	$(PY) -m arq worker.main.WorkerSettings

web:
	cd apps/web && npm run dev

dev:             ## everything for local development
	$(PY) -m scripts.dev

test:
	MODEL_PROFILE=offline $(PY) -m pytest -q

contract:
	MODEL_PROFILE=offline $(PY) -m pytest -q tests/contract

e2e:
	cd apps/web && npx playwright test

eval:
	$(PY) -m evals.runners.run_all

demo:
	$(PY) -m scripts.demo_single_agent

client:          ## regenerate TypeScript API client from FastAPI OpenAPI
	$(PY) -m scripts.export_openapi
	cd apps/web && npm run gen:api

lint:
	$(PY) -m ruff check .
	$(PY) -m scripts.check_repo
