# 万能视频下载器 — 方案设计文档

> 版本: v1.0 | 日期: 2026-06-23 | 作者: AI + 人工审核

---

## 1. 技术选型

| 层 | 技术 | 版本 | 理由 |
|---|------|------|------|
| 下载引擎 | yt-dlp | 2026.03.17 | 170k+ Star, 支持 1000+ 平台, 活跃维护 |
| 后端框架 | FastAPI | 0.135.2 | 异步高性能, 自动 Swagger 文档, 轻量 |
| 前端框架 | Vue 3 + Vite | latest | 组件化, 生态成熟, Vite HMR 极速开发 |
| CSS 框架 | Tailwind CSS v4 | latest | 原子化 CSS, 自定义色板简便, 响应式内置 |
| 进程管理 | uvicorn | latest | ASGI 服务器, 支持热重载 |
| 运行环境 | Python 3.12 | 3.12.10 | 已安装, asyncio 特性完善 |

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────┐
│                    Browser                       │
│         Vue 3 + Vite + Tailwind CSS              │
│         localhost:5173 (dev) / static (prod)      │
└─────────────────┬───────────────────────────────┘
                  │ HTTP /api/*
                  ▼
┌─────────────────────────────────────────────────┐
│              FastAPI (uvicorn)                    │
│              localhost:8001                       │
│  ┌───────────────────────────────────────────┐  │
│  │  api.py                                    │  │
│  │  POST /api/info      解析视频信息           │  │
│  │  POST /api/download  提交下载任务           │  │
│  │  GET  /api/progress  查询下载进度           │  │
│  │  GET  /api/files     已下载文件列表         │  │
│  │  DELETE /api/files   删除文件               │  │
│  └──────────────┬────────────────────────────┘  │
│                 │                                  │
│  ┌──────────────▼────────────────────────────┐  │
│  │  downloader.py                             │  │
│  │  * extract_info() -> yt-dlp --dump-json     │  │
│  │  * download()     -> asyncio subprocess     │  │
│  │  * parse_progress() -> regex stdout         │  │
│  └──────────────┬────────────────────────────┘  │
│                 │                                  │
│  ┌──────────────▼────────────────────────────┐  │
│  │  models.py                                 │  │
│  │  Pydantic: VideoInfo / FormatInfo / Task  │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│              File System                          │
│              downloads/                           │
│              +-- video1.mp4                       │
│              +-- video2.mkv                       │
│              +-- ...                              │
└─────────────────────────────────────────────────┘
```

---

## 3. 数据流

```
用户输入 URL
    │
    ▼
POST /api/info { url }
    │
    ▼
downloader.extract_info(url)
    │  yt-dlp --dump-json -> parse JSON
    ▼
{ title, thumbnail, duration, formats[], platform }
    │
    ▼
用户选择 format_id
    │
    ▼
POST /api/download { url, format_id }
    │
    ▼
downloader.download(url, format_id, task_id)
    │  asyncio.create_subprocess_exec(yt-dlp, ...)
    │  parse stdout: "[download]  45.2% of ~50MiB at 2.1MiB/s ETA 00:13"
    │  update tasks[task_id] dict
    ▼
GET /api/progress/{task_id}  <-- 前端轮询 (1s interval)
    │
    ▼
{ percent: 45.2, speed: "2.1MiB/s", eta: "00:13", status: "downloading" }
    │
    ▼
status -> "done" -> 前端展示完成弹窗
```

---

## 4. 前端组件树

```
App.vue
+-- HeroSection.vue          # 渐变蓝 Hero + 特性标签
+-- URLInput.vue             # rounded-full 胶囊搜索栏
+-- VideoPreview.vue         # 封面/标题/时长/平台 icon 卡片
│   +-- FormatSelector.vue   # 4K/1080p/720p/MP3 质量标签
+-- DownloadCard.vue         # 进度条 + 速度/ETA + 完成弹窗
+-- VideoLibrary.vue         # Masonry 瀑布流视频库
```

---

## 5. 设计对标（ai.codefather.cn）

| 设计要素 | 值 |
|---------|-----|
| 主色 | `#3a5df9` (蓝) |
| 辅色 | `#ffb801` (金/收藏) |
| 背景 | `#ffffff` |
| 卡片 | `rounded-xl` + `ring-1 ring-slate-200/50` |
| 卡片 Hover | `shadow-2xl` + blue tint |
| 搜索栏 | `rounded-full` 胶囊 |
| 按钮 | `rounded-full` + `bg-primary hover:opacity-80` |
| 标签 | `rounded-full bg-black/40 backdrop-blur-xl text-white` |
| 加载 | `animate-pulse` 骨架屏 |
| 布局 | Masonry `columns-2 md:columns-3 lg:columns-4` |
| 字体 | 系统默认 + MiSans (可选) |

---

## 6. API 设计

### POST /api/info
```
Request:  { "url": "https://www.youtube.com/watch?v=xxx" }
Response: {
  "title": "...",
  "thumbnail": "https://...",
  "duration": 1234,
  "platform": "YouTube",
  "uploader": "...",
  "formats": [
    { "format_id": "137+140", "resolution": "1080p", "ext": "mp4", "filesize": 52428800 },
    { "format_id": "140", "resolution": "audio only", "ext": "m4a", "filesize": 3145728 }
  ]
}
```

### POST /api/download
```
Request:  { "url": "...", "format_id": "137+140" }
Response: { "task_id": "uuid-xxxx", "status": "queued" }
```

### GET /api/progress/{task_id}
```
Response: {
  "task_id": "uuid-xxxx",
  "percent": 45.2,
  "speed": "2.1MiB/s",
  "eta": "00:13",
  "status": "downloading" | "done" | "error",
  "filename": "video.mp4",
  "error": null
}
```

### GET /api/files
```
Response: {
  "files": [
    { "name": "video.mp4", "size": 52428800, "date": "2026-06-23T..." }
  ]
}
```

---

## 7. 配置说明 (config.py)

```python
DOWNLOAD_DIR = "./downloads"        # 下载输出目录
MAX_CONCURRENT = 2                  # 最大并发下载数
DEFAULT_FORMAT = "bestvideo+bestaudio"  # 默认格式
HOST = "0.0.0.0"
PORT = 8001
```

---

## 8. 启动方式

```bash
# 1. 安装依赖
pip install fastapi uvicorn yt-dlp python-dotenv

# 2. 启动后端
python main.py
# -> FastAPI 运行在 http://localhost:8001
# -> API 文档: http://localhost:8001/docs

# 3. 启动前端（开发模式）
cd frontend
npm install
npm run dev
# -> Vite 运行在 http://localhost:5173
# -> /api/* 自动 proxy 到 localhost:8001
```
