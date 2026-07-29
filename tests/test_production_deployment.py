"""生产部署资产的静态回归检查。"""

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_dockerfile_uses_non_root_user_and_healthcheck() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "python:3.12" in dockerfile
    assert "USER inventory" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "COPY --chown=inventory:inventory alembic " in dockerfile
    assert "COPY --chown=inventory:inventory data/catalog " in dockerfile


def test_production_compose_security_and_operations() -> None:
    compose = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    db_section, app_section = compose.split("  app:\n", 1)

    assert "ports:" not in db_section
    assert '"127.0.0.1:${APP_HOST_PORT:-18080}:8000"' in app_section
    assert '"0.0.0.0:${APP_HOST_PORT' not in app_section
    assert "healthcheck:" in db_section
    assert "healthcheck:" in app_section
    assert "inventory_postgres_data:/var/lib/postgresql/data" in db_section
    assert "condition: service_healthy" in app_section
    assert 'max-size: "10m"' in compose
    assert 'max-file: "5"' in compose
    assert "internal: true" in app_section


def test_entrypoint_runs_migrations() -> None:
    entrypoint = (ROOT / "docker-entrypoint.sh").read_text(encoding="utf-8")
    assert "alembic upgrade head" in entrypoint
    assert 'exec "$@"' in entrypoint


def test_production_environment_template_has_no_secrets() -> None:
    values = {}
    for line in (ROOT / ".env.production.example").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value

    assert values["SECRET_KEY"] == ""
    assert values["POSTGRES_PASSWORD"] == ""
    assert values["APP_HOST_PORT"] == "18080"
    assert "@db:5432/" in values["DATABASE_URL"]


def test_maintenance_scripts_and_current_readme() -> None:
    assert (ROOT / "scripts/backup-postgres.sh").exists()
    assert (ROOT / "scripts/restore-postgres.sh").exists()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "P0 阶段尚未实现 CSV 导入命令、业务表或扫描流程" not in readme
    assert "后续阶段还需按 `PROJECT_SPEC.md` 添加库存、CSV 导入、幂等、撤销" not in readme
