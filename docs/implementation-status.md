# 本轮审计与交付记录（2026-09-21）

权威需求仍为 `CURRENT_REQUIREMENTS.md`。本页记录实现和验证证据，不修改需求定义。

## 原项目状态

审计起点：`d98721a`（已合并原生 Windows 运维 PR #14）。保留 FastAPI、SQLAlchemy、PostgreSQL、
原有两份 Alembic migration、HID/PWA、Cookie/CSRF、CSV 导入、Docker/Compose/Nginx 和镜像 CI。
基线为 34 项通过、4 项 PostgreSQL 测试因本地没有测试数据库跳过，Ruff 通过。

主要缺口：管理员只有用户列表；无库存调整、预警表或预警页面；客户端网络重试使用新 ID；
Windows 进程身份只按 PID 判断，可能停止错误进程或留下子进程；日志仅在重启时轮转；恢复演练
只有手工说明；LAN HTTP 与 Secure Cookie 配置未闭合；Windows 缺少 IANA 时区数据依赖。

## 本轮实现

- `app/services/alerts.py`、`app/services/admin.py`、`app/api/admin.py`：商品搜索、带原因的
  幂等 ADJUST 流水、四类预警、资料待核实列表和核实/阈值编辑。原有 REVERSAL 可撤销管理员调整。
- `0003_stock_alerts`：只新增预警表及活动预警唯一索引，原商品、用户和流水不重建。
- `app/static/`：管理页面、扫码即时预警、结果未知时复用原请求 ID、HTTP 下安全随机 UUID
  兼容、出库未知条码不再误引导成入库。
- 幂等键绑定操作人、条码、方向；历史无用户关联的流水也能显示；CSV BOM 支持保留。
- `app/runner.py`：数据库就绪重试、迁移失败阻止启动、可配置 host/port、日志。
- `app/runtime_logging.py`：运行期间轮转，凭据及数据库异常参数不写日志。
- `app/operations.py`：官方工具、原子备份、保留策略、独立空库恢复、随机新库演练、全表行数
  与 SHA-256 指纹。Windows 包装脚本复用同一实现，连接只由 DATABASE_URL 派生。
- Windows 计划任务、进程身份校验、启动健康检查、每日备份安装/卸载、PowerShell 5.1 解析 CI。
- tzdata 依赖及锁文件更新；Alembic 正确处理 URL 编码密码；可显式配置临时 HTTP Cookie。

## 业务语义与限制

- SOLD_OUT：数量为零；LOW_STOCK：0 < 数量 <= 下限；OVERSTOCK：数量 > 上限。
- STALE_STOCK：有库存且距最后一次销售（没有销售则商品创建日）达到 STALE_STOCK_DAYS。
  撤销不抹去曾发生销售这一历史事实。阈值跨越在扫码、调整、撤销时记录；纯时间跨越在管理员
  读取预警时重新计算。没有独立后台调度器、推送通知或外部在线条码依赖。
- 同一商品同类活动预警有数据库唯一约束；关闭记录保留，重新进入状态生成新记录。
- 幂等仅防止**同一业务请求**重试。不同 ID 的两次主动扫码代表两件商品，不能凭相同条码误去重。
- 待核实列表为已建商品中 manually_verified=false 的记录；未知扫码取消后不建立库存商品。
- 浏览器仅在内存保存待确认请求；刷新/关闭页面前必须核对流水。无离线库存写入队列。
- 支持交互创建管理员/店员；完整账号管理、CSV 导出/上传界面、自动异地加密上传和周/月经营报表不在本轮交付范围。
- 预警管理页刷新会按商品 ID 顺序锁定商品并对账，适合小型店铺；大目录需后续按批优化。

## 验证与验收边界

最终实际测试结果记录在 PR。新增回归覆盖调整权限/CSRF/原因/防负数/幂等/撤销，预警跨越和
重复刷新，跨用户幂等键冲突，搜索，备份失败和原子发布，恢复拒绝生产库/非空库，秘密日志过滤，
以及真实 PostgreSQL 并发与 dump/restore 全行比对。

Linux 本地没有 Docker、PostgreSQL 服务和 Windows，不能把跳过的检查标为通过。GitHub CI
承担 PostgreSQL、官方工具恢复、Docker 构建、Compose 与 Windows PowerShell 解析；需要查看
对应提交的运行结果。Windows 10 开机/SYSTEM/HDD ACL、真实进程树停止、证书/手机 PWA、
防火墙和 HID 连扫仍必须按 `windows-deployment.md` 在店铺机验收。

补充验证：首轮远端 CI Run 35561620586 全部通过，含 6 项 PostgreSQL 集成/恢复测试、
Docker 构建/Compose、PowerShell 5.1 解析。后续补齐商品资料编辑和 Windows 进程烟雾测试后，
须以最终 PR 提交的 CI 为准。本地新增回归后为 46 passed / 6 postgres skipped。
