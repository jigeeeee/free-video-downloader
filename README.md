# Universal Video Downloader

万能视频下载器 — 粘贴链接，一键下载，并提供字幕提取、AI 总结、思维导图、智能问答、内容改写、格式转换和任务历史管理。

支持 YouTube、Bilibili、Douyin 等 100+ 平台。项目定位为本地单机音视频生产力工具，所有下载文件、任务记录和 AI 结果默认保存在本机。

## Features

### 核心下载
- **YouTube** — 支持多格式解析与下载，自动处理音视频合并
- **YouTube 403 fallback** — 下载阶段自动切换 YouTube 客户端并降级格式，可选 PO Token
- **Bilibili** — 支持 cookies.txt、扫码登录 Cookie、浏览器扩展 Cookie 同步
- **Douyin** — 自研 XBogus + ABogus 签名引擎，直连接口获取 CDN URL
- **实时进度** — 百分比 / 速度 / 剩余时间 / 错误信息
- **视频库** — 已下载文件展示、播放/下载、删除、缩略图展示
- **安全文件访问** — 下载和删除接口限制在 `downloads/` 内，防路径穿越

### AI 与生产力
- **字幕提取** — 通过 yt-dlp 提取 `.srt` / `.txt` / 分段字幕
- **AI 视频总结** — DeepSeek 生成结构化摘要：一句话、章节、要点、标签
- **思维导图** — 生成可读的文本思维导图
- **AI 智能问答** — 基于视频字幕内容多轮问答
- **AI 内容改写** — 支持学习笔记、公众号、小红书、Twitter/X thread、Markdown 风格
- **本地转录** — 上传 `.mp3/.mp4/.wav/.m4a/.webm/.mkv/.mov` 后用 Whisper 转文字
- **字幕翻译** — DeepSeek 翻译字幕文本

### 任务与文件处理
- **SQLite 持久化** — 任务、文件历史、AI 结果写入 `downloads/video_downloader.db`
- **任务中心** — 查询所有任务，支持失败任务重试
- **批量提交** — 一次提交多个 URL 并行下载
- **格式转换** — ffmpeg 提取 MP3、转封装、压缩 MP4
- **启动检查** — `/api/health` 返回依赖和 ffmpeg 状态

## Tech Stack

| 层 | 技术 |
|---|---|
| 下载引擎 | yt-dlp + 自研 Douyin 模块 |
| 后端 | FastAPI + uvicorn |
| 前端 | Vue 3 + Vite + Tailwind CSS v4 |
| AI | DeepSeek(OpenAI-compatible SDK) + OpenAI Whisper |
| 任务队列 | 内存 worker + SQLite 持久化 |
| 存储 | 文件系统 + SQLite |
| 音视频 | ffmpeg |
| Cookie | cookies.txt / Bilibili QR Cookie / Chrome extension sync / browser cookie |

## Project Structure

```text
free-video-downloader/
├── main.py                       # 一键启动后端
├── config.py                     # 全局配置与目录初始化
├── requirements.txt              # Python 依赖
├── .env.example                  # 配置模板
├── backend/
│   ├── api.py                    # FastAPI 路由，33 个 /api 路由
│   ├── downloader.py             # 统一下载调度
│   ├── queue.py                  # 内存任务执行 + SQLite 任务记录
│   ├── storage.py                # SQLite 持久化层
│   ├── cookies.py                # 统一 Cookie 选择/同步
│   ├── media.py                  # ffmpeg 转换与安全文件路径
│   ├── startup_checks.py         # 依赖和 ffmpeg 检查
│   ├── subtitle.py               # 字幕提取
│   ├── ai.py                     # DeepSeek API：总结/问答/导图/翻译/改写
│   ├── prompts.py                # Prompt 模板
│   ├── transcribe.py             # Whisper 本地转录
│   ├── _whisper_worker.py        # Whisper 子进程
│   ├── bilibili_auth.py          # Bilibili 扫码登录 Cookie
│   ├── models.py                 # Pydantic 模型
│   └── douyin/                   # 抖音签名引擎
├── frontend/
│   └── src/components/
│       ├── AiPanel.vue           # 字幕/总结/导图/问答/改写
│       ├── TaskCenter.vue        # 任务中心与历史结果入口
│       └── VideoLibrary.vue      # 已下载视频与转换入口
├── chrome-extension/             # 浏览器 Cookie 同步扩展
├── docs/                         # 项目文档
└── downloads/                    # 输出目录
    ├── *.mp4 / *.webm / *.mkv
    ├── video_downloader.db       # SQLite 任务与历史记录
    ├── subtitles/<video_id>/
    ├── uploads/
    └── synced_cookies.txt
```

