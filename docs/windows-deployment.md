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
  Operational 日志。应用日志在 `LOG_DIR\application.log`。
- 健康检查：`health-check.ps1` 同时验证 FastAPI 和数据库。503 时先查 PostgreSQL Windows
  Service、磁盘、`.env` 与日志。迁移失败会阻止 Uvicorn 启动，不会静默提供旧 Schema。
- 更新：先备份，停止任务/应用，保留旧提交和 dump，拉取已测试版本，运行 setup、启动和健康
  检查；迁移不可盲目 downgrade，失败时停止新版本并按迁移文档回切。

## Windows 外部验收清单

仓库 CI 只能静态检查 PowerShell。必须在店铺机验证：执行策略和脚本语法、SYSTEM 对仓库/HDD
权限、PostgreSQL 服务启动顺序、开机重试、日志持续写入、Private 防火墙、真实手机 HTTPS/PWA、
HID Enter/Tab 连扫、睡眠/断网恢复，以及备份与隔离恢复。这些未在 Linux 环境执行时不得标为通过。

## HTTPS/PWA 与临时 LAN HTTP（必须选择一种）

### 方案 A：Tailscale HTTPS（推荐）

电脑和手机安装官方 Tailscale，加入同一受控 tailnet。应用设置 `APP_HOST=127.0.0.1`，保留
`APP_ENV=production` 和 `SESSION_COOKIE_SECURE=true`。管理员启用 tailnet HTTPS/MagicDNS 后：

```powershell
tailscale serve --bg http://127.0.0.1:18081
tailscale serve status
```

手机开启 Tailscale 后访问命令输出的 `https://主机名.tailnet名.ts.net`，不可用裸 LAN IP 替代。
使用 Serve，不启用 Funnel；不做路由器公网端口映射。此模式无需给 LAN 开放原始 18081。
通过 tailnet 权限规则限制访问者。官方说明：
https://tailscale.com/docs/reference/tailscale-cli/serve

### 方案 B：原生 LAN HTTPS 反向代理

由管理员为局域网域名配置受所有手机信任的证书和 HTTPS 反向代理到本机 18081，应用仍保持
`SESSION_COOKIE_SECURE=true`。证书警告未解决之前不能算 PWA 验收成功。只开放代理端口到
Private/LocalSubnet。现有 Nginx 示例保留作为可选云端参考，不自动安装或改写系统代理。

### 临时模式：仅浏览器的可信 LAN HTTP

如仅为现场调试，可设置 `APP_HOST=0.0.0.0`、`SESSION_COOKIE_SECURE=false`，继续保持
`APP_ENV=production`、PostgreSQL 和强 SECRET_KEY。访问 `http://店铺固定IP:18081`，只对
Private/LocalSubnet 开放该端口。HTTP 传输不加密，此模式不能作为完整 PWA/摄像头方案，不能
在公网使用。切换 HTTPS 后立即恢复 Secure Cookie，退出并重新登录。所有模式均保留 HttpOnly、
SameSite 和 CSRF；不把凭据放入浏览器持久化存储。

## 本轮脚本操作补充

- `start.ps1` 先验证运行记录，再启动 `app.runner`。runner 等待数据库、执行 Alembic、随后
  启动 Uvicorn。交互模式等待 `/health` 成功；失败查看日志，不重复盲目启动。
- 初次手动启动验收后，先 `stop.ps1` 再安装并启动计划任务，避免两套进程占同一端口。
- `restart.ps1` 若检测到已安装任务，继续用计划任务启动，不改成独立无监督进程。
- 新 PID 文件含开始时间和进程路径。升级前若存在旧版纯数字 PID 文件，先核实并停止旧进程，
  再删除旧文件。脚本不猜测不匹配 PID 的归属。
- 应用日志位于 `LOG_DIR/application.log`，运行中每 10 MiB 轮转，保留 5 份。启动、退出、
  数据库不可用、迁移失败和运行异常记录在其中，异常参数为避免密码泄漏而省略。
- 查看日志：`Get-Content .\logs\application.log -Tail 100 -Wait`（LOG_DIR 自定义时替换路径）。
- 使用虚拟环境创建管理员：`.\.venv\Scripts\python.exe -m app.cli create-admin`，不能依赖
  系统 `python` 恰好指向该虚拟环境。
- 按 `backup-and-restore.md` 安装每日备份任务、验证隔离恢复后，才正式切换店员客户端。
- PowerShell 静态解析：`scripts\windows\check-syntax.ps1`。解析通过不能代替 Windows 10
  实际开机、停止子进程、权限和手机验收。

原生备份/恢复/演练日志分别为 LOG_DIR 下的 `backup.log`、`restore.log`、`drill.log`，
与常驻应用日志分开轮转，避免 Windows 跨进程同时重命名同一日志文件。

创建店员：`.\.venv\Scripts\python.exe -m app.cli create-staff`（交互输入密码，不回显）。
管理员可在“库存与预警管理”搜索商品、核实名称/平台及预警阈值、填写原因调整库存；
修改资料不改变任何历史流水中的商品快照。
