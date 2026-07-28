# 实体游戏库存管理系统：项目需求规格

你现在是本项目的主开发工程师。请在当前 VS Code/Codex 工作区中，设计并实现一个可实际部署使用的“实体游戏库存管理系统”。

不要只输出伪代码、示例片段或架构建议。请先检查当前仓库状态，再按阶段创建完整源码、数据库迁移、测试、部署文件和说明文档。每完成一个阶段都要运行相应检查并修复问题。遇到不影响核心功能的细节时自行做合理决定，不要频繁停下来询问。

==================================================
一、项目背景和硬约束
==================================================

我要管理实体游戏店中销售的：

- PS5 实体光盘
- PS4 实体光盘
- Nintendo Switch 实体卡带
- Nintendo Switch 2 实体卡带

店铺里暂时没有电脑。店员只使用：

1. 任意一台可以联网的 Android 手机或 iPhone；
2. 一把支持 Bluetooth HID Keyboard 模式，或 USB-C OTG 键盘模拟模式的扫码枪；
3. 手机浏览器打开网页，或把网页安装成 PWA。

扫码枪会像外接键盘一样，把条码字符输入手机，并通常以 Enter 或 Tab 结束。

服务器、程序和数据库运行在云服务器、VPS、NAS 或其他长期在线设备上。手机只负责操作网页，不在手机本地保存正式库存数据库。

核心要求：

- 扫码入库、扫码出库必须足够简单，适合完全不懂技术的店员；
- 库存不能因为重复请求、网络抖动或并发操作而出错；
- 条码和游戏名称的对应优先使用“服务器本地映射表”，核心功能不得依赖 IGDB、UPCitemdb、Barcode Lookup 等第三方在线识别服务；
- 本地映射表可以不完整，识别不了的商品允许人工补录；
- 已人工确认过的条码以后必须永久自动识别；
- 项目必须保留清晰、可读、模块化的源码，不能只交付打包后的单文件程序、加密程序或不可修改镜像；
- 我以后要能够直接用 VS Code 打开项目，修改 Python、HTML、CSS、JavaScript 和配置文件；
- Docker 只用于方便部署，不得替代或隐藏源码；
- 中文界面和中文数据必须正常使用 UTF-8。

建议技术栈：

- Python 3.12
- FastAPI
- SQLAlchemy 2.x
- Pydantic 2.x
- Alembic
- PostgreSQL：正式环境
- SQLite：本地开发和测试
- HTML + CSS + Vanilla JavaScript
- PWA
- pytest
- Dockerfile + docker-compose.yml

除非确有必要，不使用 React、Vue 或大型前端工程。前端应保持容易修改。

==================================================
二、最重要的架构原则：本地映射表 + 业务数据库
==================================================

程序必须区分两类数据：

1. 本地条码映射目录：
   用来提供“条码 -> 游戏名称、平台、版本”等基础资料，可以由我以后自行替换、扩充和维护。

2. 正式业务数据库：
   保存商品、当前库存、出入库流水、销售统计、账号、库存预警和人工修正结果。

扫码时的查询顺序必须是：

1. 先查正式数据库中的 products；
2. 如果没有，再查已经导入数据库的本地条码目录；
3. 如果本地目录找到结果，建立或激活正式商品记录；
4. 如果本地目录也找不到，进入人工补录或待识别流程；
5. 核心扫码流程不得因为没有互联网或第三方 API 故障而失败。

本地映射表不是每次扫码时直接遍历大型 CSV。程序应将它导入专用数据库表或内存索引，再进行快速查询。

==================================================
三、本地条码映射表规范
==================================================

在项目中创建以下目录：

data/
  catalog/
    barcode_catalog.csv
    covers/
    README.md

其中：

- `data/catalog/barcode_catalog.csv` 是主映射表；
- `data/catalog/covers/` 可选保存本地封面图片；
- `data/catalog/README.md` 用中文说明格式、导入方式和注意事项。

请创建一个只有表头和少量“明显是假数据”的示例 CSV，不要虚构真实游戏条码。我要以后自己替换或扩充文件。

CSV 使用 UTF-8 编码。程序应兼容 UTF-8 和 UTF-8 with BOM。

必填列：

- barcode
- game_name
- platform

可选列：

