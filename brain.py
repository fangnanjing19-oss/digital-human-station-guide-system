from __future__ import annotations

import html
import json
import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from openai import OpenAI

from config import KNOWLEDGE_BASE_PATH, llm_config
from guide_content import build_station_response, next_station_prompt


@lru_cache(maxsize=1)
def load_kb() -> List[Dict[str, Any]]:
    """加载知识库。知识库缺失时返回空列表，避免展示现场直接崩溃。"""
    path = Path(KNOWLEDGE_BASE_PATH)
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


KNOWLEDGE_BASE = load_kb()


_STOPWORDS = set("的是了和与及在对为以把被而或并就都很也但从到中上下一些一个这个那个什么怎么为什么多少哪些时候")


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _extract_terms(query: str) -> List[str]:
    """轻量中文短语提取：适合不用额外安装 jieba 的演示项目。"""
    q = _normalize_text(query)
    terms: List[str] = []

    # 优先保留历史专名、数字、月份等强信号。
    known_phrases = [
        "遵义会议", "四渡赤水", "飞夺泸定桥", "泸定桥", "血战湘江", "湘江战役", "过草地", "夹金山", "吴起镇",
        "瑞金", "长征", "红军", "中央红军", "毛泽东", "周恩来", "朱德", "博古", "李德",
        "金沙江", "大渡河", "腊子口", "会宁", "战略转移", "生死攸关", "转折点",
    ]
    for phrase in known_phrases:
        if phrase in q:
            terms.append(phrase)

    # 2~5 字滑窗，兼顾“草地吃什么”“会议意义”等短问题。
    for n in (5, 4, 3, 2):
        for i in range(max(0, len(q) - n + 1)):
            token = q[i : i + n]
            if any(ch in _STOPWORDS for ch in token) and n <= 2:
                continue
            if token and token not in _STOPWORDS:
                terms.append(token)

    # 去重并保序。
    seen = set()
    result = []
    for term in terms:
        if term not in seen:
            seen.add(term)
            result.append(term)
    return result[:40]


def retrieve_relevant_chunks(user_query: str, top_k: int | None = None) -> List[Dict[str, Any]]:
    """中文轻量 RAG 检索：关键词命中 + 词频加权 + 来源页码保留。"""
    if not KNOWLEDGE_BASE:
        return []

    top_k = top_k or llm_config.max_context_chunks
    terms = _extract_terms(user_query)
    if not terms:
        return []

    scored = []
    for idx, chunk in enumerate(KNOWLEDGE_BASE):
        content = chunk.get("content", "") or ""
        compact = _normalize_text(content)
        source = chunk.get("source", "未知资料")
        page = chunk.get("page", "?")
        score = 0.0
        hits = []
        for term in terms:
            count = compact.count(term)
            if count:
                # 越长的词越有信息量；标题、来源命中额外加权。
                weight = 1 + math.log1p(len(term))
                if term in str(source):
                    weight += 1.2
                score += count * weight
                hits.append(term)
        if score > 0:
            scored.append({
                "index": idx,
                "score": round(score, 3),
                "hits": hits[:8],
                "source": source,
                "page": page,
                "content": content,
            })

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def _build_context(chunks: List[Dict[str, Any]]) -> str:
    if not chunks:
        return "暂无直接匹配的史料记录。请谨慎回答，并明确说明没有检索到直接证据。"
    lines = []
    for i, c in enumerate(chunks, start=1):
        content = (c.get("content", "") or "")[:900]
        lines.append(f"【证据{i}｜《{c.get('source', '未知资料')}》第{c.get('page', '?')}页｜命中：{', '.join(c.get('hits', []))}】\n{content}")
    return "\n\n".join(lines)


