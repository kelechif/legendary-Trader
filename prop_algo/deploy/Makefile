# One-shot DX helpers for prop_algo local compose (GNU make).
# From this directory: make up | make status | make smoke
# Windows: prefer manage.ps1 if make is unavailable.

COMPOSE   := docker compose
LIGHT     := -f docker-compose.yml
TORCH     := -f docker-compose.yml -f docker-compose.torch.yml --profile torch
METRICS   := -f docker-compose.yml -f docker-compose.metrics.yml --profile metrics
ALL       := -f docker-compose.yml -f docker-compose.torch.yml -f docker-compose.metrics.yml --profile torch --profile metrics
REPO_ROOT := ../..
TAIL      ?= 100

.PHONY: up up-torch up-metrics up-all down ps status smoke logs

up:
	$(COMPOSE) $(LIGHT) up -d --build

up-torch:
	$(COMPOSE) $(TORCH) up -d --build

up-metrics:
	$(COMPOSE) $(METRICS) up -d --build

up-all:
	$(COMPOSE) $(ALL) up -d --build

down:
	$(COMPOSE) $(ALL) down

ps status:
	$(COMPOSE) $(ALL) ps

smoke:
	cd $(REPO_ROOT) && python prop_algo/deploy/smoke_test.py

logs:
	$(COMPOSE) $(ALL) logs --tail=$(TAIL) -f
