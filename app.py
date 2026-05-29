from __future__ import annotations

import textwrap
import base64
import html
import os
from urllib.parse import quote

import streamlit as st
from streamlit_mic_recorder import mic_recorder

from brain import get_veteran_response, KNOWLEDGE_BASE
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


def make_action_link(label: str, query: str | None = None, guide: bool | None = None, css_class: str = "") -> str:
    params = []
    if query:
        params.append(f"q={quote(query)}")
    if guide is not None:
        params.append(f"guide={'1' if guide else '0'}")
    href = "?" + "&".join(params) if params else "#"
    return f'<a class="{css_class}" href="{href}" target="_self">{html.escape(label)}</a>'


# --- 4. 核心交互函数 ---
def handle_response(user_query: str):
    loading_slot = st.empty()
    loading_slot.markdown(
        "<div class='retrieval-loading'>正在检索长征档案、比对史料证据与关联文物...</div>",
        unsafe_allow_html=True,
    )
    try:
        full_response = get_veteran_response(user_query)
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

if params.get("guide") == "1" and not st.session_state.get("_handled_query_params"):
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
    position: fixed; top: 38%; left: 50%; transform: translate(-50%, -50%);
    text-align: center; z-index: 1; width: 100%;
}}

.answer-title-only {{
    top: 13% !important;
}}

.answer-title-only .hero-title {{
    font-size: 34px !important;
    margin-bottom: 0 !important;
}}

