from __future__ import annotations

from pathlib import Path
import tempfile

try:
    import speech_recognition as sr
except Exception:
    sr = None


def speech_to_text(audio_bytes: bytes) -> str:
    """语音转文字。识别失败时返回空字符串，避免页面崩溃。"""
    if not audio_bytes or sr is None:
        return ""
    recognizer = sr.Recognizer()
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(audio_bytes)
            tmp_path = Path(tmp.name)
        with sr.AudioFile(str(tmp_path)) as source:
            audio = recognizer.record(source)
        return recognizer.recognize_google(audio, language="zh-CN")
    except Exception:
        return ""
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
