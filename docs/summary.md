# 万能视频下载器 — 项目总结

> 版本: v1.2 | 日期: 2026-06-29

## 一、项目概述

“万能视频下载器” 是一个基于 Python + Vue 3 的本地全栈 Web 应用。用户粘贴视频链接即可解析、选择清晰度并下载到本地，同时可以对视频进行字幕提取、AI 总结、思维导图、智能问答、内容改写、本地转录和格式转换。

当前项目已从单纯下载器升级为“下载 + 理解 + 加工 + 历史管理”的音视频生产力工具。

## 二、当前完成的功能

### 核心下载

| 功能 | YouTube | Bilibili | Douyin |
|------|:---:|:---:|:---:|
| URL 解析 | ✅ | ✅ | ✅ |
| 格式选择 | ✅ | ✅ | ✅ |
| 实时下载进度 | ✅ | ✅ | ✅ |
| 音视频自动合并 | ✅ yt-dlp | ✅ yt-dlp | ✅ ffmpeg |
| Cookie 支持 | 可选 | ✅ | ✅ |
| 已下载文件展示 | ✅ | ✅ | ✅ |
| 删除/播放/下载 | ✅ | ✅ | ✅ |

### AI 与内容处理

- 字幕提取：输出 `.srt`、`.txt`、分段字幕和 manifest
- AI 总结：一句话、章节、要点、标签
- 思维导图：文本化思维导图
- AI 问答：基于字幕上下文的问答
- AI 改写：学习笔记、公众号、小红书、Twitter/X thread、Markdown
- 字幕翻译：DeepSeek 翻译字幕文本
- 本地转录：Whisper 子进程转写上传音视频

### 任务与持久化

- SQLite 保存任务、文件记录和 AI 结果
- `/api/tasks` 统一任务中心
- `/api/history` 历史记录接口
- 失败任务重试接口
- 批量下载任务
- ffmpeg 格式转换：提取音频、转封装、压缩
- `/api/health` 启动检查：依赖和 ffmpeg 状态

### Cookie 管理

- `YTDLP_COOKIES_PATH`
- Bilibili 扫码登录 Cookie
- 浏览器扩展同步 `downloads/synced_cookies.txt`
- 根目录 `cookies.txt` / `yt-dlp-cookies.txt`
- 可选浏览器 Cookie 读取：`YTDLP_COOKIES_BROWSER`

## 三、技术亮点

### 1. 自研 Douyin 签名引擎

- X-Bogus：RC4 + MD5 签名
- A-Bogus：SM3 + 自定义 Base64 + 浏览器指纹
- 直连 Douyin API 获取详情
- 视频/音频分离下载后用 ffmpeg 合并
- 多 CDN URL fallback

### 2. 统一任务层

当前仍使用内存 worker 执行任务，但任务元数据、状态、结果和错误会写入 SQLite。这样既保持本地单机简单部署，又能提供任务中心、历史记录和失败重试基础。

### 3. 本地生产力闭环

下载文件不再是终点，用户可以继续进行：

```
视频链接/本地文件
  → 下载/上传
  → 字幕或转录
  → 总结/问答/导图/改写
  → 历史归档或二次创作
```

## 四、当前 API 范围

当前 FastAPI 注册 33 个 `/api` 路由，覆盖：

- 健康检查：`/api/health`
- 下载：`/api/info`、`/api/download`、`/api/progress/{id}`
- 文件：`/api/files`、`/api/download/{name}`
- 任务：`/api/tasks`、`/api/tasks/{id}`、`/api/tasks/{id}/retry`
- 历史：`/api/history`
- 字幕/AI：`/api/subtitles`、`/api/summary`、`/api/mindmap`、`/api/ask`、`/api/translate`、`/api/rewrite`
- 转录：`/api/transcribe`
- 批量：`/api/batch`
- 转换：`/api/convert`
- Bilibili/Cookie：`/api/bilibili/*`、`/api/cookies/sync`

## 五、最近验证结果

已通过：

- 后端编译：`python -m compileall main.py config.py backend`
- 前端构建：`npm run build`
- API 路由导入
- `/api/health`、`/api/tasks`、`/api/history`、`/api/files`
- 文件路径安全校验
- 上传类型校验
- ffmpeg 转换小文件
- YouTube 解析
- YouTube 字幕提取
- DeepSeek 翻译和改写
- YouTube 小视频真实下载

未自动覆盖：

- 指定 Bilibili 视频真实下载
- 指定 Douyin 视频真实下载
- 长音视频 Whisper 转录
- 浏览器扩展真实同步流程

## 六、已知限制

1. Douyin 和 Bilibili Cookie 仍可能过期，需要重新扫码或同步。
2. AI 功能依赖 DeepSeek API Key。
3. Whisper 转录依赖本地模型下载和 ffmpeg，首次运行可能较慢。
4. 当前任务执行仍是单机内存 worker，SQLite 负责记录，不适合多进程分布式调度。
5. Bilibili/Douyin 字幕覆盖仍弱于 YouTube，缺字幕时后续应走下载音频 + Whisper 转录 fallback。

## 七、后续规划

- [ ] Bilibili/Douyin 真实回归样例库
- [ ] 字幕优先、无字幕自动 Whisper fallback
- [ ] 更完整的批量队列页面
- [ ] GIF 截取和高级转换参数
- [ ] Docker 部署包
- [ ] MCP/OpenAPI 面向 Agent 的调用层
- [ ] 用户额度/积分模型预留