- region
- edition
- language
- publisher
- release_year
- cover_filename
- aliases
- source
- verified
- notes

推荐表头：

barcode,game_name,platform,region,edition,language,publisher,release_year,cover_filename,aliases,source,verified,notes

字段规则：

1. barcode
   - 必须始终按字符串处理，绝对不能转换为整数；
   - 必须保留前导零；
   - 默认接受 8～14 位数字；
   - 去除首尾空格；
   - 在 CSV 和 Excel 中应建议用户把该列设为“文本”；
   - 数据库中建立唯一索引。

2. platform
   统一标准化为：
   - PS5
   - PS4
   - SWITCH
   - SWITCH2

   导入时允许识别常见写法，例如：
   - Switch
   - Nintendo Switch
   - Switch 2
   - NS
   - NS2

   但数据库中必须保存为统一枚举。

3. region
   可使用：
   - CN
   - HK
   - JP
   - US
   - EU
   - ASIA
   - OTHER
   - UNKNOWN

4. edition
   例如：
   - 普通版
   - 豪华版
   - 完全版
   - 限定版
   - 廉价版

5. aliases
   多个别名使用竖线 `|` 分隔，用于搜索，不用于判断条码唯一性。

6. cover_filename
   只保存文件名，例如：
   `1234567890123.jpg`

   实际文件放在：
   `data/catalog/covers/1234567890123.jpg`

7. verified
   支持 true/false、1/0、yes/no，并统一转换为布尔值。

导入功能必须实现：

- 管理员后台“导入/重新加载本地映射表”按钮；
- 命令行导入命令；
- 启动时可通过配置选择是否自动导入；
- 导入前校验列名、条码格式、平台值和重复条码；
- 生成导入报告：
  - 新增多少条；
  - 更新多少条；
  - 跳过多少条；
  - 冲突多少条；
  - 哪些行有错误；
- 单行错误不能导致整个文件全部导入失败；
- 导入过程使用数据库事务；
- 对大型 CSV 使用批量处理，不能逐条低效提交；
- 根据文件哈希判断文件是否发生变化，避免每次启动重复导入；
- 默认不能用映射表覆盖管理员已经人工修正并确认的正式商品；
- 提供“仅新增”“更新未人工确认记录”“强制覆盖”三种导入模式，其中强制覆盖只允许 ADMIN 使用；
- 本地映射表冲突时保存冲突报告，不得静默选择错误结果。

建立 `catalog_entries` 表用于保存已导入的目录数据。至少包含：

- id
- barcode
- game_name
- normalized_name
- platform
- region
- edition
- language
- publisher
- release_year
- cover_filename
- aliases
- source
- verified
- source_file
- source_row
- imported_at
- updated_at

人工补录的商品应保存到正式 `products` 表，同时提供：

- “导出人工新增映射”按钮；
- 导出为 `data/exports/manual_catalog_additions.csv`；
- 导出列格式与主映射表一致；
- 方便我以后把人工补录结果合并回自己的主映射表。

不要在多用户扫码过程中直接频繁改写主 CSV。正式运行时以数据库为准，CSV 主要用于批量导入、备份和迁移。

==================================================
四、商品和条码的业务含义
==================================================

商品应按 SKU 管理，而不是只按抽象游戏名称管理。

以下情况即使游戏名称相同，也可能是不同 SKU：

- PS4 版和 PS5 版；
- Switch 版和 Switch 2 版；
- 港版、日版、美版；
- 普通版、豪华版、限定版；
- 不同发行批次拥有不同条码。

一个条码默认对应一个商品 SKU。

建立 `products` 表，至少包含：

- id
- barcode：String，唯一索引
- game_name
- normalized_name
- platform
- region
- edition
- language
- quantity：Integer，默认 0，数据库约束 quantity >= 0
- low_stock_threshold：Integer
- overstock_threshold：Integer，可空
- cover_filename：可空
- identification_status：
  - CONFIRMED
  - CATALOG_MATCHED
  - PENDING
- metadata_source：
  - LOCAL_CATALOG
  - MANUAL
  - IMPORT
- catalog_entry_id：可空
- manually_verified：Boolean
- active：Boolean
- created_at
- updated_at

管理员人工修改并确认后，`manually_verified=true`。普通目录重新导入不得覆盖这些人工确认字段。