.hero-title {{
    color: #d4af37; font-family: "KaiTi", "STKaiti", serif; font-size: 32px;
    margin-bottom: 25px; letter-spacing: 6px;
    text-shadow: 0px 4px 15px rgba(212, 175, 55, 0.4);
}}
    .veteran-img {{
        width: 360px;
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
    top: 20%;
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
    top: 56%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: min(82vw, 1320px);
    height: 52vh;
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
        position: fixed !important; bottom: 35px !important; left: 55% !important; transform: translateX(-50%) !important;
        width: 60% !important; min-width: 400px !important; z-index: 10000 !important; padding: 6px 20px !important;
    }}
    [data-testid="stChatInput"] textarea {{
        color: #ffffff !important; background-color: transparent !important; font-size: 16px !important; line-height: 1.6 !important; caret-color: #d4af37 !important;
    }}
    [data-testid="stChatInput"] textarea::placeholder {{ color: rgba(255,255,255,0.3) !important; font-style: italic !important; }}
    [data-testid="stChatInput"] button {{ background: rgba(212, 175, 55, 0.05) !important; border-radius: 50% !important; transition: all 0.3s ease !important; }}
    [data-testid="stChatInput"] button:hover {{ background: rgba(212, 175, 55, 0.2) !important; transform: scale(1.1) !important; }}
    [data-testid="stChatInput"] button svg {{ fill: #d4af37 !important; }}

    iframe {{
        position: fixed !important; bottom: 38px !important; left: 240px !important; height: 50px !important; width: 130px !important; z-index: 99999 !important;
        filter: invert(0.95) hue-rotate(180deg) brightness(1.1) drop-shadow(0 5px 15px rgba(212,175,55,0.15)) !important;
        border-radius: 25px !important;
    }}
    .stAudio {{ display: none !important; }}
    ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
    ::-webkit-scrollbar-track {{ background: transparent; }}
    ::-webkit-scrollbar-thumb {{ background: rgba(212, 175, 55, 0.3); border-radius: 10px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: rgba(212, 175, 55, 0.6); }}

    .left-timeline {{
        position: fixed; top: 50%; left: 8%; transform: translateY(-50%); width: 250px;
        color: #d4af37; font-family: "KaiTi", "STKaiti", serif; z-index: 10;
        border-left: 2px solid rgba(212,175,55,0.4); padding-left: 20px;
    }}
    .timeline-item {{ display:block; margin-bottom: 22px; position: relative; cursor: pointer; text-decoration: none !important; color: inherit !important; }}
    .timeline-item::before {{
        content: ''; position: absolute; left: -26px; top: 6px; width: 10px; height: 10px; background: #8b0000;
        border: 2px solid #d4af37; border-radius: 50%; box-shadow: 0 0 10px rgba(212,175,55,0.8); transition: all 0.3s ease;
    }}
    .timeline-date {{ font-size: 13px; color: rgba(255,255,255,0.5); margin-bottom: 2px; transition: all 0.3s ease; }}
    .timeline-event {{ font-size: 17px; font-weight: bold; letter-spacing: 2px; text-shadow: 2px 2px 5px #000; transition: all 0.3s ease; }}
    .timeline-item:hover::before {{ background: #d4af37; box-shadow: 0 0 15px #d4af37; }}
    .timeline-item:hover .timeline-date {{ color: rgba(212,175,55,0.8); }}
    .timeline-item:hover .timeline-event {{ color: #fff; transform: translateX(5px); }}

    .right-info-panel {{
        position: fixed; top: 50%; right: 9%; transform: translateY(-50%); width: 340px; z-index: 10;
        background: rgba(30, 5, 5, 0.6); padding: 22px 24px; border-radius: 12px;
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
        st.markdown(f"<div class='subtitle-overlay'>{safe_text(llm_data.get('voice_script', ''))}</div>", unsafe_allow_html=True)

        citations = res.get("citations", [])
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


        snippets = res.get("evidence_snippets", [])
        if snippets:
            cards = []
            for idx, item in enumerate(snippets[:4], start=1):
                source_raw = item.get("source", "未知资料")
                source = safe_text(clean_source_name(source_raw))

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
            for follow_up in follow_ups[:2]:
                label = "继续下一站" if str(follow_up).startswith("讲解员模式：站点讲解") else "追问：" + str(follow_up)
                links.append(make_action_link(label, str(follow_up), css_class="followup-link"))
            followup_html = "<div class='archive-header'>💬 推荐追问</div><div class='followup-row'>" + "".join(links) + "</div><br>"

        detail_html = safe_text(llm_data.get('detailed_text', ''))
        archive_html = (
            f'<div class="archive-panel">'
            f'<div class="archive-header">📚 老红军的详细回忆档案</div>'
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
        <div style='color: #d4af37; font-size: 18px; font-weight: bold; margin-bottom: 15px; border-bottom: 1px solid rgba(212,175,55,0.3); padding-bottom: 8px; text-align: center;'>
            📚 绝密史料档案馆
        </div>
        <div style='font-size: 13px; color: #aaa; text-align: center; margin-bottom: 15px;'>
            系统已挂载 <span style='color: #d4af37; font-weight: bold; font-size: 16px;'>{len(KNOWLEDGE_BASE) or 1397}</span> 份核心档案
        </div>
        <div style='font-size: 13px; color: #888; margin-bottom: 10px;'>
            您可以点击以下问题向老红军提问：
        </div>
        {make_action_link('▶ 遵义会议最大的意义是什么？', '遵义会议最大的意义是什么？', css_class='right-question')}
        {make_action_link('▶ 飞夺泸定桥到底有多惨烈？', '飞夺泸定桥到底有多惨烈？', css_class='right-question')}
        {make_action_link('▶ 红军过草地时都吃些什么？', '红军过草地时都吃些什么？', css_class='right-question')}
        <div style='margin-top: 15px; font-size: 12px; color: #888; font-style: italic; text-align: center;'>(点击上方问题自动提问)</div>
    </div>
    """
    st.markdown(panel_html, unsafe_allow_html=True)


# --- 9. 文本提问框 ---
chat_placeholder = "向讲解员追问下一站或某一段历史..." if st.session_state.guide_mode else "向老红军请教那段历史..."
if prompt := st.chat_input(chat_placeholder):
    if st.session_state.guide_mode and not prompt.startswith("讲解员模式"):
        prompt = "讲解员模式下，请用展馆导览口吻回答：" + prompt
    handle_response(prompt)
