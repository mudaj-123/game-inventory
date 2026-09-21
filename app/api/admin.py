from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, require_admin, verify_csrf
from app.database import get_db_session
from app.models import User
from app.schemas.admin import AdjustmentRequest
from app.schemas.auth import UserResponse
from app.services.admin import adjust_stock
from app.services.inventory import InventoryConflictError

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=list[UserResponse])
async def users(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[CurrentUser, Depends(require_admin)],
) -> list[UserResponse]:
    records = (await session.scalars(select(User).order_by(User.username))).all()
    return [UserResponse(id=user.id, username=user.username, role=user.role) for user in records]


@router.get("/products")
async def products(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[CurrentUser, Depends(require_admin)],
    q: str = "",
    page: int = 1,
) -> dict[str, object]:
    from sqlalchemy import func, or_

    from app.models import Product

    page = max(1, page)
    condition = or_(
        Product.barcode.contains(q, autoescape=True), Product.game_name.contains(q, autoescape=True)
    )
    records = (
        await session.scalars(
            select(Product).where(condition).order_by(Product.id).offset((page - 1) * 50).limit(50)
        )
    ).all()
    total = await session.scalar(select(func.count(Product.id)).where(condition))
    return {
        "total": total,
        "page": page,
        "items": [
            {
                "id": p.id,
                "barcode": p.barcode,
                "game_name": p.game_name,
                "platform": p.platform,
                "quantity": p.quantity,
                "identification_status": p.identification_status,
                "manually_verified": p.manually_verified,
            }
            for p in records
        ],
    }


@router.get("/alerts")
async def alerts(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[CurrentUser, Depends(require_admin)],
) -> dict[str, object]:
    from app.models import Product, StockAlert
    from app.services.alerts import refresh_all_alerts

    async with session.begin():
        await refresh_all_alerts(session)
        records = (
            await session.execute(
                select(StockAlert, Product)
                .join(Product, Product.id == StockAlert.product_id)
                .where(StockAlert.closed_at.is_(None))
                .order_by(StockAlert.id.desc())
            )
        ).all()
        pending = (
            await session.scalars(
                select(Product).where(Product.manually_verified.is_(False)).order_by(Product.id)
            )
        ).all()
        return {
            "items": [
                {
                    "id": a.id,
                    "kind": a.kind,
                    "product_id": p.id,
                    "barcode": p.barcode,
                    "game_name": p.game_name,
                    "quantity": p.quantity,
                    "opened_at": a.opened_at,
                }
                for a, p in records
            ],
            "pending_products": [
                {"id": p.id, "barcode": p.barcode, "game_name": p.game_name} for p in pending
            ],
        }


@router.post("/products/{product_id}/adjust")
async def adjust(
    product_id: int,
    body: AdjustmentRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user: Annotated[CurrentUser, Depends(require_admin)],
    _: Annotated[None, Depends(verify_csrf)],
) -> dict[str, object]:
    try:
        return await adjust_stock(session, product_id, body, user)
    except (InventoryConflictError, IntegrityError) as error:
        detail = str(error) if isinstance(error, InventoryConflictError) else "请求编号冲突"
        raise HTTPException(status_code=409, detail=detail) from error
