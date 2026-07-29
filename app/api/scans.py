"""库存扫码 HTTP API。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, require_staff, verify_csrf
from app.database import get_db_session
from app.schemas import ResolveUnknownRequest, ScanRequest, ScanResponse
from app.services.inventory import InventoryConflictError, process_scan, resolve_unknown

router = APIRouter(prefix="/api/scans", tags=["scans"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.post("", response_model=ScanResponse)
async def scan(
    request: ScanRequest, session: DatabaseSession,
    user: Annotated[CurrentUser, Depends(require_staff)],
    _: Annotated[None, Depends(verify_csrf)],
) -> ScanResponse:
    try:
        return await process_scan(session, request, user)
    except InventoryConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/resolve-unknown", response_model=ScanResponse)
async def resolve(
    request: ResolveUnknownRequest, session: DatabaseSession,
    user: Annotated[CurrentUser, Depends(require_staff)],
    _: Annotated[None, Depends(verify_csrf)],
) -> ScanResponse:
    try:
        return await resolve_unknown(session, request, user)
    except InventoryConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
