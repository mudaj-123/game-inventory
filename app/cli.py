"""运维命令行入口。"""

import argparse
import asyncio
import json
from pathlib import Path
from typing import cast

from app.database import async_session_factory
from app.services.catalog import ImportMode, import_catalog


async def _import(path: Path, mode: ImportMode) -> None:
    async with async_session_factory() as session, session.begin():
        report = await import_catalog(session, path, mode)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="游戏库存运维工具")
    subparsers = parser.add_subparsers(dest="command", required=True)
    command = subparsers.add_parser("import-catalog", help="导入本地条码 CSV")
    command.add_argument("path", type=Path)
    command.add_argument(
        "--mode", choices=["ADD_ONLY", "UPDATE_UNVERIFIED", "FORCE"], default="ADD_ONLY"
    )
    args = parser.parse_args()
    asyncio.run(_import(args.path, cast(ImportMode, args.mode)))


if __name__ == "__main__":
    main()
