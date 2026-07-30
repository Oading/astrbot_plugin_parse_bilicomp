# B站内容解析 (astrbot_plugin_parse_bilicomp)

AstrBot 插件，解析 B站视频链接并以 HTML 图片卡片展示信息，支持视频下载、自动下载、扫码登录。

## 功能

### 1. 被动解析

自动识别消息中的 B站链接（BV/AV 号、b23.tv 短链、小程序卡片），回复视频信息卡片。

- 卡片包含：封面、UP 主头像、标题、统计数据（播放/弹幕/点赞/投币/收藏/分享/评论）、简介、热门评论
- 默认 5 分钟内同一链接不重复解析

### 2. 手动下载

```
/bili下载 <链接/BV号/AV号>
/bili 下载 <链接/BV号/AV号>
```

支持视频链接、BV/AV 号。也可直接回复一条包含 B站链接的消息，然后发送 `/bili下载` 或 `/bili 下载`（不带参数）。

### 3. 自动下载

管理员命令，控制群内自动下载：

```
/bili 自动下载 on    开启
/bili 自动下载 off   关闭
```

开启后，被动解析到视频链接时会自动下载并发送视频文件。默认仅下载 10 分钟以内的视频。

### 4. 扫码登录

```
/bili 登录   生成二维码扫码登录
/bili 状态   查看登录状态
```

登录后可获取更高清晰度视频。

## 安装

### 依赖

```
httpx>=0.25.0
bilibili-api-python>=16.0.0
```

> **注意**：必须安装 `bilibili-api-python`，不是 `bilibili-api`。

### 外部依赖

**FFmpeg** — 视频下载需要，必须安装并添加到系统 PATH。

- Windows：[FFmpeg 官网](https://ffmpeg.org/download.html) 下载，解压后将 bin 目录加入 PATH
- macOS：`brew install ffmpeg`
- Linux：`apt install ffmpeg`

## 配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enable_passive_parse` | true | 启用被动解析 |
| `render_as_image` | true | 渲染为 HTML 图片卡片，关闭则发送文字 + 封面图 |
| `send_video` | true | 解析或下载时同时发送视频文件 |
| `send_cover` | true | render_as_image=false 时附加封面图片 |
| `cache_ttl` | 5 | 去重缓存时间（分钟），0 = 关闭 |
| `auto_download_max_duration` | 10 | 自动下载最大时长（分钟），0 = 关闭限制 |
| `video_quality` | _720P | 下载清晰度：_360P / _480P / _720P / _1080P |
| `parse_template` | 见默认值 | 文字模式下的消息模板 |
| `bilibili_cookies` | — | B站 Cookie（可手动填入或用 `/bili 登录` 自动填充） |

## 注意事项

- 视频下载依赖 FFmpeg 进行音视频合并
- 高清晰度视频需要登录 B站账号
- 本插件仅使用官方 API，不支持下载会员专享内容
- 请合理使用下载功能，避免频繁大量下载导致 IP 被限制
