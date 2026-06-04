from __future__ import annotations

import textwrap
import base64
import html
import os
from urllib.parse import quote

import streamlit as st
import streamlit.components.v1 as components
from streamlit_mic_recorder import mic_recorder

from brain import get_veteran_response, KNOWLEDGE_BASE
from guide_content import STATION_GUIDES
from stt import speech_to_text
from voice import speak

# 1. 基础配置
st.set_page_config(page_title="数智长征：叙事官", layout="wide", initial_sidebar_state="collapsed")

# --- 2. 状态初始化 ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_audio_id" not in st.session_state:
    st.session_state.last_audio_id = None
if "last_audio_path" not in st.session_state:
    st.session_state.last_audio_path = None
if "guide_mode" not in st.session_state:
    st.session_state.guide_mode = False
if "active_guide_station" not in st.session_state:
    st.session_state.active_guide_station = None

# --- 3. 通用工具 ---
def get_image_base64(path: str) -> str | None:
    try:
        if os.path.exists(path):
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode()
        return None
    except Exception:
        return None


def safe_text(value) -> str:
    """模型输出只做文本展示，避免把模型生成内容当 HTML 或 Markdown 执行。"""
    text = html.escape(str(value or ""), quote=True)
    # 避免模型输出的 ``` 触发 Markdown 代码块，导致后续 HTML 原样显示
    text = text.replace("`", "&#96;")
    return text.replace("\n", "<br>")
def clean_source_name(source: str) -> str:
    """清理史料来源文件名，只保留适合展示的书名。"""
    if not source:
        return "未知史料"

    import re

    name = str(source)

    # 去掉路径
    name = name.split("/")[-1].split("\\")[-1]

    # 去掉文件扩展名
    name = name.replace(".pdf", "").replace(".PDF", "")

    # 去掉 libgen / 文件编号 / 下载痕迹
    name = name.replace("libgen.li", "")
    name = name.replace("libgen", "")

    # 去掉花括号里的作者、编号等信息，例如 {107064222}
    name = re.sub(r"\{[^}]*\}", "", name)

    # 去掉 OCR 后缀和多余空格
    name = name.replace("_ocr", "")
    name = name.replace("ocr", "")
    name = name.replace(" - ", " ")
    name = name.replace("副本", "")
    name = " ".join(name.split())

    return name.strip(" -_《》") or "未知史料"


def make_action_link(
    label: str,
    query: str | None = None,
    guide: bool | None = None,
    clear: bool = False,
    station_title: str | None = None,
    css_class: str = "",
) -> str:
    params = []
    if query:
        params.append(f"q={quote(query)}")
    if guide is not None:
        params.append(f"guide={'1' if guide else '0'}")
    if clear:
        params.append("clear=1")
    if station_title:
        params.append(f"station={quote(station_title)}")
    href = "?" + "&".join(params) if params else "#"
    return f'<a class="{css_class}" href="{href}" target="_self">{html.escape(label)}</a>'


def station_guide_prompt(station_title: str) -> str:
    return f"讲解员模式：站点讲解：{station_title}"


def station_by_index(index: int) -> dict:
    safe_index = max(0, min(index, len(STATION_GUIDES) - 1))
    station = STATION_GUIDES[safe_index]
    return {"title": station.title, "date": station.date, "index": safe_index}


def station_prompt_by_index(index: int) -> str:
    return station_guide_prompt(station_by_index(index)["title"])


def latest_user_query() -> str:
    for msg in reversed(st.session_state.get("messages", [])):
        if msg.get("role") == "user":
            return str(msg.get("content", ""))
    return ""


def build_copy_text(response_data: dict) -> str:
    llm_data = response_data.get("llm_data") or {}
    parts = []

    voice_script = str(llm_data.get("voice_script") or "").strip()
    detailed_text = str(llm_data.get("detailed_text") or "").strip()

    if voice_script:
        parts.append(f"【语音简要版】\n{voice_script}")
    if detailed_text:
        parts.append(f"【详细讲解】\n{detailed_text}")

    citations = response_data.get("citations") or []
    if citations:
        source_lines = []
        seen = set()
        for idx, citation in enumerate(citations[:8], start=1):
            source = clean_source_name(str(citation.get("source", "未知资料")))
            page = str(citation.get("page", "?"))
            key = (source, page)
            if key in seen:
                continue
            seen.add(key)
            page_part = f" 第 {page} 页" if page and page != "?" else ""
            source_lines.append(f"{idx}. 《{source}》{page_part}")
        if source_lines:
            parts.append("【引用资料来源】\n" + "\n".join(source_lines))

    relics = response_data.get("relic_matches") or []
    if relics:
        relic_lines = []
        for idx, relic in enumerate(relics[:3], start=1):
            title = str(relic.get("title", "相关长征文物")).strip()
            caption = str(relic.get("caption") or relic.get("summary") or "").strip()
            relic_lines.append(f"{idx}. {title}" + (f"\n   {caption}" if caption else ""))
        parts.append("【关联长征文物】\n" + "\n".join(relic_lines))

    return "\n\n".join(parts).strip()


def make_copy_button(label: str, text: str, css_class: str = "command-link") -> str:
    payload = base64.b64encode((text or "").encode("utf-8")).decode("ascii")
    return (
        f"<button type='button' class='{css_class} copy-button' data-copy='{payload}' data-label='{html.escape(label)}'>"
        f"{html.escape(label)}</button>"
    )


