#!/usr/bin/env bash
set -Eeuo pipefail

usage() { echo "Usage: $0 BACKUP_FILE" >&2; exit 2; }
[[ $# -eq 1 ]] || usage

readonly BACKUP_FILE="$1"
readonly COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
readonly ENV_FILE="${ENV_FILE:-.env.production}"
[[ -s "$BACKUP_FILE" ]] || { echo "Backup file missing or empty: $BACKUP_FILE" >&2; exit 2; }
[[ -f "$ENV_FILE" ]] || { echo "Environment file not found: $ENV_FILE" >&2; exit 2; }

POSTGRES_USER="$(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T db printenv POSTGRES_USER)"
POSTGRES_DB="$(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T db printenv POSTGRES_DB)"
readonly POSTGRES_USER POSTGRES_DB
[[ -n "$POSTGRES_USER" && -n "$POSTGRES_DB" ]] || { echo "Database identity is empty" >&2; exit 2; }

echo "WARNING: this will replace objects in target database '$POSTGRES_DB'."
echo "Backup: $BACKUP_FILE"
read -r -p "Type the exact database name '$POSTGRES_DB' to continue: " confirmation
[[ "$confirmation" == "$POSTGRES_DB" ]] || { echo "Confirmation did not match; restore cancelled." >&2; exit 1; }

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T db \
  pg_restore --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --clean --if-exists --no-owner --no-acl --exit-on-error <"$BACKUP_FILE"
echo "Restore complete for database: $POSTGRES_DB"
