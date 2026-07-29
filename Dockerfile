FROM python:3.12.11-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

COPY --from=ghcr.io/astral-sh/uv:0.8.3 /uv /usr/local/bin/uv
WORKDIR /build
COPY pyproject.toml uv.lock README.md ./
COPY app ./app
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12.11-slim-bookworm AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system --gid 10001 inventory \
    && useradd --system --uid 10001 --gid inventory --home-dir /app inventory

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=inventory:inventory app ./app
COPY --chown=inventory:inventory alembic ./alembic
COPY --chown=inventory:inventory alembic.ini ./alembic.ini
COPY --chown=inventory:inventory data/catalog ./data/catalog
COPY --chown=inventory:inventory docker-entrypoint.sh ./docker-entrypoint.sh
RUN mkdir -p data/exports \
    && chown -R inventory:inventory /app \
    && chmod 0755 docker-entrypoint.sh

USER inventory
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
