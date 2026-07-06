#!/usr/bin/env python3
"""Find and verify WeChat article candidates for MinerU.

The script keeps the research step separate from parsing:
1. Search Sogou Weixin for a topic.
2. Score candidates with a deliberately simple rule set.
3. Resolve Sogou redirect links with a hidden/headless Chrome session.
4. Save a candidate list, and optionally write verified URLs to urls.txt.
"""

from __future__ import annotations

import argparse
import base64
import csv
import dataclasses
import datetime as dt
import hashlib
import html
import json
import os
import random
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import requests


SOGOU_SEARCH_URL = "https://weixin.sogou.com/weixin"
DEFAULT_OUTPUT_DIR = Path("candidates")
DEFAULT_URLS_FILE = Path("urls.txt")
DEFAULT_SEARCH_CACHE_DIR = Path("work") / "sogou-search-cache"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

GOOD_TERMS = [
    "案例",
    "品牌",
    "营销",
    "增长",
    "出海",
    "联名",
    "破圈",
    "心智",
    "渠道",
    "消费者",
    "商业化",
    "投放",
    "内容",
    "新品",
]
VALUE_TERMS = [
    "案例",
    "复盘",
    "拆解",
    "解码",
    "趋势",
    "观察",
    "洞察",
    "报告",
    "研究",
    "策略",
    "方法",
    "路径",
    "增长",
    "商业化",
    "运营",
    "打法",
    "新变量",
    "变局",
    "重构",
]
ARTICLE_TYPE_TERMS = [
    "案例复盘",
    "行业分析",
    "数据报告",
    "深度访谈",
    "策略拆解",
    "案例",
    "复盘",
    "分析",
    "报告",
    "访谈",
    "拆解",
]
BUSINESS_ANALYSIS_TERMS = [
    "市场",
    "行业",
    "商业",
    "竞争",
    "竞品",
    "渠道",
    "终端",
    "价格带",
    "份额",
    "销量",
    "增长",
    "消费者",
    "用户",
    "人群",
    "场景",
    "策略",
    "投放",
    "传播",
    "供应链",
]
EVIDENCE_TERMS = [
    "数据",
    "调研",
    "样本",
    "同比",
    "环比",
    "增长率",
    "渗透率",
    "市场份额",
    "销售额",
    "销量",
    "财报",
    "图表",
    "报告",
    "访谈",
]
BEVERAGE_COMPANY_TERMS = [
    "饮料",
    "食品饮料",
    "快消",
    "瓶装水",
    "包装水",
    "矿泉水",
    "纯净水",
    "电解质水",
    "功能饮料",
    "茶饮",
    "咖啡",
    "便利店",
    "商超",
    "货架",
    "经销商",
    "SKU",
]
BRAND_CASE_TERMS = [
    "品牌",
    "赞助",
    "联名",
    "投放",
    "传播",
    "消费者",
    "场景",
    "心智",
    "破圈",
    "增长",
]
GOOD_SOURCES = [
    "广告",
    "营销",
    "品牌",
    "商业",
    "财经",
    "数据",
    "观察",
    "洞察",
    "研究",
]
NOISE_TERMS = [
    "招聘",
    "通知",
    "报名",
    "直播预告",
    "网盘",
    "资料包",
    "PDF",
    "课程",
    "培训",
    "下载",
]
LOW_VALUE_TERMS = [
    "一周",
    "周报",
    "榜单",
    "中期榜",
    "发布",
    "官宣",
    "通知",
    "合规",
    "研析",
    "法律",
    "课程",
    "直播",
    "体育战报",
    "赛程",
    "比分",
]
GENERAL_QUERY_SUFFIXES = [
    "案例",
    "复盘",
    "拆解",
    "分析",
    "趋势",
    "观察",
    "洞察",
    "报告",
    "研究",
    "策略",
    "行业",
    "方案",
    "数据",
    "访谈",
    "渠道",
    "消费者",
]
BRAND_INTENT_TERMS = [
    "营销",
    "品牌",
    "广告",
    "传播",
    "投放",
    "增长",
    "消费者",
    "商业化",
    "赞助",
    "联名",
]
GENERAL_SOURCE_TERMS = [
    "观察",
    "洞察",
    "研究",
    "报告",
    "财经",
    "商业",
    "数据",
    "智库",
    "产业",
    "行业",
    "科技",
    "产品",
]
SUBSTANTIVE_SNIPPET_MIN_LENGTH = 40
PRICE_INTENT_TERMS = [
    "降价",
    "涨价",
    "调价",
    "价格",
    "低价",
    "高价",
    "促销",
    "优惠",
    "折扣",
]
TOPIC_INTENT_TERMS = set(
    VALUE_TERMS
    + BRAND_INTENT_TERMS
    + BRAND_CASE_TERMS
    + PRICE_INTENT_TERMS
    + [
        "新闻",
        "文章",
        "公众号",
        "微信",
        "相关",
        "最新",
        "今年",
        "去年",
        "至今",
    ]
)


@dataclasses.dataclass
class Candidate:
    title: str
    snippet: str
    source: str
    date: str
    search_query: str
    search_url: str
    sogou_url: str
    score: int = 0
    rating: str = "weak"
    reason: str = ""
    relevance_tier: str = "weak"
    resolved_url: str = ""
    resolve_status: str = "pending"

    def key(self) -> str:
        if self.resolved_url:
            return self.resolved_url
        return f"{normalize_text(self.title)}::{normalize_text(self.source)}"


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value or "").strip()


