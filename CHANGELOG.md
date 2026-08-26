# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/) 规范。

## [3.0.1] - 2026-08-26

### 新增

- **多P视频下载功能**：新增 `download_all_pages` 配置项（`bool`，默认 `false`），开启后尝试下载视频所有 P（最多 10 个），关闭则只下载 1P
- **VideoCard 多P字段**：新增 `pages`（所有 P 的信息 `[{page, part, duration}]`）、`downloaded_pages`（已下载的 P 号列表）以及 `page_count`（总 P 数）属性
- **多P下载处理**：新增 `_handle_multi_page()`，逐 P 检测时长/大小限制，跳过不满足的 P 并发送提示，最后发送汇总提示、汇总卡片和逐个视频文件
- **多P汇总提示**：新增 `_format_multi_page_prompt()`，生成包含各 P 标题、时长、大小的汇总提示
- **汇总卡片多P徽标**：标题下方粉色徽标“共 N P · 本次下载 M P”
- **时长格式化工具**：新增 `format_duration()`（`core/utils.py`），将秒转换为 `MM:SS` 或 `HH:MM:SS`
- **下载计划缓存**：新增 `DownloadPlan` 数据类（`core/models.py`），缓存一次 `get_download_url` 的结果（视频/音频 URL、码率、实际画质）
- **手动下载多P支持**：`/bili 下载` 同步支持多P

### 变更

- **`service.py`**：
  - 移除 `estimate_download_size`、`download_video(bvid/aid)`、`_download_video`
  - 新增 `prepare_download()`：仅一次 `get_download_url`，失败记录 `logger.warning`
  - 新增 `estimate_size(plan)`：纯计算，无网络请求
  - 新增 `download_video(plan)` → `_download_from_plan(plan)`：复用 plan URL
  - `fetch_video_card` 移除 `download` 参数，只负责获取信息
- **`main.py` 下载流程**：改为 `prepare → estimate → check → download(plan)`
- **多P行为约定**：忽略 `?p=N` 参数，从第 1P 开始下载全部；发送汇总卡片 + 全部视频；一条汇总提示；最多 10 个 P
- **配置与文档**：`metadata.yaml` 版本 `3.0.0` → `3.0.1`；`README.md` 新增 `download_all_pages` 配置说明；`_conf_schema.json` 新增 `download_all_pages` 配置项

### 修复

- **视频偶发“只发图片不下载”（静默失败）**： `get_download_url` 被调用两次（`estimate_download_size` 与 `download_video` 各一次），连续请求易触发 B 站风控限流，第二次拿到空流导致静默失败。通过引入 `DownloadPlan` 缓存一次请求结果，将 API 请求从 4 次降到 2 次，大幅降低限流概率。同时 `plan` 为 `None` 时提示“获取下载信息失败，请稍后重试”，使失败可见
- **转发 Component（QQ 小程序卡片）去重失效**：根因是 Component 提取的短链 URL 带跟踪参数（`ts` 等），每次转发参数不同导致去重 key 不稳定。修复方式为将短链解析移到去重之前，用解析后的稳定 BV/AV 作为去重 key，并在 `on_message` 中调换“短链解析”与“去重”两段代码顺序，同时补充视频场景的 `bvid_or_url` 赋值


## [3.0.0] - 2026-08-04

### 新增
- **模块拆分**：单文件 1668 行拆分为 `core/` 子包下 7 个模块（constants / models / utils / credential / resolver / service / card_builder），`main.py` 仅保留插件入口与命令路由
- **下载大小预估**：基于 DASH `bandwidth × duration / 8` 在下载前估算视频大小
- **下载限制模式**：新增 `download_restriction_mode` 配置（duration_only / size_only / both / either / none）
- **视频最大大小限制**：新增 `max_video_size_mb` 配置项
- **下载提示**：新增 `show_download_prompt`，下载前显示标题、时长、预估大小及实际画质
- **画质不符提醒**：实际画质与请求不符时提示"⚠️ 实际画质: 720P（请求: 1080P），登录后可获取更高质量"
- **下载失败原因**：新增 `show_download_fail_reason`，告知用户因时长/大小限制无法下载的具体原因
- **下载提示撤回**：新增 `retract_download_prompt`，开启后下载提示 60 秒后通过 OneBot API 撤回
- **`/bili` 命令树**：无子命令时自动显示所有可用命令及描述
- **core/__init__.py**：统一重导出，`main.py` 一行导入所有依赖

### 变更
- **配置默认值**：
  - `passive_parse_mode`: local → global
  - `video_quality`: 720P → 480P（默认无需登录）
  - `download_restriction_mode`: 新增，默认 both
