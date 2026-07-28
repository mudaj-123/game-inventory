#!/usr/bin/env bash

# Create a complete local development environment and verify that it is usable.
set -euo pipefail

readonly REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly PYTHON_BIN="${PYTHON_BIN:-python3.12}"
readonly VENV_DIR="${VENV_DIR:-${REPOSITORY_ROOT}/.venv}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    printf 'Error: Python 3.12 is required, but %s was not found.\n' "${PYTHON_BIN}" >&2
    exit 1
fi

if ! "${PYTHON_BIN}" -c \
    'import sys; raise SystemExit(sys.version_info[:2] != (3, 12))'; then
    printf 'Error: %s must be Python 3.12.\n' "${PYTHON_BIN}" >&2
    exit 1
fi

if command -v uv >/dev/null 2>&1; then
    UV_PROJECT_ENVIRONMENT="${VENV_DIR}" uv sync \
        --project "${REPOSITORY_ROOT}" \
        --all-extras \
        --locked \
        --python "${PYTHON_BIN}"
else
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
    "${VENV_DIR}/bin/python" -m pip install --upgrade pip
    "${VENV_DIR}/bin/python" -m pip install -e "${REPOSITORY_ROOT}[dev]"
fi

if [[ ! -e "${REPOSITORY_ROOT}/.env" ]]; then
    cp "${REPOSITORY_ROOT}/.env.example" "${REPOSITORY_ROOT}/.env"
fi

(
    cd "${REPOSITORY_ROOT}"
    "${VENV_DIR}/bin/python" -m alembic upgrade head
    "${VENV_DIR}/bin/python" -c 'from app.main import app; assert app'
)

printf '\nSetup completed successfully. Activate it with:\n  source %s/bin/activate\n' \
    "${VENV_DIR}"
