"""Administrator-only read-only reports."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, require_admin
from app.database import get_db_session
from app.schemas.reports import Period, SalesReport
from app.services.reports import report_dates, sales_report

router = APIRouter(prefix="/api/admin/reports", tags=["reports"])


@router.get("/sales", response_model=SalesReport)
async def sales(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[CurrentUser, Depends(require_admin)],
    period: Period = "7d",
    start: date | None = None,
    end: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> SalesReport:
    try:
        start_date, end_date = report_dates(period, start, end)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    response.headers["Cache-Control"] = "no-store"
    return await sales_report(session, start_date, end_date, page, page_size)
