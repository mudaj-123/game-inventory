"""运行期间持续轮转日志，并去除凭据与数据库异常参数。"""

import logging
import re
from logging.handlers import RotatingFileHandler

from sqlalchemy.engine import make_url

from app.config import settings


class SafeFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # DB exception strings may include SQL parameters, passwords, URLs or client data.
        original, cached = record.exc_info, record.exc_text
        record.exc_info = None
        record.exc_text = None
        try:
            message = super().format(record)
            if original:
                message += f" [exception={original[0].__name__}; details suppressed]"
        finally:
            record.exc_info, record.exc_text = original, cached
        for secret in (
            settings.secret_key,
            settings.database_url,
            make_url(settings.database_url).password,
        ):
            if secret:
                message = message.replace(secret, "[REDACTED]")
        return re.sub(r"postgres(?:ql)?(?:\+\w+)?://\S+", "[REDACTED_URL]", message)


def configure_logging(filename: str = "application.log") -> None:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        settings.log_dir / filename,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(SafeFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    root.addHandler(handler)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        log = logging.getLogger(name)
        log.handlers.clear()
        log.propagate = True
