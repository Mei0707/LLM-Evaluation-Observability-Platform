PYTHON := .venv/bin/python
.PHONY: setup dev frontend worker test build up down benchmark reliability secure-setup
setup:
	python3 -m venv .venv
	$(PYTHON) -m pip install -r requirements.lock
	$(PYTHON) -m pip install --no-deps -e .
	cd frontend && npm ci
dev:
	$(PYTHON) -m uvicorn backend.app.api:app --host 127.0.0.1 --port 8000 --reload
frontend:
	cd frontend && npm run dev
worker:
	$(PYTHON) -m backend.app.worker
test:
	$(PYTHON) -m pytest -q
build:
	cd frontend && npm run build
up:
	docker compose up --build -d
down:
	docker compose down
benchmark:
	$(PYTHON) -m benchmarks.run --sizes 100 1000 5000 --concurrency 1 3 5 --output benchmarks/results/latest.json
reliability:
	docker compose build migrate
	$(PYTHON) -m benchmarks.distributed
secure-setup:
	$(PYTHON) scripts/security_setup.py
