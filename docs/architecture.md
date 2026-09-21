# 架构与不可破坏的边界

`CURRENT_REQUIREMENTS.md` 是权威需求；本页记录当前实现的部署决策。

## 系统边界

系统是单体 FastAPI/PWA，通过 SQLAlchemy 异步会话访问 PostgreSQL。店员手机、电脑和 HID
扫码枪只访问 Web API，绝不直连数据库。商品识别顺序是正式 `products`、已导入的
`catalog_entries`、人工补录；条码全程为字符串。本地 CSV 因此是可维护的导入源，不是并发业务
数据库，也没有在线条码服务运行依赖。

库存写入以数据库事务、`client_scan_id` 唯一约束和行锁保护。流水只追加；撤销追加关联的
`REVERSAL`，不修改原流水。迁移只能通过 Alembic。生产不使用 SQLite，也不调用
`create_all()` 升级数据库。

## 生产拓扑决策

默认生产环境是店内 Windows 10 x64 电脑：原生 PostgreSQL 仅监听 `127.0.0.1:5432`，原生
Python 3.12/FastAPI 监听配置的 LAN 地址（默认示例为 `0.0.0.0:18081`）。这能适配已有的
低功耗硬件，避免 Docker Desktop 的资源、授权和重启复杂度。应用是数据库唯一的 LAN 网关。
Dockerfile、Compose 和 CI 仍保留，定位为开发、可选云部署、灾备与可追溯构建，不是店铺机
前置条件。

`/health` 会执行 `SELECT 1`；数据库不可用时返回 HTTP 503，而不是固定“正常”。应用和迁移
错误由计划任务历史以及 `logs/application.log`、`logs/error.log` 诊断；备份/恢复脚本将失败以
非零状态上报。原生入口日志在运行中每 10 MiB 轮转并保留 5 份，管理员定期归档；不要记录 `.env` 或数据库 URL。

## 安全边界

PostgreSQL 的 `listen_addresses` 保持 `localhost`，`pg_hba.conf` 仅允许本机所需用户和数据库。
Windows 防火墙只对 Private profile 的 LocalSubnet 开放应用 TCP 端口，严禁开放 5432 或设置
路由器公网端口转发。店外访问使用 Tailscale，并将防火墙范围收窄到其地址段。

PWA Service Worker 和 `Secure` Cookie 在普通 LAN HTTP（除 localhost 外）不可可靠工作。
正式手机/PWA 使用 HTTPS：可在 Tailscale HTTPS 名称或 LAN 反向代理证书后访问。若上线初期仅
使用可信 Private LAN HTTP，只能明确将其视为临时浏览器模式，并设置与实际传输方式相符的
Cookie；不得声称其是安全或完整 PWA 部署。
