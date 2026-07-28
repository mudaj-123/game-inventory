"""库存扫码 HTTP API。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.schemas import ResolveUnknownRequest, ScanRequest, ScanResponse
from app.services.inventory import process_scan, resolve_unknown

router = APIRouter(prefix="/api/scans", tags=["scans"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.post("", response_model=ScanResponse)
async def scan(
    request: ScanRequest, session: DatabaseSession
) -> ScanResponse:
    return await process_scan(session, request)


@router.post("/resolve-unknown", response_model=ScanResponse)
async def resolve(
    request: ResolveUnknownRequest, session: DatabaseSession
) -> ScanResponse:
    return await resolve_unknown(session, request)