==================================================
五、手机端扫码流程
==================================================

店员登录后，首页只突出显示两个巨大按钮：

- 【📦 连续入库】
- 【💰 连续出库】

下方放较小按钮：

- 撤销上一步
- 今日流水
- 恢复扫码焦点
- 退出扫码
- 管理后台

进入扫码模式后必须：

- 全屏或近似全屏；
- 大号文字显示当前是“连续入库”还是“连续出库”；
- 入库和出库使用不同图标、文字和视觉样式，不能只靠颜色区别；
- 每次处理完成后保持当前模式；
- 店员可以连续扫描，不需要每件商品重新点击按钮；
- 页面明显显示在线、离线、正在提交、成功、失败状态；
- 成功和错误使用不同提示音；
- 使用 Web Speech API 中文播报结果，但语音失败不能影响库存操作。

扫码输入兼容：

- 条码字符 + Enter；
- 条码字符 + Tab；
- 扫码枪直接输入当前输入框；
- Bluetooth HID Keyboard；
- USB-C OTG 键盘模拟扫码枪。

不要只依赖 `autofocus`。必须同时实现：

1. 一个可聚焦但不妨碍布局的扫码输入框；
2. 页面级 keydown 条码缓冲；
3. Enter 或 Tab 结束符识别；
4. 页面被点击后自动恢复焦点；
5. 页面重新回到前台后恢复焦点；
6. 模态框关闭后恢复焦点；
7. 扫码提交完成后恢复焦点；
8. 提供手动输入条码的调试入口；
9. 当软键盘意外弹出时尽量避免干扰页面；
10. 显示“扫码枪已就绪”或“点击恢复扫码”。

条码校验：

- 条码作为字符串；
- 默认接受 8～14 位数字；
- 支持 EAN-8、UPC-A、EAN-13、GTIN-14；
- 校验位检查做成可配置选项，默认不强制；
- 非法输入要提示，但不能导致页面卡死。

==================================================
六、扫码幂等和并发安全
==================================================

每次扫码时，前端生成 UUID `client_scan_id`。

服务端必须对 `client_scan_id` 建立唯一约束。

同一个请求因为网络超时或前端重试被发送多次时：

- 只能改变一次库存；
- 重复请求返回第一次处理结果；
- 不能重复入库或重复出库。

注意：

- 相同条码可以连续扫描多件；
- 不同扫描必须使用不同 `client_scan_id`；
- 可以设置 200～300 毫秒的防抖；
- 不能设置过长冷却时间，因为店员可能连续扫描多份相同商品。

库存变化必须在数据库事务中完成。

正式 PostgreSQL 环境下必须正确处理并发。例如商品库存只有 1，两台手机同时出库：

- 只能一个成功；
- 另一个返回库存不足；
- quantity 绝对不能变成负数。

使用行锁、条件原子更新或其他可靠方式，并编写并发测试。

==================================================
七、已知和未知条码的处理
==================================================

1. 已知商品入库

- quantity + 1；
- 写入不可篡改流水；
- 返回游戏名称、平台、变化前库存、变化后库存；
- 播报：“游戏名称，入库成功，当前库存 X 件。”

2. 已知商品出库

库存大于 0：

- quantity - 1；
- 写入 SALE_OUT 流水；
- 播报：“游戏名称，出库成功，剩余 X 件。”

库存等于 0：

- 不修改库存；
- 不写成功流水；
- 返回 OUT_OF_STOCK；
- 播报：“游戏名称，库存不足，无法出库。”

3. 未知条码入库

按以下顺序：

- 查询 products；
- 查询 catalog_entries；
- 目录匹配成功则展示简短确认信息或按配置自动建立商品；
- 如果目录记录 `verified=true`，可直接创建 `CATALOG_MATCHED` 商品并入库；
- 如果目录记录未验证，手机显示游戏名称、平台、地区、版本，让店员一键确认；
- 如果完全查不到，弹出极简人工录入框。

人工录入框：

必填：
- 游戏名称
- 平台：PS5 / PS4 / Switch / Switch 2

可选：
- 地区
- 版本
- 低库存阈值
- 积压阈值

按钮：
- 【确认并入库】
- 【暂存为待识别】
- 【取消】

“确认并入库”必须在同一事务中：

