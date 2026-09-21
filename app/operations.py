"""跨平台 PostgreSQL 官方工具备份、空库恢复和隔离演练。"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings

ROOT = Path(__file__).resolve().parents[1]
TABLES = ("users", "catalog_entries", "products", "inventory_transactions", "stock_alerts")
logger = logging.getLogger(__name__)


def database_url(database: str | None = None) -> URL:
    url = make_url(settings.database_url)
    if url.get_backend_name() != "postgresql":
        raise ValueError("PostgreSQL DATABASE_URL is required")
    if database is not None:
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]{0,62}", database):
            raise ValueError("Target database must be a simple PostgreSQL identifier")
        url = url.set(database=database)
    return url


def pg_run(tool: str, *arguments: str, database: str | None = None) -> str:
    url = database_url(database)
    binary = tool + (".exe" if os.name == "nt" else "")
    configured = os.environ.get("POSTGRES_BIN")
    executable = str(Path(configured) / binary) if configured else shutil.which(binary)
    if not executable:
        raise RuntimeError(f"Install PostgreSQL tools or set POSTGRES_BIN ({tool})")
    env = os.environ.copy()
    # Derive every connection field from one authoritative URL; never log libpq stderr.
    env.update(
        PGHOST=url.host or "localhost",
        PGPORT=str(url.port or 5432),
        PGUSER=url.username or "",
        PGDATABASE=url.database or "",
        PGPASSWORD=url.password or "",
        PGCONNECT_TIMEOUT="10",
    )
    sslmode = url.query.get("sslmode") or url.query.get("ssl")
    if sslmode:
        env["PGSSLMODE"] = str(sslmode)
    result = subprocess.run([executable, *arguments], env=env, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(
            f"{tool} failed (exit {result.returncode}); check connection/tool/permissions"
        )
    return result.stdout


def migrate(database: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url(database).render_as_string(hide_password=False)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(
            "Alembic upgrade failed; check database availability and migration revision"
        )


async def fingerprint(database: str) -> dict[str, dict[str, object]]:
    """Consistent snapshot with full-row hashes; never output passwords or user data."""
    engine = create_async_engine(database_url(database), isolation_level="REPEATABLE READ")
    result = {}
    try:
        async with engine.begin() as connection:
            for table in TABLES:
                exists = await connection.scalar(text("SELECT to_regclass(:name)"), {"name": table})
                if exists is None:
                    continue  # Older dumps may not have an alert table yet.
                digest = hashlib.sha256()
                count = 0
                rows = await connection.stream(
                    text(f"SELECT row_to_json(t)::text FROM (SELECT * FROM {table} ORDER BY id) t")
                )
                async for row in rows:
                    digest.update(row[0].encode())
                    digest.update(b"\n")
                    count += 1
                result[table] = {"rows": count, "sha256": digest.hexdigest()}
            invalid = await connection.scalar(
                text("""
                SELECT EXISTS(SELECT 1 FROM products WHERE quantity < 0)
                OR EXISTS(SELECT barcode FROM products GROUP BY barcode HAVING count(*) > 1)
                OR EXISTS(SELECT 1 FROM inventory_transactions r
                    LEFT JOIN inventory_transactions o ON o.id = r.related_transaction_id
                    WHERE r.operation_type = 'REVERSAL' AND
                        (o.id IS NULL OR o.operation_type = 'REVERSAL'
                         OR r.product_id <> o.product_id OR r.quantity_delta <> -o.quantity_delta))
                OR EXISTS(SELECT 1 FROM inventory_transactions
                    WHERE quantity_before + quantity_delta <> quantity_after OR quantity_after < 0)
            """)
            )
            if invalid:
                raise RuntimeError("Inventory or reversal integrity validation failed")
    finally:
        await engine.dispose()
    return result


def backup(directory: Path, retention_days: int = 30) -> Path:
    if retention_days < 1:
        raise ValueError("Retention days must be positive")
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    final = directory / f"inventory_{stamp}_{uuid.uuid4().hex[:8]}.dump"
    temporary = Path(str(final) + ".tmp")
    try:
        pg_run("pg_dump", "--format=custom", "--no-password", f"--file={temporary}")
        if not temporary.is_file() or not temporary.stat().st_size:
            raise RuntimeError("pg_dump produced an empty file")
        pg_run("pg_restore", "--list", str(temporary))
        temporary.replace(final)
    finally:
        temporary.unlink(missing_ok=True)
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    for old in directory.glob("inventory_*.dump"):
        if datetime.fromtimestamp(old.stat().st_mtime, UTC) < cutoff:
            old.unlink()
    logger.info("Backup completed: %s", final)
    return final


def restore(dump: Path, target: str, confirm: str) -> dict[str, dict[str, object]]:
    if target != confirm:
        raise ValueError("Confirm target must exactly match target database")
    database_url(target)
    if target == database_url().database:
        raise ValueError(
            "Restore must use a separate empty database, never the configured live database"
        )
    if not dump.is_file():
        raise ValueError("Backup file not found")
    count = pg_run(
        "psql",
        "--no-password",
        "-XAt",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        "SELECT count(*) FROM pg_tables WHERE schemaname='public'",
        database=target,
    )
    if count.strip() != "0":
        raise ValueError("Restore target is not empty; create a new database")
    pg_run("pg_restore", "--list", str(dump))
    pg_run(
        "pg_restore",
        "--no-password",
        "--no-owner",
        "--no-acl",
        "--exit-on-error",
        "--single-transaction",
        f"--dbname={target}",
        str(dump),
        database=target,
    )
    migrate(target)
    result = asyncio.run(fingerprint(target))
    logger.info("Restore, migration and inventory integrity checks completed")
    return result


def drill(dump: Path) -> dict[str, dict[str, object]]:
    # Never restore or drop a caller-supplied database name in a drill.
    target = "inventory_drill_" + uuid.uuid4().hex
    pg_run("createdb", "--no-password", target)
    try:
        return restore(dump, target, target)
    finally:
        pg_run("dropdb", "--no-password", target)


def main() -> None:
    from app.runtime_logging import configure_logging

    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("backup")
    b.add_argument("--directory", type=Path, default=os.environ.get("BACKUP_DIR"))
    b.add_argument(
        "--retention-days", type=int, default=int(os.environ.get("BACKUP_RETENTION_DAYS", "30"))
    )
    r = sub.add_parser("restore")
    r.add_argument("dump", type=Path)
    r.add_argument("--target", required=True)
    r.add_argument("--confirm", required=True)
    d = sub.add_parser("drill")
    d.add_argument("dump", type=Path)
    sub.add_parser("fingerprint")
    args = parser.parse_args()
    try:
        if args.command == "backup":
            if not args.directory:
                parser.error("--directory or BACKUP_DIR is required")
            print(backup(args.directory, args.retention_days))
        elif args.command == "restore":
            print(json.dumps(restore(args.dump, args.target, args.confirm), indent=2))
        elif args.command == "drill":
            print(json.dumps(drill(args.dump), indent=2))
        else:
            print(json.dumps(asyncio.run(fingerprint(database_url().database)), indent=2))
    except Exception as error:
        # Unexpected exceptions may include connection credentials. Never print their text.
        logger.error(
            "%s failed (%s); check configuration, tool version and target permissions",
            args.command,
            type(error).__name__,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
