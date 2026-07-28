"""Pydantic 请求与响应结构包。"""

from app.schemas.inventory import ResolveUnknownRequest, ScanRequest, ScanResponse

__all__ = ["ResolveUnknownRequest", "ScanRequest", "ScanResponse"]
