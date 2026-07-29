#!/usr/bin/env bash
set -Eeuo pipefail

readonly COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
readonly ENV_FILE="${ENV_FILE:-.env.production}"
readonly BACKUP_DIR="${BACKUP_DIR:-backups}"
readonly RETENTION_DAYS="${RETENTION_DAYS:-7}"

[[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] || { echo "RETENTION_DAYS must be a non-negative integer" >&2; exit 2; }
[[ -f "$ENV_FILE" ]] || { echo "Environment file not found: $ENV_FILE" >&2; exit 2; }

POSTGRES_USER="$(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T db printenv POSTGRES_USER)"
POSTGRES_DB="$(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T db printenv POSTGRES_DB)"
readonly POSTGRES_USER POSTGRES_DB
[[ -n "$POSTGRES_USER" && -n "$POSTGRES_DB" ]] || { echo "Database identity is empty" >&2; exit 2; }

mkdir -p "$BACKUP_DIR"
timestamp="$(TZ=UTC date +%Y%m%dT%H%M%SZ)"
backup_file="${BACKUP_DIR%/}/${POSTGRES_DB}_${timestamp}.dump"
partial_file="${backup_file}.partial"
trap 'rm -f "$partial_file"' EXIT

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T db \
  pg_dump --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --format=custom \
  --no-owner --no-acl >"$partial_file"

[[ -s "$partial_file" ]] || { echo "Backup is empty; refusing to keep it" >&2; exit 1; }
mv "$partial_file" "$backup_file"
find "$BACKUP_DIR" -maxdepth 1 -type f -name "${POSTGRES_DB}_*.dump" \
  -mtime "+$RETENTION_DAYS" -delete
trap - EXIT
printf 'Backup complete: %s\n' "$backup_file"
