"""运维命令失败安全与秘密保护。"""

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import operations
from app.config import settings
from app.runtime_logging import SafeFormatter


@pytest.fixture
def pg_config(monkeypatch):
    monkeypatch.setattr(
        settings, "database_url", "postgresql+asyncpg://user:secret%40pass@localhost:5432/live"
    )
    monkeypatch.setenv("POSTGRES_BIN", "/test/postgres")


def test_pg_tools_derive_url_without_password_in_arguments(pg_config, monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout="ok")

    monkeypatch.setattr(operations.subprocess, "run", run)
    operations.pg_run("pg_dump", "--format=custom")
    args, kwargs = calls[0]
    assert "secret" not in str(args)
    assert kwargs["env"]["PGPASSWORD"] == "secret@pass"
    assert kwargs["env"]["PGDATABASE"] == "live"


def test_failed_dump_never_publishes_or_removes_previous_backups(pg_config, tmp_path, monkeypatch):
    previous = tmp_path / "inventory_previous.dump"
    previous.write_bytes(b"valid")

    def fail(*args, **kwargs):
        raise RuntimeError("failed")

    monkeypatch.setattr(operations, "pg_run", fail)
    with pytest.raises(RuntimeError):
        operations.backup(tmp_path)
    assert list(tmp_path.iterdir()) == [previous]


def test_backup_validates_before_atomic_publication(pg_config, tmp_path, monkeypatch):
    calls = []

    def run(tool, *args, **kwargs):
        calls.append(tool)
        if tool == "pg_dump":
            Path(next(a[7:] for a in args if a.startswith("--file="))).write_bytes(b"PGDMP")
        else:
            assert not list(tmp_path.glob("*.dump"))
        return ""

    monkeypatch.setattr(operations, "pg_run", run)
    result = operations.backup(tmp_path)
    assert result.read_bytes() == b"PGDMP" and calls == ["pg_dump", "pg_restore"]
    assert not list(tmp_path.glob("*.tmp"))


def test_restore_refuses_live_database_and_nonempty_target(pg_config, tmp_path, monkeypatch):
    dump = tmp_path / "test.dump"
    dump.write_bytes(b"PGDMP")
    with pytest.raises(ValueError, match="separate empty"):
        operations.restore(dump, "live", "live")
    monkeypatch.setattr(operations, "pg_run", lambda *a, **kw: "1\n")
    with pytest.raises(ValueError, match="not empty"):
        operations.restore(dump, "other", "other")
    with pytest.raises(ValueError, match="exactly match"):
        operations.restore(dump, "other", "wrong")


def test_log_formatter_redacts_credentials_and_exception_values(pg_config, monkeypatch):
    monkeypatch.setattr(settings, "secret_key", "session-secret")
    record = logging.LogRecord(
        "test",
        logging.ERROR,
        "",
        0,
        "postgresql://user:secret@host/db session-secret secret@pass",
        (),
        (ValueError, ValueError("password FROM SQL parameters"), None),
    )
    formatted = SafeFormatter().format(record)
    assert "session-secret" not in formatted and "secret@pass" not in formatted
    assert "password FROM" not in formatted
    assert "exception=ValueError" in formatted


def test_secure_cookie_defaults_and_explicit_lan_override():
    from app.config import Settings

    assert Settings(_env_file=None, app_env="production").secure_cookie
    assert not Settings(
        _env_file=None, app_env="production", session_cookie_secure=False
    ).secure_cookie
