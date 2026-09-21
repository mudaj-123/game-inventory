"""实际 pg_dump -> 新临时库 -> pg_restore -> Alembic -> 全行指纹比对。"""

import asyncio
import os

import pytest

from app import operations
from app.config import settings
from tests.test_postgres_concurrency import (  # noqa: F401
    add_catalog,
    request,
    run_scan,
)
from tests.test_postgres_concurrency import (
    postgres_factory as postgres_factory,
)

pytestmark = pytest.mark.postgres


async def test_official_tools_restore_preserves_all_rows(postgres_factory, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_url", os.environ["TEST_POSTGRES_URL"])
    await add_catalog(postgres_factory, "00009999")
    await run_scan(postgres_factory, request("00009999", "IN"))
    before = await operations.fingerprint(operations.database_url().database)
    dump = await asyncio.to_thread(operations.backup, tmp_path)
    assert dump.read_bytes().startswith(b"PGDMP")
    after = await asyncio.to_thread(operations.drill, dump)
    assert before == after
    assert before["users"]["rows"] == 1
    assert before["products"]["rows"] == 1
    assert before["inventory_transactions"]["rows"] == 1
    assert before["stock_alerts"]["rows"] == 1
    # No live rows changed and no temporary database remains.
    assert await operations.fingerprint(operations.database_url().database) == before
    databases = await asyncio.to_thread(
        operations.pg_run,
        "psql",
        "-XAt",
        "-c",
        "SELECT datname FROM pg_database WHERE datname LIKE 'inventory_drill_%'",
    )
    assert not databases.strip()