def split_keywords(value: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for item in re.split(r"[,，;；\s]+", value or ""):
        term = item.strip()
        if term and term not in seen:
            terms.append(term)
            seen.add(term)
    return terms


def strip_tags(value: str) -> str:
    value = re.sub(r"(?is)<script.*?</script>", " ", value)
    value = re.sub(r"(?is)<style.*?</style>", " ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


UNAVAILABLE_WECHAT_MARKERS = [
    "该内容已被发布者删除",
    "此内容已被发布者删除",
    "该内容已被删除",
    "此内容已被删除",
    "此内容因违规无法查看",
    "该内容因违规无法查看",
    "此内容已被投诉并经审核",
    "该公众号已被封禁",
    "此账号已被封",
    "该公众号已迁移",
    "原账号迁移时未将文章素材同步至新账号",
    "该链接已不可访问",
    "链接已过期",
    "文章不存在",
    "内容不存在",
    "参数错误",
    "该内容无法查看",
    "此内容无法查看",
]


SOGOU_BLOCK_MARKERS = [
    "antispider",
    "请输入验证码",
    "验证码",
    "您的访问过于频繁",
    "异常访问",
    "用户您好",
]


class SogouSearchBlockedError(RuntimeError):
    """Raised when Sogou returns an anti-spider page instead of search results."""


def unavailable_wechat_marker(value: str) -> str:
    compact = normalize_text(strip_tags(value))
    for marker in UNAVAILABLE_WECHAT_MARKERS:
        if normalize_text(marker) in compact:
            return marker
    return ""


def sogou_block_marker(value: str) -> str:
    compact = normalize_text(strip_tags(value))
    lower_value = value.lower()
    for marker in SOGOU_BLOCK_MARKERS:
        if marker == "antispider" and marker in lower_value:
            return marker
        if normalize_text(marker) in compact:
            return marker
    return ""


def safe_name(value: str, fallback: str = "research") -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value).strip(" ._")
    value = re.sub(r"\s+", "_", value)
    return (value[:60] or fallback)


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def make_search_url(query: str) -> str:
    params = {"type": "2", "query": query}
    return f"{SOGOU_SEARCH_URL}?{urllib.parse.urlencode(params)}"


def years_from_range(start_date: dt.date | None, end_date: dt.date | None) -> list[str]:
    if not start_date and not end_date:
        return []
    start_year = start_date.year if start_date else 2020
    end_year = end_date.year if end_date else dt.date.today().year
    if start_year > end_year:
        return []
    return [str(year) for year in range(start_year, end_year + 1)]


def contains_year(value: str) -> bool:
    return bool(re.search(r"20\d{2}", value))


def query_angle_terms(extra_keywords: str, topic: str, limit: int = 2) -> list[str]:
    topic_compact = normalize_text(topic)
    generic_terms = {
        "品牌",
        "活动",
        "饮料",
        "市场营销",
        "品牌营销",
        "传播",
        "促销",
        "合作",
        "曝光",
        "销量",
        "行业",
        "方案",
        "案例",
        "复盘",
        "分析",
        "报告",
    }
    terms: list[str] = []
    seen: set[str] = set()
    for term in split_keywords(extra_keywords):
        compact = normalize_text(term)
        if not compact or compact in seen:
            continue
        if compact in generic_terms or compact in topic_compact:
            continue
        terms.append(term)
        seen.add(compact)
        if len(terms) >= limit:
            break
    return terms


def year_topic_variants(topic: str, years: list[str]) -> list[str]:
    if len(years) != 1:
        return []
    year = years[0]
    if year in topic:
        return []
    variants: list[str] = []
    for token in split_keywords(topic):
        if "世界杯" in token and not contains_year(token):
            variants.append(topic.replace(token, f"{year}{token}", 1))
            break
    return variants


def generate_queries(
    topic: str,
    extra_keywords: str,
    max_queries: int,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
) -> list[str]:
    years = years_from_range(start_date, end_date)
    topic = re.sub(r"\s+", " ", topic).strip()
    primary_year = years[-1] if years else ""
    angle_terms = query_angle_terms(extra_keywords, topic)
    fallback_terms = [
        term
        for term in ["案例", "分析", "复盘", "报告", "策略", "数据", "消费者", "渠道"]
        if term not in angle_terms and term not in topic
    ]

    parts = [topic]
    parts.extend(year_topic_variants(topic, years))
    if primary_year and not contains_year(topic) and not any(contains_year(item) for item in parts):
        parts.append(f"{topic} {primary_year}")
    for word in angle_terms:
        parts.append(f"{topic} {word}")
    for suffix in fallback_terms:
        parts.append(f"{topic} {suffix}")
    for year in years[-2:]:
        if year and year not in topic:
            for suffix in fallback_terms[:3]:
                parts.append(f"{topic} {suffix} {year}")

    queries: list[str] = []
    seen: set[str] = set()
    for item in parts:
        item = re.sub(r"\s+", " ", item).strip()
        if item and item not in seen:
            queries.append(item)
            seen.add(item)
        if len(queries) >= max_queries:
            break
    return queries


def core_topic_terms(topic: str) -> list[str]:
    terms: list[str] = []

    compact = normalize_text(topic)
    stripped_compact = compact
    for intent_term in sorted(TOPIC_INTENT_TERMS, key=len, reverse=True):
        stripped_compact = stripped_compact.replace(normalize_text(intent_term), "")
    if len(stripped_compact) >= 2 and not stripped_compact.isdigit():
        terms.append(stripped_compact)

    for raw_term in re.split(r"[,，\s]+", topic):
        term = raw_term.strip()
        if len(term) < 2 or term.isdigit():
            continue
        compact_term = normalize_text(term)
        for intent_term in sorted(TOPIC_INTENT_TERMS, key=len, reverse=True):
            compact_term = compact_term.replace(normalize_text(intent_term), "")
        if len(compact_term) >= 2 and not compact_term.isdigit():
            terms.append(compact_term)

    seen: set[str] = set()
    clean_terms: list[str] = []
    for term in terms:
        if term and term not in seen:
            clean_terms.append(term)
            seen.add(term)
    return clean_terms


def candidate_matches_core_topic(candidate: Candidate, topic: str) -> bool:
    core_terms = core_topic_terms(topic)
    if not core_terms:
        return True
    blob = normalize_text(f"{candidate.title} {candidate.snippet}")
    return any(term in blob for term in core_terms)


def required_intent_terms(topic: str) -> list[str]:
    blob = normalize_text(topic)
    return [term for term in PRICE_INTENT_TERMS if normalize_text(term) in blob]


def candidate_matches_required_intent(candidate: Candidate, topic: str) -> bool:
    required_terms = required_intent_terms(topic)
    if not required_terms:
        return True
    blob = normalize_text(f"{candidate.title} {candidate.snippet}")
    return any(normalize_text(term) in blob for term in required_terms)


def candidate_matches_exclusion(candidate: Candidate, exclude_keywords: str) -> list[str]:
    terms = [normalize_text(term) for term in split_keywords(exclude_keywords)]
    if not terms:
        return []
    blob = normalize_text(f"{candidate.title} {candidate.snippet} {candidate.source}")
    return [term for term in terms if term and term in blob]


def count_term_hits(blob: str, terms: list[str], max_hits: int = 3) -> int:
    return min(max_hits, sum(1 for term in terms if normalize_text(term) in blob))


def relevance_tier(candidate: Candidate, topic: str) -> str:
    compact_blob = normalize_text(f"{candidate.title} {candidate.snippet}")
    compact_topic = normalize_text(topic)
    has_exact_topic = bool(compact_topic and compact_topic in compact_blob)
    has_core = candidate_matches_core_topic(candidate, topic)
    required_terms = required_intent_terms(topic)
    has_required_intent = candidate_matches_required_intent(candidate, topic)

    if has_exact_topic:
        return "exact"
    if has_core and required_terms and has_required_intent:
        return "core_intent"
    if has_core:
        return "core_related"
    if not core_topic_terms(topic) and has_required_intent:
        return "intent_related"
    return "weak"


RELEVANCE_TIER_PRIORITY = {
    "exact": 4,
    "core_intent": 3,
    "core_related": 2,
    "intent_related": 1,
    "weak": 0,
}


def score_candidate(
    candidate: Candidate,
    topic: str,
    extra_keywords: str = "",
    exclude_keywords: str = "",
) -> None:
    title_blob = f"{candidate.title} {candidate.snippet}"
    compact_blob = normalize_text(title_blob)
    compact_topic = normalize_text(topic)
    source_blob = normalize_text(candidate.source)
    query_blob = normalize_text(candidate.search_query)
    reasons: list[str] = []
    score = 0
    core_terms = core_topic_terms(topic)
    has_core_match = any(term in compact_blob for term in core_terms)
    required_terms = required_intent_terms(topic)
    has_required_intent = not required_terms or any(
        normalize_text(term) in compact_blob for term in required_terms
    )

    if compact_topic and compact_topic in compact_blob:
        score += 5
        reasons.append("direct topic match")
    elif has_core_match:
        score += 3
        reasons.append("core topic match")
    if required_terms and has_required_intent:
        score += 2
        reasons.append("required intent match")

    if any(term in candidate.title for term in ARTICLE_TYPE_TERMS):
        score += 3
        reasons.append("preferred article type")
    if any(term in candidate.title for term in VALUE_TERMS):
        score += 2
        reasons.append("title value signal")
    if any(term in candidate.snippet for term in VALUE_TERMS):
        score += 2
        reasons.append("snippet analysis signal")
    business_hits = count_term_hits(compact_blob, BUSINESS_ANALYSIS_TERMS, max_hits=3)
    if business_hits:
        score += business_hits
        reasons.append("business analysis signal")
    evidence_hits = count_term_hits(compact_blob, EVIDENCE_TERMS, max_hits=2)
    if evidence_hits:
        score += evidence_hits
        reasons.append("evidence or data signal")
    beverage_hits = count_term_hits(compact_blob + source_blob, BEVERAGE_COMPANY_TERMS, max_hits=2)
    if beverage_hits:
        score += beverage_hits
        reasons.append("beverage/consumer goods context")
    if any(normalize_text(term) in query_blob for term in VALUE_TERMS + BUSINESS_ANALYSIS_TERMS):
        score += 1
        reasons.append("high-intent query signal")
    if len(normalize_text(candidate.snippet)) >= SUBSTANTIVE_SNIPPET_MIN_LENGTH:
        score += 1
        reasons.append("substantive snippet")
    source_terms = GENERAL_SOURCE_TERMS
    if any(normalize_text(term) in source_blob for term in source_terms):
        score += 2
        reasons.append("relevant account")
    if any(term in title_blob for term in NOISE_TERMS):
        score -= 4
        reasons.append("possible noise")
    if any(term in candidate.title for term in LOW_VALUE_TERMS):
        score -= 4
        reasons.append("low-value format")
    exclusion_hits = candidate_matches_exclusion(candidate, exclude_keywords)
    if exclusion_hits:
        score -= 6
        reasons.append(f"memory exclusion: {'/'.join(exclusion_hits[:3])}")
    if core_terms and not has_core_match and compact_topic not in compact_blob:
        score -= 4
        reasons.append("missing core topic")

    candidate.score = score
    if score >= 10:
        candidate.rating = "strong"
    elif score >= 5:
        candidate.rating = "maybe"
    else:
        candidate.rating = "weak"
    candidate.relevance_tier = relevance_tier(candidate, topic)
    if required_terms and not has_required_intent and candidate.relevance_tier == "core_related":
        reasons.append("broader core-related context")
    candidate.reason = ", ".join(reasons) or "low signal"


def cache_path_for_query(cache_dir: Path, query: str) -> Path:
    key = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return cache_dir / f"{key}.html"


def read_cached_sogou_result(cache_dir: Path, query: str, ttl_hours: float) -> str | None:
    if ttl_hours <= 0:
        return None
    cache_path = cache_path_for_query(cache_dir, query)
    if not cache_path.exists():
        return None
    max_age = ttl_hours * 3600
    age = time.time() - cache_path.stat().st_mtime
    if age > max_age:
        return None
    try:
        return cache_path.read_text(encoding="utf-8")
    except OSError:
        return None


def write_cached_sogou_result(cache_dir: Path, query: str, page_text: str) -> None:
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path_for_query(cache_dir, query).write_text(page_text, encoding="utf-8")
    except OSError:
        return


def fetch_sogou_results(
    session: requests.Session,
    query: str,
    timeout: int,
    cache_dir: Path | None = None,
    cache_ttl_hours: float = 0,
) -> str:
    if cache_dir is not None:
        cached = read_cached_sogou_result(cache_dir, query, cache_ttl_hours)
        if cached is not None:
            print("  cache hit")
            return cached

    response = session.get(
        make_search_url(query),
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
            "Referer": "https://weixin.sogou.com/",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    if not response.encoding or response.encoding.lower() == "iso-8859-1":
        response.encoding = response.apparent_encoding or "utf-8"
    page_text = response.text
    marker = sogou_block_marker(page_text)
    if marker:
        raise SogouSearchBlockedError(
            f"Sogou returned an anti-spider page ({marker}) instead of search results."
        )
    if cache_dir is not None:
        write_cached_sogou_result(cache_dir, query, page_text)
    return page_text


def parse_sogou_results(page_html: str, query: str) -> list[Candidate]:
    search_url = make_search_url(query)
    blocks = re.findall(r'(?is)<div\s+class=["\']txt-box["\'].*?</li>', page_html)
    candidates: list[Candidate] = []

    for block in blocks:
        link_match = re.search(r'(?is)<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', block)
        if not link_match:
            continue
        raw_url = html.unescape(link_match.group(1).strip())
        title = strip_tags(link_match.group(2))
        if not title:
            continue
        if raw_url.startswith("/"):
            raw_url = urllib.parse.urljoin("https://weixin.sogou.com/", raw_url)

        snippet_match = re.search(r'(?is)<p\s+class=["\']txt-info["\'][^>]*>(.*?)</p>', block)
        snippet = strip_tags(snippet_match.group(1)) if snippet_match else ""

        source = ""
        for pattern in [
            r'(?is)<a[^>]+account_name[^>]*>(.*?)</a>',
            r'(?is)<span\s+class=["\']all-time-y2["\'][^>]*>.*?</span>\s*<a[^>]*>(.*?)</a>',
            r'(?is)<label[^>]*name=["\']em_weixinhao["\'][^>]*>(.*?)</label>',
        ]:
            source_match = re.search(pattern, block)
            if source_match:
                source = strip_tags(source_match.group(1))
                break

        date = ""
        time_match = re.search(r"timeConvert\(['\"]?(\d+)['\"]?\)", block)
        if time_match:
            try:
                date = dt.datetime.fromtimestamp(int(time_match.group(1))).strftime("%Y-%m-%d")
            except (OSError, ValueError):
                date = ""

        candidates.append(
            Candidate(
                title=title,
                snippet=snippet,
                source=source,
                date=date,
                search_query=query,
                search_url=search_url,
                sogou_url=raw_url,
            )
        )

    return candidates


def browser_page_snapshot(cdp: "CdpClient", html_limit: int = 400000) -> dict[str, str]:
    limit = int(max(10000, html_limit))
    snapshot = cdp.evaluate(
        f"""
(() => ({{
  url: location.href,
  title: document.title,
  html: document.documentElement ? document.documentElement.innerHTML.slice(0, {limit}) : ""
}}))()
""",
        timeout=20,
    )
    return {
        "url": (snapshot or {}).get("url", ""),
        "title": (snapshot or {}).get("title", ""),
        "html": (snapshot or {}).get("html", ""),
    }


def fetch_sogou_results_with_browser(
    cdp: "CdpClient",
    query: str,
    verification_timeout: int,
    min_delay: float,
    max_delay: float,
) -> str:
    search_url = make_search_url(query)
    cdp.call("Page.navigate", {"url": search_url}, timeout=20)
    sleep_random(min_delay, max_delay)

    deadline = time.time() + max(10, verification_timeout)
    prompted = False
    last_marker = ""
    while time.time() < deadline:
        snapshot = browser_page_snapshot(cdp)
        page_html = snapshot.get("html", "")
        marker = sogou_block_marker(page_html)
        if not marker:
            return page_html

        last_marker = marker
        if not prompted:
            print(
                "  Sogou verification is required in the opened browser. "
                f"Complete it there; waiting up to {verification_timeout} seconds..."
            )
            prompted = True
        time.sleep(2)

    raise SogouSearchBlockedError(
        "Sogou verification was not completed before timeout"
        + (f" ({last_marker})" if last_marker else "")
    )


def collect_candidates(
    topic: str,
    extra_keywords: str,
    exclude_keywords: str,
    max_queries: int,
    top_per_query: int,
    timeout: int,
    min_delay: float,
    max_delay: float,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
    browser_search: bool = True,
    chrome_path: str | None = None,
    verification_timeout: int = 180,
    search_cache_dir: Path | None = DEFAULT_SEARCH_CACHE_DIR,
    cache_ttl_hours: float = 12,
    stop_on_block: bool = True,
    target_screening_count: int = 0,
    stop_after_empty_rounds: int = 2,
) -> tuple[list[Candidate], requests.cookies.RequestsCookieJar]:
    session = requests.Session()
    session.trust_env = False
    queries = generate_queries(topic, extra_keywords, max_queries, start_date, end_date)
    collected: list[Candidate] = []
    blocked_count = 0
    browser_proc: subprocess.Popen[Any] | None = None
    browser_cdp: CdpClient | None = None
    browser_profile_dir: Path | None = None
    qualified_total = 0
    empty_rounds = 0

    try:
        for index, query in enumerate(queries, start=1):
            print(f"Search {index}/{len(queries)}: {query}")
            try:
                page = fetch_sogou_results(
                    session,
                    query,
                    timeout,
                    cache_dir=search_cache_dir,
                    cache_ttl_hours=cache_ttl_hours,
                )
                results = parse_sogou_results(page, query)[:top_per_query]
            except SogouSearchBlockedError as exc:
                blocked_count += 1
                print(f"  search blocked: {exc}")
                results = []
                if browser_search:
                    if browser_cdp is None:
                        port = free_port()
                        browser_profile_dir = browser_work_dir("chrome-sogou-search", port)
                        try:
                            browser_proc, browser_path, headless, log_path = launch_debug_browser(
                                chrome_path,
                                port,
                                browser_profile_dir,
                                visible=True,
                                allow_headless=False,
                            )
                            print(
                                "  Browser search using "
                                f"{Path(browser_path).name} ({'headless' if headless else 'visible'}); "
                                f"log: {log_path}"
                            )
                            browser_cdp = CdpClient(new_cdp_page(port))
                            browser_cdp.call("Page.enable")
                            browser_cdp.call("Runtime.enable")
                        except Exception as browser_exc:
                            print(f"  browser search unavailable: {type(browser_exc).__name__}: {browser_exc}")
                            stop_process(browser_proc)
                            browser_proc = None
                            browser_profile_dir = None
                    if browser_cdp is not None:
                        try:
                            page = fetch_sogou_results_with_browser(
                                browser_cdp,
                                query,
                                verification_timeout=verification_timeout,
                                min_delay=min_delay,
                                max_delay=max_delay,
                            )
                            results = parse_sogou_results(page, query)[:top_per_query]
                            print(f"  browser parsed {len(results)} results")
                        except Exception as browser_exc:
                            print(f"  browser search failed: {type(browser_exc).__name__}: {browser_exc}")
                    if not results and stop_on_block:
                        print("  stopping this search run to avoid repeated blocked requests")
                        break
                elif stop_on_block:
                    print("  stopping this search run to avoid repeated blocked requests")
                    break
            except Exception as exc:
                print(f"  search failed: {type(exc).__name__}: {exc}")
                results = []
            for candidate in results:
                score_candidate(
                    candidate,
                    topic,
                    extra_keywords=extra_keywords,
                    exclude_keywords=exclude_keywords,
                )
            collected.extend(results)
            current_candidates = dedupe_candidates(collected)
            new_qualified_total = screenable_candidate_count(
                current_candidates,
                topic=topic,
                exclude_keywords=exclude_keywords,
                start_date=start_date,
                end_date=end_date,
            )
            delta = new_qualified_total - qualified_total
            if delta > 0:
                print(f"  added {delta} screenable candidates; total screenable={new_qualified_total}")
                empty_rounds = 0
            else:
                empty_rounds += 1
                print(f"  no new screenable candidates; empty_rounds={empty_rounds}/{stop_after_empty_rounds}")
            qualified_total = max(qualified_total, new_qualified_total)
            if target_screening_count and qualified_total >= target_screening_count:
                print(f"  target screening pool reached ({qualified_total}/{target_screening_count}); stopping search.")
                break
            if stop_after_empty_rounds > 0 and empty_rounds >= stop_after_empty_rounds:
                print("  stopping search after consecutive low-yield keyword rounds.")
                break
            if index < len(queries):
                sleep_random(min_delay, max_delay)

        if not collected and blocked_count:
            raise RuntimeError(
                "Sogou blocked all usable search attempts with anti-spider pages; "
                "no candidates could be collected. Complete verification in the opened browser "
                "and rerun, try again later, or use manual URLs."
            )
    finally:
        if browser_cdp:
            browser_cdp.close()
        stop_process(browser_proc)
        if browser_profile_dir:
            shutil.rmtree(browser_profile_dir, ignore_errors=True)

    return dedupe_candidates(collected), session.cookies


def dedupe_candidates(candidates: list[Candidate]) -> list[Candidate]:
    best_by_key: dict[str, Candidate] = {}
    for candidate in candidates:
        key = candidate.key()
        existing = best_by_key.get(key)
        if existing is None or candidate.score > existing.score:
            best_by_key[key] = candidate
    return sorted(best_by_key.values(), key=lambda item: (item.score, item.date), reverse=True)


def parse_date_arg(value: str, label: str) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be YYYY-MM-DD, got: {value}") from exc


def filter_candidates_by_date(
    candidates: list[Candidate],
    start_date: dt.date | None,
    end_date: dt.date | None,
) -> list[Candidate]:
    if not start_date and not end_date:
        return candidates

    filtered: list[Candidate] = []
    for candidate in candidates:
        if not candidate.date:
            continue
        try:
            candidate_date = dt.date.fromisoformat(candidate.date)
        except ValueError:
            continue
        if start_date and candidate_date < start_date:
            continue
        if end_date and candidate_date > end_date:
            continue
        filtered.append(candidate)
    return filtered


def candidate_in_date_range(
    candidate: Candidate,
    start_date: dt.date | None,
    end_date: dt.date | None,
) -> bool:
    if not start_date and not end_date:
        return True
    if not candidate.date:
        return False
    try:
        candidate_date = dt.date.fromisoformat(candidate.date)
    except ValueError:
        return False
    if start_date and candidate_date < start_date:
        return False
    if end_date and candidate_date > end_date:
        return False
    return True


def candidate_is_screenable(
    candidate: Candidate,
    topic: str,
    exclude_keywords: str,
    start_date: dt.date | None,
    end_date: dt.date | None,
) -> bool:
    return (
        candidate_in_date_range(candidate, start_date, end_date)
        and RATING_LEVELS.get(candidate.rating, 0) >= RATING_LEVELS["maybe"]
        and candidate_matches_core_topic(candidate, topic)
        and RELEVANCE_TIER_PRIORITY.get(candidate.relevance_tier, 0) >= RELEVANCE_TIER_PRIORITY["core_related"]
        and not candidate_matches_exclusion(candidate, exclude_keywords)
    )


def screenable_candidate_count(
    candidates: list[Candidate],
    topic: str,
    exclude_keywords: str,
    start_date: dt.date | None,
    end_date: dt.date | None,
) -> int:
    return sum(
        1
        for candidate in candidates
        if candidate_is_screenable(candidate, topic, exclude_keywords, start_date, end_date)
    )


def rank_for_screening(candidates: list[Candidate]) -> list[Candidate]:
    return sorted(candidates, key=lambda item: (item.score, item.date), reverse=True)


def rank_for_final(candidates: list[Candidate]) -> list[Candidate]:
    return sorted(
        candidates,
        key=lambda item: (
            1 if "mp.weixin.qq.com" in item.resolved_url else 0,
            RELEVANCE_TIER_PRIORITY.get(item.relevance_tier, 0),
            item.score,
            item.date,
        ),
        reverse=True,
    )


def screening_pool_multiplier(mode: str) -> int:
    return 2 if mode == "fast" else 4


def select_screening_pool(
    candidates: list[Candidate],
    count: int,
    pool_size: int,
    mode: str = "slow",
) -> list[Candidate]:
    multiplier = screening_pool_multiplier(mode)
    if pool_size > 0:
        max_pool_size = max(count, count * 8)
        target_pool_size = min(max(count, pool_size), max_pool_size)
    else:
        max_pool_size = max(count, count * multiplier)
        target_pool_size = min(max(count, pool_size), max_pool_size)
    return rank_for_screening(candidates)[:target_pool_size]


RATING_LEVELS = {"weak": 0, "maybe": 1, "strong": 2}


def candidate_is_final_eligible(
    candidate: Candidate,
    min_rating: str = "maybe",
    topic: str = "",
    exclude_keywords: str = "",
) -> bool:
    min_level = RATING_LEVELS.get(min_rating, RATING_LEVELS["maybe"])
    return (
        "mp.weixin.qq.com" in candidate.resolved_url
        and RATING_LEVELS.get(candidate.rating, 0) >= min_level
        and candidate_matches_core_topic(candidate, topic)
        and RELEVANCE_TIER_PRIORITY.get(candidate.relevance_tier, 0) >= RELEVANCE_TIER_PRIORITY["core_related"]
        and not candidate_matches_exclusion(candidate, exclude_keywords)
    )


def select_final_candidates(
    candidates: list[Candidate],
    count: int,
    min_rating: str = "maybe",
    topic: str = "",
    exclude_keywords: str = "",
) -> list[Candidate]:
    resolved = [
        candidate
        for candidate in candidates
        if candidate_is_final_eligible(candidate, min_rating, topic, exclude_keywords)
    ]
    return rank_for_final(resolved)[:count]


def sleep_random(min_delay: float, max_delay: float) -> None:
    delay = random.uniform(max(0, min_delay), max(min_delay, max_delay))
    time.sleep(delay)


def find_chrome_candidates() -> list[str]:
    explicit_browser = os.environ.get("CHROME_PATH", "")
    candidates = [
        explicit_browser,
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    found_items: list[str] = []
    for item in candidates:
        if item and Path(item).exists():
            found_items.append(item)
    command_names = ["chrome", "google-chrome", "chromium", "chromium-browser"]
    for name in command_names:
        found = shutil.which(name)
        if found and found not in found_items:
            found_items.append(found)
    return found_items


def find_chrome() -> str | None:
    candidates = find_chrome_candidates()
    return candidates[0] if candidates else None


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def browser_work_dir(prefix: str, port: int) -> Path:
    return Path(tempfile.gettempdir()) / "wechat-article-screening" / f"{prefix}-{port}"


def launch_chrome(
    chrome_path: str,
    port: int,
    profile_dir: Path,
    log_path: Path,
    headless: bool = False,
    visible: bool = False,
) -> subprocess.Popen[Any]:
    profile_dir = profile_dir.resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)
    args = [
        chrome_path,
        "--remote-debugging-address=127.0.0.1",
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f"--user-data-dir={profile_dir}",
        "--window-size=900,700",
        "--disable-gpu",
        "--disable-extensions",
        "--disable-component-extensions-with-background-pages",
        "--disable-dev-shm-usage",
        "--disable-crash-reporter",
        "--disable-crashpad",
        "--disable-breakpad",
        "--disable-logging",
        "--no-sandbox",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-mode",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-client-side-phishing-detection",
        "--disable-features=CalculateNativeWinOcclusion,RendererCodeIntegrity,NetworkServiceSandbox",
        "--disable-search-engine-choice-screen",
        "--disable-notifications",
        "--password-store=basic",
        "--disable-sync",
        "--disable-blink-features=AutomationControlled",
        "about:blank",
    ]
    if not visible:
        args.insert(8, "--window-position=-32000,-32000")
    if headless:
        args.insert(1, "--headless=new")
    creationflags = 0 if visible else getattr(subprocess, "CREATE_NO_WINDOW", 0)
    startupinfo = None
    if os.name == "nt" and not visible:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
    log_handle = log_path.open("ab")
    return subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=log_handle,
        creationflags=creationflags,
        startupinfo=startupinfo,
    )


def open_json(url: str, timeout: float = 5.0, method: str = "GET") -> Any:
    request = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_chrome(port: int, timeout: float = 25.0) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            open_json(f"http://127.0.0.1:{port}/json/version", timeout=1.0)
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.25)
    raise RuntimeError(f"Chrome debugging port did not open: {last_error}")