def render_copy_binder() -> None:
    components.html(
        """
        <script>
        (() => {
          const parentDoc = window.parent.document;
          async function copyToClipboard(text) {
            if (navigator.clipboard && window.isSecureContext) {
              try {
                await navigator.clipboard.writeText(text);
                return true;
              } catch (error) {
                // Fall through to the selection-based fallback below.
              }
            }

            const textarea = parentDoc.createElement("textarea");
            textarea.value = text;
            textarea.setAttribute("readonly", "");
            textarea.style.position = "fixed";
            textarea.style.left = "-9999px";
            textarea.style.top = "0";
            textarea.style.opacity = "0";
            parentDoc.body.appendChild(textarea);
            textarea.focus();
            textarea.select();
            textarea.setSelectionRange(0, textarea.value.length);

            let copied = false;
            try {
              copied = parentDoc.execCommand("copy");
            } finally {
              parentDoc.body.removeChild(textarea);
            }
            return copied;
          }

          const buttons = parentDoc.querySelectorAll(".copy-button[data-copy]");
          buttons.forEach((button) => {
            if (button.dataset.copyBound === "1") return;
            button.dataset.copyBound = "1";
            button.addEventListener("click", async (event) => {
              event.preventDefault();
              event.stopPropagation();
              const original = button.dataset.label || button.innerText || "复制回答";
              try {
                const bytes = Uint8Array.from(atob(button.dataset.copy || ""), (c) => c.charCodeAt(0));
                const text = new TextDecoder().decode(bytes);
                const copied = await copyToClipboard(text);
                if (copied) {
                  button.innerText = "已复制";
                  window.setTimeout(() => { button.innerText = original; }, 1600);
                } else {
                  button.innerText = "复制失败";
                  window.setTimeout(() => { button.innerText = original; }, 1800);
                }
              } catch (error) {
                button.innerText = "复制失败";
                window.setTimeout(() => { button.innerText = original; }, 1800);
              }
            });
          });
        })();
        </script>
        """,
        height=0,
        width=0,
    )


def get_station_by_title(station_title: str) -> dict | None:
    for idx, station in enumerate(STATION_GUIDES):
        if station.title == station_title:
            return {"title": station.title, "date": station.date, "index": idx}
    return None


def infer_station_from_text(text: str) -> dict | None:
    value = str(text or "")
    if not value:
        return None

    best_match = None
    best_score = 0
    for idx, station in enumerate(STATION_GUIDES):
        score = 0
        if station.title in value:
            score += 6
        for alias in station.aliases:
            if alias and alias in value:
                score += 3
        if station.search_query and any(term in value for term in station.search_query.split()):
            score += 1
        if score > best_score:
            best_score = score
            best_match = {"title": station.title, "date": station.date, "index": idx}

    return best_match if best_score >= 3 else None


def get_latest_guide_station() -> dict:
    current = st.session_state.get("active_guide_station")
    if isinstance(current, dict) and current.get("title"):
        return current

    for msg in reversed(st.session_state.get("messages", [])):
        if msg.get("role") != "assistant":
            continue
        station = (msg.get("data") or {}).get("guide_station") or {}
        if station.get("title"):
            st.session_state.active_guide_station = station
            return station

    for msg in reversed(st.session_state.get("messages", [])):
        if msg.get("role") == "user":
            station = infer_station_from_text(msg.get("content", ""))
        else:
            data = msg.get("data") or {}
            llm_data = data.get("llm_data") or {}
            station = infer_station_from_text(
                " ".join([
                    str(llm_data.get("voice_script", "")),
                    str(llm_data.get("detailed_text", "")),
                    " ".join(str(item) for item in llm_data.get("follow_ups", [])),
                ])
            )
        if station:
            st.session_state.active_guide_station = station
            return station

    return {}


# --- 4. 核心交互函数 ---
def handle_response(user_query: str):
    loading_slot = st.empty()
    loading_slot.markdown(
        "<div class='retrieval-loading'>正在检索长征档案、比对史料证据与关联文物...</div>",
        unsafe_allow_html=True,
    )
    try:
        full_response = get_veteran_response(user_query)
        guide_station = full_response.get("guide_station")
        if guide_station:
            st.session_state.active_guide_station = guide_station
        voice_script = full_response.get("llm_data", {}).get("voice_script", "")
        try:
            audio_path = speak(voice_script) if voice_script else None
        except Exception:
            audio_path = None
        st.session_state.last_audio_path = audio_path
        st.session_state.messages.append({"role": "user", "content": user_query})
        st.session_state.messages.append({"role": "assistant", "data": full_response})
    finally:
        loading_slot.empty()
    st.rerun()


# --- 5. 处理 URL 点击事件：不再用 Streamlit 按钮改布局 ---
try:
    params = dict(st.query_params)
except Exception:
    params = {}

param_station = str(params.get("station") or "").strip()
if param_station:
    station = get_station_by_title(param_station) or infer_station_from_text(param_station)
    if station:
        st.session_state.active_guide_station = station

if params.get("clear") == "1" and not st.session_state.get("_handled_query_params"):
    st.session_state._handled_query_params = True
    st.session_state.messages = []
    st.session_state.last_audio_path = None
    st.session_state.active_guide_station = None
    try:
        st.query_params.clear()
    except Exception:
        pass
    st.rerun()
elif params.get("guide") == "1" and not st.session_state.get("_handled_query_params"):
    st.session_state._handled_query_params = True
    st.session_state.guide_mode = True
    try:
        st.query_params.clear()
    except Exception:
        pass
    handle_response("讲解员模式：站点讲解：瑞金集结出发")
elif params.get("guide") == "0" and not st.session_state.get("_handled_query_params"):
    st.session_state._handled_query_params = True
    st.session_state.guide_mode = False
    try:
        st.query_params.clear()
    except Exception:
        pass
    st.rerun()
elif params.get("q") and not st.session_state.get("_handled_query_params"):
    st.session_state._handled_query_params = True
    query = str(params.get("q"))
    if query.startswith("讲解员模式：站点讲解："):
        st.session_state.guide_mode = True
        station_title = query.split("讲解员模式：站点讲解：", 1)[1].strip()
        station = get_station_by_title(station_title)
        if station:
            st.session_state.active_guide_station = station
    try:
        st.query_params.clear()
    except Exception:
        pass
    handle_response(query)
else:
    st.session_state._handled_query_params = False


