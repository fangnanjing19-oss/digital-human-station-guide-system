"""项目统一配置。

优先读取 Streamlit secrets，其次读取环境变量，避免把 API Key 写死在代码里。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    import streamlit as st
except Exception:  # 允许在非 Streamlit 场景下导入
    st = None


BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_BASE_PATH = BASE_DIR / "knowledge_base.json"
AUDIO_CACHE_DIR = BASE_DIR / "audio_cache"
DEFAULT_AVATAR_PATH = BASE_DIR / "veteran.png"


def _get_secret(name: str, default: str = "") -> str:
    if st is not None:
        try:
            value = st.secrets.get(name, "")
            if value:
                return str(value)
        except Exception:
            pass
    return os.getenv(name, default)


@dataclass(frozen=True)
class LLMConfig:
    api_key: str = _get_secret("MOONSHOT_API_KEY")
    base_url: str = _get_secret("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1")
    model: str = _get_secret("MOONSHOT_MODEL", "moonshot-v1-8k")
    temperature: float = float(_get_secret("MOONSHOT_TEMPERATURE", "0.25") or 0.25)
    max_context_chunks: int = int(_get_secret("MAX_CONTEXT_CHUNKS", "5") or 5)


llm_config = LLMConfig()
