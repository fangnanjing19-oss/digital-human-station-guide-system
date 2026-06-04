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

RELIC_CATALOG_PATH = Path("relic_catalog.json")


@lru_cache(maxsize=1)
def load_relic_catalog() -> List[Dict[str, Any]]:
    """加载长征文物目录。没有文件时返回空列表，避免程序崩溃。"""
    if not RELIC_CATALOG_PATH.exists():
        return []

    try:
        with RELIC_CATALOG_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def match_relics(question: str, answer_text: str, top_k: int = 2) -> List[Dict[str, Any]]:
    """更保守的长征文物匹配：优先看用户问题，避免因为回答正文太长而误匹配。"""
    catalog = load_relic_catalog()
    if not catalog:
        return []

    q = str(question or "")
    a = str(answer_text or "")

    # 这些词太泛，单独命中不能作为展示文物的理由
    weak_terms = {
        "红军", "长征", "战斗", "战场", "工具", "文物", "资料", "根据地",
        "渡江", "过河", "行军", "群众", "宣传", "布告", "手稿", "会师",
        "抗日", "北上", "缴获", "雪山", "草地"
    }

    # 用户问得比较泛时，做少量人工增强，避免“渡江工具”乱匹配
    special_boost = {}
    if any(x in q for x in ["渡江", "过河", "船只", "竹筏", "棕绳", "水马", "乌江"]):
        special_boost["relic_009"] = 4

    if any(x in q for x in ["泸定桥", "铁索桥", "铁索链", "飞夺泸定"]):
        special_boost["relic_017"] = 5

    if any(x in q for x in ["遵义", "遵义会议", "总政治部布告"]):
        special_boost["relic_010"] = 4

    if any(x in q for x in ["湘江", "血战湘江", "抢渡湘江"]):
        special_boost["relic_006"] = 4

    if any(x in q for x in ["赤水", "四渡赤水", "一渡赤水"]):
        special_boost["relic_011"] = 4

    if any(x in q for x in ["草地", "过草地", "松潘草地", "日记"]):
        special_boost["relic_028"] = 4

    if any(x in q for x in ["雪山", "夹金山", "防滑", "钉鞋"]):
        special_boost["relic_025"] = 4

    matches = []

    for relic in catalog:
        rid = relic.get("id", "")
        title = str(relic.get("title", ""))
        theme = str(relic.get("theme", ""))
        keywords = [str(k).strip() for k in relic.get("keywords", []) if str(k).strip()]

        score = 0.0
        strong_hit = False

        # 人工增强优先
        if rid in special_boost:
            score += special_boost[rid]
            strong_hit = True

        # 标题/主题在问题中出现，强相关
        if title and title in q:
            score += 6
            strong_hit = True

        if theme and theme in q:
            score += 3
            strong_hit = True

        # 关键词：主要匹配用户问题
        for kw in keywords:
            if kw in q:
                if kw in weak_terms:
                    score += 0.25
                else:
                    score += 1.5
                    strong_hit = True

        # 回答文本只做弱参考，不能单独决定展示
        for kw in keywords:
            if kw not in weak_terms and kw in a:
                score += 0.25

        # 必须有强命中，或者人工增强；否则不展示
        if strong_hit and score >= 1.5:
            item = dict(relic)
            item["match_score"] = score
            matches.append(item)

    matches.sort(key=lambda x: x.get("match_score", 0), reverse=True)
    return matches[:top_k]

KNOWLEDGE_BASE = load_kb()


_STOPWORDS = set("的是了和与及在对为以把被而或并就都很也但从到中上下一些一个这个那个什么怎么为什么多少哪些时候")


_BROAD_TERMS = {
    "红军", "长征", "中央红军", "战役", "战斗", "问题", "原因", "影响", "意义",
}


