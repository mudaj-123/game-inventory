"""Generate complete UTF-8 BOM CSV downloads before sending any response bytes."""

import csv
import os
import shutil
import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime
from io import TextIOWrapper
from pathlib import Path
from typing import BinaryIO
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import CatalogEntry, Product
from app.schemas.products import InventoryFilters
from app.services.csv_format import TEXT_ENCODING, TEXT_ENCODING_COLUMN, safe_cell
from app.services.products import inventory_item, inventory_query

CATALOG_COLUMNS = [
    "barcode", "game_name", "platform", "region", "edition", "language", "publisher",
    "release_year", "cover_filename", "aliases", "source", "verified", "notes",
    TEXT_ENCODING_COLUMN,
]
INVENTORY_COLUMNS = [
    "barcode", "game_name", "platform", "region", "edition", "quantity", "states", "active",
    "manually_verified", "low_stock_threshold", "overstock_threshold", "period_sales",
    "period_inbound", "last_sale_at", "updated_at", "period_start", "period_end", "timezone",
    "exported_at_utc",
]


def read_chunks(file: BinaryIO) -> Iterator[bytes]:
    try:
        while chunk := file.read(64 * 1024):
            yield chunk
    finally:
        file.close()


async def create_export(
    session: AsyncSession, filters: InventoryFilters | None = None,
) -> BinaryIO:
    """Export manual mappings or all inventory matches, ignoring pagination."""
    file = tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b")
    text = TextIOWrapper(file, encoding="utf-8-sig", newline="")
    writer = csv.writer(text)
    try:
        if filters is None:
            writer.writerow(CATALOG_COLUMNS)
            statement = (
                select(Product, CatalogEntry)
                .outerjoin(CatalogEntry, CatalogEntry.id == Product.catalog_entry_id)
                .where(Product.metadata_source == "MANUAL").order_by(Product.id)
            )
            stream = await session.stream(statement.execution_options(yield_per=500))
            try:
                async for p, catalog in stream:
                    values = [p.barcode, p.game_name, p.platform, p.region, p.edition, p.language,
                              catalog.publisher if catalog else None,
                              catalog.release_year if catalog else None, p.cover_filename,
                              catalog.aliases if catalog else None, "MANUAL",
                              "true" if p.manually_verified else "false", "", TEXT_ENCODING]
                    writer.writerow([safe_cell(value) for value in values])
            finally:
                await stream.close()
        else:
            statement, start, end, states = inventory_query(filters)
            timezone = ZoneInfo(settings.app_timezone)
            exported_at = datetime.now(UTC).isoformat()
            writer.writerow(INVENTORY_COLUMNS)
            stream = await session.stream(statement.execution_options(yield_per=500))
            try:
                async for row in stream:
                    p = inventory_item(row, states, include_cover=False)
                    values = [p.barcode, p.game_name, p.platform, p.region, p.edition, p.quantity,
                              "|".join(p.states), str(p.active).lower(),
                              str(p.manually_verified).lower(), p.low_stock_threshold,
                              p.overstock_threshold, p.period_sales, p.period_inbound,
                              p.last_sale_at.astimezone(timezone).isoformat()
                              if p.last_sale_at else "",
                              p.updated_at.astimezone(timezone).isoformat(), start, end,
                              settings.app_timezone, exported_at]
                    writer.writerow([safe_cell(value) for value in values])
            finally:
                await stream.close()
        text.flush()
        file.seek(0)
        text.detach()
        return file
    except BaseException:
        text.close()
        file.close()
        raise


def save_export(file: BinaryIO, destination: Path) -> None:
    """Atomic CLI publication; failed writes preserve an existing export."""
    temporary: Path | None = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, suffix=".tmp", delete=False,
        ) as out:
            temporary = Path(out.name)
            file.seek(0)
            shutil.copyfileobj(file, out)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, destination)
    finally:
        file.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
