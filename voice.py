from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import edge_tts

from config import AUDIO_CACHE_DIR


async def generate_voice(text: str, output_path: str | Path) -> None:
    """将文字转为语音。"""
    communicate = edge_tts.Communicate(text or "", "zh-CN-YunxiNeural", rate="-15%")
    await communicate.save(str(output_path))


def speak(text: str) -> str:
    """生成语音并返回文件路径。相同文本复用缓存，避免反复覆盖 speech.mp3。"""
    AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.md5((text or "").encode("utf-8")).hexdigest()[:16]
    output_path = AUDIO_CACHE_DIR / f"speech_{digest}.mp3"
    if not output_path.exists():
        asyncio.run(generate_voice(text, output_path))
    return str(output_path)
