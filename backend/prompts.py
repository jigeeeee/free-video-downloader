"""Prompt templates for AI video processing.

Each template is a function that receives structured data and returns
a formatted prompt string ready for the LLM.
"""

from __future__ import annotations

from typing import List


def summarize_prompt(
    title: str,
    subtitle_text: str,
    lang: str = "zh",
) -> str:
    """Generate a structured video summary.

    Args:
        title: Video title.
        subtitle_text: Full transcript / subtitle text.
        lang: Output language ("zh" or "en").

    Returns a prompt that instructs the LLM to output a structured JSON.
    """
    lang_instruction = {
        "zh": "请用中文回复。",
        "en": "Please reply in English.",
    }.get(lang, "请用中文回复。")

    return f"""你是一个专业的视频内容分析师。请根据以下视频字幕/转录文本，生成一份结构化的视频总结。

视频标题：{title}

{lang_instruction}

请按以下 JSON 格式输出（严格 JSON，不要多余文字）：

{{
  "one_liner": "一句话总结（30字以内）",
  "chapters": [
    {{ "timestamp": "MM:SS", "title": "章节标题" }}
  ],
  "key_points": [
    "关键要点1",
    "关键要点2",
    "关键要点3"
  ],
  "tags": ["标签1", "标签2", "标签3"]
}}

规则：
- one_liner: 用一句话概括视频核心内容
- chapters: 识别视频的章节/段落，每个包含时间戳和标题（至少3个，最多8个）
- key_points: 提炼3-7个核心观点或知识点
- tags: 给出3-5个关键词标签

以下是视频字幕文本：

{subtitle_text}"""


def question_prompt(
    title: str,
    subtitle_text: str,
    question: str,
    chat_history: List[dict] | None = None,
    lang: str = "zh",
) -> str:
    """Generate an answer for a user question based on video content.

    Args:
        title: Video title.
        subtitle_text: Full transcript.
        question: User's current question.
        chat_history: Previous Q&A pairs for multi-turn context.
        lang: Output language.
    """
    lang_instruction = {
        "zh": "请用中文回复，简洁明了。",
        "en": "Please reply in English, concisely.",
    }.get(lang, "请用中文回复，简洁明了。")

    history_block = ""
    if chat_history:
        pairs = []
        for h in chat_history[-6:]:  # last 6 turns max
            pairs.append(f"用户: {h.get('question', '')}\n助手: {h.get('answer', '')}")
        if pairs:
            history_block = "对话历史：\n" + "\n".join(pairs) + "\n\n"

    return f"""你是一个视频内容问答助手。根据以下视频字幕内容回答用户问题。

视频标题：{title}
{lang_instruction}

{history_block}视频字幕内容：
{subtitle_text}

用户问题：{question}

请基于字幕内容回答。如果字幕中没有相关信息，请如实说没有找到。回答时引用相关时间戳。"""


def mindmap_prompt(
    title: str,
    subtitle_text: str,
    lang: str = "zh",
) -> str:
    """Generate a visual text-based mindmap using emoji + tree characters.

    The LLM outputs a tree diagram that looks like a picture when displayed
    in monospace font — no external renderer needed.
    """
    lang_instruction = {
        "zh": "所有文字使用中文。",
        "en": "Use English for all text.",
    }.get(lang, "所有文字使用中文。")

    return f"""你是一个知识可视化专家。请根据以下视频字幕内容，生成一个用 emoji + 树状符号绘制的思维导图。

视频标题：{title}

{lang_instruction}

请严格按照以下**横向**格式输出（根在左，分支向右展开，不要用竖向树）：

🧠 视频标题 ──┬── 🔹 第一章节 ──┬── 子要点1
              │                ├── 子要点2
              │                └── 子要点3
              │
              ├── 🔹 第二章节 ──┬── 子要点1
              │                └── 子要点2
              │
              └── 🔹 第三章节 ──┬── 子要点1
                              └── 子要点2

格式规则：
- 第一行：🧠 + 标题 + ──┬── + 🔹 第一个章节 → 向右展开
- 标题在左侧，章节/子要点依次向右延伸
- 第一层章节用 ──┬── 🔹 连接，在标题右方
- 第二层子要点用 ├── ──┬── 继续向右延伸
- 更深层用 │ 垂直对齐 + ├── 向右
- 使用 ─ ┬ ├ └ │ 这些制表符，不要用 Mermaid
- 每个节点配一个相关 emoji
- 严格只输出思维导图本身，不要任何前言后语

以下是视频字幕文本：

{subtitle_text}"""


def translate_prompt(text: str, target_lang: str = "zh") -> str:
    """Translate text to the target language, preserving timestamps.

    Args:
        text: Source text (with optional SRT timestamps).
        target_lang: Target language, e.g. "简体中文".

    Returns a prompt for accurate timestamp-preserving translation.
    """
    return f"""请将以下字幕文本翻译成{target_lang}。

规则：
- 保留所有时间戳格式（如 00:01:23,456 --> 00:01:25,789）
- 保留 SRT 序号
- 只输出翻译后的内容，不要添加额外说明
- 翻译要自然流畅，符合口语习惯

原文：

{text}"""