## Quick Start

```powershell
# 1. 安装依赖
cd free-video-downloader
pip install -r requirements.txt

# 2. 安装/配置 ffmpeg
# Windows: 将 ffmpeg.exe 所在 bin 目录加入 PATH
# macOS: brew install ffmpeg
# Linux: apt install ffmpeg

# 3. 配置 DeepSeek（AI 功能需要）
cp .env.example .env
# 编辑 .env：
#   DEEPSEEK_API_KEY=sk-xxxxx
#   DEEPSEEK_MODEL=deepseek-chat

# 4. 配置 Cookie（Bilibili / Douyin 常用）
# 方式 A：导出 cookies.txt 放到项目根目录
# 方式 B：使用 Bilibili 扫码登录接口
# 方式 C：安装 chrome-extension，自动同步 YouTube/Bilibili/Douyin Cookie 到后端
# 方式 D：设置 YTDLP_COOKIES_BROWSER=chrome/edge/firefox/brave 作为备用读取方式

# 5. 启动后端
python main.py
# API:  http://localhost:8002
# Docs: http://localhost:8002/docs

# 6. 启动前端
cd frontend
npm install
npm run dev
# http://localhost:5173
```

## Testing

```powershell
# 后端单元测试（不访问真实平台）
python -m pytest

# 后端静态编译检查
python -m compileall main.py config.py backend

# 前端生产构建检查
cd frontend
npm run build
```

真实平台回归默认跳过，避免日常测试依赖网络和 Cookie。需要验证时设置对应 URL 后再运行：

```powershell
$env:LIVE_YOUTUBE_URL="https://www.youtube.com/watch?v=..."
$env:LIVE_BILIBILI_URL="https://www.bilibili.com/video/..."
$env:LIVE_DOUYIN_URL="https://www.douyin.com/video/..."
python -m pytest -m live
```