_TOPIC_PROFILES: List[Dict[str, Any]] = [
    {
        "name": "topic_ruijin_departure",
        "scene": "瑞金集结出发",
        "triggers": ["瑞金", "集结出发", "长征起点", "中央苏区", "战略转移"],
        "retrieval_query": "瑞金 中央苏区 集结出发 战略转移 突围 西征 长征开始",
        "required_terms": ["瑞金", "中央苏区", "战略转移", "西征"],
        "boost_terms": ["突围", "集结", "出发", "中央革命根据地", "第五次反围剿"],
        "forbidden_terms": ["湘江", "遵义", "赤水", "泸定桥", "夹金山", "草地", "吴起镇"],
    },
    {
        "name": "topic_xiangjiang",
        "scene": "湘江战役/血战湘江",
        "triggers": ["湘江", "血战湘江", "湘江战役", "抢渡湘江", "第四道封锁线", "湘桂封锁线"],
        "retrieval_query": "湘江战役 血战湘江 抢渡湘江 第四道封锁线 湘桂封锁线 界首 光华铺 损失 伤亡",
        "required_terms": ["湘江", "湘江战役", "血战湘江", "抢渡湘江"],
        "boost_terms": ["第四道封锁线", "湘桂封锁线", "界首", "光华铺", "损失", "伤亡", "惨烈"],
        "forbidden_terms": ["直罗", "直落", "泸定桥", "草地", "夹金山", "吴起镇", "群众家", "银元"],
    },
    {
        "name": "topic_zunyi",
        "scene": "遵义会议",
        "triggers": ["遵义", "遵义会议", "生死攸关", "转折点", "军事路线"],
        "retrieval_query": "遵义会议 遵义 政治局 扩大会议 军事路线 转折 毛泽东 博古 李德",
        "required_terms": ["遵义", "遵义会议", "政治局", "军事路线"],
        "boost_terms": ["转折", "毛泽东", "博古", "李德", "领导", "生死攸关"],
        "forbidden_terms": ["湘江战役", "泸定桥", "草地", "夹金山", "吴起镇", "群众家", "银元"],
    },
    {
        "name": "topic_chishui",
        "scene": "四渡赤水",
        "triggers": ["四渡赤水", "赤水", "赤水河", "运动战", "出奇兵"],
        "retrieval_query": "四渡赤水 赤水河 运动战 佯动 机动 遵义后 毛泽东",
        "required_terms": ["四渡赤水", "赤水", "赤水河"],
        "boost_terms": ["运动战", "机动", "佯动", "调动敌人", "遵义后"],
        "forbidden_terms": ["湘江", "泸定桥", "草地", "夹金山", "吴起镇", "群众家", "银元"],
    },
    {
        "name": "topic_luding",
        "scene": "飞夺泸定桥/大渡河",
        "triggers": ["飞夺泸定桥", "泸定桥", "大渡河", "铁索桥", "安顺场", "强渡大渡河"],
        "retrieval_query": "飞夺泸定桥 泸定桥 大渡河 安顺场 铁索桥 渡河点 夺取 战略胜利",
        "required_terms": ["飞夺泸定桥", "泸定桥", "大渡河", "安顺场"],
        "boost_terms": ["铁索桥", "渡河点", "夺取", "战略胜利", "夹河而上"],
        "forbidden_terms": ["湘江战役", "草地", "夹金山", "吴起镇", "群众家", "银元"],
    },
    {
        "name": "topic_snow_mountain",
        "scene": "翻越夹金山/雪山",
        "triggers": ["夹金山", "甲金山", "雪山", "翻雪山", "缺氧", "高寒"],
        "retrieval_query": "夹金山 甲金山 雪山 高寒 空气稀薄 饥寒 翻越 达维",
        "required_terms": ["夹金山", "甲金山", "雪山"],
        "boost_terms": ["空气稀薄", "高寒", "达维", "晕倒", "风雨", "死尸"],
        "forbidden_terms": ["湘江", "泸定桥", "草地", "吴起镇", "群众家", "银元"],
    },
    {
        "name": "grassland_hardship",
        "scene": "跨越松潘草地",
        "triggers": ["过草地", "松潘草地", "草地", "毛儿盖", "班佑"],
        "retrieval_query": (
            "过草地 松潘草地 毛儿盖 班佑 阿坝 包座 草地行军 "
            "粮食 缺粮 筹粮 干粮 露营 夜雨 无树 泥沼 向导 肿脚 冻坏 牺牲"
        ),
        "required_terms": ["过草地", "草地", "毛儿盖", "班佑", "阿坝", "包座"],
        "boost_terms": ["粮食", "缺粮", "筹粮", "干粮", "露营", "夜雨", "无树", "泥沼", "向导", "肿脚", "冻坏"],
        "forbidden_terms": ["群众家", "全村", "银元", "神龛", "苗家", "廖洞", "黄古屯", "石阡", "湘江", "泸定桥"],
    },
    {
        "name": "topic_wuqizhen",
        "scene": "吴起镇大会师",
        "triggers": ["吴起镇", "吴起", "大会师", "陕北", "会师"],
        "retrieval_query": "吴起镇 吴起 陕北 会师 中央红军 长征胜利 到达陕北",
        "required_terms": ["吴起镇", "吴起", "陕北", "会师"],
        "boost_terms": ["到达", "胜利", "中央红军", "大会师"],
        "forbidden_terms": ["湘江", "遵义", "赤水", "泸定桥", "草地", "群众家", "银元"],
    },
]


