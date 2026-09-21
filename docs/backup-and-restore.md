# PostgreSQL 备份、恢复与演练

## 自动备份

`scripts/windows/backup.ps1` 调用 PostgreSQL 官方 `pg_dump.exe` 生成 custom-format 文件。文件先写
`.tmp`，以 `pg_restore --list` 校验后才原子改名为 UTC 时间戳名称，并按
`BACKUP_RETENTION_DAYS` 清理。密码只由进程环境 `PGPASSWORD` 提供，不出现在参数或日志。
建议 Windows Task Scheduler 每日以 SYSTEM 运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\GameInventory\scripts\windows\backup.ps1
```

检查退出码、任务历史和 HDD 新文件。每次重大更新和数据迁移前另做手动备份。本机 HDD 不同于
异地备份：定期把 dump 客户端加密后复制到受控的另一设备/云账号，并演练下载和解密。

## 安全恢复与完整演练

恢复会清理**明确指定的目标数据库**中的同名对象。先冻结应用写入并再次备份。绝不在首次演练
中使用 `inventory`，也不要复制 PostgreSQL data directory。以管理员创建空测试库
`inventory_restore_drill_YYYYMMDD`，赋予 inventory 角色，然后：

```powershell
.\scripts\windows\restore.ps1 -DumpFile D:\GameInventoryBackups\inventory_....dump `
  -TargetDatabase inventory_restore_drill_YYYYMMDD -ConfirmTarget inventory_restore_drill_YYYYMMDD
```

脚本先验证归档、执行 `pg_restore --clean --if-exists --exit-on-error`，再针对目标运行
`alembic upgrade head`。之后把 `DATABASE_URL` 临时指向演练库，执行健康检查与自动化测试，并
用只读 SQL 比较用户、商品、目录、库存、流水和预警行数；验证条码唯一、库存均非负、每个
REVERSAL 的关联存在、管理员登录及抽样商品前后库存一致。记录 dump 哈希、时间、行数和结果。
核验完才删除**演练库**，不得删除生产库。

真实灾难恢复也必须停止应用，使用同样的明确双重数据库名确认，完成行数/约束/登录/扫码检查后
才恢复客户端。若检查失败，保持客户端冻结，保存日志，重新创建空目标再恢复上一份已验证 dump。
