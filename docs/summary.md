# 万能视频下载器 — 项目总结

> 版本: v1.0 | 日期: 2026-06-25

## 一、项目概述

"万能视频下载器" 是一个基于 Python + Vue 3 的全栈 Web 应用。用户粘贴视频链接即可解析、选择清晰度、一键下载到本地。已支持 YouTube、Bilibili、Douyin（抖音）三大主流平台。

## 二、完成的功能

### 核心功能（Phase 1-3）

| 功能 | YouTube | Bilibili | Douyin |
|------|:---:|:---:|:---:|
| URL 解析 | ✅ | ✅ | ✅ |
| 格式选择 | ✅ 16 格式 / 4K | ✅ | ✅ 1080p |
| 实时下载进度 | ✅ | ✅ | ✅ |
| 音视频自动合并 | ✅ yt-dlp 内置 | ✅ yt-dlp 内置 | ✅ ffmpeg |
| 无需登录 | ✅ | ❌ cookies.txt | ❌ cookies.txt |
| 应用内播放 | ✅ | ✅ | ✅ |
| 删除已下载 | ✅ | ✅ | ✅ |

### 扩展功能

- **Masonry 瀑布流视频库** — 已下载视频卡片式展示
- **cdn 容错** — Douyin 3 个 CDN 备用 URL 自动 fallback
- **响应式 UI** — 手机/平板/PC 自适应
- **设计系统** — 仿 ai.codefather.cn 风格（#3a5df9 蓝主色、glassmorphism 标签、rounded-full 搜索栏、shadow-2xl 卡片 hover）

## 三、技术亮点

### 1. 自研 Douyin 签名引擎

Douyin 是三大平台中最难攻克的一个。yt-dlp 对 Douyin 支持不完整（"Fresh cookies" 错误）。项目自研了完整的签名方案：

- **X-Bogus**：RC4 + MD5 签名，纯 Python 实现
- **A-Bogus**：SM3 国密哈希 + 自定义 Base64 + 浏览器指纹
- **API 直调**：绕过 yt-dlp，requests 直连 Douyin API
- **音视频分离合并**：Douyin 的 video 和 audio 是独立 CDN 流，项目分别下载后用 ffmpeg 合成

### 2. 多平台统一调度

`backend/downloader.py` 作为统一入口，根据 URL 自动路由：

```
URL → _detect_platform()
  ├── YouTube  → yt-dlp (3 客户端策略 fallback)
  ├── Bilibili → yt-dlp + cookies.txt
  ├── Douyin   → 自研模块 (XBogus + ABogus)
  └── Other    → yt-dlp 通用
```

### 3. Cookie 管理

- `cookies.txt` 统一管理（Netscape 格式）
- 支持 Bilibili + Douyin 多站点共存
- Douyin 模块独立读取，不依赖 yt-dlp 的 cookie 逻辑

## 四、架构演进记录

| 日期 | 变更 | 原因 |
|------|------|------|
| 06-23 | yt-dlp subprocess → Python API | header 控制更好 |
| 06-23 | 3 客户端策略 (web/android/ios) | YouTube bot 检测 |
| 06-24 | 添加 XBogus 签名 | Bilibili 412 / Douyin "Fresh cookies" |
| 06-24 | 添加 ABogus (GMSSL) | Douyin API 强制要求 a_bogus |
| 06-25 | Douyin 完全绕开 yt-dlp | Chrome cookie 锁 + 直链过期 |
| 06-25 | CDN 3 URL fallback | Douyin 单 URL 超时率高 |
| 06-25 | ffmpeg 音视频合并 | Douyin 视频无声音 |
| 06-25 | COOKIES_BROWSER 默认关闭 | Chrome 锁导致 Bilibili 无法下载 |

## 五、性能数据

| 指标 | 数值 |
|------|------|
| YouTube 解析速度 | ~3s |
| Bilibili 解析速度 | ~2s |
| Douyin 解析速度 | ~2s（含签名计算） |
| Douyin 1080p 下载 | ~30s（视频 80% + 音频 20%） |
| 前端构建 | 184ms (Vite) |

## 六、已知限制

1. **Douyin** — cookies 需定期刷新（7 天左右），过期需重新导出
2. **YouTube** — 部分被标记的视频需要 cookies
3. **Git 推送** — 当前环境需通过代理（7890）或 GitHub API

## 七、后续规划

- [ ] 批量下载（多 URL 队列）
- [ ] 视频格式转换（MP4 / MKV / MP3）
- [ ] AI 视频总结（DeepSeek API）
- [ ] 字幕下载
- [ ] VIP 付费系统
- [ ] Docker 一键部署
