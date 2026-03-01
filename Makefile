DC      = docker compose
DC_DEV  = FRONTEND_PORT=3080 docker compose -f docker-compose.yml -f docker-compose.dev.yml

# ── Production ────────────────────────────────────────────────────────────────

.PHONY: build
build:
	$(DC) build

.PHONY: up
up:
	$(DC) up

.PHONY: prod
prod: dev-down
	$(DC) up --build

.PHONY: down
down:
	$(DC) down

# ── Development (hot reload) ──────────────────────────────────────────────────

.PHONY: dev
dev: down
	$(DC_DEV) up --build

.PHONY: dev-down
dev-down:
	$(DC_DEV) down

# ── Logs & status ─────────────────────────────────────────────────────────────

.PHONY: logs
logs:
	$(DC) logs -f

.PHONY: ps
ps:
	$(DC) ps

# ── Cleanup ───────────────────────────────────────────────────────────────────

.PHONY: clean
clean:
	$(DC) down --volumes --remove-orphans