- 创建正式商品；
- quantity 从 0 变为 1；
- 创建第一次入库流水。

“暂存为待识别”：

- 创建名称为 `待识别商品-{条码后六位}` 的 PENDING 商品；
- quantity 设为 1；
- 正常创建入库流水；
- 店员立即继续扫码；
- 管理后台集中处理待识别商品。

以后管理员补全 PENDING 商品后，同一条码永久使用新资料。

4. 未知条码出库

- 默认禁止出库；
- 不自动创建库存为负或库存不明的商品；
- 提示：“未知条码，请先入库登记或由管理员补全资料。”

==================================================
八、不可删除的库存流水和撤销
==================================================

建立 `inventory_transactions` 表：

- id
- client_scan_id：UUID，唯一索引
- product_id
- barcode_snapshot
- game_name_snapshot
- platform_snapshot
- operation_type：
  - IN
  - SALE_OUT
  - ADJUST_IN
  - ADJUST_OUT
  - REVERSAL
- quantity_delta
- quantity_before
- quantity_after
- related_transaction_id：可空
- user_id
- device_id：可空
- note：可空
- created_at

流水创建后不允许直接删除或改写。

撤销必须创建 REVERSAL 反向流水：

- 撤销 IN：生成 -1；
- 撤销 SALE_OUT：生成 +1；
- 原流水保留；
- 同一条流水不能撤销两次；
- 如果撤销会导致库存小于 0，则拒绝；
- STAFF 默认只能撤销自己最近一次、且在配置时间窗口内的操作；
- ADMIN 可以撤销指定流水。

==================================================
九、库存预警
==================================================

至少实现：

- LOW_STOCK：低库存
- SOLD_OUT：售罄
- OVERSTOCK：库存偏多
- STALE_STOCK：长期无销售

建立 `inventory_alerts` 表：

- id
- product_id
- alert_type
- transaction_id
- quantity_at_trigger
- message
- status：OPEN / ACKNOWLEDGED / RESOLVED
- created_at
- acknowledged_at
- resolved_at

状态逻辑：

- quantity == 0：售罄；
- 0 < quantity <= low_stock_threshold：低库存；
- quantity >= overstock_threshold：库存偏多；
- 当前有库存，但超过 `stale_stock_days` 没有 SALE_OUT：长期无销售。

预警必须按“状态跨越”创建，不能每次扫码重复提醒。

例子：

- 2 -> 1，阈值为 1：创建低库存预警；
- 1 -> 0：创建售罄预警；
- 已经为 0 时失败出库：不重复创建；
- 0 -> 1：关闭售罄预警；
- 补货到阈值以上：关闭低库存预警。

通知层级：

第一阶段必须实现：

- 当前扫码手机立即显示醒目售罄/低库存提示；
- 管理后台预警中心；
- 首页显示售罄、低库存、积压和待识别数量；
- 未处理预警可确认和关闭。

第二阶段实现标准 PWA Web Push：

- 管理员主动开启通知；
- 保存 PushSubscription；
- 服务端使用 VAPID；
- 商品售罄或进入低库存时向管理员设备推送；
- 推送失败不能回滚库存事务；
- 密钥全部使用环境变量。

另外提供可选 `ALERT_WEBHOOK_URL`，但不得成为核心功能依赖。

==================================================
十、查询、排序和销售统计
==================================================

创建移动端友好的管理后台。

库存列表支持搜索：

- 游戏名称
- 别名
- 条码
- 平台
- 地区
- 版本

筛选：

- 全部
- 正常库存
- 低库存
- 售罄
- 库存偏多
- 长期无销售
- 待识别

排序必须支持升序和降序：

- 当前库存
- 游戏名称
- 最近更新时间
- 最近销售时间
- 指定时间段销量
- 入库数量
- 出库数量

每项显示：

- 本地封面缩略图（没有则显示占位图）
- 游戏名称
- 平台
- 地区和版本
- 条码
- 当前库存
- 库存状态
- 最近销售时间
- 当前统计时间段销量

销售统计支持：

- 本周
- 本月
- 最近 7 天
- 最近 30 天
- 自定义开始和结束时间

统计：

- 总出库件数
- 每日出库件数
- 各平台销量
- 各游戏销量
- 销量最高商品
- 销量低但有库存商品
- 完全没有销售但有库存商品
- 售罄商品
- 低库存商品
- 库存积压商品

