"""DeepSeek AI integration for video summarization, Q&A, and more.

Uses OpenAI-compatible SDK to call DeepSeek API.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Union

import openai
from dotenv import load_dotenv

import config
from backend.prompts import summarize_prompt, question_prompt

load_dotenv(config.ROOT_DIR / ".env")

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Client singleton
# ---------------------------------------------------------------------------

_client: Optional[openai.AsyncOpenAI] = None


def _get_client() -> openai.AsyncOpenAI:
    global _client
    if _client is not None:
        return _client

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    _client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
    return _client


# ---------------------------------------------------------------------------
# Video summarization
# ---------------------------------------------------------------------------

async def summarize_video(
    title: str,
    subtitle_text: str,
    lang: str = "zh",
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate an AI summary from subtitle text.

    Args:
        title: Video title.
        subtitle_text: Combined subtitle transcript.
        lang: Output language ("zh" / "en").
        model: Override DeepSeek model (default from DEEPSEEK_MODEL env or "deepseek-chat").

    Returns parsed dict:
        { one_liner, chapters: [...], key_points: [...], tags: [...] }
    """
    client = _get_client()
    model_name = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    prompt = summarize_prompt(title, _trim_text(subtitle_text), lang)

    resp = await client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=4096,
    )

    content = resp.choices[0].message.content or ""
    parsed = _parse_json_response(content)
    return _normalize_summary(parsed)


# ---------------------------------------------------------------------------
# Video Q&A
# ---------------------------------------------------------------------------

async def ask_video(
    title: str,
    subtitle_text: str,
    question: str,
    chat_history: Optional[List[Dict[str, str]]] = None,
    lang: str = "zh",
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Answer a question based on video subtitle content.

    Returns { answer, tokens_used }.
    """
    client = _get_client()
    model_name = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    prompt = question_prompt(title, _trim_text(subtitle_text), question, chat_history, lang)

    resp = await client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=2048,
    )

    content = resp.choices[0].message.content or ""
    usage = resp.usage

    return {
        "answer": content.strip(),
        "question": question,
        "tokens_used": {
            "input": usage.prompt_tokens if usage else 0,
            "output": usage.completion_tokens if usage else 0,
        },
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> Dict[str, Any]:
    """Extract a JSON object from LLM response (may be wrapped in markdown)."""
    text = text.strip()

    # Remove markdown code fences
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find {...} in the text
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

        # Return raw text as fallback
        return {
            "raw_text": text,
            "one_liner": "",
            "chapters": [],
            "key_points": [],
            "tags": [],
        }


async def test_connection() -> Dict[str, Any]:
    """Quick connectivity check — calls DeepSeek with a tiny prompt."""
    client = _get_client()
    model_name = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    resp = await client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": "回复 OK"}],
        max_tokens=10,
    )
    return {
        "ok": True,
        "model": model_name,
        "reply": resp.choices[0].message.content.strip(),
    }


# ---------------------------------------------------------------------------
# Mindmap generation
# ---------------------------------------------------------------------------

async def generate_mindmap(
    title: str,
    subtitle_text: str,
    lang: str = "zh",
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a visual text-based mindmap from video subtitle text.

    Returns { mindmap_text, tokens_used }.
    """
    from backend.prompts import mindmap_prompt

    client = _get_client()
    model_name = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    prompt = mindmap_prompt(title, _trim_text(subtitle_text), lang)

    resp = await client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=4096,
    )

    content = resp.choices[0].message.content or ""
    usage = resp.usage

    return {
        "mindmap_text": content.strip(),
        "video_title": title,
        "tokens_used": {
            "input": usage.prompt_tokens if usage else 0,
            "output": usage.completion_tokens if usage else 0,
        },
    }


def _extract_mermaid_block(text: str) -> str:
    """Extract the Mermaid code block from LLM output."""
    import re
    # Try ```mermaid ... ``` first
    m = re.search(r"```mermaid\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Try bare mermaid code (mindmap root(...))
    if re.search(r"^\s*mindmap", text, re.MULTILINE):
        return text.strip()
    # Fallback: return raw text
    return text.strip()


def _trim_text(text: str, max_chars: int = 24000) -> str:
    """Keep LLM prompts bounded while preserving beginning and ending context."""
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    head = text[: max_chars // 2]
    tail = text[-max_chars // 2 :]
    return f"{head}\n\n...[middle omitted for length]...\n\n{tail}"


def _normalize_summary(data: Dict[str, Any]) -> Dict[str, Any]:
    chapters = data.get("chapters") if isinstance(data.get("chapters"), list) else []
    key_points = data.get("key_points") if isinstance(data.get("key_points"), list) else []
    tags = data.get("tags") if isinstance(data.get("tags"), list) else []
    return {
        **data,
        "one_liner": str(data.get("one_liner") or ""),
        "chapters": chapters,
        "key_points": [str(item) for item in key_points],
        "tags": [str(item) for item in tags],
    }


# ---------------------------------------------------------------------------
# Subtitle translation
# ---------------------------------------------------------------------------

async def translate_subtitles(
    subtitle_text: str,
    target_lang: str = "简体中文",
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Translate subtitle text via DeepSeek, preserving SRT timestamps.

    Returns { translated_text, tokens_used }.
    """
    from backend.prompts import translate_prompt

    client = _get_client()
    model_name = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    prompt = translate_prompt(_trim_text(subtitle_text, 30000), target_lang)

    resp = await client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=8192,
    )

    content = resp.choices[0].message.content or ""
    usage = resp.usage

    return {
        "translated_text": content.strip(),
        "target_lang": target_lang,
        "tokens_used": {
            "input": usage.prompt_tokens if usage else 0,
            "output": usage.completion_tokens if usage else 0,
        },
    }


async def rewrite_content(
    title: str,
    source_text: str,
    style: str = "notes",
    lang: str = "zh",
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Rewrite transcript/summary content into an editorial format."""
    from backend.prompts import rewrite_prompt

    client = _get_client()
    model_name = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    prompt = rewrite_prompt(title, _trim_text(source_text), style, lang)

    resp = await client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=4096,
    )

    content = resp.choices[0].message.content or ""
    usage = resp.usage
    return {
        "title": title,
        "style": style,
        "content": content.strip(),
        "tokens_used": {
            "input": usage.prompt_tokens if usage else 0,
            "output": usage.completion_tokens if usage else 0,
        },
    }
