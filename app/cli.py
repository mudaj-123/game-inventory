"""运维命令行入口。"""

import argparse
import asyncio
import getpass
import json
from pathlib import Path
from typing import cast

from sqlalchemy import select

from app.auth.security import hash_password
from app.database import async_session_factory
from app.models import User
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
    admin = subparsers.add_parser("create-admin", help="创建首个管理员")
    admin.add_argument("--username", help="省略时安全交互输入")
    admin.add_argument("--password", help="明确传入（可能出现在 shell 历史中）")
    args = parser.parse_args()
    if args.command == "import-catalog":
        asyncio.run(_import(args.path, cast(ImportMode, args.mode)))
    else:
        username = (args.username or input("管理员用户名: ")).strip()
        password = args.password or getpass.getpass("管理员密码: ")
        if not username or not password:
            parser.error("用户名和密码不得为空")
        asyncio.run(_create_admin(username, password))


async def _create_admin(username: str, password: str) -> None:
    async with async_session_factory() as session, session.begin():
        if await session.scalar(select(User.id).where(User.username == username)) is not None:
            raise SystemExit(f"错误：用户名 {username!r} 已存在")
        session.add(User(username=username, password_hash=hash_password(password), role="ADMIN"))
    print(f"管理员 {username!r} 创建成功")


if __name__ == "__main__":
    main()