## Configuration

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DOWNLOAD_DIR` | `downloads/` | 下载和数据库输出目录 |
| `SUBTITLE_DIR` | `downloads/subtitles/` | 字幕输出目录 |
| `DB_PATH` | `downloads/video_downloader.db` | SQLite 数据库路径 |
| `HOST` | `0.0.0.0` | 后端监听地址 |
| `PORT` | `8002` | 后端端口 |
| `MAX_CONCURRENT` | `2` | 并发任务数 |
| `MAX_UPLOAD_MB` | `500` | 上传转录文件大小限制 |
| `YTDLP_COOKIES_BROWSER` | 空 | 空=优先平台同步 Cookie；也可设 `chrome/edge/firefox/brave` 作为备用 |
| `YTDLP_YOUTUBE_COOKIES_PATH` | 空 | 可选 YouTube 专属 Netscape Cookie 文件 |
| `YTDLP_BILIBILI_COOKIES_PATH` | 空 | 可选 Bilibili 专属 Netscape Cookie 文件 |
| `YTDLP_DOUYIN_COOKIES_PATH` | 空 | 可选 Douyin 专属 Netscape Cookie 文件 |
| `YTDLP_YOUTUBE_PO_TOKEN` | 空 | 可选 YouTube PO Token，例如 `web.gvs+TOKEN_VALUE` |
| `YTDLP_YOUTUBE_VISITOR_DATA` | 空 | 可选 YouTube Visitor Data，部分 PO Token 场景需要 |
| `DEEPSEEK_API_KEY` | 空 | AI 功能 API Key |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek API 地址 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | AI 模型 |

### YouTube 403 Notes

如果 YouTube 解析成功但下载时报 `HTTP Error 403: Forbidden`，后端会自动按 `default -> web_safari -> ios -> android -> android_vr -> tv` 切换客户端。用户明确选择某个清晰度/格式时不会静默降级，避免出现“点 1080p 实际下到低清”的情况。若仍失败，通常需要刷新 Cookie、升级 yt-dlp，或在 `.env` 配置：

```env
YTDLP_YOUTUBE_PO_TOKEN=web.gvs+TOKEN_VALUE
YTDLP_YOUTUBE_VISITOR_DATA=VISITOR_DATA_VALUE
```

如果报 `This video is DRM protected`，表示平台返回的是 DRM 受保护视频流；本工具不会绕过 DRM，也无法下载这类受保护内容。请更换非 DRM 视频，或使用平台提供的官方离线/下载能力。

`/api/health` 会返回 ffmpeg、Node.js、三平台 Cookie 来源、YouTube PO Token/Visitor Data、DeepSeek API Key 等诊断状态。遇到下载或 AI 功能异常时，建议先看这个接口的 `checks` 字段。也可以直接访问 `/api/cookies/status` 查看 YouTube/Bilibili/Douyin 的 Cookie 状态。

## API Endpoints

### 基础与任务
| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | 健康检查，含依赖与 ffmpeg 状态 |
| GET | `/api/tasks` | 统一任务列表 |
| GET | `/api/tasks/{id}` | 查询单个任务 |
| POST | `/api/tasks/{id}/retry` | 重试失败任务 |
| GET | `/api/history` | 文件历史与 AI 结果历史 |

### 下载与文件
| Method | Path | Description |
|---|---|---|
| POST | `/api/info` | 解析视频信息 |
| POST | `/api/download` | 提交下载任务 |
| GET | `/api/progress/{id}` | 查询下载进度 |
| GET | `/api/files` | 已下载文件列表 |
| DELETE | `/api/files/{name}` | 删除文件 |
| GET | `/api/download/{name}` | 播放/下载文件 |
| POST | `/api/batch` | 批量提交多个 URL |
| GET | `/api/batch/{id}` | 查询批量进度 |

### AI 与字幕
| Method | Path | Description |
|---|---|---|
| POST | `/api/subtitles` | 提交字幕提取 |
| GET | `/api/subtitles/{id}` | 查询字幕结果 |
| POST | `/api/summary` | 提交 AI 视频总结 |
| GET | `/api/summary/{id}` | 查询总结结果 |
| POST | `/api/mindmap` | 提交思维导图生成 |
| GET | `/api/mindmap/{id}` | 查询思维导图结果 |
| POST | `/api/ask` | 提交 AI 视频问答 |
| GET | `/api/ask/{id}` | 查询回答 |
| POST | `/api/translate` | 翻译字幕文本 |
| POST | `/api/rewrite` | 提交内容改写 |
| GET | `/api/rewrite/{id}` | 查询改写结果 |
| POST | `/api/transcribe` | 上传本地文件转录 |
| GET | `/api/transcribe/{id}` | 查询转录结果 |

### 转换与 Cookie
| Method | Path | Description |
|---|---|---|
| POST | `/api/convert` | 提交 ffmpeg 转换任务 |
| GET | `/api/convert/{id}` | 查询转换结果 |
| GET/POST | `/api/bilibili/qrcode` | 生成 Bilibili 登录二维码 |
| GET | `/api/bilibili/qrcode/status` | 查询扫码状态 |
| GET | `/api/bilibili/status` | 查询 Bilibili Cookie 状态 |
| GET | `/api/cookies/status` | 查询三平台 Cookie 状态 |
| POST | `/api/cookies/sync` | 接收浏览器扩展同步 Cookie |

## Recent Verification

已验证：后端编译、前端构建、API 路由导入、文件路径安全、SQLite 任务/历史、ffmpeg 转换、YouTube 解析、YouTube 字幕提取、DeepSeek 翻译/改写、YouTube 小视频下载。

未在自动测试中覆盖：指定 Bilibili/Douyin 链接的真实下载、长音视频 Whisper 转录、真实浏览器扩展同步流程。

## Cookie Priority

默认 Cookie 优先级：

1. 平台专属环境变量：`YTDLP_YOUTUBE_COOKIES_PATH` / `YTDLP_BILIBILI_COOKIES_PATH` / `YTDLP_DOUYIN_COOKIES_PATH`
2. Bilibili QR 登录保存的 Cookie（仅 Bilibili）
3. 浏览器扩展同步的 `downloads/cookies/<platform>.txt`
4. 如果设置 `YTDLP_COOKIES_BROWSER=chrome/edge/firefox/brave`，则使用 yt-dlp 的浏览器 Cookie 读取能力作为备用
5. 通用 Cookie：`YTDLP_COOKIES_PATH`、`downloads/synced_cookies.txt`、项目根目录 `cookies.txt`、项目根目录 `yt-dlp-cookies.txt`

## Disclaimer

本项目仅供学习研究使用。请尊重版权，仅下载您拥有合法权限的视频内容。

## License

MIT
