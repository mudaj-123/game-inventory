"""原生部署入口：等待数据库、执行 Alembic、启动 Web 并持续记录日志。"""

import asyncio
import logging
import subprocess
import sys
import time

import uvicorn
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.runtime_logging import configure_logging

logger = logging.getLogger(__name__)


async def wait_for_database() -> None:
    try:
        for attempt in range(30):
            try:
                async with asyncio.timeout(3), engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
                return
            except Exception:
                logger.warning("Database unavailable; startup attempt %s/30", attempt + 1)
                await asyncio.sleep(2)
        raise RuntimeError("Database did not become ready")
    finally:
        await engine.dispose()


def main() -> None:
    configure_logging()
    try:
        if settings.app_env == "production":
            if not settings.database_url.startswith("postgresql+"):
                raise ValueError("Production requires PostgreSQL")
            if len(settings.secret_key) < 32 or "CHANGE_ME" in settings.secret_key:
                raise ValueError("Configure a strong SECRET_KEY before startup")
        logger.info("Application startup requested")
        asyncio.run(wait_for_database())
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"], capture_output=True, text=True
        )
        if result.returncode:
            raise RuntimeError("Alembic migration failed; Web server not started")
        logger.info("Alembic upgrade completed")
        if settings.auto_import_local_catalog:
            if settings.local_catalog_path.is_file():
                imported = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "app.cli",
                        "import-catalog",
                        str(settings.local_catalog_path),
                        "--mode",
                        settings.catalog_import_mode,
                    ],
                    capture_output=True,
                    text=True,
                )
                if imported.returncode:
                    raise RuntimeError("Local catalog import failed; review configured CSV")
                logger.info("Local catalog import completed; existing confirmed products preserved")
            else:
                logger.warning(
                    "Local catalog file missing; manual barcode registration remains available"
                )
        started = time.monotonic()
        uvicorn.run(
            "app.main:app",
            host=settings.app_host,
            port=settings.app_port,
            log_config=None,
            access_log=False,
        )
        logger.info("Application stopped after %.1f seconds", time.monotonic() - started)
    except Exception as error:
        logger.error(
            "Application startup failed (%s); check configuration/database/migrations",
            type(error).__name__,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
