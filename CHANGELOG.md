# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/) 规范。

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
