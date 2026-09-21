# PostgreSQL 备份、空库恢复与隔离演练

## 手动与自动备份

`.env` 配置 DATABASE_URL、POSTGRES_BIN、BACKUP_DIR（HDD）、BACKUP_RETENTION_DAYS。
Windows 包装脚本加载配置后调用 `app.operations`；pg_dump/pg_restore 的全部连接字段统一从
DATABASE_URL 解析，避免备份一个库却给另一个库迁移。密码通过子进程环境提供，不在命令行中。
`PG*` 仅供手动 psql 等旧工具使用，不再控制新脚本。

```powershell
.\scripts\windows\backup.ps1
.\scripts\windows\install-backup-task.ps1 -At '03:00'
Start-ScheduledTask -TaskName GameInventoryBackup
Get-ScheduledTaskInfo -TaskName GameInventoryBackup
# 卸载每日任务
.\scripts\windows\install-backup-task.ps1 -Uninstall
```

custom-format 文件先写同目录 `.tmp`，非空且 `pg_restore --list` 成功后原子改名，文件名含 UTC
时间和随机后缀。成功后才清理超期 `inventory_*.dump`；失败返回非零，保留旧备份。工具版本必须
兼容源库，建议与生产 PostgreSQL 同主版本。SYSTEM 必须能读 .env 和程序，并能写 HDD。

定期把备份加密后复制到另一设备或独立云账号；同一电脑的 HDD 无法防止整机故障。密钥另存，
还必须验证下载和解密。项目不自动持有云账号凭据。

## 隔离恢复演练

```powershell
.\scripts\windows\verify-backup.ps1 -DumpFile 'D:\GameInventoryBackups\inventory_....dump'
```

命令通过官方 createdb 创建随机 `inventory_drill_<UUID>` 临时库，依次执行 pg_restore、
Alembic upgrade head、完整性校验，输出关键表行数和全行 SHA-256 指纹，最后只删除该随机临时库。
演练账号需要 CREATEDB 权限，可在验收窗口临时授予后撤销；日常应用账号无需此权限。
异常中断可能留下临时库，确认无用后由管理员手工清理，不能使用生产库名代替。

验证范围包括 users、catalog_entries、products、inventory_transactions、stock_alerts；全行
指纹可识别相同行数但用户权限、库存或流水内容不同的问题。输出不包含密码或完整业务记录。
完整性检查包含非负库存、条码唯一、流水前后值和增减一致、撤销商品/数量/关联正确。

要证明指定迁移副本与源库相同，必须先停止所有写入，再运行：

```powershell
# 先导入 .env 到当前会话（仅本机，不打印配置）
. .\scripts\windows\common.ps1
Import-InventoryEnvironment
& (Get-InventoryPython) -m app.operations fingerprint > data\exports\before.json
.\scripts\windows\backup.ps1
# 对上一步输出的 dump 做演练，将 JSON 结果保存
& (Get-InventoryPython) -m app.operations drill 'D:\GameInventoryBackups\inventory_....dump' > data\exports\restored.json
Compare-Object (Get-Content data\exports\before.json) (Get-Content data\exports\restored.json)
```

比较无差异才表示冻结时刻的数据完全一致。若旧版本尚无 stock_alerts，应仅对共同的历史表比较，
新表初始为空。运行中的生产库会继续变化，不能拿较晚的实时指纹冒充备份时刻数据。
CI 使用隔离测试库执行 dump→新库→restore→migration→逐表行数和全行指纹比对。

## 真正恢复

恢复脚本拒绝覆盖 DATABASE_URL 指定的现用库，也拒绝非空目标库。停止应用和写入，保留当前库，
由管理员创建新的空目标（同一实例、相同角色），然后：

```powershell
.\scripts\windows\restore.ps1 -DumpFile 'D:\GameInventoryBackups\inventory_....dump' `
  -TargetDatabase inventory_recovered_20260921 -ConfirmTarget inventory_recovered_20260921
```

恢复使用单事务、无 `--clean`，不会先删除原库中的对象。验证行数、指纹、用户角色、登录及
抽样库存后，将 `.env` 的 DATABASE_URL 切到新库，再启动应用。失败则保持冻结，保存日志，重建
另一个空目标重试；不让失败副本开始写入。测试套件会清空测试库，**禁止对生产库运行 pytest**。
