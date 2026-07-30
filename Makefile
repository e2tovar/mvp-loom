# Makefile — entradas de verificación del proyecto.
# El CI (.github/workflows/ci.yml) llama a estos mismos targets: un solo sitio
# donde vive la definición de "verificado".

PY := .venv/bin/python
FROZEN_CACHE := eval/fixtures/llm-cache

.PHONY: help lint test seed gates verify up down

help:
	@echo "make lint    — ruff sobre backend/ eval/ tests/"
	@echo "make test    — suite completa (integración se omite sin Neo4j)"
	@echo "make seed    — siembra el grafo desde la caché congelada (gratis)"
	@echo "make gates   — los tres gates de eval en modo estricto (fallan si se omitirían)"
	@echo "make verify  — lint + test + seed + gates. Lo que el CI ejecuta."
	@echo "make up/down — arranca/para Neo4j"

up:
	docker compose up -d
	@echo "Esperando a Neo4j…"
	@for i in $$(seq 1 40); do \
		$(PY) -c "from backend.graph import client; client.get_driver().verify_connectivity()" \
			2>/dev/null && echo "Neo4j listo" && exit 0; \
		sleep 3; \
	done; \
	echo "Neo4j no respondió a tiempo" && exit 1

down:
	docker compose down

lint:
	.venv/bin/ruff check backend/ eval/ tests/

test:
	$(PY) -m pytest tests/ -q

seed:
	LOOM_CACHE_DIR=$(FROZEN_CACHE) $(PY) -m eval.seed

gates:
	LOOM_EVAL_STRICT=1 LOOM_CACHE_DIR=$(FROZEN_CACHE) $(PY) -m pytest tests/eval -v -rs

verify: lint test seed gates
	@echo ""
	@echo "verificado: lint, suite, siembra y los tres gates medidos de verdad."