这里的销售只表示 SALE_OUT 件数，不表示销售金额。暂时不实现收入和利润，避免在没有进价、售价模型时混淆。

业务时区通过环境变量设置，例如：

`APP_TIMEZONE=Asia/Shanghai`

数据库时间统一保存 UTC，显示和报表转换为业务时区。

==================================================
十一、弱网和断网处理
==================================================

页面明显显示在线状态。

默认规则：

- 断网时禁止出库，因为无法确认最新库存；
- 入库可以选择加入 IndexedDB 待同步队列；
- 入库待同步记录保存原始 client_scan_id；
- 网络恢复后按顺序同步；
- 服务端幂等保证不会重复入库；
- 离线入库只能提示“已加入待同步队列”，不能假装已经被服务器确认。

环境变量：

`ALLOW_OFFLINE_OUT=false`

默认必须是 false。

==================================================
十二、账号和权限
==================================================

至少两种角色：

- ADMIN
- STAFF

使用用户名和密码登录。

要求：

- 密码使用 Argon2 或 bcrypt 哈希；
- 登录状态使用安全的 HttpOnly Cookie；
- 正式环境支持 HTTPS；
- 做基本的 CSRF、XSS、SQL 注入防护；
- 前端不得保存数据库密码和服务器密钥；
- 不在代码中写死管理员密码。

STAFF：

- 入库
- 出库
- 查看今日流水
- 在限制条件下撤销自己的最后一步

ADMIN：

- 全部 STAFF 权限
- 查看全部库存和报表
- 编辑商品资料
- 处理待识别商品
- 修改库存阈值
- 处理预警
- 导入本地映射表
- 导出人工新增映射
- 管理账号
- 启用推送
- 查看导入冲突和系统设置

提供创建首个管理员的命令行命令。

==================================================
十三、建议 API
==================================================

至少提供：

认证：
- POST /api/auth/login
- POST /api/auth/logout
- GET /api/auth/me

扫码：
- POST /api/scans
- POST /api/scans/resolve-unknown

撤销和流水：
- POST /api/transactions/undo-last
- POST /api/transactions/{id}/reverse
- GET /api/transactions
- GET /api/reports/daily

商品：
- GET /api/products
- GET /api/products/{id}
- PATCH /api/products/{id}

报表：
- GET /api/reports/sales
- GET /api/reports/stock-health

预警：
- GET /api/alerts
- POST /api/alerts/{id}/acknowledge

本地目录：
- POST /api/admin/catalog/import
- GET /api/admin/catalog/import-status
- GET /api/admin/catalog/conflicts
- GET /api/admin/catalog/export-manual-additions

推送：
- POST /api/push/subscribe
- DELETE /api/push/subscribe

所有列表接口支持分页。

扫码请求示例：

{
  "client_scan_id": "UUID",
  "barcode": "0012345678905",
  "operation": "IN",
  "device_id": "optional-device-id"
}

扫码成功返回至少包括：

- success
- code
- message
- product
- quantity_before
- quantity_after
- transaction_id
- alerts_created
- idempotent_replay

业务错误使用清晰 code，例如：

- INVALID_BARCODE
- UNKNOWN_BARCODE
- UNKNOWN_BARCODE_REQUIRES_INPUT
- OUT_OF_STOCK
- DUPLICATE_REQUEST
- OFFLINE_OUT_NOT_ALLOWED
- PERMISSION_DENIED

不要把正常业务错误全部作为 HTTP 500。

==================================================
十四、前端和 PWA
==================================================

至少创建：

- app/static/index.html
- app/static/app.js
- app/static/styles.css
- app/static/manifest.webmanifest
- app/static/service-worker.js
- app/templates/ 或等价目录

要求：

- 手机优先；
- 支持 320px 宽度；
- 大触控按钮；
- 不依赖鼠标悬停；
- PWA 可添加到主屏幕；
- 缓存应用外壳；
- 不缓存敏感库存 API 响应；
- 新版本 Service Worker 有更新提示；
- 网络状态可见；
- 扫码结果使用 aria-live；
- 不使用难以维护的复杂前端构建工具；
- HTML、CSS、JS 分文件，注释清楚。

