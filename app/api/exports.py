"""Authenticated CSV downloads, with shared inventory filtering semantics."""

from datetime import UTC, datetime
from typing import Annotated, BinaryIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.auth import CurrentUser, require_admin
from app.database import get_db_session
from app.schemas.products import InventoryFilters
from app.services.exports import create_export, read_chunks

router = APIRouter(prefix="/api/admin/exports", tags=["exports"])


async def download(
    session: AsyncSession, file: BinaryIO, filename: str,
) -> StreamingResponse:
    try:
        # Finished CSV is independent of the database; release the connection before transfer.
        await session.rollback()
    except BaseException:
        file.close()
        raise
    return StreamingResponse(
        read_chunks(file), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"',
                 "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        background=BackgroundTask(file.close),
    )


@router.get("/manual-catalog.csv")
async def manual_catalog(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[CurrentUser, Depends(require_admin)],
) -> StreamingResponse:
    return await download(session, await create_export(session), "manual_catalog_additions.csv")


@router.get("/inventory.csv")
async def inventory(
    filters: Annotated[InventoryFilters, Query()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[CurrentUser, Depends(require_admin)],
) -> StreamingResponse:
    try:
        file = await create_export(session, filters)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    filename = f"inventory_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.csv"
    return await download(session, file, filename)
