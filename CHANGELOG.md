# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/) 规范。

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