def verify_chrome_target(port: int) -> None:
    data = open_json(
        f"http://127.0.0.1:{port}/json/new?{urllib.parse.quote('about:blank', safe='')}",
        timeout=3.0,
        method="PUT",
    )
    if not data.get("webSocketDebuggerUrl"):
        raise RuntimeError("Chrome debugging target was not created")


def stop_process(proc: subprocess.Popen[Any] | None) -> None:
    if proc is None:
        return
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def launch_debug_browser(
    chrome_path: str | None,
    port: int,
    profile_dir: Path,
    visible: bool = False,
    allow_headless: bool = True,
) -> tuple[subprocess.Popen[Any], str, bool, str]:
    candidates = [chrome_path] if chrome_path else find_chrome_candidates()
    candidates = [item for item in candidates if item]
    if not candidates:
        raise RuntimeError("Chrome was not found. Install Chrome or set CHROME_PATH.")

    attempts: list[str] = []
    headless_options = (False, True) if allow_headless else (False,)
    for browser_path in candidates:
        for headless in headless_options:
            profile = profile_dir / (safe_name(Path(browser_path).stem) + ("-headless" if headless else ""))
            log_path = profile / "browser.log"
            proc: subprocess.Popen[Any] | None = None
            try:
                proc = launch_chrome(
                    browser_path,
                    port,
                    profile,
                    log_path=log_path,
                    headless=headless,
                    visible=visible,
                )
                wait_for_chrome(port)
                verify_chrome_target(port)
                return proc, browser_path, headless, str(log_path)
            except Exception as exc:
                exit_code = proc.poll() if proc else None
                detail = f"{Path(browser_path).name} {'headless' if headless else 'normal'}: {type(exc).__name__}: {exc}"
                if exit_code is not None:
                    detail += f"; exited={exit_code}"
                detail += f"; log={log_path}"
                attempts.append(detail)
                stop_process(proc)
    raise RuntimeError("All browser launch attempts failed. " + " | ".join(attempts))