- **清晰度选项**：去下划线（`_720P` → `720P`），WebUI 展示更友好
- **移除 `0=关闭限制`**：`auto_download_max_duration` 和 `max_video_size_mb` 不再支持 0 表示关闭，改为通过 `download_restriction_mode` 控制
- **命令精简**：移除独立 `/bili下载`、`/b站下载` 指令，统一为 `/bili 下载`
- **依赖注入**：`CardBuilder` 通过构造函数接收 `html_render` 可调用对象，解耦 Star 基类
- **网络 I/O 集中**：`download_b64`、`fetch_comments`、`resolve_short` 迁移至 `BilibiliService`
- **README**：更新

### 修复
- `resolve_short()` 短链解析后 AV 号检测误用 `BV_PATTERN`
- `/bili` 指令组下 `状态`/`登录`/`登出` 脱离为独立指令（装饰器顺序：`@permission_type` 必须在 `@bili.command` 外层）
- 撤回提示重复发送（`_send_via_onebot` 返回值歧义导致回退至 `event.send()`）
- 撤回从未执行（`event.send()` 返回对象非 `dict`，`message_id` 提取失败）
- `FONT_PATH` 路径适配 `core/` 目录结构

## [2.1.1] - 2026-08-01

### 新增
- 补全requirements中的缺失依赖

## [2.1.0] - 2026-08-01

### 新增
- 加入了之前忘记加的许可证
- B站专栏链接（`/read/cv`）解析：支持 API 获取标题、作者、正文，渲染为图片卡片
- B站图文动态链接（`/opus`、`t.bilibili.com`）解析：支持文字、图片、转发内容，渲染为图片卡片
- QQ 转发小组件短链（`b23.tv`）自动识别并解析为对应内容类型
- 专栏类 opus 自动转为 `/read/cv` 渲染（通过 `Dynamic.turn_to_article()`）
- `opus_try_article` 配置开关：控制 opus 无文字时是否尝试转专栏获取全文
- 图文动态卡片统计栏使用 vanfont 图标字体，与视频卡片风格统一

### 修复
- 短链重定向到非视频页面（opus/cv）时 bot 无反应
- 不同 URL 格式（`t.bilibili.com` vs `www.bilibili.com/opus`）触发去重互相拦截
- 专栏正文前 YAML frontmatter 导致卡片显示元数据而非正文
- 纯文本动态通过 polymer API 无法获取 desc 文字（缺少 `timezone_offset` 参数）

### 变更
- `fetch_article_info` 使用 `bilibili_api.article.Article` 类（对齐 ZhenXun），含 `json()` 和 `info.summary` 两级回退

## [2.0.1] - 2026-08-01

### 变更
- 仅仅是加了CHANGELOG而已

## [2.0.0] - 2026-08-01

### 新增
- `/bili 登出` 命令，登出后自动清空 `credential.json`、`bilibili_cookies` 及内存凭证
- `/bili 状态` 输出三行：解析模式、群解析状态、登录状态
- `passive_parse_mode` 配置项，支持全局模式与局部模式
- `enabled_groups` 配置项，局部模式下可手动配置生效群号
- 扫码登录后 Cookie 自动同步到 WebUI `bilibili_cookies` 面板

### 变更
- **配置**：`enable_passive_parse` 移除，改为 `passive_parse_mode`（`global` / `local`）
- **配置**：`send_cover` 描述改为"文字消息附带封面图"
- **配置**：`auto_download_max_duration` 描述改为"视频最大时长"
- **配置**：`video_quality` 从硬编码改为实际读取配置项
- **被动解析**：局部模式下 `/bili 自动下载 on/off` 控制群聊是否解析（原仅控制视频发送）
- **被动解析**：群组列表从 `auto_download.json` 迁移至 `config["enabled_groups"]`，命令操作实时同步 WebUI
- **扫码登录**：弃用 `bilibili-api` 的 `QrCodeLogin`，改用自有 `httpx` 客户端直调 B站 API
- **扫码登录**：本地使用 `qrcode` 库生成二维码图片

### 修复
- 视频下载无声音（DASH 流音频轨未正确检测）
- 时长限制 `auto_download_max_duration` 从未生效
- HTML 卡片分享与评论图标不显示（vanfont 码点错误）
- HTML 卡片右侧留白

### os
1.0.1简直是灾难 但是我今天更新了2.0.0 因为是基本上全改了 也加了CHANGELOG 但是因为没法撤回发版 CHANGELOG的添加也需要一个新的版本号

## [1.0.1] - 2026-07-30

### 变更
- 更新 README.md 内容

## [1.0.0] - 2026-07-30

### 新增
- 首个正式版本
- 被动解析：自动识别 B站链接并回复视频信息卡片
- 手动下载：`/bili下载` 或 `/bili 下载`
- 自动下载：`/bili 自动下载 on/off`
- 扫码登录：`/bili 登录`
- 登录状态查询：`/bili 状态`
- HTML 图片卡片渲染（封面、UP 主头像、统计数据、简介、热门评论）
- 去重缓存机制
- 视频下载清晰度配置
