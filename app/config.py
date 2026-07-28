"""应用配置及环境变量读取。"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """集中管理开发和生产环境均可覆盖的配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_timezone: str = "Asia/Shanghai"
    secret_key: str = ""
    database_url: str = "sqlite+aiosqlite:///./inventory.db"

    auto_import_local_catalog: bool = True
    local_catalog_path: Path = Path("./data/catalog/barcode_catalog.csv")
    local_cover_dir: Path = Path("./data/catalog/covers")
    catalog_import_mode: Literal["ADD_ONLY", "UPDATE_UNVERIFIED", "FORCE"] = "ADD_ONLY"

    default_low_stock_threshold: int = Field(default=1, ge=0)
    default_overstock_threshold: int | None = Field(default=10, ge=0)
    stale_stock_days: int = Field(default=30, ge=1)
    allow_offline_out: bool = False
    undo_window_minutes: int = Field(default=10, ge=1)

    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:example@example.com"
    alert_webhook_url: str = ""


@lru_cache
def get_settings() -> Settings:
    """返回进程内复用的不可变配置入口。"""

    return Settings()


settings = get_settings()
