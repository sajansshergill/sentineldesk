PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip
DATA_DIR ?= ./var
DATA_N ?= 2500

.PHONY: install data train api console eval smoke

install:
	python3 -m venv .venv
	$(PIP) install -r requirements.txt
	cd apps/console && npm install

data:
	$(PYTHON) -m data.generator.main --out $(DATA_DIR) --n $(DATA_N)

train: data
	$(PYTHON) -m services.anomaly.train --data $(DATA_DIR) --out $(DATA_DIR)/model/iforest.joblib

api:
	MODE=local SENTINEL_DATA_DIR=$(DATA_DIR) uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000

console:
	cd apps/console && NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev

eval:
	$(PYTHON) -m evals.run_all --data $(DATA_DIR)

smoke:
	$(PYTHON) -m compileall apps services data evals
	cd apps/console && npm run lint && npm run typecheck && npm run build