def new_cdp_page(port: int) -> str:
    encoded_url = urllib.parse.quote("about:blank", safe="")
    endpoint = f"http://127.0.0.1:{port}/json/new?{encoded_url}"
    try:
        data = open_json(endpoint, method="PUT")
    except urllib.error.HTTPError:
        data = open_json(endpoint, method="GET")
    websocket_url = data.get("webSocketDebuggerUrl")
    if not websocket_url:
        raise RuntimeError("Chrome did not return a websocket URL")
    return websocket_url


class MiniWebSocket:
    def __init__(self, websocket_url: str) -> None:
        parsed = urllib.parse.urlparse(websocket_url)
        if parsed.scheme != "ws":
            raise RuntimeError(f"Only ws:// CDP URLs are supported: {websocket_url}")
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or 80
        self.path = parsed.path
        if parsed.query:
            self.path += f"?{parsed.query}"
        self.sock = socket.create_connection((self.host, self.port), timeout=10)
        self.sock.settimeout(10)
        self._handshake()

    def _handshake(self) -> None:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self.sock.sendall(request.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            response += chunk
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise RuntimeError("WebSocket handshake failed")

    def send_text(self, payload: str) -> None:
        data = payload.encode("utf-8")
        header = bytearray([0x81])
        length = len(data)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(data))
        self.sock.sendall(bytes(header) + masked)

    def recv_text(self) -> str:
        while True:
            first = self._recv_exact(2)
            opcode = first[0] & 0x0F
            masked = bool(first[1] & 0x80)
            length = first[1] & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._recv_exact(8))[0]
            mask = self._recv_exact(4) if masked else b""
            payload = self._recv_exact(length) if length else b""
            if masked:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            if opcode == 0x1:
                return payload.decode("utf-8", errors="replace")
            if opcode == 0x8:
                raise RuntimeError("WebSocket closed")
            if opcode == 0x9:
                self._send_pong(payload)

    def _send_pong(self, payload: bytes) -> None:
        header = bytearray([0x8A])
        header.append(0x80 | len(payload))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _recv_exact(self, length: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < length:
            chunk = self.sock.recv(length - len(chunks))
            if not chunk:
                raise RuntimeError("Socket closed")
            chunks.extend(chunk)
        return bytes(chunks)

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class CdpClient:
    def __init__(self, websocket_url: str) -> None:
        self.ws = MiniWebSocket(websocket_url)
        self.next_id = 1

    def call(self, method: str, params: dict[str, Any] | None = None, timeout: float = 12.0) -> Any:
        message_id = self.next_id
        self.next_id += 1
        self.ws.sock.settimeout(timeout)
        self.ws.send_text(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self.ws.recv_text())
            if message.get("id") == message_id:
                if "error" in message:
                    raise RuntimeError(f"CDP {method} failed: {message['error']}")
                return message.get("result")

    def evaluate(self, expression: str, timeout: float = 12.0) -> Any:
        result = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
            timeout=timeout,
        )
        value = result.get("result", {})
        return value.get("value")

    def close(self) -> None:
        self.ws.close()


