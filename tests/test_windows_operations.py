"""Windows 原生部署资产的静态安全契约。"""

from pathlib import Path

ROOT = Path(__file__).parents[1]
WINDOWS = ROOT / "scripts" / "windows"


def test_windows_operational_scripts_exist() -> None:
    expected = {
        "setup.ps1",
        "start.ps1",
        "stop.ps1",
        "restart.ps1",
        "install-service.ps1",
        "backup.ps1",
        "restore.ps1",
        "health-check.ps1",
    }
    assert expected <= {path.name for path in WINDOWS.glob("*.ps1")}


def test_windows_startup_migrates_before_uvicorn() -> None:
    script = (WINDOWS / "start.ps1").read_text(encoding="utf-8")
    assert script.index("alembic upgrade head") < script.index("uvicorn")
    assert "APP_HOST" in script
    assert "APP_PORT" in script


def test_backup_is_atomic_and_uses_official_tools() -> None:
    source = (ROOT / "app/operations.py").read_text(encoding="utf-8")
    assert '"pg_dump"' in source and '"pg_restore"' in source
    assert 'temporary.replace(final)' in source
    assert '"--format=custom"' in source
    assert 'capture_output=True' in source


def test_restore_requires_explicit_matching_target() -> None:
    script = (WINDOWS / "restore.ps1").read_text(encoding="utf-8")
    source = (ROOT / "app/operations.py").read_text(encoding="utf-8")
    assert "TargetDatabase -ne $ConfirmTarget" in script
    assert 'target == database_url().database' in source
    assert '"--single-transaction"' in source
    assert 'quantity < 0' in source
    assert 'inventory_drill_' in source


def test_stop_checks_process_identity_and_stops_supervisor() -> None:
    common = (WINDOWS / "common.ps1").read_text(encoding="utf-8")
    stop = (WINDOWS / "stop.ps1").read_text(encoding="utf-8")
    assert 'StartTime.ToUniversalTime()' in common and '$process.Path' in common
    assert stop.index('Stop-ScheduledTask') < stop.index('taskkill.exe')


def test_windows_environment_template_contains_no_real_secret() -> None:
    template = (ROOT / ".env.windows.example").read_text(encoding="utf-8")
    assert "APP_HOST=0.0.0.0" in template
    assert "APP_PORT=18081" in template
    assert "BACKUP_DIR=D:\\GameInventoryBackups" in template
    assert "CHANGE_ME" in template