img_base64 = get_image_base64("veteran.png")
has_answer = bool(st.session_state.messages and st.session_state.messages[-1].get("role") == "assistant")
hero_class = "veteran-img speaking" if has_answer else "veteran-img"

if has_answer:
    hero_html = """
<div class="veteran-hero-container answer-title-only">
    <div class="hero-title">长征老红军</div>
</div>
"""
else:
    hero_html = f"""
<div class="veteran-hero-container">
    <div class="hero-title">长征老红军</div>
    <img src="data:image/png;base64,{img_base64 if img_base64 else ''}" class="{hero_class}">
</div>
"""

# --- 6. 原 UI 样式：保持板块位置与比例，只加轻微增强 ---
st.markdown(f"""
    <style>
    [data-testid="stHeader"], [data-testid="stToolbar"], footer, [data-testid="stDecoration"] {{
        display: none !important;
    }}

    .stApp, [data-testid="stAppViewContainer"], [data-testid="stMainViewContainer"] {{
        background: radial-gradient(circle at center 40%, #2a0808 0%, #050000 80%, #000000 100%) !important;
        background-color: transparent !important;
    }}
    html, body {{ height: 100vh !important; margin: 0 !important; overflow: hidden !important; }}

    .veteran-hero-container {{
    position: fixed; top: 40%; left: 49%; transform: translate(-50%, -50%);
    text-align: center; z-index: 1; width: min(36vw, 520px);
}}

.answer-title-only {{
    top: 8% !important;
}}

.answer-title-only .hero-title {{
    font-size: 34px !important;
    margin-bottom: 0 !important;
}}

.hero-title {{
    color: #d4af37; font-family: "KaiTi", "STKaiti", serif; font-size: 34px;
    margin-bottom: 20px; letter-spacing: 6px;
    text-shadow: 0px 4px 15px rgba(212, 175, 55, 0.4);
}}
    .veteran-img {{
        width: clamp(380px, 25.5vw, 460px);
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.05);
        box-shadow: 0 20px 60px rgba(0,0,0,0.9), 0 0 30px rgba(139, 0, 0, 0.3);
        animation: veteranBreath 6s ease-in-out infinite;
        transition: box-shadow 0.4s ease, filter 0.4s ease;
    }}
    .veteran-img.speaking {{
        box-shadow: 0 20px 65px rgba(0,0,0,0.95), 0 0 42px rgba(212,175,55,0.36), 0 0 75px rgba(139,0,0,0.45);
        filter: saturate(1.06) contrast(1.03);
    }}
    @keyframes veteranBreath {{
        0%, 100% {{ transform: scale(1); filter: brightness(1); }}
        50% {{ transform: scale(1.01); filter: brightness(1.04); }}
    }}

    .subtitle-overlay {{
    position: fixed;
    top: 15%;
    left: 50%;
    transform: translateX(-50%);
    width: min(82vw, 1250px);
    text-align: center;
    color: #ffffff;
    font-size: 26px;
    font-weight: 700;
    line-height: 1.55;
    letter-spacing: 1px;
    text-shadow: 0 4px 18px rgba(0,0,0,0.9);
    z-index: 10;
    pointer-events: none;
}}
    .archive-panel {{
    position: fixed;
    top: 53%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: min(82vw, 1320px);
    height: 57vh;
    overflow-y: auto;
    color: #e8e8e8;
    font-size: 18px;
    line-height: 1.95;
    z-index: 9;
    background: rgba(20, 0, 0, 0.68);
    backdrop-filter: blur(15px);
    -webkit-backdrop-filter: blur(15px);
    padding: 30px 40px;
    border-radius: 16px;
    border: 1px solid rgba(212,175,55,0.22);
    box-shadow: 0 14px 42px rgba(0,0,0,0.85);
}}
    .archive-header {{
    color: #d4af37;
    font-size: 22px;
    margin-bottom: 14px;
    padding-bottom: 10px;
    border-bottom: 1px solid rgba(212,175,55,0.25);
}}
    .citation-chip {{
        display: inline-block; margin: 0 8px 8px 0; padding: 5px 10px;
        border: 1px solid rgba(212,175,55,0.28); border-radius: 999px;
        background: rgba(212,175,55,0.07); color: #d4af37; font-size: 12px;
    }}
    .evidence-details {{
        margin-top: 6px; border: 1px solid rgba(212,175,55,0.18); border-radius: 10px;
        background: rgba(0,0,0,0.16); overflow: hidden;
    }}
    .evidence-details summary {{
        cursor: pointer; list-style: none; padding: 10px 12px; color: #d4af37;
        font-size: 14px; letter-spacing: 1px; user-select: none;
    }}
    .evidence-details summary::-webkit-details-marker {{ display: none; }}
    .evidence-details summary::before {{ content: '▸'; display: inline-block; margin-right: 8px; transition: transform .2s ease; }}
    .evidence-details[open] summary::before {{ transform: rotate(90deg); }}
    .evidence-card {{
        margin: 0 12px 12px 12px; padding: 12px 14px; border-left: 2px solid rgba(212,175,55,0.45);
        background: rgba(40, 10, 10, 0.42); color: #bfbfbf; border-radius: 8px; font-size: 13px; line-height: 1.75;
    }}
    .relic-grid {{
    display: grid;
    grid-template-columns: minmax(360px, 620px);
    justify-content: center;
    gap: 16px;
    margin-top: 14px;
}}

.relic-card {{
    background: rgba(0,0,0,0.22);
    border: 1px solid rgba(212,175,55,0.22);
    border-radius: 12px;
    padding: 14px;
}}

.relic-img {{
    width: 100%;
    max-height: 420px;
    object-fit: contain;
    border-radius: 8px;
    background: rgba(255,255,255,0.04);
    margin-bottom: 10px;
}}

.relic-title {{
    color: #d4af37;
    font-weight: 700;
    font-size: 16px;
    line-height: 1.5;
}}

.relic-meta {{
    color: #aaa;
    font-size: 13px;
    margin-top: 4px;
}}

.relic-topic {{
    color: #ddd;
    font-size: 14px;
    margin-top: 8px;
}}

.relic-summary {{
    color: #cfcfcf;
    font-size: 14px;
    line-height: 1.65;
    margin-top: 8px;
}}
.relic-zoom {{
    margin-top: 8px;
}}

.relic-zoom summary {{
    cursor: pointer;
    color: #d4af37;
    font-size: 13px;
    user-select: none;
    list-style: none;
}}

.relic-zoom summary::-webkit-details-marker {{
    display: none;
}}

.relic-img-large {{
    width: 100%;
    max-height: none;
    object-fit: contain;
    border-radius: 10px;
    margin-top: 10px;
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(212,175,55,0.18);
}}
    .evidence-meta {{ color: #d4af37; font-size: 12px; margin-bottom: 6px; }}
    .retrieval-loading {{
        position: fixed; top: 58%; left: 50%; transform: translateX(-50%); z-index: 10001;
        padding: 12px 22px; border-radius: 999px;
        background: rgba(20,0,0,0.82); border: 1px solid rgba(212,175,55,0.35);
        color: #d4af37; box-shadow: 0 0 35px rgba(212,175,55,0.14);
        letter-spacing: 2px; font-size: 14px;
    }}
    .retrieval-loading::before {{ content: ""; display: inline-block; width: 8px; height: 8px; margin-right: 9px; border-radius: 50%; background: #d4af37; animation: archivePulse 1s infinite; }}
    @keyframes archivePulse {{ 0% {{ opacity: .25; transform: scale(.75); }} 50% {{ opacity: 1; transform: scale(1.15); }} 100% {{ opacity: .25; transform: scale(.75); }} }}

    [data-testid="stBottom"], [data-testid="stBottomBlockContainer"] {{
        background: transparent !important;
        padding-bottom: 0 !important;
    }}
    [data-testid="stChatInput"] {{
        background: linear-gradient(145deg, rgba(40,10,10,0.95), rgba(15,0,0,0.98)) !important;
        backdrop-filter: blur(25px) !important; -webkit-backdrop-filter: blur(25px) !important;
        border: 1px solid rgba(212, 175, 55, 0.4) !important;
        border-radius: 35px !important;
        box-shadow: 0 10px 40px rgba(0,0,0,0.9), inset 0 1px 0 rgba(255,255,255,0.05) !important;
        position: fixed !important; bottom: 22px !important; left: 55% !important; transform: translateX(-50%) !important;
        width: min(58vw, 1120px) !important; min-width: 520px !important; z-index: 10000 !important; padding: 6px 20px !important;
    }}
    [data-testid="stChatInput"] textarea {{
        color: #ffffff !important; background-color: transparent !important; font-size: 16px !important; line-height: 1.6 !important; caret-color: #d4af37 !important;
    }}
    [data-testid="stChatInput"] textarea::placeholder {{ color: rgba(255,255,255,0.3) !important; font-style: italic !important; }}
    [data-testid="stChatInput"] button {{ background: rgba(212, 175, 55, 0.05) !important; border-radius: 50% !important; transition: all 0.3s ease !important; }}
    [data-testid="stChatInput"] button:hover {{ background: rgba(212, 175, 55, 0.2) !important; transform: scale(1.1) !important; }}
    [data-testid="stChatInput"] button svg {{ fill: #d4af37 !important; }}

    iframe[title*="streamlit_mic_recorder"] {{
        position: fixed !important; bottom: 24px !important; left: 15vw !important; height: 50px !important; width: 140px !important; z-index: 99999 !important;
        filter: invert(0.95) hue-rotate(180deg) brightness(1.1) drop-shadow(0 5px 15px rgba(212,175,55,0.15)) !important;
        border-radius: 25px !important;
    }}
    .stAudio {{
        position: fixed !important;
        right: 46px !important;
        bottom: 124px !important;
        width: 340px !important;
        z-index: 9997 !important;
        opacity: .94 !important;
    }}
    .stAudio audio {{
        width: 100% !important;
        height: 42px !important;
        border-radius: 999px !important;
        box-shadow: 0 8px 24px rgba(0,0,0,0.45) !important;
    }}
    ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
    ::-webkit-scrollbar-track {{ background: transparent; }}
    ::-webkit-scrollbar-thumb {{ background: rgba(212, 175, 55, 0.3); border-radius: 10px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: rgba(212, 175, 55, 0.6); }}

    .left-timeline {{
        position: fixed; top: 50%; left: 7%; transform: translateY(-50%); width: 270px;
        color: #d4af37; font-family: "KaiTi", "STKaiti", serif; z-index: 10;
        border-left: 2px solid rgba(212,175,55,0.4); padding-left: 18px;
    }}
    .timeline-item {{ display:block; margin-bottom: 20px; position: relative; cursor: pointer; text-decoration: none !important; color: inherit !important; }}
    .timeline-item::before {{
        content: ''; position: absolute; left: -26px; top: 6px; width: 10px; height: 10px; background: #8b0000;
        border: 2px solid #d4af37; border-radius: 50%; box-shadow: 0 0 10px rgba(212,175,55,0.8); transition: all 0.3s ease;
    }}
    .timeline-date {{ font-size: 13px; color: rgba(255,255,255,0.5); margin-bottom: 2px; transition: all 0.3s ease; }}
    .timeline-event {{ font-size: 18px; font-weight: bold; letter-spacing: 2px; text-shadow: 2px 2px 5px #000; transition: all 0.3s ease; }}
    .timeline-item:hover::before {{ background: #d4af37; box-shadow: 0 0 15px #d4af37; }}
    .timeline-item:hover .timeline-date {{ color: rgba(212,175,55,0.8); }}
    .timeline-item:hover .timeline-event {{ color: #fff; transform: translateX(5px); }}

    .right-info-panel {{
        position: fixed; top: 50%; right: 7%; transform: translateY(-50%); width: clamp(350px, 20vw, 390px); z-index: 10;
        background: rgba(30, 5, 5, 0.6); padding: 24px 26px; border-radius: 14px;
        border: 1px solid rgba(212,175,55,0.3); backdrop-filter: blur(15px); -webkit-backdrop-filter: blur(15px);
        box-shadow: 0 10px 30px rgba(0,0,0,0.8);
    }}
    .mode-row {{ display: flex; gap: 10px; justify-content: center; margin-bottom: 16px; }}
    .mode-link {{
        display: inline-block; padding: 6px 10px; border: 1px solid rgba(212,175,55,0.28); border-radius: 999px;
        color: #d4af37 !important; text-decoration: none !important; background: rgba(212,175,55,0.06);
        font-size: 12px; letter-spacing: .5px;
    }}
    .mode-link:hover {{ background: rgba(212,175,55,0.16); color: #fff !important; }}
    .right-question {{
        display:block; color:#d4af37 !important; text-decoration:none !important; font-size:15px;
        padding: 7px 0; transition: all .3s ease;
    }}
    .right-question:hover {{ color:#fff !important; transform: translateX(5px); }}
    .followup-row {{ margin-top: 12px; display: flex; flex-wrap: wrap; gap: 8px; }}
    .followup-link {{
        display: inline-block; padding: 7px 11px; border: 1px solid rgba(212,175,55,0.26); border-radius: 999px;
        color: #d4af37 !important; text-decoration: none !important; background: rgba(212,175,55,0.06);
        font-size: 13px; line-height: 1.45;
    }}
    .followup-link:hover {{ background: rgba(212,175,55,0.15); color: #fff !important; }}
    .source-line {{ margin-bottom: 6px; color: #cfcfcf; font-size: 13px; line-height: 1.65; }}
    .source-index {{ color: #d4af37; font-weight: 700; }}
    .command-bar {{
        display: flex; align-items: center; justify-content: space-between; gap: 12px;
        margin-bottom: 18px; padding-bottom: 14px; border-bottom: 1px solid rgba(212,175,55,0.2);
    }}
    .command-title {{
        color: #d4af37; font-size: 18px; font-weight: 700; line-height: 1.35;
    }}
    .command-subtitle {{
        color: #9f9f9f; font-size: 12px; margin-top: 3px; letter-spacing: .5px;
    }}
    .command-actions {{
        display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end;
    }}
    .command-link {{
        display: inline-flex; align-items: center; justify-content: center;
        min-height: 32px; padding: 7px 12px; border-radius: 999px;
        border: 1px solid rgba(212,175,55,0.28); color: #d4af37 !important;
        background: rgba(212,175,55,0.06); text-decoration: none !important;
        font-size: 12px; line-height: 1.2; white-space: nowrap;
    }}
    button.command-link {{
        font-family: inherit; cursor: pointer;
    }}
    .command-link:hover {{ background: rgba(212,175,55,0.16); color: #fff !important; }}
    .status-grid {{
        display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px;
        margin: 12px 0 18px;
    }}
    .status-card {{
        min-height: 64px; padding: 10px 12px; border-radius: 10px;
        border: 1px solid rgba(212,175,55,0.18); background: rgba(0,0,0,0.18);
    }}
    .status-label {{ color: #8e8e8e; font-size: 12px; margin-bottom: 4px; }}
    .status-value {{ color: #f1d47a; font-size: 17px; font-weight: 700; line-height: 1.25; }}
    .guide-progress {{
        margin: 0 0 16px; padding: 12px 14px; border-radius: 10px;
        background: rgba(212,175,55,0.07); border: 1px solid rgba(212,175,55,0.2);
    }}
    .guide-progress-top {{
        display: flex; justify-content: space-between; gap: 12px; color: #d4af37;
        font-size: 13px; margin-bottom: 9px;
    }}
    .guide-track {{
        height: 8px; border-radius: 999px; background: rgba(255,255,255,0.08);
        overflow: hidden;
    }}
    .guide-fill {{
        height: 100%; border-radius: 999px;
        background: linear-gradient(90deg, #8b0000, #d4af37);
    }}
    .station-nav {{
        display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px;
        margin: 0 0 18px;
    }}
    .station-pill {{
        display: block; min-height: 38px; padding: 7px 8px; border-radius: 999px;
        border: 1px solid rgba(212,175,55,0.18); color: #bfa34d !important;
        background: rgba(0,0,0,0.16); text-decoration: none !important;
        font-size: 12px; line-height: 1.25; text-align: center;
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }}
    .station-pill:hover {{ color: #fff !important; background: rgba(212,175,55,0.12); }}
    .station-pill.active {{
        color: #fff4bd !important; background: rgba(212,175,55,0.16);
        border-color: rgba(212,175,55,0.48); box-shadow: inset 0 0 18px rgba(212,175,55,0.08);
    }}
    .trust-note {{
        margin: 0 0 16px; padding: 11px 13px; border-radius: 10px;
        background: rgba(0,0,0,0.18); border-left: 3px solid rgba(212,175,55,0.58);
        color: #cfcfcf; font-size: 13px; line-height: 1.7;
    }}
    .trust-note strong {{ color: #d4af37; }}
    .copy-notice {{
        margin: 0 0 16px; padding: 9px 12px; border-radius: 10px;
        background: rgba(212,175,55,0.08); border: 1px solid rgba(212,175,55,0.18);
        color: #d4af37; font-size: 13px; line-height: 1.6;
    }}
    .panel-section-title {{
        color: #d4af37; font-size: 18px; font-weight: 700; margin-bottom: 10px;
        border-bottom: 1px solid rgba(212,175,55,0.3); padding-bottom: 8px; text-align: center;
    }}
    .panel-copy {{
        color: #aaa; font-size: 13px; line-height: 1.65; text-align: center;
    }}
    .panel-metrics {{
        display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 14px 0;
    }}
    .panel-metric {{
        padding: 10px 8px; border: 1px solid rgba(212,175,55,0.18); border-radius: 10px;
        background: rgba(0,0,0,0.18); text-align: center;
    }}
    .panel-metric-value {{ color: #d4af37; font-size: 18px; font-weight: 800; }}
    .panel-metric-label {{ color: #888; font-size: 12px; margin-top: 3px; }}
    .panel-hint {{ margin-top: 14px; font-size: 12px; color: #888; font-style: italic; text-align: center; }}
    @media (max-width: 1180px) {{
        .left-timeline {{ left: 24px; width: 210px; }}
        .right-info-panel {{ right: 24px; width: 300px; }}
        [data-testid="stChatInput"] {{ width: 58% !important; left: 57% !important; min-width: 360px !important; }}
    }}
    @media (max-width: 900px) {{
        html, body {{ overflow: auto !important; }}
        .veteran-hero-container {{ position: relative; top: auto; left: auto; transform: none; margin: 28px auto 8px; }}
        .veteran-img {{ width: min(70vw, 300px); }}
        .left-timeline, .right-info-panel, .archive-panel, .subtitle-overlay {{
            position: relative; top: auto; left: auto; right: auto; transform: none; width: calc(100vw - 32px);
            margin: 16px auto; height: auto; max-height: none;
        }}
        .left-timeline {{ border-left: 0; border-top: 1px solid rgba(212,175,55,0.34); padding: 14px 0 0; }}
        .timeline-item {{ margin-bottom: 14px; padding-left: 18px; }}
        .timeline-item::before {{ left: 0; top: 7px; }}
        .subtitle-overlay {{ text-align: left; font-size: 20px; pointer-events: auto; }}
        .archive-panel {{ padding: 22px 18px; font-size: 16px; }}
        .command-bar {{ align-items: flex-start; flex-direction: column; }}
        .command-actions {{ justify-content: flex-start; }}
        .status-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
        .station-nav {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
        .relic-grid {{ grid-template-columns: 1fr; }}
        [data-testid="stChatInput"] {{
            position: sticky !important; bottom: 12px !important; left: auto !important; transform: none !important;
            width: calc(100vw - 24px) !important; min-width: 0 !important; margin: 0 auto !important;
        }}
        .stAudio {{ position: relative !important; right: auto !important; bottom: auto !important; width: calc(100vw - 32px) !important; margin: 12px auto !important; }}
        iframe[title*="streamlit_mic_recorder"] {{ position: sticky !important; bottom: 82px !important; left: 12px !important; }}
    }}
    </style>
    {hero_html}
""", unsafe_allow_html=True)



