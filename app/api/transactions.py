from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_staff, verify_csrf
from app.database import get_db_session
from app.models import User
from app.schemas.transactions import ReverseResponse, TransactionPage
from app.services.transactions import TransactionError, list_transactions, reverse_transaction

router = APIRouter(prefix="/api/transactions", tags=["transactions"])
Db = Annotated[AsyncSession, Depends(get_db_session)]
Staff = Annotated[User, Depends(require_staff)]


@router.get("", response_model=TransactionPage)
async def today(session: Db, user: Staff, page: Annotated[int, Query(ge=1)] = 1,
                page_size: Annotated[int, Query(ge=1, le=100)] = 20,
                operation_type: Literal["IN", "SALE_OUT", "REVERSAL"] | None = None
                ) -> TransactionPage:
    return await list_transactions(session, user, page, page_size, operation_type)


async def _reverse(
    session: AsyncSession, user: User, transaction_id: int | None
) -> ReverseResponse:
    try:
        return await reverse_transaction(session, user, transaction_id)
    except TransactionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except SQLAlchemyError as error:
        await session.rollback()
        raise HTTPException(status_code=503, detail="数据库操作失败，撤销未生效") from error


@router.post("/undo-last", response_model=ReverseResponse)
async def undo_last(session: Db, user: Staff,
                    _: Annotated[None, Depends(verify_csrf)]) -> ReverseResponse:
    return await _reverse(session, user, None)


@router.post("/{transaction_id}/reverse", response_model=ReverseResponse)
async def reverse(transaction_id: int, session: Db, user: Staff,
                  _: Annotated[None, Depends(verify_csrf)]) -> ReverseResponse:
    return await _reverse(session, user, transaction_id)
