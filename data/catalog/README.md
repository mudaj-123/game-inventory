# 本地条码目录

`barcode_catalog.csv` 是本系统离线维护的“条码 → SKU 资料”主映射表。核心库存流程不依赖任何第三方在线条码识别服务。模板中的记录是明显的假数据，仅用于展示格式，正式使用前请删除或替换。

## 文件格式

- 编码：UTF-8；后续导入器也应兼容 UTF-8 with BOM。
- 表头：`barcode,game_name,platform,region,edition,language,publisher,release_year,cover_filename,aliases,source,verified,notes`
- 必填列：`barcode`、`game_name`、`platform`；其余列可为空。
- `barcode` 必须按**文本**保存，去除首尾空格后通常为 8～14 位数字，并保留所有前导零。在 Excel 中编辑时请预先将整列设置为“文本”。
- `platform` 的标准值为 `PS5`、`PS4`、`SWITCH`、`SWITCH2`。
- `aliases` 中的多个别名以竖线 `|` 分隔。
- `cover_filename` 只填写文件名；对应图片放入 `covers/`。
- `verified` 可填写 `true`/`false`、`1`/`0` 或 `yes`/`no`。
- 每个条码应唯一；不要填写真实密钥、用户资料或其他敏感数据。

## 导入说明

P0 初始化阶段只提供模板，尚未实现目录导入命令。下一阶段将把 CSV 校验后批量导入 `catalog_entries` 数据库表，而不是在每次扫码时遍历 CSV。届时将提供仅新增、更新未人工确认记录和管理员强制覆盖三种模式，并输出逐行错误及冲突报告。
