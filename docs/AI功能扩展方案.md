# AI 功能扩展方案 — 实施文档

> 最后更新：2026-06-29  
> 当前状态：字幕、总结、导图、问答、翻译、改写、本地转录已接入；任务和 AI 结果已持久化到 SQLite。

## 一、当前 AI 能力总览

| 能力 | 接口 | 状态 | 输入来源 |
|---|---|---|---|
| 字幕提取 | `/api/subtitles` | 已实现 | yt-dlp 字幕 |
| AI 总结 | `/api/summary` | 已实现 | 字幕文本 |
| 思维导图 | `/api/mindmap` | 已实现 | 字幕文本 |
| AI 问答 | `/api/ask` | 已实现 | 字幕文本 + history |
| 字幕翻译 | `/api/translate` | 已实现 | 文本/SRT |
| 内容改写 | `/api/rewrite` | 已实现 | 用户文本或 URL 字幕 |
| 本地转录 | `/api/transcribe` | 已实现 | 上传音视频 + Whisper |
| 历史记录 | `/api/history` | 已实现 | SQLite |
| 任务中心 | `/api/tasks` | 已实现 | SQLite + 内存 worker |

## 二、相关文件

```text
backend/
├── api.py              # AI 与任务接口
├── ai.py               # DeepSeek 调用封装
├── prompts.py          # 总结/问答/导图/翻译/改写 Prompt
├── subtitle.py         # 字幕提取
├── transcribe.py       # Whisper 转录入口
├── _whisper_worker.py  # Whisper 子进程
├── queue.py            # 任务执行
├── storage.py          # SQLite 任务/历史/AI 结果
└── models.py           # Pydantic 模型

frontend/src/components/
├── AiPanel.vue         # AI 前端面板
└── TaskCenter.vue      # 任务和历史展示
```

## 三、任务持久化

所有 AI 任务通过 `queue.enqueue()` 提交。任务会写入 `tasks` 表，完成后结果保存在 `tasks.result`。总结、导图、问答、改写等 AI 结果额外写入 `ai_results` 表，供 `/api/history` 展示。

任务状态：

- `queued`
- `processing`
- `done`
- `error`

## 四、API 说明

### 4.1 字幕提取

```bash
curl -X POST http://127.0.0.1:8001/api/subtitles \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.youtube.com/watch?v=jNQXAC9IVRw", "languages":["en"]}'

curl http://127.0.0.1:8001/api/subtitles/<task_id>
```

输出包括：

- `video_id`
- `title`
- `available_langs`
- `extracted[].text_preview`
- `extracted[].segments`
- `txt_path`
- `srt_path`

### 4.2 AI 总结

```bash
curl -X POST http://127.0.0.1:8001/api/summary \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.youtube.com/watch?v=jNQXAC9IVRw", "lang":"zh"}'
```

返回：

```json
{
  "one_liner": "一句话总结",
  "chapters": [{"timestamp": "00:00", "title": "章节标题"}],
  "key_points": ["要点1"],
  "tags": ["标签"]
}
```

### 4.3 思维导图

```bash
curl -X POST http://127.0.0.1:8001/api/mindmap \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.youtube.com/watch?v=jNQXAC9IVRw", "lang":"zh"}'
```

当前输出为文本思维导图，前端直接用等宽文本展示。

### 4.4 AI 问答

```bash
curl -X POST http://127.0.0.1:8001/api/ask \
  -H "Content-Type: application/json" \
  -d '{
    "url":"https://www.youtube.com/watch?v=jNQXAC9IVRw",
    "question":"视频讲了什么？",
    "lang":"zh",
    "history":[]
  }'
```

### 4.5 内容改写

```bash
curl -X POST http://127.0.0.1:8001/api/rewrite \
  -H "Content-Type: application/json" \
  -d '{
    "title":"视频标题",
    "text":"原始字幕或总结文本",
    "style":"notes",
    "lang":"zh"
  }'

curl http://127.0.0.1:8001/api/rewrite/<task_id>
```

`style` 可选：

- `notes`：学习笔记
- `wechat`：公众号
- `xiaohongshu`：小红书
- `twitter`：Twitter/X thread
- `markdown`：Markdown 长文

### 4.6 本地转录

```bash
curl -X POST http://127.0.0.1:8001/api/transcribe \
  -F "file=@/path/to/audio.mp3"
```

支持扩展名：`.mp3/.mp4/.wav/.m4a/.webm/.mkv/.mov`。大小上限由 `MAX_UPLOAD_MB` 控制。

### 4.7 任务和历史

```bash
curl http://127.0.0.1:8001/api/tasks
curl http://127.0.0.1:8001/api/tasks/<task_id>
curl -X POST http://127.0.0.1:8001/api/tasks/<task_id>/retry
curl http://127.0.0.1:8001/api/history
```

## 五、Prompt 策略

- 总结要求输出严格 JSON，并在代码中做 schema 兜底。
- 问答保留最近 6 轮对话上下文。
- 长文本会裁剪保留首尾上下文，避免 prompt 过长。
- 改写仅允许基于原文信息，不鼓励编造。

## 六、当前限制与后续优化

| 项目 | 当前状态 | 后续建议 |
|---|---|---|
| 字幕来源 | 主要依赖平台字幕 | 无字幕时自动 Whisper fallback |
| 长视频 | 已做文本裁剪 | 后续做 chunk + map-reduce 总结 |
| Bilibili/Douyin 字幕 | 覆盖有限 | 下载音频后转录 |
| AI 结果导出 | 前端展示 | 增加 Markdown/TXT 下载 |
| 成本控制 | 无额度系统 | 记录 token 用量并接入积分模型 |

## 七、验证记录

已通过真实或本地烟测：

- YouTube 视频信息解析
- YouTube 英文字幕提取
- DeepSeek 字幕翻译
- DeepSeek 内容改写
- SQLite AI 结果保存
- 前端构建