# --- 7. 语音提问逻辑 ---

audio_input = mic_recorder(
    start_prompt="🎤 语音提问",
    stop_prompt="🔴 停止识别",
    key="veteran_mic_v8"
)
if audio_input:
    current_audio_id = f"{len(audio_input['bytes'])}-{audio_input['bytes'][:10]}"
    if current_audio_id != st.session_state.last_audio_id:
        st.session_state.last_audio_id = current_audio_id
        user_text = speech_to_text(audio_input["bytes"])
        if user_text:
            handle_response(user_text)


# --- 8. 渲染回答区 ---
if st.session_state.messages:
    last_msg = st.session_state.messages[-1]
    if last_msg["role"] == "assistant":
        res = last_msg["data"]
        llm_data = res.get("llm_data", {})
        relics = res.get("relic_matches", [])
        guide_station = res.get("guide_station") or {}
        st.markdown(f"<div class='subtitle-overlay'>{safe_text(llm_data.get('voice_script', ''))}</div>", unsafe_allow_html=True)

        citations = res.get("citations", [])
        snippets = res.get("evidence_snippets", [])
        answer_mode = "讲解员模式" if guide_station or st.session_state.guide_mode else "问答模式"
        active_guide_station = guide_station or get_latest_guide_station()
        station_title = guide_station.get("title") or "自由问答"
        station_date = guide_station.get("date") or "按需检索"
        station_index = int(guide_station.get("index", 0) or 0)
        total_stations = max(len(STATION_GUIDES), 1)
        progress_width = int(((station_index + 1) / total_stations) * 100) if guide_station else 0
        guide_progress_html = ""
        if guide_station:
            guide_progress_html = (
                f"<div class='guide-progress'>"
                f"<div class='guide-progress-top'>"
                f"<span>当前站点：{safe_text(station_title)} · {safe_text(station_date)}</span>"
                f"<span>第 {station_index + 1} / {total_stations} 站</span>"
                f"</div>"
                f"<div class='guide-track'><div class='guide-fill' style='width:{progress_width}%;'></div></div>"
                f"</div>"
            )
        elif active_guide_station:
            resume_index = int(active_guide_station.get("index", 0) or 0)
            resume_title = active_guide_station.get("title", "当前站点")
            resume_date = active_guide_station.get("date", "")
            resume_width = int(((resume_index + 1) / total_stations) * 100)
            guide_progress_html = (
                f"<div class='guide-progress'>"
                f"<div class='guide-progress-top'>"
                f"<span>追问来自：{safe_text(resume_title)} · {safe_text(resume_date)}</span>"
                f"<span>可直接回到第 {resume_index + 1} / {total_stations} 站</span>"
                f"</div>"
                f"<div class='guide-track'><div class='guide-fill' style='width:{resume_width}%;'></div></div>"
                f"</div>"
            )
        status_html = (
            f"<div class='status-grid'>"
            f"<div class='status-card'><div class='status-label'>运行模式</div><div class='status-value'>{safe_text(answer_mode)}</div></div>"
            f"<div class='status-card'><div class='status-label'>命中史料</div><div class='status-value'>{len(citations)} 条</div></div>"
            f"<div class='status-card'><div class='status-label'>关联文物</div><div class='status-value'>{len(relics)} 件</div></div>"
            f"<div class='status-card'><div class='status-label'>资料切片</div><div class='status-value'>{len(snippets)} 段</div></div>"
            f"</div>"
        )
        if citations:
            top_source = clean_source_name(str(citations[0].get("source", "未知资料")))
            trust_html = (
                f"<div class='trust-note'><strong>证据状态：已命中史料。</strong>"
                f" 本次回答检索到 {len(citations)} 条资料线索，优先证据来自《{safe_text(top_source)}》。"
                f" 展开下方“原始史料证据”可核对片段。</div>"
            )
        else:
            trust_html = (
                "<div class='trust-note'><strong>证据状态：需要补充。</strong>"
                " 本次没有检索到直接匹配的史料切片，回答应作为谨慎讲解，不宜当作精确出处引用。</div>"
            )
        copy_text = build_copy_text(res)
        if not active_guide_station and len(st.session_state.messages) >= 2:
            active_guide_station = infer_station_from_text(st.session_state.messages[-2].get("content", ""))
            if active_guide_station:
                st.session_state.active_guide_station = active_guide_station
        guide_resume_title = str(active_guide_station.get("title") or "")
        nav_index = int(active_guide_station.get("index", 0) or 0) if active_guide_station else 0
        prev_station = station_by_index(nav_index - 1)
        next_station = station_by_index(nav_index + 1)
        if guide_resume_title:
            guide_action = make_action_link(
                f"回到本站讲解：{guide_resume_title}",
                station_guide_prompt(guide_resume_title),
                css_class="command-link",
            )
        else:
            guide_action = make_action_link("开启讲解员模式", guide=True, css_class="command-link")
        station_nav_html = ""
        if active_guide_station:
            station_links = []
            for idx, station in enumerate(STATION_GUIDES):
                active_class = " active" if idx == nav_index else ""
                station_links.append(
                    make_action_link(
                        f"{idx + 1}. {station.title}",
                        station_guide_prompt(station.title),
                        station_title=station.title,
                        css_class=f"station-pill{active_class}",
                    )
                )
            station_nav_html = (
                f"<div class='command-actions' style='justify-content:flex-start;margin-bottom:12px;'>"
                f"{make_action_link('上一站', station_prompt_by_index(nav_index - 1), station_title=prev_station['title'], css_class='command-link')}"
                f"{make_action_link('回到本站', station_guide_prompt(guide_resume_title), station_title=guide_resume_title, css_class='command-link')}"
                f"{make_action_link('下一站', station_prompt_by_index(nav_index + 1), station_title=next_station['title'], css_class='command-link')}"
                f"{make_action_link('展线总览', clear=True, css_class='command-link')}"
                f"</div>"
                f"<div class='station-nav'>{''.join(station_links)}</div>"
            )
        current_user_query = latest_user_query()
        regenerate_action = (
            make_action_link(
                "重新生成",
                query=current_user_query,
                station_title=guide_resume_title or None,
                css_class="command-link",
            )
            if current_user_query
            else ""
        )
        command_html = (
            f"<div class='command-bar'>"
            f"<div>"
            f"<div class='command-title'>老红军的详细回忆档案</div>"
            f"<div class='command-subtitle'>基于知识库检索、站点导览与文物目录的综合讲解</div>"
            f"</div>"
            f"<div class='command-actions'>"
            f"{make_action_link('返回展线首页', clear=True, css_class='command-link')}"
            f"{guide_action}"
            f"{make_copy_button('复制回答', copy_text)}"
            f"{regenerate_action}"
            f"{make_action_link('切换问答模式', guide=False, css_class='command-link')}"
            f"</div>"
            f"</div>"
        )
        if citations:
            lines = []
            seen = set()
            for idx, c in enumerate(citations[:5], start=1):
                source_raw = str(c.get("source", "未知资料"))
                source_display = safe_text(clean_source_name(source_raw))

                page = safe_text(c.get("page", "?"))

                key = (source_raw, page)
                if key in seen:
                    continue

                seen.add(key)

                page_part = f" 第 {page} 页" if page and page != "?" else ""

                lines.append(
                    f"<div class='source-line'>"
                    f"<span class='source-index'>证据源 {idx}</span> | 《{source_display}》{page_part}"
                    f"</div>"
                )
            citation_html = "".join(lines)
        else:
            citation_html = "<span style='font-size: 13px; color: #aaa;'>本次没有检索到直接匹配的史料切片。</span>"
        if relics:
            relic_cards = []
            for idx, relic in enumerate(relics[:3], start=1):
                title = safe_text(relic.get("title", "相关长征文物"))
                caption = safe_text(relic.get("caption") or relic.get("summary") or "")

                page = safe_text(relic.get("page", "?"))

                image_path = relic.get("image") or relic.get("image_path") or ""

                img_html = ""
                if image_path and os.path.exists(image_path):
                    try:
                        with open(image_path, "rb") as f:
                            img_b64 = base64.b64encode(f.read()).decode("utf-8")
                        img_html = (
                            f"<img class='relic-img' src='data:image/png;base64,{img_b64}'>"
                            f"<details class='relic-zoom'>"
                            f"<summary>🔍 展开查看大图</summary>"
                            f"<img class='relic-img-large' src='data:image/png;base64,{img_b64}'>"
                            f"</details>"
                        )
                    except Exception:
                        img_html = ""

                relic_cards.append(
                    f'<div class="relic-card">'
                    f'{img_html}'
                    f'<div class="relic-title">{title}</div>'
                    f'<div class="relic-meta">来源：《红色文物中的长征》</div>'
                    f'<div class="relic-summary">{caption}</div>'
                    f'</div>'
                )

            relic_html = (
                f'<br>'
                f'<div class="archive-header">🏺 本次回答关联长征文物</div>'
                f'<div class="relic-grid">'
                f'{"".join(relic_cards)}'
                f'</div>'
            )
        else:
            relic_html = ""


        if snippets:
            cards = []
            for idx, item in enumerate(snippets[:4], start=1):
                source_raw = item.get("source", "未知资料")
                source = safe_text(clean_source_name(source_raw))
                page = safe_text(item.get("page", "?"))
                hits = safe_text("、".join(item.get("hits", [])[:5]))
                content = safe_text(item.get("content", ""))
                cards.append(
                    f"<div class='evidence-card'>"
                    f"<div class='evidence-meta'>证据 {idx} ｜《{source}》第 {page} 页 ｜ 命中：{hits}</div>"
                    f"<div>{content}</div>"
                    f"</div>"
                )
            evidence_html = "".join(cards)
        else:
            raw = safe_text(res.get("raw_evidence", "本次没有检索到可展示的原始史料片段。"))
            evidence_html = f"<div class='evidence-card'>{raw}</div>"

        follow_ups = llm_data.get("follow_ups", [])
        followup_html = ""
        if follow_ups:
            links = []
            followup_station_title = str(active_guide_station.get("title") or "")
            for follow_up in follow_ups[:2]:
                is_next_station = str(follow_up).startswith("讲解员模式：站点讲解")
                label = "继续下一站" if is_next_station else "追问：" + str(follow_up)
                links.append(
                    make_action_link(
                        label,
                        str(follow_up),
                        station_title=None if is_next_station else followup_station_title,
                        css_class="followup-link",
                    )
                )
            followup_html = "<div class='archive-header'>💬 推荐追问</div><div class='followup-row'>" + "".join(links) + "</div><br>"

        detail_html = safe_text(llm_data.get('detailed_text', ''))
        archive_html = (
            f'<div class="archive-panel">'
            f'{command_html}'
            f'{guide_progress_html}'
            f'{station_nav_html}'
            f'{status_html}'
            f'{trust_html}'
            f'<div class="detail-text">{detail_html}</div>'
            f'<br>'
            f'{followup_html}'
            f'<div class="archive-header">🧾 本次回答引用资料来源</div>'
            f'<div>{citation_html}</div>'
            f'{relic_html}'
            f'<br>'
            f'<div class="archive-header">🔍 本次回答引用的原始史料证据</div>'
            f'<details class="evidence-details">'
            f'<summary>展开查看命中的馆藏资料片段</summary>'
            f'{evidence_html}'
            f'</details>'
            f'</div>'
        )

        st.markdown(archive_html, unsafe_allow_html=True)
        render_copy_binder()

        audio_path = st.session_state.get("last_audio_path") or "speech.mp3"
        if audio_path and os.path.exists(audio_path):
            st.audio(audio_path, format="audio/mp3", autoplay=True)
