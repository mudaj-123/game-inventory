from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, require_admin, verify_csrf
from app.database import get_db_session
from app.models import Product, User
from app.schemas.admin import AdjustmentRequest, ProductUpdate
from app.schemas.auth import UserResponse
from app.schemas.products import InventoryFilters, InventoryPage
from app.services.admin import adjust_stock
from app.services.inventory import InventoryConflictError
from app.services.products import cover_path, list_inventory

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=list[UserResponse])
async def users(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[CurrentUser, Depends(require_admin)],
) -> list[UserResponse]:
    records = (await session.scalars(select(User).order_by(User.username))).all()
    return [UserResponse(id=user.id, username=user.username, role=user.role) for user in records]


@router.get("/products", response_model=InventoryPage)
async def products(
    response: Response,
    filters: Annotated[InventoryFilters, Query()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[CurrentUser, Depends(require_admin)],
) -> InventoryPage:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await list_inventory(session, filters)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/products/{product_id}/cover")
async def product_cover(
    product_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[CurrentUser, Depends(require_admin)],
) -> FileResponse:
    product = await session.get(Product, product_id)
    path = cover_path(product.cover_filename) if product else None
    if path is None:
        raise HTTPException(status_code=404, detail="没有可用的本地封面")
    return FileResponse(
        path, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


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


@router.patch("/products/{product_id}")
async def update_product(
    product_id: int,
    body: ProductUpdate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[CurrentUser, Depends(require_admin)],
    _csrf: Annotated[None, Depends(verify_csrf)],
) -> dict[str, object]:
    from app.models import Product
    from app.services.alerts import refresh_product_alerts
    from app.services.catalog import normalize_name

    async with session.begin():
        product = await session.scalar(
            select(Product).where(Product.id == product_id).with_for_update()
        )
        if product is None:
            raise HTTPException(status_code=404, detail="商品不存在")
        product.game_name = body.game_name
        product.normalized_name = normalize_name(body.game_name)
        product.platform = body.platform
        product.low_stock_threshold = body.low_stock_threshold
        product.overstock_threshold = body.overstock_threshold
        product.manually_verified = True
        product.identification_status = "CONFIRMED"
        product.metadata_source = "MANUAL"
        await session.flush()
        alerts = await refresh_product_alerts(session, product)
        return {"id": product.id, "alerts": alerts}


@router.post("/catalog/import")
async def import_local_catalog(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[CurrentUser, Depends(require_admin)],
    _csrf: Annotated[None, Depends(verify_csrf)],
) -> dict[str, object]:
    from app.config import settings
    from app.services.catalog import import_catalog

    try:
        async with session.begin():
            report = await import_catalog(session, settings.local_catalog_path, "ADD_ONLY")
            return report.as_dict()
    except (OSError, ValueError) as error:
        raise HTTPException(
            status_code=400, detail="目录无法导入，请检查配置的 CSV 文件和表头"
        ) from error
