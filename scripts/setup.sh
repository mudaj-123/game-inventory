#!/usr/bin/env bash

# Create a complete local development environment and verify that it is usable.
set -euo pipefail

readonly REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly PYTHON_BIN="${PYTHON_BIN:-python3.12}"
readonly VENV_DIR="${VENV_DIR:-${REPOSITORY_ROOT}/.venv}"
run_checks=true

print_usage() {
    cat <<'EOF'
Usage: ./scripts/setup.sh [--skip-checks] [--help]

Create the development environment, apply migrations, and verify the project.

Options:
  --skip-checks  Do not run pytest and Ruff after setup.
  -h, --help     Show this help message and exit.
EOF
}

while (($# > 0)); do
    case "$1" in
        --skip-checks)
            run_checks=false
            ;;
        -h | --help)
            print_usage
            exit 0
            ;;
        *)
            printf 'Error: unknown option: %s\n\n' "$1" >&2
            print_usage >&2
            exit 2
            ;;
    esac
    shift
done

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

    if [[ "${run_checks}" == true ]]; then
        "${VENV_DIR}/bin/python" -m pytest
        "${VENV_DIR}/bin/python" -m ruff check .
    fi
)

printf '\nSetup completed successfully. Activate it with:\n  source %s/bin/activate\n' \
    "${VENV_DIR}"