def resolve_candidates_with_browser(
    candidates: list[Candidate],
    count: int,
    min_delay: float,
    max_delay: float,
    chrome_path: str | None,
    cookies: requests.cookies.RequestsCookieJar | None = None,
    target_verified_count: int = 0,
    min_rating: str = "maybe",
    topic: str = "",
    exclude_keywords: str = "",
) -> None:
    if not candidates:
        return

    for candidate in candidates[:count]:
        if "mp.weixin.qq.com" in candidate.resolved_url:
            setattr(candidate, "_resolved_url_for_recheck", candidate.resolved_url)
            candidate.resolved_url = ""
            candidate.resolve_status = "pending_recheck"

    port = free_port()
    profile_dir = browser_work_dir("chrome-research", port)
    proc: subprocess.Popen[Any] | None = None
    cdp: CdpClient | None = None
    keep_profile_dir = False
    try:
        try:
            proc, browser_path, headless, log_path = launch_debug_browser(
                chrome_path,
                port,
                profile_dir,
                visible=True,
                allow_headless=False,
            )
            print(
                "Browser verification using "
                f"{Path(browser_path).name} ({'headless' if headless else 'visible'}); log: {log_path}"
            )
            print("Complete any Sogou verification in the opened browser window if it appears.")
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            keep_profile_dir = True
            for candidate in candidates[:count]:
                candidate.resolve_status = f"browser_unavailable: {detail}"
            print(f"Browser verification failed: {detail}")
            print(f"Browser diagnostic files kept at: {profile_dir}")
            print("If an AI tool asks for permission to open a local browser, allow it and rerun this step.")
            return
        try:
            cdp = CdpClient(new_cdp_page(port))
            cdp.call("Network.enable")
            install_sogou_cookies(cdp, cookies)
            cdp.call("Page.enable")
            cdp.call("Runtime.enable")
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            for candidate in candidates[:count]:
                if not candidate.resolve_status or candidate.resolve_status == "pending":
                    candidate.resolve_status = f"browser_unavailable: {detail}"
            print(f"Browser verification unavailable after launch: {detail}")
            print("Continuing with collected search candidates instead of failing the whole run.")
            return

        for index, candidate in enumerate(candidates[:count], start=1):
            if target_verified_count > 0:
                verified_count = sum(
                    1
                    for item in candidates[:count]
                    if candidate_is_final_eligible(item, min_rating, topic, exclude_keywords)
                )
                if verified_count >= target_verified_count:
                    print(
                        "Eligible target reached "
                        f"({verified_count}/{target_verified_count}); stopping browser verification early."
                    )
                    break
            if candidate.resolved_url:
                continue
            print(f"Verify {index}/{min(count, len(candidates))}: {candidate.title[:50]}")
            try:
                resolve_one_candidate(cdp, candidate, min_delay, max_delay)
            except Exception as exc:
                candidate.resolve_status = f"failed: {type(exc).__name__}: {exc}"
            sleep_random(min_delay, max_delay)
    finally:
        if cdp:
            try:
                cdp.close()
            except Exception:
                pass
        stop_process(proc)
        if not keep_profile_dir:
            shutil.rmtree(profile_dir, ignore_errors=True)


