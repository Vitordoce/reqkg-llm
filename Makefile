PYTHON ?= python3
PYTHON_VERSION := 3.14
VENV := .venv
VENV_PYTHON := $(VENV)/bin/python
PIP_INSTALL := $(VENV_PYTHON) -m pip install --require-hashes --only-binary :all:
COMPOSE := docker compose
COMPOSE_WITHOUT_ENV := $(if $(wildcard .env),,NEO4J_USER=unused NEO4J_PASSWORD=unused )
NEO4J_WAIT_SECONDS ?= 180

.PHONY: check-python venv test neo4j-up neo4j-wait neo4j-down graph-fixture

check-python:
	@$(PYTHON) -c 'import sys; sys.exit(0 if sys.version_info[:2] == tuple(map(int, "$(PYTHON_VERSION)".split("."))) else 1)' || { \
		echo "$(PYTHON) é $$($(PYTHON) --version 2>&1). O lock foi resolvido para Python $(PYTHON_VERSION)."; \
		echo "Instale com: brew install python@$(PYTHON_VERSION), e rode: make <alvo> PYTHON=python$(PYTHON_VERSION)"; exit 1; }
	@echo "Python $$($(PYTHON) -c 'import platform; print(platform.python_version())') ok"

venv: check-python
	@if [ -x $(VENV_PYTHON) ] && ! $(VENV_PYTHON) -c 'import sys; sys.exit(0 if sys.version_info[:2] == tuple(map(int, "$(PYTHON_VERSION)".split("."))) else 1)'; then \
		echo "$(VENV) foi criado com outro Python. Apague $(VENV) e rode make venv de novo."; exit 1; fi
	@if [ -x $(VENV_PYTHON) ]; then echo "$(VENV) já existe"; else $(PYTHON) -m venv $(VENV); fi
	$(PIP_INSTALL) -r requirements.lock

test: venv
	$(VENV_PYTHON) -m pytest code -q

neo4j-up:
	@$(PYTHON) tools/check_env.py
	$(COMPOSE) up -d neo4j

neo4j-wait:
	@container=$$($(COMPOSE_WITHOUT_ENV)$(COMPOSE) ps -q neo4j); \
	if [ -z "$$container" ]; then echo "Neo4j não está rodando. Rode make neo4j-up."; exit 1; fi; \
	elapsed=0; \
	while [ $$elapsed -lt $(NEO4J_WAIT_SECONDS) ]; do \
		status=$$(docker inspect -f '{{.State.Health.Status}}' $$container); \
		if [ "$$status" = healthy ]; then echo "Neo4j healthy após $${elapsed}s"; exit 0; fi; \
		if [ "$$status" = unhealthy ]; then echo "Neo4j unhealthy. Veja docker compose logs neo4j."; exit 1; fi; \
		sleep 2; elapsed=$$((elapsed + 2)); \
	done; \
	echo "Neo4j não ficou healthy em $(NEO4J_WAIT_SECONDS)s. Veja docker compose logs neo4j."; exit 1

neo4j-down:
	$(COMPOSE_WITHOUT_ENV)$(COMPOSE) down

graph-fixture: neo4j-up neo4j-wait
	PYTHONPATH=code $(VENV_PYTHON) -m graph fixture
