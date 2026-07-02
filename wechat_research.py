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
]
MARKETING_QUERY_SUFFIXES = [
    "品牌营销",
    "营销案例",
    "品牌案例",
    "商业化",
    "增长",
    "消费者",
    "内容营销",
    "新品",
    "投放",
    "传播",
]
MARKETING_HINT_TERMS = [
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
    + MARKETING_HINT_TERMS
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
    resolved_url: str = ""
    resolve_status: str = "pending"

    def key(self) -> str:
        if self.resolved_url:
            return self.resolved_url
        return f"{normalize_text(self.title)}::{normalize_text(self.source)}"


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value or "").strip()


def strip_tags(value: str) -> str:
    value = re.sub(r"(?is)<script.*?</script>", " ", value)
    value = re.sub(r"(?is)<style.*?</style>", " ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


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


def resolve_focus(topic: str, extra_keywords: str, focus: str = "auto") -> str:
    if focus in {"general", "marketing"}:
        return focus
    blob = f"{topic} {extra_keywords}"
    if any(term in blob for term in MARKETING_HINT_TERMS):
        return "marketing"
    return "general"


def generate_queries(
    topic: str,
    extra_keywords: str,
    max_queries: int,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
    focus: str = "auto",
) -> list[str]:
    years = years_from_range(start_date, end_date)
    resolved_focus = resolve_focus(topic, extra_keywords, focus)
    suffixes = list(GENERAL_QUERY_SUFFIXES)
    if resolved_focus == "marketing":
        suffixes = MARKETING_QUERY_SUFFIXES + suffixes

    parts = [topic.strip()]
    for year in years:
        parts.append(f"{topic} {year}")
    for suffix in suffixes:
        if years:
            for year in years:
                parts.append(f"{topic} {suffix} {year}")
        else:
            parts.append(f"{topic} {suffix}")
    for word in re.split(r"[,，\s]+", extra_keywords or ""):
        word = word.strip()
        if word:
            if years:
                for year in years:
                    parts.append(f"{topic} {word} {year}")
            else:
                parts.append(f"{topic} {word}")

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


def score_candidate(candidate: Candidate, topic: str, focus: str = "auto", extra_keywords: str = "") -> None:
    title_blob = f"{candidate.title} {candidate.snippet}"
    compact_blob = normalize_text(title_blob)
    compact_topic = normalize_text(topic)
    source_blob = candidate.source
    query_blob = candidate.search_query
    resolved_focus = resolve_focus(topic, extra_keywords, focus)
    reasons: list[str] = []
    score = 0
    core_terms = core_topic_terms(topic)
    has_core_match = any(term in compact_blob for term in core_terms)
    required_terms = required_intent_terms(topic)
    has_required_intent = not required_terms or any(
        normalize_text(term) in compact_blob for term in required_terms
    )

    if compact_topic and compact_topic in compact_blob:
        score += 4
        reasons.append("direct topic match")
    elif has_core_match:
        score += 2
        reasons.append("core topic match")
    if required_terms and has_required_intent:
        score += 1
        reasons.append("required intent match")

    if any(term in candidate.title for term in VALUE_TERMS):
        score += 3
        reasons.append("title value signal")
    if any(term in candidate.snippet for term in VALUE_TERMS):
        score += 2
        reasons.append("snippet value signal")
    if any(term in query_blob for term in VALUE_TERMS):
        score += 1
        reasons.append("value query signal")
    if len(normalize_text(candidate.snippet)) >= SUBSTANTIVE_SNIPPET_MIN_LENGTH:
        score += 1
        reasons.append("substantive snippet")
    if resolved_focus == "marketing" and any(term in candidate.title for term in BRAND_CASE_TERMS):
        score += 2
        reasons.append("marketing signal")
    if resolved_focus == "marketing" and any(term in candidate.snippet for term in BRAND_CASE_TERMS):
        score += 1
        reasons.append("snippet marketing signal")
    source_terms = GENERAL_SOURCE_TERMS + (GOOD_SOURCES if resolved_focus == "marketing" else [])
    if any(term in source_blob for term in source_terms):
        score += 2
        reasons.append("relevant account")
    if any(term in title_blob for term in NOISE_TERMS):
        score -= 4
        reasons.append("possible noise")
    if any(term in candidate.title for term in LOW_VALUE_TERMS):
        score -= 4
        reasons.append("low-value format")
    if core_terms and not has_core_match and compact_topic not in compact_blob:
        score -= 4
        reasons.append("missing core topic")
    if not has_required_intent:
        score -= 4
        reasons.append("missing required intent")

    candidate.score = score
    if score >= 8:
        candidate.rating = "strong"
    elif score >= 4:
        candidate.rating = "maybe"
    else:
        candidate.rating = "weak"
    candidate.reason = ", ".join(reasons) or "low signal"


def fetch_sogou_results(session: requests.Session, query: str, timeout: int) -> str:
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
    return response.text


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


def collect_candidates(
    topic: str,
    extra_keywords: str,
    max_queries: int,
    top_per_query: int,
    timeout: int,
    min_delay: float,
    max_delay: float,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
    focus: str = "auto",
) -> tuple[list[Candidate], requests.cookies.RequestsCookieJar]:
    session = requests.Session()
    session.trust_env = False
    queries = generate_queries(topic, extra_keywords, max_queries, start_date, end_date, focus)
    collected: list[Candidate] = []

    for index, query in enumerate(queries, start=1):
        print(f"Search {index}/{len(queries)}: {query}")
        try:
            page = fetch_sogou_results(session, query, timeout)
            results = parse_sogou_results(page, query)[:top_per_query]
        except Exception as exc:
            print(f"  search failed: {type(exc).__name__}: {exc}")
            results = []
        for candidate in results:
            score_candidate(candidate, topic, focus=focus, extra_keywords=extra_keywords)
        collected.extend(results)
        if index < len(queries):
            sleep_random(min_delay, max_delay)

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


def rank_for_screening(candidates: list[Candidate]) -> list[Candidate]:
    return sorted(candidates, key=lambda item: (item.score, item.date), reverse=True)


def rank_for_final(candidates: list[Candidate]) -> list[Candidate]:
    return sorted(
        candidates,
        key=lambda item: (
            1 if "mp.weixin.qq.com" in item.resolved_url else 0,
            item.score,
            item.date,
        ),
        reverse=True,
    )


def select_screening_pool(candidates: list[Candidate], count: int, pool_size: int) -> list[Candidate]:
    target_pool_size = max(count, pool_size)
    return rank_for_screening(candidates)[:target_pool_size]


RATING_LEVELS = {"weak": 0, "maybe": 1, "strong": 2}


def select_final_candidates(
    candidates: list[Candidate],
    count: int,
    min_rating: str = "maybe",
    topic: str = "",
) -> list[Candidate]:
    min_level = RATING_LEVELS.get(min_rating, RATING_LEVELS["maybe"])
    resolved = [
        candidate
        for candidate in candidates
        if "mp.weixin.qq.com" in candidate.resolved_url
        and RATING_LEVELS.get(candidate.rating, 0) >= min_level
        and candidate_matches_core_topic(candidate, topic)
        and candidate_matches_required_intent(candidate, topic)
    ]
    return rank_for_final(resolved)[:count]


def sleep_random(min_delay: float, max_delay: float) -> None:
    delay = random.uniform(max(0, min_delay), max(min_delay, max_delay))
    time.sleep(delay)


def find_chrome() -> str | None:
    candidates = [
        os.environ.get("CHROME_PATH", ""),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for item in candidates:
        if item and Path(item).exists():
            return item
    for name in ["chrome", "msedge", "google-chrome", "chromium", "chromium-browser"]:
        found = shutil.which(name)
        if found:
            return found
    return None


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def launch_chrome(chrome_path: str, port: int, profile_dir: Path) -> subprocess.Popen[Any]:
    profile_dir = profile_dir.resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)
    args = [
        chrome_path,
        "--remote-debugging-address=127.0.0.1",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--window-position=-32000,-32000",
        "--window-size=900,700",
        "--disable-gpu",
        "--disable-extensions",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "about:blank",
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    startupinfo = None
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
    return subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
        startupinfo=startupinfo,
    )


def open_json(url: str, timeout: float = 5.0, method: str = "GET") -> Any:
    request = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_chrome(port: int, timeout: float = 10.0) -> None:
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
) -> None:
    if not candidates:
        return

    chrome = chrome_path or find_chrome()
    if not chrome:
        print("Browser verification skipped: Chrome or Edge was not found.")
        return

    port = free_port()
    profile_dir = Path("work") / f"chrome-research-{port}"
    proc = launch_chrome(chrome, port, profile_dir)
    cdp: CdpClient | None = None
    try:
        try:
            wait_for_chrome(port)
        except Exception as exc:
            exit_code = proc.poll()
            detail = f"{type(exc).__name__}: {exc}"
            if exit_code is not None:
                detail += f"; browser exited with code {exit_code}"
            for candidate in candidates[:count]:
                candidate.resolve_status = f"browser_unavailable: {detail}"
            print(f"Browser verification skipped: {detail}")
            return
        cdp = CdpClient(new_cdp_page(port))
        cdp.call("Network.enable")
        install_sogou_cookies(cdp, cookies)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")

        for index, candidate in enumerate(candidates[:count], start=1):
            print(f"Verify {index}/{min(count, len(candidates))}: {candidate.title[:50]}")
            try:
                resolve_one_candidate(cdp, candidate, min_delay, max_delay)
            except Exception as exc:
                candidate.resolve_status = f"failed: {type(exc).__name__}: {exc}"
            sleep_random(min_delay, max_delay)
    finally:
        if cdp:
            cdp.close()
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


