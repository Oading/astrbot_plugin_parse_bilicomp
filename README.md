<div align="center">

  <img src="https://raw.githubusercontent.com/Oading/astrbot_plugin_parse_bilicomp/main/logo.png" width="200">

# B站内容解析

</div>

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12%2B-blue)](Python)
[![AstrBot](https://img.shields.io/badge/AstrBot-%E2%89%A54.10.4-green)](AstrBot)

**解析B站相关内容组件并以图片展示，支持视频下载、动态/专栏预览等功能。**

> [!NOTE]
> 下文包含的命令前缀 `/` 即默认用户在WebUI中 配置文件>平台配置>唤醒词 使用了 `/` 如使用了其他唤醒词则直接替换即可
---
## 功能

| 名称 | 说明 |
|:---|:---|
| **被动解析** | 插件配置中可选不同的模式！自动识别消息中的 B 站内容组件（BV/AV 号、b23.tv 短链、小程序卡片），自动回复信息卡片 |
| **视频信息卡片** | 展示封面、UP 主头像、标题、播放/弹幕/点赞/投币/收藏/分享/评论数据、简介以及热门评论 |
| **动态/专栏信息卡片** | 展示动态或专栏的部分预览 |
| **解析冷却机制** | 默认 5 分钟内同一链接不重复解析，避免重复刷屏 |
| **手动下载** | 支持 `/bili 下载 <链接/BV号/AV号>` 主动下载 B 站视频 |
| **自动下载** | 管理员可通过`/bili 自动下载 on`、`/bili 自动下载 off`控制群内自动下载功能，该指令在全局解析下无效 |
| **下载限制** | 默认仅自动下载 10 分钟/100MB以内的视频，避免过大文件影响群聊体验 可通过WebUI配置下载视频最长时长与最大大小；且支持下载限制模式切换 |
| **下载提示** |  下载视频前会显示视频标题和预估大小，可选择是否主动撤回提示；当无法下载会告知原因 |
| **扫码登录** | 支持 `/bili 登录` 生成二维码扫码登录 B 站账号 |
| **登录状态查询** | 支持 `/bili 状态` 查看当前被动解析模式相关与登录状态 |
| **登出账号** | 支持 `/bili 登出` 登出后会清空bilibili_cookies的值 |

---

## 前置依赖

**FFmpeg** — 视频下载需要，必须安装并添加到系统 PATH。

- Windows：[FFmpeg](https://ffmpeg.org/download.html)
- macOS：`brew install ffmpeg`
- Linux：`apt install ffmpeg`

---

##  安装方式
> [!NOTE]
> 安装前请务必！务必！检查前置依赖是否正确安装

### 方式一：WebUI 安装(推荐)

```
在 AstrBot 管理面板中：

1. 进入 插件>插件市场（默认插件源）
2. 搜索 B站内容解析
3. 点击安装
```

### 方式二：手动安装

```
前往项目主页，在 Release 页面下载最新版本压缩包：

1. 下载插件压缩包
2. 解压到 AstrBot 插件目录
3. 重启 AstrBot 完成加载
```


## 配置说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `passive_parse_mode` | global | 被动解析模式 |
| `enabled_groups` | — | 当被动解析模式为local时可以按需添加需要被动解析的群组 |
| `send_video` | true | 解析或下载时同时发送视频文件 |
| `send_cover` | true | 渲染为图片卡片关闭时附加封面图片 |
| `render_as_image` | true | 渲染为 HTML 图片卡片，关闭则发送文字 + 封面图 |
| `cache_ttl` | 5 | 去重缓存时间（分钟），0 = 关闭 |
| `auto_download_max_duration` | 10 | 自动下载最大时长（分钟） |
| `max_video_size_mb` | 100 | 自动下载最大大小（MB） |
| `download_restriction_mode` | both | 下载限制模式 |
| `show_download_prompt` | true | 下载提示信息 |
| `show_download_fail_reason` | true | 下载失败信息 |
| `retract_download_prompt` | false | 开启后，下载成功时下载提示信息在一分钟后会尝试撤回 |
| `download_all_pages` | false | 开启后尝试下载视频的所有P（最多10个），每个P独立检测时长/大小限制；关闭则只下载1P |
| `video_quality` | 480P | 下载清晰度：360P / 480P / 720P / 1080P |
| `parse_template` | 详见插件配置 | 文字模式下的消息模板 |
| `opus_try_article` | true | 当识别到 /opus 时，尝试转为 /read/cv 获取全文。仅对专栏类动态生效，普通图文无效 |
| `*bilibili_cookies` | — | B站 Cookies（`/bili 登录` 扫码填充） |

---

<div align="center">

好用的话给个 ⭐ 吧
有问题请移步 [Issue](https://github.com/Oading/astrbot_plugin_parse_bilicomp/issues) 

</div>