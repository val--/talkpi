.PHONY: help up down build logs restart clean

# Default target
.DEFAULT_GOAL := help

# Variables
COMPOSE_FILE = docker-compose.server.yml
COMPOSE = docker compose -f $(COMPOSE_FILE)

help: ## Affiche cette aide
	@echo "Commandes disponibles:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

up: ## Démarre le serveur (build + up)
	$(COMPOSE) up -d --build

down: ## Arrête le serveur
	$(COMPOSE) down

restart: ## Redémarre le serveur
	$(COMPOSE) restart

logs: ## Affiche les logs du serveur
	$(COMPOSE) logs -f

build: ## Rebuild l'image Docker
	$(COMPOSE) build --no-cache

clean: ## Arrête et supprime les conteneurs
	$(COMPOSE) down -v

status: ## Affiche le statut des conteneurs
	$(COMPOSE) ps

shell: ## Ouvre un shell dans le conteneur
	$(COMPOSE) exec app /bin/bash

# Commandes locales (docker-compose.yml)
local-up: ## Démarre en mode local (port 5001)
	docker compose -f docker-compose.yml up -d --build

local-down: ## Arrête le mode local
	docker compose -f docker-compose.yml down

local-logs: ## Logs du mode local
	docker compose -f docker-compose.yml logs -f