def resolve_one_candidate(cdp: CdpClient, candidate: Candidate, min_delay: float, max_delay: float) -> None:
    if "mp.weixin.qq.com" in candidate.sogou_url:
        candidate.resolved_url = candidate.sogou_url
        candidate.resolve_status = "direct"
        return

    direct_status, direct_url = navigate_and_extract_wechat(cdp, candidate.sogou_url, min_delay, max_delay)
    if direct_url:
        candidate.resolved_url = direct_url
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


def navigate_and_extract_wechat(
    cdp: CdpClient,
    url: str,
    min_delay: float,
    max_delay: float,
) -> tuple[str, str]:
    cdp.call("Page.navigate", {"url": url}, timeout=20)
    sleep_random(min_delay, max_delay)
    final = cdp.evaluate(
        """
(() => ({
  url: location.href,
  title: document.title,
  html: document.documentElement.innerHTML.slice(0, 12000)
}))()
""",
        timeout=20,
    )
    final_url = (final or {}).get("url", "")
    final_html = (final or {}).get("html", "")
    if "mp.weixin.qq.com" in final_url:
        return "resolved", final_url

    match = re.search(r"https://mp\.weixin\.qq\.com/s/[A-Za-z0-9_-]+", final_html)
    if match:
        return "resolved_from_html", match.group(0)

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
        handle.write("| # | Rating | Score | Title | Account | Date | Status | Reason | URL |\n")
        handle.write("|---:|---|---:|---|---|---|---|---|---|\n")
        for index, candidate in enumerate(candidates, start=1):
            url = candidate.resolved_url or candidate.sogou_url
            title = markdown_cell(candidate.title)
            source = markdown_cell(candidate.source)
            status = markdown_cell(candidate.resolve_status)
            reason = markdown_cell(candidate.reason)
            handle.write(
                f"| {index} | {candidate.rating} | {candidate.score} | "
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


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search and verify WeChat article URLs.")
    parser.add_argument("--topic", required=True, help="Research topic, for example: AI hardware marketing")
    parser.add_argument("--count", type=int, default=20, help="Number of final candidates to keep")
    parser.add_argument("--pool-size", type=int, default=0, help="How many screened candidates to resolve before final selection. Default: about count * 1.5")
    parser.add_argument("--extra-keywords", default="", help="Optional comma/space separated keywords")
    parser.add_argument("--focus", choices=["auto", "general", "marketing"], default="auto", help="Scoring/query preset. Default: auto")
    parser.add_argument("--min-rating", choices=["weak", "maybe", "strong"], default="maybe", help="Minimum rating for final URLs. Default: maybe")
    parser.add_argument("--start-date", default="", help="Keep articles on or after this date, YYYY-MM-DD")
    parser.add_argument("--end-date", default="", help="Keep articles on or before this date, YYYY-MM-DD")
    parser.add_argument("--max-queries", type=int, default=8, help="How many search phrases to try")
    parser.add_argument("--top-per-query", type=int, default=10, help="How many results to read from each search")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--write-urls", action="store_true", help="Overwrite urls.txt with verified WeChat URLs")
    parser.add_argument("--urls-file", type=Path, default=DEFAULT_URLS_FILE)
    parser.add_argument("--no-browser", action="store_true", help="Skip hidden browser verification")
    parser.add_argument("--chrome-path", default=None, help="Optional Chrome or Edge executable path")
    parser.add_argument("--min-delay", type=float, default=1.0, help="Minimum random delay in seconds")
    parser.add_argument("--max-delay", type=float, default=3.0, help="Maximum random delay in seconds")
    parser.add_argument("--timeout", type=int, default=15, help="Search request timeout in seconds")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.count <= 0:
        print("Invalid count: --count must be greater than 0")
        return 2
    if args.max_delay < args.min_delay:
        args.max_delay = args.min_delay
    pool_size = args.pool_size if args.pool_size > 0 else args.count + max(4, args.count // 2)
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
    print(f"Focus: {resolve_focus(args.topic, args.extra_keywords, args.focus)}")
    if start_date or end_date:
        print(
            "Date range: "
            f"{start_date.isoformat() if start_date else 'any'} to "
            f"{end_date.isoformat() if end_date else 'any'}"
        )
    print("Collecting candidates...")
    candidates, sogou_cookies = collect_candidates(
        topic=args.topic,
        extra_keywords=args.extra_keywords,
        max_queries=args.max_queries,
        top_per_query=args.top_per_query,
        timeout=args.timeout,
        min_delay=args.min_delay,
        max_delay=args.max_delay,
        start_date=start_date,
        end_date=end_date,
        focus=args.focus,
    )
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
        before_intent_filter = len(candidates)
        intent_candidates = [
            candidate for candidate in candidates if candidate_matches_required_intent(candidate, args.topic)
        ]
        if intent_candidates:
            candidates = intent_candidates
            print(
                "Required intent filter "
                f"({', '.join(intent_terms)}) kept {len(candidates)} of {before_intent_filter} candidates."
            )

    screening_pool = select_screening_pool(candidates, args.count, pool_size)
    print(f"Screening pool: {len(screening_pool)} candidates for {args.count} final URLs.")

    if not args.no_browser:
        print("Verifying redirect links in a hidden browser...")
        resolve_candidates_with_browser(
            screening_pool,
            count=len(screening_pool),
            min_delay=args.min_delay,
            max_delay=args.max_delay,
            chrome_path=args.chrome_path,
            cookies=sogou_cookies,
        )
        screening_pool = dedupe_candidates(screening_pool)

    screening_pool = filter_candidates_by_date(screening_pool, start_date, end_date)
    final_candidates = select_final_candidates(
        screening_pool,
        args.count,
        min_rating=args.min_rating,
        topic=args.topic,
    )
    if len(final_candidates) < args.count:
        print(
            f"Only {len(final_candidates)} verified WeChat URLs with rating >= {args.min_rating} "
            f"were found for the requested {args.count}."
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
