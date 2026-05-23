#!/usr/bin/env sh
set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

if [ ! -f .env ]; then
  echo "No .env found. Copy .env.production.example to .env and fill BOT_TOKEN, DOMAIN and PUBLIC_BASE_URL." >&2
  exit 1
fi

mkdir -p data
docker compose -f "$COMPOSE_FILE" pull caddy || true
docker compose -f "$COMPOSE_FILE" up -d --build
docker compose -f "$COMPOSE_FILE" ps
