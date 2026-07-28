"""FastAPI 路由包。"""

from app.api.scans import router as scans_router

__all__ = ["scans_router"]
