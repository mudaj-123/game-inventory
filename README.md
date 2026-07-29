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
├── docker-compose.prod.yml   # 隔离的生产应用与 PostgreSQL 服务
├── Dockerfile               # 非 root、锁定依赖的生产镜像
├── deploy/                  # 独立反向代理 virtual host 示例
├── scripts/                  # 安装、备份和恢复脚本
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

详见 `data/catalog/README.md`。当前已实现 CSV 目录导入、库存业务表、已知/未知条码扫码流程、幂等写入、今日流水和安全撤销。

## 检查与测试

安装开发依赖后运行：

```bash
python3.12 -m pytest
python3.12 -m ruff check .
```

测试覆盖健康检查、认证权限、库存与 CSV 导入、移动扫码、幂等与撤销，并包含需要真实 PostgreSQL 的并发集成测试。部署结构测试还会检查 Docker、Compose、环境变量模板和维护脚本。

## 当前限制与后续阶段

尚未实现目录导出、预警报表和完整用户管理界面。数据库升级必须继续使用 Alembic，不能以 `Base.metadata.create_all()` 代替，也不能接入第三方在线条码识别作为核心依赖。

## 腾讯云 Linux 生产部署

该方案只管理本仓库的 `app` 与 `db`，不会管理、停止或修改服务器上的 OpenClaw。应用仅在宿主机回环地址 `127.0.0.1:18080` 监听，PostgreSQL **没有宿主机端口映射**，并位于 Compose 内部网络。公网访问必须使用独立域名和 HTTPS；生产模式的会话 Cookie 会启用 `Secure`，直接使用 HTTP 将无法正常、安全地登录。

### 1. 准备与首次启动

```bash
# 确认插件式 Compose 可用
docker --version
docker compose version

git clone <repository-url> game-inventory
cd game-inventory
cp .env.production.example .env.production

# 生成强随机值，将输出填入 SECRET_KEY（不要把输出贴到工单或日志）
python3.12 -c 'import secrets; print(secrets.token_urlsafe(64))'
chmod 600 .env.production
```

编辑 `.env.production`，为 `POSTGRES_PASSWORD` 和 `SECRET_KEY` 设置互不复用的强随机值，并让 `DATABASE_URL` 的用户名、密码、数据库名与三个 `POSTGRES_*` 变量完全一致。主机必须使用 Docker 内部服务名 `db`，例如 `postgresql+asyncpg://inventory:URL编码后的密码@db:5432/inventory`。若密码含 `@`、`:`、`/` 等字符，须先进行 URL 编码。

```bash
# 构建并启动；app 会等待 db 健康，入口脚本随后自动执行 alembic upgrade head
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.production -f docker-compose.prod.yml ps
curl --fail http://127.0.0.1:18080/health

# 可重复执行的显式迁移检查/升级
docker compose --env-file .env.production -f docker-compose.prod.yml exec app alembic upgrade head

# 首个管理员（交互输入密码且不回显）
docker compose --env-file .env.production -f docker-compose.prod.yml exec app python -m app.cli create-admin
```

首次启动前确保非 root 容器用户能写导出目录：`sudo chown -R 10001:10001 data/exports`。目录 CSV 与封面只需对 UID 10001 可读；如需让应用写入它们，再按相同方式授权，避免使用全员可写权限。

镜像默认启动命令是 `uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=*`；容器入口会先迁移，再以 `exec` 启动 Uvicorn，使其直接接收 SIGTERM 并优雅停止。镜像及 Compose 均配置 `/health` 健康检查。

### 2. 独立反向代理、HTTPS 与手机 PWA

把 `deploy/nginx-inventory.conf.example` 作为**新的独立 server block** 合并进现有 Nginx 配置，将 `inventory.example.com` 换成库存域名，并沿用服务器已有的证书签发流程。不要覆盖 OpenClaw 的域名、virtual host 或配置文件。示例把 HTTP 强制跳转至 HTTPS，转发到 `127.0.0.1:18080`，并传递代理头与 WebSocket 升级头。执行 `nginx -t` 后再 reload；它不让 Compose 接管宿主机 80/443。

通过手机浏览器打开 `https://inventory.example.com` 并登录。Android Chrome 可从菜单选择“添加到主屏幕/安装应用”；iOS Safari 可从分享菜单选择“添加到主屏幕”。摄像头及 PWA 能力应始终通过 HTTPS 使用。

### 3. 日常维护、更新与回滚

```bash
# 日志（已按每文件 10 MiB、最多 5 个文件轮转）
docker compose --env-file .env.production -f docker-compose.prod.yml logs -f --tail=200 app db

# 更新前先备份，并记录当前提交；审阅代码后再构建
./scripts/backup-postgres.sh
git rev-parse HEAD
git fetch origin
git checkout <reviewed-release-or-commit>
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build

# 回滚应用：检出已记录的旧提交并重建。迁移能否降级须逐版本审阅，切勿盲目 downgrade。
git checkout <previous-known-good-commit>
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build

# 停止本项目（保留数据库卷）
docker compose --env-file .env.production -f docker-compose.prod.yml stop

# 状态及磁盘巡检
docker compose --env-file .env.production -f docker-compose.prod.yml ps
docker system df
df -h
docker volume inspect game_inventory_postgres_data
```

> **数据安全警告：** 不要随意运行 `docker compose down -v`、`docker volume rm` 或任何清卷命令；`-v` 会删除数据库持久卷。普通 `stop`、`down`（不带 `-v`）和重新构建不会主动删除命名卷，但操作前仍应备份并核对命令。OpenClaw 不在此 Compose 项目内，不应对其容器执行任何操作。

Compose 数据用途如下：

- `game_inventory_postgres_data`：PostgreSQL 数据目录的独立命名卷；
- `./data/catalog`：宿主机可维护的 CSV 目录（其 `covers` 子目录也明确挂载）；
- `./data/exports`：宿主机持久化的运行时导出目录；
- `./backups`：备份脚本默认输出目录，不挂入应用容器且不提交 Git。

### 4. PostgreSQL 备份与恢复演练

备份脚本在数据库容器内调用 `pg_dump`，在宿主机写出 UTC 时间戳的 custom-format 文件，默认保留最近 7 天。可通过 `RETENTION_DAYS=30` 或 `BACKUP_DIR=/safe/path` 覆盖。脚本不会输出密码，并在成功前使用临时文件、验证结果非空。

```bash
./scripts/backup-postgres.sh
RETENTION_DAYS=30 BACKUP_DIR=/srv/inventory-backups ./scripts/backup-postgres.sh
```

**同一块云硬盘上的 `./backups` 不是完整异地备份。** 应定期加密复制到腾讯云 COS 或其他账号/故障域中的独立存储，并验证保留策略和可下载性。

恢复会清理目标库中的同名对象，因此先安排维护窗口、停止应用写入、再次备份，并核对 `.env.production` 中显示的目标。脚本要求输入**完整目标数据库名**，不会静默确认：

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml stop app
./scripts/backup-postgres.sh
./scripts/restore-postgres.sh backups/inventory_YYYYMMDDTHHMMSSZ.dump
docker compose --env-file .env.production -f docker-compose.prod.yml up -d app
docker compose --env-file .env.production -f docker-compose.prod.yml ps
curl --fail http://127.0.0.1:18080/health
```

首次上线前应使用非生产副本完整演练：创建测试数据库/独立 Compose 项目、恢复备份、执行迁移并抽查管理员登录、商品和流水。不要把演练直接指向生产数据库，也不要以恢复演练为由删除生产 volume。