==================================================
十五、源码目录和 VS Code 可维护性
==================================================

建议目录：

app/
  main.py
  config.py
  database.py
  models/
  schemas/
  api/
  services/
    inventory_service.py
    alert_service.py
    report_service.py
    catalog_service.py
  auth/
  static/
  templates/
alembic/
data/
  catalog/
    barcode_catalog.csv
    covers/
    README.md
  exports/
tests/
scripts/
.vscode/
Dockerfile
docker-compose.yml
requirements.txt 或 pyproject.toml
.env.example
README.md

要求：

- 不把全部逻辑塞进 main.py；
- 路由、业务服务、数据库模型、数据校验分离；
- 使用类型注解；
- 核心业务逻辑写中文注释；
- 使用清晰命名；
- 提供 `.vscode/launch.json` 和必要的开发说明；
- 支持在 VS Code 中直接运行和调试；
- 不混淆开发配置和生产配置；
- 不生成混淆、加密或压缩后的源码作为唯一交付物；
- Dockerfile 中复制的是当前源码；
- README 解释每个主要目录用途。

==================================================
十六、环境变量
==================================================

提供 `.env.example`，至少包含：

APP_ENV=development
APP_TIMEZONE=Asia/Shanghai
SECRET_KEY=
DATABASE_URL=sqlite+aiosqlite:///./inventory.db

AUTO_IMPORT_LOCAL_CATALOG=true
LOCAL_CATALOG_PATH=./data/catalog/barcode_catalog.csv
LOCAL_COVER_DIR=./data/catalog/covers
CATALOG_IMPORT_MODE=ADD_ONLY

DEFAULT_LOW_STOCK_THRESHOLD=1
DEFAULT_OVERSTOCK_THRESHOLD=10
STALE_STOCK_DAYS=30
ALLOW_OFFLINE_OUT=false
UNDO_WINDOW_MINUTES=10

VAPID_PUBLIC_KEY=
VAPID_PRIVATE_KEY=
VAPID_SUBJECT=mailto:example@example.com
ALERT_WEBHOOK_URL=

正式 PostgreSQL 示例：

DATABASE_URL=postgresql+asyncpg://inventory_user:password@db:5432/inventory

不能提交真实密钥。

==================================================
十七、迁移、初始化、备份和部署
==================================================

使用 Alembic。

不能把 `Base.metadata.create_all()` 作为正式环境唯一升级方式。

提供命令或脚本：

- 初始化开发环境；
- 执行数据库迁移；
- 创建管理员；
- 导入本地条码目录；
- 导出人工新增映射；
- 导出库存 CSV；
- 备份数据库；
- 恢复数据库。

提供：

- Dockerfile
- docker-compose.yml
- PostgreSQL 服务
- 健康检查
- 数据持久化 volume
- 日志配置

README 分别说明：

1. Windows + VS Code 本地开发；
2. SQLite 快速启动；
3. Docker Compose + PostgreSQL 启动；
4. 云服务器部署；
5. 域名和 HTTPS；
6. 手机打开网页并添加到主屏幕；
7. 扫码枪切换到 HID Keyboard 模式；
8. 扫码枪后缀设置为 Enter；
9. 更换或扩充 barcode_catalog.csv；
10. 重新导入映射表；
11. 导入冲突如何处理；
12. 创建管理员；
13. 开启 Web Push；
14. 备份和恢复。

==================================================
十八、测试要求
==================================================

使用 pytest，必须实际运行。

至少覆盖：

1. 已知商品入库；
2. 已知商品出库；
3. 零库存禁止出库；
4. 未知条码禁止出库；
5. 本地目录匹配后创建商品并入库；
6. 本地目录查不到后人工创建商品；
7. PENDING 商品创建；
8. 条码前导零不会丢失；
9. UTF-8 BOM CSV 可以导入；
10. 平台别名被正确标准化；
11. CSV 重复条码被报告；
12. 单行错误不导致整个导入失败；
13. 人工确认商品不被普通目录导入覆盖；
14. 同一 client_scan_id 重复发送不重复改变库存；
15. 相同条码使用不同 client_scan_id 可以连续计数；
16. 撤销入库；
17. 撤销出库；
18. 同一流水不能撤销两次；
19. 撤销不删除原流水；
20. 低库存状态跨越创建预警；
21. 售罄状态跨越创建预警；
22. 补货关闭售罄预警；
23. 失败出库不重复创建售罄预警；
24. 库存排序升序和降序；
25. 周、月、自定义时间段销售统计；
26. 长期无销售判断；
27. 两个并发请求争抢最后一件库存时只能成功一个；
28. 数据库异常会回滚；
29. 无本地映射文件时程序仍可启动并允许人工录入；
30. 导出人工映射 CSV 格式正确。

