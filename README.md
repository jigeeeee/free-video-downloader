# 🎬 Universal Video Downloader

万能视频下载器 — 粘贴链接，一键下载 + AI 总结 / 思维导图 / 智能问答。

支持 YouTube、Bilibili、Douyin 等 100+ 平台。

## ✨ Features

### 核心下载
- **YouTube** — 16 格式 / 4K，无需登录
- **Bilibili** — cookies.txt 登录后下载
- **Douyin** — 自研 XBogus + ABogus 签名引擎
- **音视频自动合并** — ffmpeg 合成
- **实时进度** — 速度 / 剩余时间

### 🆕 AI 增值服务（Sprint 1-5）
- **字幕提取** — YouTube → .srt / .txt，支持 157 种语言
- **AI 视频总结** — DeepSeek 生成结构化摘要（章节 + 要点 + 标签）
- **思维导图** — 自动生成 Mermaid mindmap，前端可直接渲染
- **AI 智能问答** — 基于视频内容的多轮对话
- **本地转录** — 上传 .mp3/.mp4，Whisper 语音转文字
- **批量队列** — 一次提交多个 URL 并行处理

## 🏗️ Tech Stack

| 层 | 技术 |
|---|---|
| 下载引擎 | yt-dlp + 自研 Douyin 模块 |
| 后端 | FastAPI + uvicorn |
| 前端 | Vue 3 + Vite + Tailwind CSS v4 |
| AI | DeepSeek（总结/问答/导图） + OpenAI Whisper（本地转录） |
| 任务队列 | 内存队列（适配器模式，可切换 Celery） |
| 音视频 | ffmpeg |

## 📁 Project Structure

```
free-video-downloader/
├── main.py                       # 一键启动
├── config.py                     # 全局配置
├── requirements.txt
├── .env                          # DeepSeek API Key
├── backend/
│   ├── api.py                    # 🆕 18 个 API 端点
│   ├── downloader.py             # 统一下载调度
│   ├── queue.py                  # 🆕 任务队列抽象层
│   ├── subtitle.py               # 🆕 字幕提取
│   ├── ai.py                     # 🆕 DeepSeek API（总结/问答/导图）
│   ├── prompts.py                # 🆕 Prompt 模板
│   ├── transcribe.py             # 🆕 Whisper 本地转录
│   ├── _whisper_worker.py        # 🆕 Whisper 子进程
│   ├── models.py                 # 🔄 Pydantic 模型（25+）
│   └── douyin/                   # 抖音签名引擎
├── frontend/                     # Vue 3 前端
├── docs/
│   ├── AI功能扩展方案.md          # 🆕 完整 API 文档 + 使用指南
│   ├── 竞品调研报告.md
│   ├── design.md
│   └── requirements.md
└── downloads/                    # 输出目录
    ├── *.mp4 / *.webm
    ├── subtitles/<video_id>/     # 🆕 字幕输出
    └── uploads/                  # 🆕 临时上传
```

## 🚀 Quick Start

```powershell
# 1. 安装依赖
cd free-video-downloader
pip install -r requirements.txt

# 2. 配置（可选但推荐）
cp .env.example .env
# 编辑 .env，填入 DeepSeek API Key：
#   DEEPSEEK_API_KEY=sk-xxxxx
#   （不配置 AI Key 则下载功能不受影响）

# 3. 配置 cookies（Bilibili / Douyin 需要）
#    浏览器安装 Get cookies.txt LOCALLY 插件
#    登录后导出 cookies.txt 放到项目根目录

# 4. 启动后端
python main.py
# → API: http://localhost:8001
# → Docs: http://localhost:8001/docs

# 5. 启动前端（可选，新终端）
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

## 📡 API Endpoints

### 下载
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/info` | 解析视频信息 |
| POST | `/api/download` | 提交下载任务 |
| GET | `/api/progress/{id}` | 查询下载进度 |
| GET | `/api/files` | 已下载文件列表 |
| DELETE | `/api/files/{name}` | 删除文件 |
| GET | `/api/download/{name}` | 播放/下载文件 |

### 🆕 AI 功能
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/subtitles` | 提交字幕提取 |
| GET | `/api/subtitles/{id}` | 查询字幕结果 |
| POST | `/api/summary` | 提交 AI 视频总结 |
| GET | `/api/summary/{id}` | 查询总结结果 |
| POST | `/api/mindmap` | 提交思维导图生成 |
| GET | `/api/mindmap/{id}` | 查询 Mermaid 代码 |
| POST | `/api/ask` | 提交 AI 视频问答 |
| GET | `/api/ask/{id}` | 查询回答 |
| POST | `/api/transcribe` | 上传本地文件转录 |
| GET | `/api/transcribe/{id}` | 查询转录结果 |
| POST | `/api/batch` | 批量提交多个 URL |
| GET | `/api/batch/{id}` | 查询批量进度 |

> 详细使用示例见 [`docs/AI功能扩展方案.md`](docs/AI功能扩展方案.md)

## 🔧 Cookie 配置

| 平台 | 需要 Cookie | 方式 |
|------|:---:|------|
| YouTube | ❌ | 大部分视频无需登录 |
| Bilibili | ✅ | cookies.txt |
| Douyin | ✅ | cookies.txt |

## ⚠️ Disclaimer

本项目仅供学习研究使用。请尊重版权，仅下载您拥有合法权限的视频内容。

## 📄 License

MIT
