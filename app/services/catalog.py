"""本地 CSV 条码目录校验和批量导入。"""

import csv
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogEntry

BARCODE_PATTERN = re.compile(r"^[0-9]{8,14}$")
REQUIRED_COLUMNS = {"barcode", "game_name", "platform"}
PLATFORM_ALIASES = {
    "PS5": "PS5",
    "PLAYSTATION 5": "PS5",
    "PS4": "PS4",
    "PLAYSTATION 4": "PS4",
    "SWITCH": "SWITCH",
    "NINTENDO SWITCH": "SWITCH",
    "NS": "SWITCH",
    "SWITCH 2": "SWITCH2",
    "SWITCH2": "SWITCH2",
    "NINTENDO SWITCH 2": "SWITCH2",
    "NS2": "SWITCH2",
}
TRUE_VALUES = {"true", "1", "yes", "y"}
FALSE_VALUES = {"false", "0", "no", "n", ""}
ImportMode = Literal["ADD_ONLY", "UPDATE_UNVERIFIED", "FORCE"]


@dataclass(slots=True)
class ImportErrorDetail:
    row: int
    barcode: str
    error: str


@dataclass(slots=True)
class ImportReport:
    added: int = 0
    updated: int = 0
    skipped: int = 0
    conflicts: int = 0
    errors: list[ImportErrorDetail] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["error_count"] = len(self.errors)
        return result


def normalize_platform(value: str) -> str:
    """把常见平台写法归一为四个业务值。"""

    normalized = " ".join(value.strip().upper().replace("-", " ").split())
    try:
        return PLATFORM_ALIASES[normalized]
    except KeyError as error:
        raise ValueError(f"不支持的平台值: {value}") from error


def normalize_name(value: str) -> str:
    return " ".join(value.casefold().split())


def _optional(row: dict[str, str], key: str) -> str | None:
    value = (row.get(key) or "").strip()
    return value or None


def _parse_row(row: dict[str, str], row_number: int, source_file: str) -> dict[str, object]:
    barcode = (row.get("barcode") or "").strip()
    if not BARCODE_PATTERN.fullmatch(barcode):
        raise ValueError("条码必须是 8～14 位数字")
    game_name = (row.get("game_name") or "").strip()
    if not game_name:
        raise ValueError("游戏名不能为空")
    verified_value = (row.get("verified") or "").strip().casefold()
    if verified_value not in TRUE_VALUES | FALSE_VALUES:
        raise ValueError("verified 必须是 true/false、1/0 或 yes/no")
    release_year_text = (row.get("release_year") or "").strip()
    if release_year_text and (not release_year_text.isdigit() or len(release_year_text) != 4):
        raise ValueError("release_year 必须是四位年份")
    return {
        "barcode": barcode,
        "game_name": game_name,
        "normalized_name": normalize_name(game_name),
        "platform": normalize_platform(row.get("platform") or ""),
        "region": (row.get("region") or "UNKNOWN").strip().upper() or "UNKNOWN",
        "edition": _optional(row, "edition"),
        "language": _optional(row, "language"),
        "publisher": _optional(row, "publisher"),
        "release_year": int(release_year_text) if release_year_text else None,
        "cover_filename": _optional(row, "cover_filename"),
        "aliases": _optional(row, "aliases"),
        "source": _optional(row, "source"),
        "verified": verified_value in TRUE_VALUES,
        "source_file": source_file,
        "source_row": row_number,
    }


async def import_catalog(
    session: AsyncSession, path: Path, mode: ImportMode = "ADD_ONLY"
) -> ImportReport:
    """在调用方事务中导入 CSV；坏行被报告但不影响其他有效行。"""

    report = ImportReport()
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise ValueError(f"CSV 缺少必填列: {', '.join(sorted(missing))}")
        parsed: list[dict[str, object]] = []
        seen: set[str] = set()
        for row_number, row in enumerate(reader, start=2):
            barcode = (row.get("barcode") or "").strip()
            try:
                values = _parse_row(row, row_number, str(path))
                if barcode in seen:
                    report.conflicts += 1
                    report.errors.append(ImportErrorDetail(row_number, barcode, "文件内条码重复"))
                    continue
                seen.add(barcode)
                parsed.append(values)
            except ValueError as error:
                report.errors.append(ImportErrorDetail(row_number, barcode, str(error)))

    existing = {
        entry.barcode: entry
        for entry in (
            await session.scalars(select(CatalogEntry).where(CatalogEntry.barcode.in_(seen)))
        ).all()
    }
    for values in parsed:
        barcode = str(values["barcode"])
        entry = existing.get(barcode)
        if entry is None:
            session.add(CatalogEntry(**values))
            report.added += 1
        elif mode == "ADD_ONLY" or (mode == "UPDATE_UNVERIFIED" and entry.verified):
            report.skipped += 1
        else:
            for key, value in values.items():
                setattr(entry, key, value)
            report.updated += 1
    await session.flush()
    return report