如果 SQLite 不能准确模拟 PostgreSQL 锁，提供 PostgreSQL 集成测试或清晰说明验证方法。

==================================================
十九、移动端验收场景
==================================================

场景 A：连续入库

1. 手机登录；
2. 点击连续入库；
3. 扫码枪输入条码并发送 Enter；
4. 本地目录能识别；
5. 服务器完成入库；
6. 手机播报名称和库存；
7. 不需要再次点击，继续扫描下一件。

场景 B：未知商品

1. 扫描目录中不存在的条码；
2. 弹出简单录入框；
3. 输入名称、选择平台；
4. 点击确认并入库；
5. 商品库存为 1；
6. 以后再次扫描直接识别；
7. 可以导出到人工新增映射 CSV。

场景 C：售罄

1. 扫描库存为 1 的商品出库；
2. 库存变成 0；
3. 当前手机立即提示售罄；
4. 管理后台出现售罄预警；
5. 管理员 PWA 收到推送；
6. 再次出库提示库存不足；
7. 库存不为负数。

场景 D：并发

1. 两台手机同时出库库存为 1 的商品；
2. 一台成功；
3. 另一台库存不足；
4. 数据库无负库存。

场景 E：更换映射表

1. 把新的 barcode_catalog.csv 放进指定目录；
2. 管理员点击重新导入；
3. 页面显示新增、更新、跳过和冲突数量；
4. 原人工确认商品不被覆盖；
5. 新条码可以立即识别；
6. 不需要修改程序源码。

场景 F：无外部网络识别服务

1. 禁用所有第三方商品查询服务；
2. 只保留手机到本系统服务器的连接；
3. 本地映射表查询、人工补录、入库、出库、报表全部正常工作。

==================================================
二十、实施顺序
==================================================

请严格按以下阶段推进：

阶段 1：检查仓库，给出简短实施计划。
阶段 2：建立项目结构、配置、开发环境和 VS Code 调试配置。
阶段 3：实现数据库模型和 Alembic 迁移。
阶段 4：实现本地目录 CSV 校验、导入、冲突报告和导出。
阶段 5：实现库存事务、幂等、并发安全和撤销。
阶段 6：实现商品、扫码、流水和报表 API。
阶段 7：实现预警。
阶段 8：实现认证和权限。
阶段 9：实现手机连续扫码页面。
阶段 10：实现 PWA、离线入库队列和 Web Push。
阶段 11：编写并运行测试。
阶段 12：实际启动应用，检查主要接口和页面。
阶段 13：修复错误，补充 README 和部署文件。

优先级：

P0：
- 库存正确
- 条码前导零不丢失
- 连续扫码稳定
- 本地映射表可靠
- 未知商品可人工处理
- 幂等
- 并发不出现负库存
- 源码可维护

P1：
- 查询、排序、销售统计
- 低库存和售罄预警
- CSV 导入导出
- PWA

P2：
- Web Push
- 更丰富图表
- 非核心界面美化

不要为了实现 P2 而牺牲 P0。

==================================================
二十一、最终交付要求
==================================================

完成后必须报告：

- 创建和修改了哪些文件；
- 项目目录结构；
- 已实现功能；
- 尚未实现或有限制的功能；
- 数据库模型；
- 本地映射表格式；
- 测试命令和测试结果；
- 本地 SQLite 启动命令；
- PostgreSQL/Docker 启动命令；
- VS Code 调试方法；
- 首个管理员创建方法；
- 映射表导入方法；
- 人工新增映射导出方法；
- 云服务器部署步骤；
- 还需要我提供哪些环境变量或凭据。

不要声称未实际运行的测试已经通过。
不要留下会阻断核心流程的 TODO。
不要依赖第三方在线条码识别服务完成核心功能。
不要只交付打包结果；必须交付完整、可读、可修改的源码。
