# 实体游戏库存管理系统

面向实体游戏店的移动端库存管理系统。目标运行环境为 Python 3.12、FastAPI、SQLAlchemy 2.x 与 Alembic；正式环境使用 PostgreSQL，本地开发和测试可使用 SQLite。条码始终按字符串处理并保留前导零，商品识别优先使用服务器本地目录，不依赖第三方在线条码识别服务。

当前版本包含 Cookie 认证、角色权限、归属到操作员的扫码流水、今日流水以及只追加的安全撤销。

## 环境要求

- Python **3.12**（项目声明为 `>=3.12,<3.13`）
- SQLite（本地默认）或 PostgreSQL（正式环境）
- 支持 Bluetooth HID Keyboard 或 USB-C OTG 键盘模式的扫码枪（后续扫码界面使用）

不要因操作系统当前安装了其他 Python 版本而降低项目版本要求。

## 项目结构

```text
.
├── AGENTS.md                 # 仓库开发约定
├── PROJECT_SPEC.md           # 完整项目需求规格（原文保留）
├── pyproject.toml            # Python 3.12 项目元数据及依赖
├── .env.example              # 环境变量模板（不含真实密钥）
├── .vscode/                  # VS Code 运行和测试配置
├── app/
│   ├── main.py               # FastAPI 入口与健康检查
│   ├── config.py             # 环境变量配置
│   ├── database.py           # SQLAlchemy 异步引擎和会话
│   ├── api/                  # API 路由
│   ├── auth/                 # 认证与权限
│   ├── models/               # SQLAlchemy 模型
│   ├── schemas/              # Pydantic 请求/响应结构
│   ├── services/             # 业务服务
│   ├── static/               # 无构建步骤的前端静态资源
│   └── templates/            # 服务端模板
├── alembic/
│   ├── env.py                # 异步 Alembic 环境
│   └── versions/             # 数据库迁移版本
├── data/
│   ├── catalog/
│   │   ├── barcode_catalog.csv # 本地条码目录模板
│   │   ├── README.md           # CSV 格式说明
│   │   └── covers/             # 本地封面
│   └── exports/              # 运行时导出（内容不提交）
├── scripts/                  # 后续维护脚本
└── tests/                    # 自动化测试
```

## 配置

复制环境变量模板，至少在非本地环境中设置强随机密钥：

```bash
cp .env.example .env
```

默认数据库为 `sqlite+aiosqlite:///./inventory.db`。正式 PostgreSQL 可改为：

```dotenv
DATABASE_URL=postgresql+asyncpg://inventory_user:password@db:5432/inventory
```

不得提交 `.env` 或真实密钥。完整变量及安全的空值示例见 `.env.example`。

## 安装与后续启动

准备好 Python 3.12 后，可使用已验证的安装脚本创建虚拟环境、安装开发依赖、
复制首次使用的环境变量模板、运行数据库迁移，并执行测试与静态检查：

```bash
./scripts/setup.sh
source .venv/bin/activate
uvicorn app.main:app --reload
```

脚本仅支持 Python 3.12，任何步骤失败都会返回非零退出码；已有 `.env` 不会被覆盖。
如果系统安装了 `uv`，脚本会使用已提交的锁文件进行可复现安装，否则回退到 `pip`。
可通过 `PYTHON_BIN` 指定 Python 3.12 命令，通过 `VENV_DIR` 指定虚拟环境目录。
需要快速准备环境而暂不执行 pytest 和 Ruff 时，可传入 `--skip-checks`；使用 `--help`
可查看脚本参数。
Windows 用户可按原步骤手工创建虚拟环境并执行 `python -m pip install -e '.[dev]'`。

浏览器访问 `http://127.0.0.1:8000/health`，预期返回应用状态。启动前必须执行 `alembic upgrade head` 应用库存核心及认证流水迁移。

### 创建首个管理员

先执行 `alembic upgrade head`，再用交互方式创建管理员（密码由 `getpass` 读取，不回显）：

```bash
uv run python -m app.cli create-admin
```

自动化部署也可明确传入 `--username` 和 `--password`；命令行参数可能进入 shell 历史，优先使用交互输入。源码没有默认密码，重复用户名会返回清晰错误。生产环境必须设置强随机 `SECRET_KEY`，此时会话 Cookie 自动启用 `Secure`；所有环境均使用 `HttpOnly` 和 `SameSite=Lax`。登录响应中的 CSRF token 只保存在页面内存中，前端不会把密码、会话或数据库凭据写入 `localStorage`。

`STAFF` 可扫码、查看自己的当日流水，并在 `UNDO_WINDOW_MINUTES` 内撤销自己最近一条可撤销流水；`ADMIN` 可查看全部当日流水并指定流水撤销。撤销永不更新或删除原流水，而是追加关联的 `REVERSAL`。

### VS Code

1. 使用 Python 3.12 创建 `.venv` 并安装开发依赖。
2. 在 VS Code 中选择 `.venv` 解释器。
3. 复制 `.env.example` 为 `.env`。
4. 打开“运行和调试”，选择 **FastAPI: 开发服务器**。

## 本地条码目录

编辑 `data/catalog/barcode_catalog.csv` 时：

- 使用 UTF-8，导入器后续也会兼容 UTF-8 with BOM；
- 把 `barcode` 列设为文本，保留前导零；
- 只使用 `PS5`、`PS4`、`SWITCH`、`SWITCH2` 标准平台值；
- 删除模板中的明显假数据，再加入真实目录记录；
- 封面文件放入 `data/catalog/covers/`。

详见 `data/catalog/README.md`。P0 阶段尚未实现 CSV 导入命令、业务表或扫描流程。

## 检查与测试

安装开发依赖后运行：

```bash
python3.12 -m pytest
python3.12 -m ruff check .
```

`tests/test_health.py` 需要 FastAPI、HTTPX、SQLAlchemy 和 SQLite 异步驱动。`tests/test_project_structure.py` 本身只使用标准库，但建议安装依赖后统一交由 pytest 运行。后续阶段还需按 `PROJECT_SPEC.md` 添加库存、CSV 导入、幂等、撤销、预警及 PostgreSQL 并发集成测试。

## 当前限制与后续阶段

尚未实现目录导出、预警报表和完整用户管理界面。数据库升级必须继续使用 Alembic，不能以 `Base.metadata.create_all()` 代替，也不能接入第三方在线条码识别作为核心依赖。