def _topic_profile_from_query(query: str) -> Dict[str, Any] | None:
    q = _normalize_text(query)
    for profile in _TOPIC_PROFILES:
        if any(trigger in q for trigger in profile["triggers"]):
            return profile
    return None


def _intent_from_profile(profile: Dict[str, Any], user_query: str) -> Dict[str, Any]:
    return {
        "name": profile["name"],
        "scene": profile["scene"],
        "canonical_answer": f"必须限定在“{profile['scene']}”这一历史场景内作答。",
        "retrieval_query": profile["retrieval_query"],
        "required_terms": profile["required_terms"],
        "boost_terms": profile.get("boost_terms", []),
        "forbidden_terms": profile.get("forbidden_terms", []),
        "strict_required": True,
        "instruction": (
            f"用户问题已归入“{profile['scene']}”场景。回答只能使用与该场景直接相关的 Context。"
            "证据真实但地点、阶段、战役不符时也不可引用；如果直接证据不足，必须明说不足。"
        ),
    }


def _detect_query_intent(user_query: str) -> Dict[str, Any] | None:
    """把判断型问题先锚定到可靠史实方向，避免泛词检索把答案带偏。"""
    q = _normalize_text(user_query)
    if not q:
        return None

    battle_scope = any(x in q for x in ["战役", "战斗", "一仗", "哪仗", "哪一仗", "长征"])
    costly_words = ["最惨烈", "最惨重", "最惨", "伤亡最大", "损失最大", "代价最大", "牺牲最大", "损失最重", "伤亡最重"]
    dangerous_words = ["最惊险", "最险", "最危急", "最危险", "最紧张"]

    if battle_scope and any(x in q for x in costly_words):
        return {
            "name": "long_march_bloodiest_battle",
            "scene": "湘江战役/血战湘江",
            "canonical_answer": "湘江战役（血战湘江）",
            "retrieval_query": (
                "湘江战役 血战湘江 湘江 第四道封锁线 湘桂封锁线 "
                "敌人阻止 红军渡过湘江 损失 牺牲 1934年11月 1934年12月"
            ),
            "required_terms": ["湘江战役", "血战湘江", "湘江"],
            "boost_terms": ["第四道封锁线", "湘桂封锁线", "损失", "伤亡", "惨烈", "惨重"],
            "forbidden_terms": ["直罗", "直落", "泸定桥", "草地", "群众家", "银元"],
            "strict_required": True,
            "instruction": (
                "用户问的是长征中牺牲代价、损失程度或惨烈程度最高的战役。"
                "回答必须以“湘江战役/血战湘江”为核心；如果 Context 没有直接写“最惨烈”，"
                "也要说明这是按伤亡代价和生死危机维度作出的判断，不能改答直罗镇战役、遵义战斗、四渡赤水或泸定桥。"
            ),
        }

    if battle_scope and any(x in q for x in dangerous_words):
        return {
            "name": "long_march_most_dangerous_battle",
            "scene": "长征惊险事件判断",
            "canonical_answer": "需先说明评价标准：按惨烈代价偏向湘江战役，按夺取险要通道常讲飞夺泸定桥/强渡大渡河。",
            "retrieval_query": (
                "湘江战役 血战湘江 湘江 飞夺泸定桥 泸定桥 大渡河 "
                "铁索桥 封锁线 危急 生死关口 长征"
            ),
            "required_terms": ["湘江", "泸定桥", "大渡河"],
            "boost_terms": ["惊险", "危急", "伤亡", "渡河点", "铁索桥", "战略危机"],
            "forbidden_terms": ["直罗", "直落", "群众家", "银元"],
            "strict_required": False,
            "instruction": (
                "用户问的是“最惊险/最危急”，这不是单一史料标签。必须先交代评价标准："
                "若按伤亡惨烈和战略危机，应重点讲湘江战役；若按险要通道和突击场面，常指飞夺泸定桥/大渡河。"
                "不要把无关战役武断说成唯一答案。"
            ),
        }

    profile = _topic_profile_from_query(user_query)
    if profile:
        return _intent_from_profile(profile, user_query)

    return None


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _extract_terms(query: str) -> List[str]:
    """轻量中文短语提取：适合不用额外安装 jieba 的演示项目。"""
    q = _normalize_text(query)
    terms: List[str] = []

    # 优先保留历史专名、数字、月份等强信号。
    known_phrases = [
        "遵义会议", "四渡赤水", "飞夺泸定桥", "泸定桥", "血战湘江", "湘江战役", "湘江", "过草地", "夹金山", "吴起镇",
        "瑞金", "长征", "红军", "中央红军", "毛泽东", "周恩来", "朱德", "博古", "李德",
        "金沙江", "大渡河", "腊子口", "会宁", "战略转移", "生死攸关", "转折点",
        "第四道封锁线", "湘桂封锁线", "突破封锁线", "抢渡湘江", "光华铺", "界首",
        "惨烈", "惨重", "伤亡", "损失", "牺牲", "代价", "惊险", "危急",
        "松潘草地", "毛儿盖", "班佑", "阿坝", "包座", "筹粮", "干粮", "缺粮",
        "露营", "夜雨", "无树", "泥沼", "向导", "肿脚", "冻坏",
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
    return result[:48]


def retrieve_relevant_chunks(
    user_query: str,
    top_k: int | None = None,
    intent: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    """中文轻量 RAG 检索：问题意图锚定 + 关键词命中 + 词频加权 + 来源页码保留。"""
    if not KNOWLEDGE_BASE:
        return []

    top_k = top_k or llm_config.max_context_chunks
    terms = _extract_terms(user_query)
    if intent:
        for term in intent.get("required_terms", []):
            if term and term not in terms:
                terms.insert(0, term)
    if not terms:
        return []

    required_terms = [str(t) for t in (intent or {}).get("required_terms", []) if str(t)]
    boost_terms = [str(t) for t in (intent or {}).get("boost_terms", []) if str(t)]
    forbidden_terms = [str(t) for t in (intent or {}).get("forbidden_terms", []) if str(t)]
    strict_required = bool((intent or {}).get("strict_required"))
    scored = []
    for idx, chunk in enumerate(KNOWLEDGE_BASE):
        content = chunk.get("content", "") or ""
        compact = _normalize_text(content)
        source = chunk.get("source", "未知资料")
        page = chunk.get("page", "?")
        source_compact = _normalize_text(str(source))
        required_hit = any(term in compact or term in source_compact for term in required_terms)
        if strict_required and required_terms and not required_hit:
            continue
        forbidden_hit = any(term in compact or term in source_compact for term in forbidden_terms)

        score = 0.0
        hits = []
        for term in terms:
            count = compact.count(term)
            source_count = source_compact.count(term)
            if count:
                # 越长的词越有信息量；标题、来源命中额外加权。
                weight = 1 + math.log1p(len(term))
                if term in _BROAD_TERMS:
                    weight *= 0.18
                if any(ch.isdigit() for ch in term):
                    weight *= 0.15
                if required_terms and term in required_terms:
                    weight += 5
                if term in str(source):
                    weight += 1.2
                score += count * weight
                hits.append(term)
            elif source_count:
                weight = 1.5 + math.log1p(len(term))
                if term in _BROAD_TERMS:
                    weight *= 0.18
                if any(ch.isdigit() for ch in term):
                    weight *= 0.15
                score += source_count * weight
                hits.append(term)
        if required_hit:
            score += 18
        for term in boost_terms:
            if term in compact or term in source_compact:
                score += 12 + math.log1p(len(term))

        if intent and intent.get("name") == "long_march_bloodiest_battle":
            if "湘江战役" in compact:
                score += 42
            if "血战湘江" in compact:
                score += 42
            if any(x in compact for x in ["战况非常惨烈", "伤亡惨重", "损失是比较严重", "严重损失"]):
                score += 70
            if any(x in compact for x in ["损失", "伤亡", "牺牲", "惨烈", "惨重"]):
                score += 24

        if intent and intent.get("name") == "grassland_hardship":
            if any(x in compact for x in ["毛儿盖", "班佑", "阿坝", "包座", "松潘草地", "草地"]):
                score += 40
            if any(x in compact for x in ["粮食", "缺粮", "筹粮", "干粮", "各部粮", "电台已绝粮"]):
                score += 36
            if any(x in compact for x in ["露营", "夜雨", "无丛树", "无森林", "河水涨", "不能徒涉", "无响导", "冻坏", "肿脚"]):
                score += 34
            if any(x in compact for x in ["群众家", "全村", "银元", "神龛", "苗家", "廖洞", "黄古屯", "石阡"]):
                score *= 0.04

        if forbidden_hit:
            score *= 0.08

        toc_like = (
            compact.count("⋯") >= 4
            or compact.count("/") >= 8
            or (compact.count("关于") >= 6 and compact.count("电") >= 4)
        )
        if toc_like:
            score *= 0.28
        if any(x in compact for x in ["目录", "出版说明"]) and len(compact) < 900:
            score *= 0.55
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


def _build_factual_guard(intent: Dict[str, Any] | None, chunks: List[Dict[str, Any]]) -> str:
    if not intent:
        return ""

    required_terms = [str(t) for t in intent.get("required_terms", []) if str(t)]
    forbidden_terms = [str(t) for t in intent.get("forbidden_terms", []) if str(t)]
    evidence_text = _normalize_text("\n".join(c.get("content", "") or "" for c in chunks))
    direct_hits = [term for term in required_terms if term in evidence_text]
    forbidden_hits = [term for term in forbidden_terms if term in evidence_text]
    direct_status = "、".join(direct_hits) if direct_hits else "未在已选 Context 中直接命中核心词"
    forbidden_status = "、".join(forbidden_hits) if forbidden_hits else "未发现明显跨场景风险词"

    return f"""
# Factual Guard
当前问题已识别为：{intent.get('name', '历史事实校准问题')}
限定场景：{intent.get('scene', '以用户问题和 Context 为准')}
史实锚点：{intent.get('canonical_answer', '以 Context 为准')}
证据命中状态：{direct_status}
跨场景风险：{forbidden_status}
回答纪律：
- {intent.get('instruction', '必须优先依据 Context，不能脱离证据扩写。')}
- 如果 Context 只提供了过程证据、没有直接给出“最……”的定性，请明确说“按伤亡代价/战略危机等维度判断”，不要伪装成档案原文直接写了这个结论。
- 不得把没有在 Context 中形成强证据链的事件说成答案；不得为了显得有依据而引用不相关页码。
- 严禁跨场景拼接：某一地点、阶段、民族地区或战役的材料，不能挪用到另一个历史场景中。
"""


def _extract_tag(tag: str, text: str) -> str:
    pattern = rf"\[{tag}\](.*?)\[/{tag}\]"
    match = re.search(pattern, text or "", re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _safe_default_response(message: str, detail: str, context: str, citations: List[Dict[str, Any]], evidence_snippets: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    return {
        "llm_data": {
            "voice_script": message,
            "detailed_text": detail,
            "follow_ups": _build_discovery_followups("", message, detail, [], [], citations, None),
        },
        "raw_evidence": context,
        "citations": citations,
        "evidence_snippets": evidence_snippets or [],
        "relic_matches": [],
    }


def _followup_event_label(user_query: str, answer_text: str, intent: Dict[str, Any] | None) -> str:
    combined = f"{user_query}\n{answer_text}"
    if intent and intent.get("scene"):
        return str(intent["scene"])
    event_markers = [
        ("遵义", "遵义会议"),
        ("赤水", "四渡赤水"),
        ("泸定桥", "飞夺泸定桥"),
        ("大渡河", "大渡河与泸定桥"),
        ("草地", "跨越松潘草地"),
        ("毛儿盖", "跨越松潘草地"),
        ("班佑", "跨越松潘草地"),
        ("夹金山", "翻越夹金山"),
        ("雪山", "翻越夹金山"),
        ("湘江", "湘江战役"),
        ("瑞金", "瑞金集结出发"),
        ("吴起", "吴起镇大会师"),
        ("陕北", "吴起镇大会师"),
    ]
    for marker, label in event_markers:
        if marker in combined:
            return label
    return "本段长征史实"


def _build_discovery_followups(
    user_query: str,
    voice_script: str,
    detailed_text: str,
    raw_followups: List[str],
    relic_matches: List[Dict[str, Any]],
    citations: List[Dict[str, Any]],
    intent: Dict[str, Any] | None,
) -> List[Dict[str, str]]:
    """生成稳定的三类知识发现追问；LLM 给的问题只作为补充素材。"""
    answer_text = f"{voice_script}\n{detailed_text}"
    event = _followup_event_label(user_query, answer_text, intent)

    basic_map = {
        "湘江战役/血战湘江": ["为什么说湘江战役是长征初期最沉重的生死关口？", "湘江战役和遵义会议之间有什么因果关系？"],
        "湘江战役": ["为什么说湘江战役是长征初期最沉重的生死关口？", "湘江战役和遵义会议之间有什么因果关系？"],
        "遵义会议": ["遵义会议主要解决了哪些军事路线和组织领导问题？", "为什么说遵义会议是长征中的关键转折？"],
        "四渡赤水": ["四渡赤水为什么不能简单理解为红军渡了四次河？", "四渡赤水怎样体现红军从被动转向主动？"],
        "飞夺泸定桥/大渡河": ["飞夺泸定桥为什么关系到红军能否继续北上？", "强渡大渡河和飞夺泸定桥分别解决了什么问题？"],
        "大渡河与泸定桥": ["大渡河和泸定桥为什么关系到红军能否继续北上？", "强渡大渡河和飞夺泸定桥分别解决了什么问题？"],
        "翻越夹金山/雪山": ["红军翻越夹金山时最大的困难是什么？", "为什么说雪山考验的是行军组织而不只是个人意志？"],
        "跨越松潘草地": ["红军过草地最核心的困难是什么？", "为什么说草地的危险不同于普通战斗？"],
        "瑞金集结出发": ["为什么说瑞金出发是一次被迫的战略转移？", "长征出发时红军为什么必须带着机关和辎重一起行动？"],
        "吴起镇大会师": ["吴起镇大会师为什么标志着长征打开了新局面？", "中央红军到达陕北为什么不只是走到终点？"],
    }
    detail_map = {
        "湘江战役/血战湘江": ["湘江战役中界首、光华铺等渡河点为什么如此关键？", "红三十四师等后卫部队在湘江战役中承担了什么任务？"],
        "湘江战役": ["湘江战役中界首、光华铺等渡河点为什么如此关键？", "红三十四师等后卫部队在湘江战役中承担了什么任务？"],
        "遵义会议": ["遵义会议前的通道会议、黎平会议和猴场会议各自解决了什么问题？", "遵义会议后军事指挥和组织分工有哪些逐步变化？"],
        "四渡赤水": ["四渡赤水中红军怎样通过佯动和转向调动敌军？", "四渡赤水与巧渡金沙江之间有什么战略衔接？"],
        "飞夺泸定桥/大渡河": ["安顺场、泸定桥和大渡河渡河点之间是什么关系？", "泸定桥的通道价值为什么比战斗场面本身更关键？"],
        "大渡河与泸定桥": ["安顺场、泸定桥和大渡河渡河点之间是什么关系？", "泸定桥的通道价值为什么比战斗场面本身更关键？"],
        "翻越夹金山/雪山": ["夹金山的高寒、缺氧和装备不足怎样影响行军组织？", "翻越夹金山时伤病员和掉队风险如何被放大？"],
        "跨越松潘草地": ["过草地时缺粮、疾病、掉队和泥沼风险是怎样叠加的？", "草地行军中筹粮、干粮和露营记录说明了什么？"],
        "瑞金集结出发": ["长征出发时机关、辎重和部队行动方式带来了哪些后续压力？", "从瑞金到湘江之间，红军行动为什么会逐步变得被动？"],
        "吴起镇大会师": ["中央红军到达陕北后，为什么能为革命保存骨干力量？", "吴起镇会师与陕北根据地之间怎样形成战略接续？"],
    }

    basics = basic_map.get(event, [f"{event}的核心历史意义是什么？", f"理解{event}时最容易忽略哪一点？"])
    details = detail_map.get(event, [f"{event}中有哪些容易被忽略的关键细节？", f"{event}有哪些需要结合史料核对的细节？"])

    if relic_matches:
        relic_title = str(relic_matches[0].get("title") or "这件相关文物")
        related_items = [
            f"{relic_title}背后反映了怎样的行军处境和历史压力？",
            f"如果把这件文物放回{event}现场，它能证明或补充哪些史料细节？",
        ]
    elif citations:
        source = str(citations[0].get("source") or "本次命中的史料")
        short_source = source.split("/")[-1].replace(".pdf", "").replace("_ocr", "").replace("副本", "")
        related_items = [
            f"从《{short_source[:28]}》这类史料看，{event}还有哪些值得继续核对的细节？",
            f"{event}还应与哪些人物、会议、战役或路线变化联系起来考察？",
        ]
    else:
        related_items = [
            f"{event}还应与哪些人物、会议、战役或路线变化联系起来考察？",
            f"如果继续查史料，{event}最应该补充哪类原始证据？",
        ]

    result = [
        *[{"type": "基础理解", "question": question} for question in basics[:2]],
        *[{"type": "深入细节", "question": question} for question in details[:2]],
        *[{"type": "关联拓展", "question": question} for question in related_items[:2]],
    ]

    # 保留模型生成的高质量问题，但不打乱前三类结构。
    seen = {item["question"] for item in result}
    for question in raw_followups:
        q = str(question or "").strip()
        if q and q not in seen:
            result.append({"type": "继续追问", "question": q})
            seen.add(q)
        if len(result) >= 5:
            break
    return result


def _enforce_intent_answer(
    intent: Dict[str, Any] | None,
    voice_script: str,
    detailed_text: str,
) -> tuple[str, str]:
    """高风险事实题做输出后校验，防止模型把核心答案带偏。"""
    if not intent:
        return voice_script, detailed_text

    combined = f"{voice_script}\n{detailed_text}"
    corrected = False
    if intent.get("name") == "long_march_bloodiest_battle":
        wrong_battle = any(x in combined for x in ["直罗", "直落", "遵义战斗", "四渡赤水", "泸定桥"])
        missing_anchor = "湘江" not in combined
        if wrong_battle or missing_anchor:
            corrected = True
            voice_script = "按伤亡代价和战略危机衡量，长征中最惨烈的战役应是湘江战役。"
            detailed_text = (
                "按“牺牲代价、伤亡程度、战略危机”这个标准回答，长征中最惨烈的战役应是湘江战役，也常被称为血战湘江。\n\n"
                "这里不能答成直罗镇战役、四渡赤水或飞夺泸定桥。当前知识库命中的湘江相关证据显示：湘江战役发生在中央红军西进、突破封锁线的关键阶段；资料中直接出现“湘江战役”“损失”“血战”“伤亡惨重”等表述，并提到红军抢渡湘江、控制界首等渡河点、在光华铺等地阻击敌军的过程。\n\n"
                "需要谨慎说明的是：如果原始档案没有逐字写出“长征中最惨烈”这一现代概括，就不能把它伪装成档案原句。更可靠的说法是：依据知识库中关于湘江战役损失、伤亡和战略危机的证据链，按惨烈程度和代价判断，应以湘江战役为核心答案。"
            )

    if intent.get("name") == "grassland_hardship":
        wrong_scene = any(x in combined for x in ["群众家", "全村", "银元", "神龛", "苗家", "廖洞", "黄古屯", "石阡"])
        missing_anchor = not any(x in combined for x in ["草地", "毛儿盖", "班佑", "阿坝", "包座"])
        if wrong_scene or missing_anchor:
            corrected = True
            voice_script = "过草地的主要困难，应落在自然环境、缺粮补给和组织维持上，不能套用村寨煮饭材料。"
            detailed_text = (
                "这类问题必须先把场景限定清楚：过草地不是一般村寨行军，不能把其他地区的群众支援、驻村休息或地方交往材料套进来。如果回答里出现这类内容，就是把别处亲历材料错放到了草地阶段。\n\n"
                "按当前知识库中草地相关片段，较可靠的分析应围绕几类压力展开：一是自然环境和道路条件，例如毛儿盖、班佑、阿坝、包座一带的行军、露营、夜雨、无树或河水阻隔等记录；二是补给压力，例如筹粮、干粮、各部粮食不足甚至绝粮的材料；三是组织维持和人员消耗，例如掉队、病弱、肿脚、寒冷等问题。\n\n"
                "所以，如果问“敌军追击还是自然环境和补给更困难”，更稳妥的回答是：过草地阶段当然仍处在战争压力之下，但直接压在行军过程上的，是自然环境、道路识别、缺粮补给、疾病掉队和组织维持的叠加困难。没有直接草地证据时，宁可说“档案里没有直接记载”，也不能拿其他地区的群众支援材料来补。"
            )

    forbidden_terms = [str(t) for t in intent.get("forbidden_terms", []) if str(t)]
    required_terms = [str(t) for t in intent.get("required_terms", []) if str(t)]
    forbidden_hits = [term for term in forbidden_terms if term in combined]
    missing_anchor = required_terms and not any(term in combined for term in required_terms)
    if not corrected and (forbidden_hits or missing_anchor):
        scene = intent.get("scene", "当前问题对应的历史场景")
        required_text = "、".join(required_terms[:6]) or "直接相关证据"
        forbidden_text = "、".join(forbidden_hits[:5]) if forbidden_hits else "无"
        voice_script = f"这个问题必须回到“{scene}”的直接证据，不能跨场景拼接材料。"
        detailed_text = (
            f"为保证准确性，本次回答需要先做证据校正：问题已限定在“{scene}”，"
            f"应优先围绕这些证据锚点展开：{required_text}。\n\n"
            f"刚才生成内容中出现了跨场景风险或核心锚点不足。风险词：{forbidden_text}。"
            "证据真实并不等于可以挪用；不同地点、不同阶段、不同战役的材料不能互相替代。\n\n"
            "更稳妥的处理是：只根据当前 Context 中与该场景直接相关的片段回答；如果 Context 不能支撑某个细节，就明确说“档案里没有直接记载”，而不是补写听起来合理但场景不符的内容。"
        )

    return voice_script, detailed_text


def get_veteran_response(user_query: str) -> Dict[str, Any]:
    guide_mode = "讲解员模式" in user_query or "导览" in user_query or "站点讲解" in user_query
    station = None
    station_index = 0
    retrieval_query = user_query
    intent = None
    if guide_mode:
        station, station_index = build_station_response(user_query)
        retrieval_query = station.search_query
        profile = _topic_profile_from_query(f"{station.title} {station.search_query}")
        if profile:
            intent = _intent_from_profile(profile, user_query)
            retrieval_query = intent["retrieval_query"]
    else:
        intent = _detect_query_intent(user_query)
        if intent:
            retrieval_query = intent["retrieval_query"]

    chunks = retrieve_relevant_chunks(retrieval_query, top_k=10 if guide_mode else None, intent=intent)
    context = _build_context(chunks)
    factual_guard = _build_factual_guard(intent, chunks)
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

        relic_matches = match_relics(user_query, station.voice + station.detail + context)
        guide_followups = _build_discovery_followups(
            user_query,
            station.voice,
            station.detail,
            [next_station_prompt(station_index), station.deep_followup],
            relic_matches,
            citations,
            intent,
        )
        return {
            "llm_data": {
                "voice_script": station.voice,
                "detailed_text": station.detail + evidence_note,
                "follow_ups": guide_followups,
            },
            "raw_evidence": context,
            "citations": citations,
            "evidence_snippets": evidence_snippets,
            "relic_matches": relic_matches,
            "answer_intent": intent,
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
7. 所有“最惨烈、最惊险、最大、最重要”这类判断，必须先说明判断标准，再给出答案；不能把不相关证据当作引用。
8. 严禁跨场景引用：回答草地问题只能使用草地、毛儿盖、班佑、阿坝、包座等相关证据；回答湘江问题只能使用湘江相关证据。证据真实但场景不符，也必须视为不可用。
{factual_guard}
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

        voice_script, detailed_text = _enforce_intent_answer(intent, voice_script, detailed_text)
        relic_matches = match_relics(
            user_query,
            voice_script + detailed_text + context
        )
        follow_ups = _build_discovery_followups(
            user_query,
            voice_script,
            detailed_text,
            [q for q in [followup_1, followup_2] if q],
            relic_matches,
            citations,
            intent,
        )
        return {
            "llm_data": {
                "voice_script": voice_script,
                "detailed_text": detailed_text,
                "follow_ups": follow_ups,
            },
            "raw_evidence": context,
            "citations": citations,
            "evidence_snippets": evidence_snippets,
            "relic_matches": relic_matches,
            "answer_intent": intent,
        }
    except Exception as e:
        return _safe_default_response(
            "孩子，通讯设备出了点故障，老红军暂时听不清你的话。",
            "系统通讯暂时繁忙，可能是模型服务正在过载。请稍后重新提问，老红军会继续为你讲述这段历史。",
            context,
            citations,
            evidence_snippets,
        )