else:
    timeline_items = [
        ("1934年10月", "瑞金集结出发", "红军为什么要从瑞金出发开始长征？"),
        ("1934年11月", "血战湘江", "血战湘江为什么这么惨烈？"),
        ("1935年01月", "遵义会议召开", "遵义会议最大的意义是什么？"),
        ("1935年03月", "四渡赤水出奇兵", "四渡赤水为什么被称为运动战典范？"),
        ("1935年05月", "飞夺泸定桥", "飞夺泸定桥到底有多惨烈？"),
        ("1935年06月", "翻越夹金山", "红军翻越夹金山面临哪些困难？"),
        ("1935年08月", "跨越松潘草地", "红军过草地时都吃些什么？"),
        ("1935年10月", "吴起镇大会师", "吴起镇会师对长征意味着什么？"),
    ]
    timeline_html = "".join(
        f"<a class='timeline-item' href='?q={quote(question)}' target='_self'>"
        f"<div class='timeline-date'>{html.escape(date)}</div><div class='timeline-event'>{html.escape(event)}</div></a>"
        for date, event, question in timeline_items
    )

    mode_label = "讲解员模式" if st.session_state.guide_mode else "问答模式"
    panel_html = f"""
    <div class="left-timeline">{timeline_html}</div>
    <div class="right-info-panel">
        <div class="mode-row">
            {make_action_link('🎙 开启讲解员模式', guide=True, css_class='mode-link')}
            {make_action_link('💬 问答模式', guide=False, css_class='mode-link')}
        </div>
        <div style='font-size:12px;color:#aaa;text-align:center;margin-bottom:12px;'>当前：{mode_label}</div>
        <div class="panel-section-title">
            📚 绝密史料档案馆
        </div>
        <div class="panel-copy">
            系统已挂载长征知识库、站点讲稿和文物目录，点击左侧展线或下方问题即可开始讲解。
        </div>
        <div class="panel-metrics">
            <div class="panel-metric">
                <div class="panel-metric-value">{len(KNOWLEDGE_BASE) or 1397}</div>
                <div class="panel-metric-label">核心档案</div>
            </div>
            <div class="panel-metric">
                <div class="panel-metric-value">{len(STATION_GUIDES)}</div>
                <div class="panel-metric-label">导览站点</div>
            </div>
        </div>
        <div style='font-size: 13px; color: #888; margin-bottom: 10px;'>
            常用讲解入口：
        </div>
        {make_action_link('▶ 遵义会议最大的意义是什么？', '遵义会议最大的意义是什么？', css_class='right-question')}
        {make_action_link('▶ 飞夺泸定桥到底有多惨烈？', '飞夺泸定桥到底有多惨烈？', css_class='right-question')}
        {make_action_link('▶ 红军过草地时都吃些什么？', '红军过草地时都吃些什么？', css_class='right-question')}
        <div class="panel-hint">点击问题自动提问，或用底部输入框自由追问。</div>
    </div>
    """
    st.markdown(panel_html, unsafe_allow_html=True)


# --- 9. 文本提问框 ---
chat_placeholder = "向讲解员追问下一站或某一段历史..." if st.session_state.guide_mode else "向老红军请教那段历史..."
if prompt := st.chat_input(chat_placeholder):
    if st.session_state.guide_mode and not prompt.startswith("讲解员模式"):
        prompt = "讲解员模式下，请用展馆导览口吻回答：" + prompt
    handle_response(prompt)
