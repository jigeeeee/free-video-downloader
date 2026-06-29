# 万能视频下载器 — 方案设计文档

> 版本: v1.2 | 日期: 2026-06-29

## 1. 技术选型

| 层 | 技术 | 说明 |
|---|---|---|
| 下载引擎 | yt-dlp + 自研 Douyin 模块 | 通用平台走 yt-dlp，Douyin 走签名 API |
| 后端框架 | FastAPI + uvicorn | 异步 API、Swagger 文档、轻量部署 |
| 前端框架 | Vue 3 + Vite | 单页应用，开发体验好 |
| CSS | Tailwind CSS v4 | 原子化样式和响应式布局 |
| AI | DeepSeek + OpenAI-compatible SDK | 总结、问答、导图、翻译、改写 |
| 转录 | OpenAI Whisper | 本地音视频转文字 |
| 任务 | 内存 worker + asyncio.Semaphore | 单机并发控制 |
| 持久化 | SQLite | 任务、文件历史、AI 结果 |
| 音视频 | ffmpeg | 合并、转码、压缩、音频提取 |
| Cookie | 统一 CookieManager | QR/synced/cookies.txt/browser 多来源 |

## 2. 系统架构

```text
Browser / Vue 3
  ├─ URLInput / VideoPreview / FormatSelector
  ├─ AiPanel: 字幕、总结、导图、问答、改写
  ├─ VideoLibrary: 文件库、播放、删除、转换入口
  └─ TaskCenter: 任务状态、历史、失败重试
          │ HTTP /api/*
          ▼
FastAPI backend
  ├─ api.py              路由编排
  ├─ queue.py            内存任务 worker + 并发控制
  ├─ storage.py          SQLite 持久化
  ├─ downloader.py       yt-dlp 与平台路由
  ├─ douyin/             XBogus + ABogus 签名
  ├─ subtitle.py         字幕提取
  ├─ ai.py/prompts.py    DeepSeek 能力
  ├─ transcribe.py       Whisper 子进程
  ├─ media.py            ffmpeg 转换 + 安全路径
  ├─ cookies.py          Cookie 统一选择/同步
  └─ startup_checks.py   依赖检查
          │
          ▼
downloads/
  ├─ 视频/音频文件
  ├─ subtitles/
  ├─ uploads/
  ├─ synced_cookies.txt
  └─ video_downloader.db
```

## 3. 核心数据流

### 3.1 下载链路

```text
POST /api/info
  → downloader.extract_info(url)
  → 返回标题、封面、时长、格式

POST /api/download
  → queue.enqueue(download)
  → downloader.download()
  → yt-dlp 或 Douyin 专用下载
  → 进度写入内存 tasks + SQLite
  → 完成后文件写入 downloads/，文件记录写入 SQLite

GET /api/progress/{task_id}
  → 优先读取下载实时进度
  → 同步写回 SQLite
```

### 3.2 AI 链路

```text
URL
  → subtitle.extract_subtitles()
  → transcript text
  → DeepSeek: summary / mindmap / ask / rewrite / translate
  → ai_results 写入 SQLite
```

目前策略是字幕优先。后续缺字幕时应补“下载音频 → Whisper 转录 → AI”的 fallback。

### 3.3 转换链路

```text
POST /api/convert
  → queue.enqueue(convert)
  → media.convert_media()
  → ffmpeg 输出新文件
  → 文件记录写入 SQLite
```

## 4. API 设计总览

当前注册 33 个 `/api` 路由。

### 基础与任务

- `GET /api/health`
- `GET /api/tasks`
- `GET /api/tasks/{task_id}`
- `POST /api/tasks/{task_id}/retry`
- `GET /api/history`

### 下载与文件

- `POST /api/info`
- `POST /api/download`
- `GET /api/progress/{task_id}`
- `GET /api/files`
- `DELETE /api/files/{filename}`
- `GET /api/download/{filename}`
- `POST /api/batch`
- `GET /api/batch/{batch_id}`

### AI 与字幕

- `POST /api/subtitles`
- `GET /api/subtitles/{task_id}`
- `POST /api/summary`
- `GET /api/summary/{task_id}`
- `POST /api/mindmap`
- `GET /api/mindmap/{task_id}`
- `POST /api/ask`
- `GET /api/ask/{task_id}`
- `POST /api/translate`
- `POST /api/rewrite`
- `GET /api/rewrite/{task_id}`
- `POST /api/transcribe`
- `GET /api/transcribe/{task_id}`

### 转换与 Cookie

- `POST /api/convert`
- `GET /api/convert/{task_id}`
- `GET|POST /api/bilibili/qrcode`
- `GET /api/bilibili/qrcode/status`
- `GET /api/bilibili/status`
- `POST /api/cookies/sync`

## 5. 数据模型

### tasks

| 字段 | 说明 |
|---|---|
| `task_id` | 任务 ID |
| `task_type` | download/subtitle/summary/mindmap/ask/transcribe/convert/rewrite |
| `status` | queued/processing/done/error |
| `percent` | 进度 |
| `result` | JSON 结果 |
| `error` | 错误信息 |
| `metadata` | 原始任务参数 |
| `created_at` / `updated_at` | 时间戳 |

### files

保存已下载或转换生成的文件名、大小、路径、缩略图和时间。

### ai_results

保存 AI 任务结果：summary、mindmap、ask、rewrite 等。

## 6. 前端组件树

```text
App.vue
├── HeroSection.vue
├── URLInput.vue
├── VideoPreview.vue
├── AiPanel.vue
│   ├── 字幕
│   ├── AI 总结
│   ├── 思维导图
│   ├── 问答
│   └── 内容改写
├── FormatSelector.vue
├── DownloadCard.vue
├── VideoLibrary.vue
│   ├── 播放/下载
│   ├── 删除
│   ├── 提取 MP3
│   └── 压缩 MP4
└── TaskCenter.vue
    ├── 任务列表
    ├── 进度展示
    ├── 失败重试
    └── 最近 AI 结果
```

## 7. 安全设计

- 文件读取和删除必须通过 `resolve_download_file()`，拒绝路径分隔符和目录穿越。
- 上传转录只允许媒体扩展名，并受 `MAX_UPLOAD_MB` 限制。
- Cookie 同步保存为 Netscape 格式文件，不在 API 响应中展开 Cookie 内容。
- `.env`、`cookies.txt`、`downloads/` 已在 `.gitignore` 中排除。

## 8. 配置说明

```python
DOWNLOAD_DIR = "./downloads"
SUBTITLE_DIR = "./downloads/subtitles"
DB_PATH = "./downloads/video_downloader.db"
MAX_CONCURRENT = 2
MAX_UPLOAD_MB = 500
HOST = "0.0.0.0"
PORT = 8001
YTDLP_COOKIES_BROWSER = ""
```

## 9. 验证方式

```bash
python -m compileall main.py config.py backend
cd frontend && npm run build
```

已额外验证：YouTube 解析、字幕提取、下载、DeepSeek 翻译/改写、ffmpeg 转换、路径安全。