def resolve_one_candidate(cdp: CdpClient, candidate: Candidate, min_delay: float, max_delay: float) -> None:
    recheck_url = getattr(candidate, "_resolved_url_for_recheck", "")
    if "mp.weixin.qq.com" in recheck_url:
        direct_status, direct_url = navigate_and_extract_wechat(cdp, recheck_url, min_delay, max_delay)
        if direct_url:
            candidate.resolved_url = direct_url
        candidate.resolve_status = direct_status
        return

    if "mp.weixin.qq.com" in candidate.sogou_url:
        direct_status, direct_url = navigate_and_extract_wechat(cdp, candidate.sogou_url, min_delay, max_delay)
        if direct_url:
            candidate.resolved_url = direct_url
        candidate.resolve_status = direct_status
        return

    direct_status, direct_url = navigate_and_extract_wechat(cdp, candidate.sogou_url, min_delay, max_delay)
    if direct_url:
        candidate.resolved_url = direct_url
        candidate.resolve_status = direct_status
        return

    if not candidate.search_url:
        candidate.resolve_status = direct_status
        return

    cdp.call("Page.navigate", {"url": candidate.search_url}, timeout=20)
    sleep_random(min_delay, max_delay)

    target = json.dumps(normalize_text(candidate.title), ensure_ascii=False)
    expression = f"""
(() => {{
  const target = {target};
  const norm = (s) => (s || "").replace(/\\s+/g, "");
  const anchors = Array.from(document.querySelectorAll("a"));
  let link = anchors.find((a) => norm(a.innerText) === target);
  if (!link) {{
    link = anchors.find((a) => {{
      const text = norm(a.innerText);
      return text && (text.includes(target.slice(0, 18)) || target.includes(text.slice(0, 18)));
    }});
  }}
  if (!link) {{
    return {{status: "not_found", location: location.href, title: document.title}};
  }}
  link.dispatchEvent(new MouseEvent("mousedown", {{bubbles: true, cancelable: true, view: window}}));
  return {{status: "found", href: link.href, text: link.innerText}};
}})()
"""
    clicked = cdp.evaluate(expression)
    if not clicked or clicked.get("status") != "found" or not clicked.get("href"):
        candidate.resolve_status = direct_status if direct_status == "blocked_by_sogou" else "not_found_on_search_page"
        return

    fallback_status, fallback_url = navigate_and_extract_wechat(cdp, clicked["href"], min_delay, max_delay)
    if fallback_url:
        candidate.resolved_url = fallback_url
    candidate.resolve_status = fallback_status


def browser_safe_url(url: str) -> str:
    return urllib.parse.quote((url or "").strip(), safe=":/?&=%#._~+-")


def navigate_and_extract_wechat(
    cdp: CdpClient,
    url: str,
    min_delay: float,
    max_delay: float,
    allow_html_extract: bool = True,
) -> tuple[str, str]:
    cdp.call("Page.navigate", {"url": browser_safe_url(url)}, timeout=20)
    sleep_random(min_delay, max_delay)
    final = cdp.evaluate(
        """
(() => ({
  url: location.href,
  title: document.title,
  text: document.body ? document.body.innerText.slice(0, 30000) : "",
  html: document.documentElement.innerHTML.slice(0, 80000),
  hasContent: !!document.getElementById("js_content")
}))()
""",
        timeout=20,
    )
    final_url = (final or {}).get("url", "")
    final_html = (final or {}).get("html", "")
    final_text = (final or {}).get("text", "")
    if "mp.weixin.qq.com" in final_url:
        marker = unavailable_wechat_marker(f"{final_text}\n{final_html}")
        if marker:
            return f"wechat_unavailable: {marker}", ""
        if not (final or {}).get("hasContent"):
            return "wechat_unavailable: content_not_found", ""
        return "resolved", final_url

    if not allow_html_extract:
        return "not_wechat_url", ""

    match = re.search(r"https://mp\.weixin\.qq\.com/s/[A-Za-z0-9_-]+", final_html)
    if match:
        nested_status, nested_url = navigate_and_extract_wechat(
            cdp,
            match.group(0),
            min_delay,
            max_delay,
            allow_html_extract=False,
        )
        if nested_url:
            return "resolved_from_html", nested_url
        return nested_status, ""

    if "antispider" in final_url or "请输入验证码" in final_html:
        return "blocked_by_sogou", ""
    return "not_wechat_url", ""


