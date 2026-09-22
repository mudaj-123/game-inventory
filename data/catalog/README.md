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

## 导出人工新增映射

管理员在“库存与预警管理”点击“导出人工新增映射 CSV”，下载
`manual_catalog_additions.csv`。它包含 `metadata_source=MANUAL` 的商品（人工补录及人工
修正的目录商品，含未核实与停用商品），不受库存页筛选影响；`verified` 使用实际核实状态。
目录关联存在时补充 publisher、release_year、aliases，其余使用商品当前资料。
仅从目录导入、未经人工修正的商品不包含在此文件。

也可以在应用目录运行：

```powershell
.\.venv\Scripts\python.exe -m app.cli export-manual-catalog
# 可选另存位置
.\.venv\Scripts\python.exe -m app.cli export-manual-catalog --output D:\exports\manual.csv
```

默认写入 `data/exports/manual_catalog_additions.csv`。生成完整后原子替换；失败保留原文件，
不自动合并或覆盖主目录。浏览器下载保存到客户端，不会自动写入服务器上述路径。

导出使用 UTF-8 BOM，业务列与主目录一致，额外的 `csv_text_encoding=apostrophe-v1` 列
表示文本转义方式：以公式字符或单引号等开头的文本增加一个保护单引号，避免表格软件将其
当公式执行。本系统导入时根据标记还原；没有该标记的普通 CSV 仍按原格式读取。
保留标记列及保护前缀可直接重新导入本系统，不要手工删除它们或给普通 CSV 随意加上标记。
若要并入不带该标记的主目录，请保留原导出文件单独导入，避免混用两种文本编码。

条码在文件中是原始数字字符串（包含前导零），没有用公式包装。Excel/WPS 自动推断类型可能
丢弃前导零：请用“从文本/CSV 导入”，在加载前把 barcode 列设为文本，不要直接双击后保存。
表格软件重存文件可能改变条码或保护前缀；重新导入前请核对原文件。导入建议先使用 ADD_ONLY；
现有条码会跳过，修改已核实条目需谨慎选择原有的导入模式。
