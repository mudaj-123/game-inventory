"""FastAPI 路由包。"""

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.scans import router as scans_router
from app.api.transactions import router as transactions_router

__all__ = ["admin_router", "auth_router", "scans_router", "transactions_router"]