def install_sogou_cookies(
    cdp: CdpClient,
    cookies: requests.cookies.RequestsCookieJar | None,
) -> None:
    if not cookies:
        return
    for cookie in cookies:
        domain = cookie.domain or ".sogou.com"
        if domain.startswith("."):
            cookie_url = f"https://weixin{domain}/"
        else:
            cookie_url = f"https://{domain}/"
        params = {
            "name": cookie.name,
            "value": cookie.value,
            "url": cookie_url,
            "path": cookie.path or "/",
        }
        try:
            cdp.call("Network.setCookie", params, timeout=5)
        except Exception:
            continue


def write_outputs(
    candidates: list[Candidate],
    topic: str,
    output_dir: Path,
    pool_candidates: list[Candidate] | None = None,
) -> tuple[Path, Path, Path | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    base = f"{now_stamp()}-{safe_name(topic)}"
    csv_path = output_dir / f"{base}.csv"
    md_path = output_dir / f"{base}.md"
    pool_csv_path = output_dir / f"{base}-screened-pool.csv" if pool_candidates is not None else None

    fields = [
        "relevance_tier",
        "rating",
        "score",
        "title",
        "source",
        "date",
        "resolved_url",
        "resolve_status",
        "sogou_url",
        "search_query",
        "reason",
        "snippet",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for candidate in candidates:
            writer.writerow({field: getattr(candidate, field) for field in fields})

    with md_path.open("w", encoding="utf-8-sig") as handle:
        handle.write(f"# WeChat article candidates: {topic}\n\n")
        handle.write(f"Generated at: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        handle.write("| # | Tier | Rating | Score | Title | Account | Date | Status | Reason | URL |\n")
        handle.write("|---:|---|---|---:|---|---|---|---|---|---|\n")
        for index, candidate in enumerate(candidates, start=1):
            url = candidate.resolved_url or candidate.sogou_url
            title = markdown_cell(candidate.title)
            source = markdown_cell(candidate.source)
            status = markdown_cell(candidate.resolve_status)
            reason = markdown_cell(candidate.reason)
            handle.write(
                f"| {index} | {candidate.relevance_tier} | {candidate.rating} | {candidate.score} | "
                f"[{title}]({url}) | {source} | {candidate.date} | {status} | {reason} | "
                f"[link]({url}) |\n"
            )
    if pool_csv_path is not None and pool_candidates is not None:
        selected_urls = {candidate.resolved_url for candidate in candidates if candidate.resolved_url}
        pool_fields = ["selected"] + fields
        with pool_csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=pool_fields)
            writer.writeheader()
            for candidate in pool_candidates:
                row = {field: getattr(candidate, field) for field in fields}
                row["selected"] = "yes" if candidate.resolved_url in selected_urls else "no"
                writer.writerow(row)
    return csv_path, md_path, pool_csv_path


def load_candidates_from_csv(csv_path: Path) -> list[Candidate]:
    candidates: list[Candidate] = []
    with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            resolved_url = (row.get("resolved_url") or "").strip()
            resolve_status = (row.get("resolve_status") or "pending").strip()
            if "mp.weixin.qq.com" not in resolved_url:
                resolved_url = ""
                resolve_status = "pending"
            try:
                score = int(row.get("score") or 0)
            except ValueError:
                score = 0
            candidates.append(
                Candidate(
                    title=(row.get("title") or "").strip(),
                    snippet=(row.get("snippet") or "").strip(),
                    source=(row.get("source") or "").strip(),
                    date=(row.get("date") or "").strip(),
                    search_query=(row.get("search_query") or "").strip(),
                    search_url=(row.get("search_url") or "").strip(),
                    sogou_url=(row.get("sogou_url") or "").strip(),
                    score=score,
                    rating=(row.get("rating") or "weak").strip(),
                    reason=(row.get("reason") or "").strip(),
                    relevance_tier=(row.get("relevance_tier") or "weak").strip(),
                    resolved_url=resolved_url,
                    resolve_status=resolve_status,
                )
            )
    return [candidate for candidate in candidates if candidate.title and candidate.sogou_url]


def markdown_cell(value: str) -> str:
    return (value or "").replace("|", "\\|").replace("\n", " ").strip()


def write_urls_file(candidates: list[Candidate], urls_path: Path, count: int) -> int:
    urls = []
    seen: set[str] = set()
    for candidate in candidates:
        url = candidate.resolved_url
        if "mp.weixin.qq.com" not in url:
            continue
        if url in seen:
            continue
        urls.append(url)
        seen.add(url)
        if len(urls) >= count:
            break

    urls_path.write_text("\n".join(urls) + ("\n" if urls else ""), encoding="utf-8")
    return len(urls)


def load_params_file(args: argparse.Namespace) -> argparse.Namespace:
    params_file = getattr(args, "params_file", None)
    if not params_file:
        return args
    try:
        data = json.loads(Path(params_file).read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise ValueError(f"Could not read --params-file {params_file}: {exc}") from exc

    mapping = {
        "topic": "topic",
        "count": "count",
        "mode": "mode",
        "pool_size": "pool_size",
        "max_queries": "max_queries",
        "top_per_query": "top_per_query",
        "extra_keywords": "extra_keywords",
        "exclude_keywords": "exclude_keywords",
        "min_rating": "min_rating",
        "start_date": "start_date",
        "end_date": "end_date",
        "write_urls": "write_urls",
        "urls_file": "urls_file",
        "no_browser": "no_browser",
        "chrome_path": "chrome_path",
        "sogou_verify_timeout": "sogou_verify_timeout",
        "search_cache_dir": "search_cache_dir",
        "cache_ttl_hours": "cache_ttl_hours",
        "continue_after_block": "continue_after_block",
        "stop_on_block": "stop_on_block",
        "stop_after_empty_rounds": "stop_after_empty_rounds",
        "min_delay": "min_delay",
        "max_delay": "max_delay",
        "timeout": "timeout",
    }
    for key, attribute in mapping.items():
        if key in data and data[key] not in (None, ""):
            value = data[key]
            if attribute in {"urls_file"}:
                value = Path(value)
            if attribute in {"search_cache_dir"}:
                value = Path(value)
            setattr(args, attribute, value)
    return args


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search and verify WeChat article URLs.")
    parser.add_argument("--params-file", type=Path, default=None, help="UTF-8 JSON file containing search parameters")
    parser.add_argument("--topic", default="", help="Research topic, for example: AI hardware")
    parser.add_argument("--count", type=int, default=20, help="Number of final candidates to keep")
    parser.add_argument("--mode", choices=["fast", "slow"], default="slow", help="Search effort mode. fast is one bounded pass; slow searches broader. Default: slow")
    parser.add_argument("--pool-size", type=int, default=0, help="How many screened candidates to resolve before final selection. Capped by mode.")
    parser.add_argument("--extra-keywords", default="", help="Optional comma/space separated keywords")
    parser.add_argument("--exclude-keywords", default="", help="Optional comma/space separated terms to downrank and exclude from final URLs")
    parser.add_argument("--min-rating", choices=["weak", "maybe", "strong"], default="maybe", help="Minimum rating for final URLs. Default: maybe")
    parser.add_argument("--start-date", default="", help="Keep articles on or after this date, YYYY-MM-DD")
    parser.add_argument("--end-date", default="", help="Keep articles on or before this date, YYYY-MM-DD")
    parser.add_argument("--max-queries", type=int, default=0, help="How many search phrases to try. Default depends on --mode")
    parser.add_argument("--top-per-query", type=int, default=0, help="How many results to read from each search. Default depends on --mode")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--candidate-csv", type=Path, default=None, help="Reuse an existing candidate CSV and only rerun filtering/browser verification")
    parser.add_argument("--write-urls", action="store_true", help="Overwrite urls.txt with verified WeChat URLs")
    parser.add_argument("--urls-file", type=Path, default=DEFAULT_URLS_FILE)
    parser.add_argument("--no-browser", action="store_true", help="Skip browser-based Sogou search verification and redirect verification")
    parser.add_argument("--chrome-path", default=None, help="Optional Chrome executable path")
    parser.add_argument("--sogou-verify-timeout", type=int, default=180, help="Seconds to wait for manual Sogou verification in the opened browser")
    parser.add_argument("--search-cache-dir", type=Path, default=DEFAULT_SEARCH_CACHE_DIR, help="Directory for cached Sogou search result pages")
    parser.add_argument("--cache-ttl-hours", type=float, default=12, help="How long to reuse cached Sogou search pages. Set 0 to disable")
    parser.add_argument("--continue-after-block", action="store_true", help="Keep trying remaining queries after Sogou blocks a request")
    parser.add_argument("--stop-after-empty-rounds", type=int, default=2, help="Stop after this many keyword rounds add no screenable candidates")
    parser.add_argument("--min-delay", type=float, default=1.0, help="Minimum random delay in seconds")
    parser.add_argument("--max-delay", type=float, default=3.0, help="Maximum random delay in seconds")
    parser.add_argument("--timeout", type=int, default=15, help="Search request timeout in seconds")
    try:
        args = load_params_file(parser.parse_args(argv))
    except ValueError as exc:
        parser.error(str(exc))
    if hasattr(args, "stop_on_block"):
        args.continue_after_block = not bool(getattr(args, "stop_on_block"))
    if not args.topic:
        parser.error("--topic is required unless it is provided by --params-file")
    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.count <= 0:
        print("Invalid count: --count must be greater than 0")
        return 2
    if args.max_delay < args.min_delay:
        args.max_delay = args.min_delay
    default_max_queries = 5 if args.mode == "fast" else 12
    default_top_per_query = 8 if args.mode == "fast" else 10
    max_queries = args.max_queries if args.max_queries > 0 else default_max_queries
    top_per_query = args.top_per_query if args.top_per_query > 0 else default_top_per_query
    pool_multiplier = screening_pool_multiplier(args.mode)
    pool_size = args.pool_size if args.pool_size > 0 else args.count * pool_multiplier
    try:
        start_date = parse_date_arg(args.start_date, "--start-date")
        end_date = parse_date_arg(args.end_date, "--end-date")
    except ValueError as exc:
        print(f"Invalid date range: {exc}")
        return 2
    if start_date and end_date and start_date > end_date:
        print("Invalid date range: --start-date cannot be later than --end-date")
        return 2

    print(f"Topic: {args.topic}")
    print("Screening mode: general")
    print(
        f"Mode: {args.mode} "
        f"(max_queries={max_queries}, top_per_query={top_per_query}, pool_cap={pool_size}, result_cap={args.count})"
    )
    if start_date or end_date:
        print(
            "Date range: "
            f"{start_date.isoformat() if start_date else 'any'} to "
            f"{end_date.isoformat() if end_date else 'any'}"
        )
    if args.exclude_keywords:
        print(f"Local memory exclusions: {args.exclude_keywords}")
    if args.candidate_csv:
        if not args.candidate_csv.exists():
            print(f"Candidate CSV was not found: {args.candidate_csv}")
            return 2
        print(f"Loading existing candidates: {args.candidate_csv}")
        candidates = load_candidates_from_csv(args.candidate_csv)
        sogou_cookies = requests.cookies.RequestsCookieJar()
        print(f"Loaded {len(candidates)} candidates from CSV.")
    else:
        print("Collecting candidates...")
        try:
            candidates, sogou_cookies = collect_candidates(
                topic=args.topic,
                extra_keywords=args.extra_keywords,
                exclude_keywords=args.exclude_keywords,
                max_queries=max_queries,
                top_per_query=top_per_query,
                timeout=args.timeout,
                min_delay=args.min_delay,
                max_delay=args.max_delay,
                start_date=start_date,
                end_date=end_date,
                browser_search=not args.no_browser,
                chrome_path=args.chrome_path,
                verification_timeout=args.sogou_verify_timeout,
                search_cache_dir=args.search_cache_dir,
            cache_ttl_hours=args.cache_ttl_hours,
            stop_on_block=not args.continue_after_block,
            target_screening_count=pool_size,
            stop_after_empty_rounds=args.stop_after_empty_rounds,
        )
        except RuntimeError as exc:
            print(f"Search collection failed: {exc}")
            return 1
        print(f"Collected {len(candidates)} unique candidates.")

    before_date_filter = len(candidates)
    candidates = filter_candidates_by_date(candidates, start_date, end_date)
    if start_date or end_date:
        print(f"Date filter kept {len(candidates)} of {before_date_filter} candidates.")

    core_terms = core_topic_terms(args.topic)
    if core_terms:
        before_core_filter = len(candidates)
        core_candidates = [candidate for candidate in candidates if candidate_matches_core_topic(candidate, args.topic)]
        if core_candidates:
            candidates = core_candidates
            print(
                "Core topic filter "
                f"({', '.join(core_terms)}) kept {len(candidates)} of {before_core_filter} candidates."
            )

    intent_terms = required_intent_terms(args.topic)
    if intent_terms:
        intent_candidates = [
            candidate for candidate in candidates if candidate_matches_required_intent(candidate, args.topic)
        ]
        print(
            "Required intent signal "
            f"({', '.join(intent_terms)}) matched {len(intent_candidates)} of {len(candidates)} candidates; "
            "keeping broader core-related candidates for recall."
        )

    screening_pool = select_screening_pool(candidates, args.count, pool_size, mode=args.mode)
    print(f"Screening pool: {len(screening_pool)} candidates for {args.count} result cap.")

    if not args.no_browser:
        print("Verifying redirect links in Chrome...")
        resolve_candidates_with_browser(
            screening_pool,
            count=len(screening_pool),
            min_delay=args.min_delay,
            max_delay=args.max_delay,
            chrome_path=args.chrome_path,
            cookies=sogou_cookies,
            target_verified_count=args.count,
            min_rating=args.min_rating,
            topic=args.topic,
            exclude_keywords=args.exclude_keywords,
        )
        screening_pool = dedupe_candidates(screening_pool)

    screening_pool = filter_candidates_by_date(screening_pool, start_date, end_date)
    resolved_count = sum(1 for candidate in screening_pool if "mp.weixin.qq.com" in candidate.resolved_url)
    print(f"Resolved WeChat URLs before final quality filter: {resolved_count}.")
    final_candidates = select_final_candidates(
        screening_pool,
        args.count,
        min_rating=args.min_rating,
        topic=args.topic,
        exclude_keywords=args.exclude_keywords,
    )
    if len(final_candidates) < args.count:
        print(
            f"Only {len(final_candidates)} verified WeChat URLs with rating >= {args.min_rating} "
            f"were found under the result cap {args.count}."
        )
    csv_path, md_path, pool_csv_path = write_outputs(
        final_candidates,
        args.topic,
        args.output_dir,
        pool_candidates=screening_pool,
    )

    print(f"Candidate CSV: {csv_path}")
    print(f"Candidate Markdown: {md_path}")
    if pool_csv_path:
        print(f"Screened pool CSV: {pool_csv_path}")
    if args.write_urls:
        written = write_urls_file(final_candidates, args.urls_file, args.count)
        print(f"Wrote {written} verified URLs to {args.urls_file}")
    else:
        print("urls.txt was not changed. Add --write-urls when you want to replace it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
