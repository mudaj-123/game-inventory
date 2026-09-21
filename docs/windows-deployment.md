# Windows 10 店铺机部署与验收

## 首次部署顺序

1. 安装 SSD、内存和 Windows 10 x64，完成系统更新；磁盘预留足够空间，1 TB HDD 分配固定
   盘符（示例 `D:`）。将网络设为 **Private**，在路由器为店铺机配置 DHCP Reservation。
2. 安装 PostgreSQL 16 x64，设置独立强密码；创建 `inventory` 登录角色及数据库。确认服务启动
   类型为 Automatic。令 `listen_addresses='localhost'`，在 `pg_hba.conf` 仅保留本机最小规则，
   重启后用 `netstat -ano | findstr :5432` 确认没有 LAN 监听。
3. 安装 Python 3.12 和 Git，把仓库放在例如 `C:\GameInventory`。管理员 PowerShell 执行
   `scripts\windows\setup.ps1`。复制生成的 `.env` 后按 `.env.windows.example` 填写强随机
   `SECRET_KEY`、URL 编码后的 `DATABASE_URL`、`PG*`、PostgreSQL 工具目录和 HDD 备份目录。
   用 ACL 将 `.env` 限制为管理员和 SYSTEM；不要把它提交或发到聊天记录。
4. 执行 `scripts\windows\start.ps1`，再执行 `scripts\windows\health-check.ps1`。用
   `python -m app.cli create-admin` 创建首个管理员。确认登录、入库、出库、重复请求、最后一件
   竞争、撤销和中文/前导零条码。
5. 以管理员运行 `scripts\windows\install-service.ps1`。它只使用 Windows Task Scheduler，创建
   SYSTEM 开机任务 `GameInventory`，不下载 NSSM/WinSW。运行
   `Start-ScheduledTask -TaskName GameInventory`，重启电脑并验证自动启动、迁移失败可见且健康检查
   成功。卸载使用 `scripts\windows\install-service.ps1 -Uninstall`。
6. 防火墙只开放应用端口：
   `New-NetFirewallRule -DisplayName 'Game Inventory LAN' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 18081 -Profile Private -RemoteAddress LocalSubnet`。
   不创建 5432 入站规则，不关闭防火墙，不做公网端口映射。端口变化时同步 `.env` 和规则。
7. 从 Android/iPhone 访问配置的 HTTPS URL，验证登录、Enter/Tab 连扫、焦点恢复、视觉/声音反馈
   和安装 PWA。店外访问优先安装 Tailscale，仅向所需 Tailscale 范围开放 Web 端口。
8. 配置每日 `backup.ps1` 计划任务并完成一次下述隔离恢复演练，再开始正式使用。

## 日常操作与故障排查

- 交互启动/停止/重启：`start.ps1`、`stop.ps1`、`restart.ps1`。
- 自动任务状态：`Get-ScheduledTask -TaskName GameInventory`；运行历史在 Task Scheduler 的
  Operational 日志。应用日志在 `logs\application.log` 和 `logs\error.log`。
- 健康检查：`health-check.ps1` 同时验证 FastAPI 和数据库。503 时先查 PostgreSQL Windows
  Service、磁盘、`.env` 与日志。迁移失败会阻止 Uvicorn 启动，不会静默提供旧 Schema。
- 更新：先备份，停止任务/应用，保留旧提交和 dump，拉取已测试版本，运行 setup、启动和健康
  检查；迁移不可盲目 downgrade，失败时停止新版本并按迁移文档回切。

## Windows 外部验收清单

仓库 CI 只能静态检查 PowerShell。必须在店铺机验证：执行策略和脚本语法、SYSTEM 对仓库/HDD
权限、PostgreSQL 服务启动顺序、开机重试、日志持续写入、Private 防火墙、真实手机 HTTPS/PWA、
HID Enter/Tab 连扫、睡眠/断网恢复，以及备份与隔离恢复。这些未在 Linux 环境执行时不得标为通过。