def _extract_tag(tag: str, text: str) -> str:
    pattern = rf"\[{tag}\](.*?)\[/{tag}\]"
    match = re.search(pattern, text or "", re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _safe_default_response(message: str, detail: str, context: str, citations: List[Dict[str, Any]], evidence_snippets: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    return {
        "llm_data": {
            "voice_script": message,
            "detailed_text": detail,
            "follow_ups": [],
        },
        "raw_evidence": context,
        "citations": citations,
        "evidence_snippets": evidence_snippets or [],
    }


def get_veteran_response(user_query: str) -> Dict[str, Any]:
    guide_mode = "讲解员模式" in user_query or "导览" in user_query or "站点讲解" in user_query
    station = None
    station_index = 0
    retrieval_query = user_query
    if guide_mode:
        station, station_index = build_station_response(user_query)
        retrieval_query = station.search_query
    chunks = retrieve_relevant_chunks(retrieval_query, top_k=10 if guide_mode else None)
    context = _build_context(chunks)
    citations = [
        {
            "source": c.get("source", "未知资料"),
            "page": c.get("page", "?"),
            "score": c.get("score", 0),
            "hits": c.get("hits", []),
        }
        for c in chunks
    ]
    evidence_snippets = [
        {
            "source": c.get("source", "未知资料"),
            "page": c.get("page", "?"),
            "score": c.get("score", 0),
            "hits": c.get("hits", []),
            "content": (c.get("content", "") or "")[:1200],
        }
        for c in chunks[:4]
    ]

    if guide_mode and station is not None:
        evidence_note = ""
        if citations:
            c0 = citations[0]
            evidence_note = f"\n\n【史料提示】本馆知识库已为本讲解命中相关档案，例如《{c0.get('source', '未知资料')}》第 {c0.get('page', '?')} 页。你可以展开下方“原始史料证据”查看具体片段。"
        else:
            evidence_note = "\n\n【史料提示】当前知识库没有检索到足够直接的站点片段，本段采用预设展线讲稿结构；后续可继续补充对应原始 PDF 资料。"

        return {
            "llm_data": {
                "voice_script": station.voice,
                "detailed_text": station.detail + evidence_note,
                "follow_ups": [next_station_prompt(station_index), station.deep_followup],
            },
            "raw_evidence": context,
            "citations": citations,
            "evidence_snippets": evidence_snippets,
            "guide_station": {
                "title": station.title,
                "date": station.date,
                "index": station_index,
            },
        }

    if not llm_config.api_key:
        return _safe_default_response(
            "孩子，系统还没有配置 API Key，老红军暂时没法开口。",
            "请在 .streamlit/secrets.toml 中配置 MOONSHOT_API_KEY。配置完成后重新运行 streamlit run app.py。",
            context,
            citations,
            evidence_snippets,
        )

    mode_requirements = """
# Mode: 展馆讲解员模式
用户正在使用讲解员模式。你的输出必须像纪念馆现场讲解词，不能像百科摘要。

【硬性结构】
- [VOICE] 只写 1 句“当前站点导语”，不超过 45 字，避免字幕遮挡画面。
- [DETAIL] 写 900—1200 字，分成 6—8 个自然段。
- 必须按展线顺序讲：瑞金集结出发 → 血战湘江 → 遵义会议 → 四渡赤水 → 飞夺泸定桥 → 翻越夹金山 → 跨越松潘草地 → 吴起镇大会师。
- 每个重要节点至少说明三件事：当时处境、发生了什么、为什么影响后续行军。
- 至少引用 3 处 Context 中的证据，格式用“据档案记载……”或“史料中提到……”，不要把引用来源写成很长的文件名。
- 结尾必须收束到“长征为什么不是简单行军，而是战略转移、组织重塑和精神锻造”。

【写作风格】
- 用“各位同志/观众朋友，现在我们来到……”这样的展厅口吻。
- 要有现场感：道路、江河、雪山、草地、战斗压力、队伍抉择。
- 不要空泛堆词，禁止连续使用“伟大、壮丽、史诗、精神丰碑”这类词而不解释。
- 不要编造具体伤亡数字、具体对话、天气细节；没有证据就用“档案未直接记载”。
""" if guide_mode else """
# Mode: 问答模式
用户正在单点提问。请直接回答问题，避免空泛抒情；详尽档案说明控制在 300—600 字。
"""

    system_prompt = f"""
# Role
你不是普通聊天机器人。你是一位“长征老红军数字讲解员”，既要有亲历者的沉稳口吻，也要有展馆讲解员的结构化表达。

# Context
以下史料是你回答的主要依据。请优先使用这些材料，不要编造材料外的具体数字、地点、人名。
{context}

# Global Requirements
1. 语气沉稳、克制、有历史重量，可以称呼提问者为“同志”，但不要过度表演，不要每段都喊口号。
2. 回答必须落到“具体事件 + 具体原因 + 具体影响”，不能只讲价值判断。
3. 详细档案必须尽量引用 Context 中的时间、地点、人名、数字、事件细节。
4. 如果 Context 没有直接证据，要明确说“档案里没有直接记载”，再谨慎补充通识性说明。
5. 避免空话套话，例如不要只说“伟大转折”“精神丰碑”，必须解释原因和证据。
6. [VOICE] 是页面上方字幕，必须短；[DETAIL] 是档案面板，可写完整。
{mode_requirements}

# Output Format
你必须且只能按照以下标签输出：

[VOICE]
一句话核心回答。问答模式不超过80字；讲解员模式不超过60字。
[/VOICE]

[DETAIL]
详尽档案说明。分段清楚，至少引用2处 Context 中的具体细节。
[/DETAIL]

[FOLLOWUP1]
基于本次答案继续追问的专业问题。
[/FOLLOWUP1]

[FOLLOWUP2]
另一个基于史料的专业追问。
[/FOLLOWUP2]
"""

    try:
        client = OpenAI(api_key=llm_config.api_key, base_url=llm_config.base_url)
        response = client.chat.completions.create(
            model=llm_config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query},
            ],
            temperature=llm_config.temperature,
            stream=False,
        )
        response_text = response.choices[0].message.content.strip()

        voice_script = _extract_tag("VOICE", response_text)
        detailed_text = _extract_tag("DETAIL", response_text)
        followup_1 = _extract_tag("FOLLOWUP1", response_text)
        followup_2 = _extract_tag("FOLLOWUP2", response_text)

        if not voice_script and not detailed_text:
            voice_script = "孩子，这段往事要从档案里慢慢讲起。"
            detailed_text = response_text

        follow_ups = [q for q in [followup_1, followup_2] if q]
        return {
            "llm_data": {
                "voice_script": voice_script,
                "detailed_text": detailed_text,
                "follow_ups": follow_ups,
            },
            "raw_evidence": context,
            "citations": citations,
            "evidence_snippets": evidence_snippets,
        }
    except Exception as e:
        return _safe_default_response(
            "孩子，通讯设备出了点故障，老红军暂时听不清你的话。",
            "系统通讯暂时繁忙，可能是模型服务正在过载。请稍后重新提问，老红军会继续为你讲述这段历史。",
            context,
            citations,
            evidence_snippets,
        )
