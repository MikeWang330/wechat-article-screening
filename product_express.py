#!/usr/bin/env python3
"""New beverage product report helpers.

This module deliberately keeps network-dependent collection outside the core
report writer. The local web app can reuse the existing WeChat search pipeline,
then call these helpers to produce a structured product report from whatever
verified evidence was actually found.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "product_reports"
DATA_DIR = ROOT / "data"
DISCOVERY_FILE = DATA_DIR / "new_product_discoveries.json"

DEFAULT_PRODUCT_KEYWORDS = [
    "新品",
    "上新",
    "饮料新品",
    "新口味",
    "新包装",
    "限定口味",
    "0糖新品",
    "无糖茶新品",
    "茶饮新品",
    "气泡水新品",
    "电解质水新品",
    "功能饮料新品",
    "果汁新品",
    "咖啡新品",
    "元气森林新品",
    "农夫山泉新品",
    "东方树叶新品",
    "可口可乐新品",
    "百事新品",
    "娃哈哈新品",
    "统一新品",
    "康师傅新品",
    "雀巢新品",
    "伊利新品",
    "蒙牛新品",
]

EXCLUDE_HINTS = [
    "招聘",
    "课程",
    "资料包下载",
    "纯新闻快讯",
    "活动预告",
    "会议通知",
    "低价值转载",
    "不可访问链接",
    "正文过短文章",
]

REPORT_SECTIONS = [
    "新品基础信息",
    "价格信息",
    "供应链信息",
    "渠道信息",
    "产品定位",
    "口味和商品细节",
    "产品五张牌分析",
    "竞品对比",
    "商业分析结论",
    "来源和可信度",
]


def safe_slug(value: str, fallback: str = "new-product") -> str:
    text = re.sub(r"[\\/:*?\"<>|]+", "_", value.strip())
    text = re.sub(r"\s+", "_", text).strip("._")
    return text[:80] or fallback


def now_id() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def product_search_topic(payload: dict[str, Any]) -> str:
    brand = str(payload.get("brand_name", "")).strip()
    product = str(payload.get("product_name", "")).strip()
    pieces = [
        "" if brand and brand in product else brand,
        product,
        str(payload.get("category_keyword", "")).strip(),
        "新品",
        "上新",
        "饮料",
        "价格",
        "渠道",
        "口味",
        "供应链",
    ]
    seen: set[str] = set()
    result: list[str] = []
    for piece in pieces:
        if not piece or piece in seen:
            continue
        seen.add(piece)
        result.append(piece)
    return " ".join(result)


def product_keyword_variants(payload: dict[str, Any]) -> list[str]:
    product = str(payload.get("product_name", "")).strip()
    brand = str(payload.get("brand_name", "")).strip()
    category = str(payload.get("category_keyword", "")).strip()
    aliases = re.split(r"[\s/｜|、,，]+", product)
    aliases = [item for item in aliases if item and item != brand]
    flavor_words = [item for item in aliases if any(key in item for key in ("味", "口味", "柠檬", "桃", "茶", "莓", "橙", "葡萄"))]
    pieces = [
        product_search_topic(payload),
        " ".join(item for item in [brand, "新品"] if item),
        " ".join(item for item in [brand, "上新"] if item),
        " ".join(item for item in [brand, "新口味"] if item),
        " ".join(item for item in [brand, category] if item),
        " ".join(item for item in [category, "新品"] if item),
    ]
    for word in flavor_words[:3]:
        pieces.append(f"{word} 饮料")
    for alias in aliases[:3]:
        pieces.append(alias)
    seen: set[str] = set()
    variants: list[str] = []
    for piece in pieces:
        compact = re.sub(r"\s+", " ", piece).strip()
        if not compact or compact in seen:
            continue
        seen.add(compact)
        variants.append(compact)
    return variants


def fallback_attempts(payload: dict[str, Any], limit: int = 15) -> list[dict[str, Any]]:
    try:
        selected_intensity = float(payload.get("intensity", 0.6))
    except (TypeError, ValueError):
        selected_intensity = 0.6
    try:
        selected_days = int(payload.get("range_days", 90))
    except (TypeError, ValueError):
        selected_days = 90

    days_order = [selected_days, 30, 90, 180, 365]
    intensities = [selected_intensity, 0.6, 0.4, 0.2, 0.0]
    keywords = product_keyword_variants(payload)
    attempts: list[dict[str, Any]] = []
    seen: set[tuple[str, int, float]] = set()

    def add(topic: str, days: int, intensity: float, reason: str) -> None:
        key = (topic, days, intensity)
        if key in seen or len(attempts) >= limit:
            return
        seen.add(key)
        attempts.append({"topic": topic, "days": days, "intensity": intensity, "reason": reason})

    base_topic = keywords[0] if keywords else product_search_topic(payload)
    add(base_topic, selected_days, selected_intensity, "原始条件")
    for topic in keywords[1:]:
        add(topic, selected_days, selected_intensity, "自动放宽关键词")
    for days in days_order:
        if days >= selected_days:
            add(base_topic, days, selected_intensity, "自动放宽时间范围")
    for intensity in intensities:
        if intensity <= selected_intensity:
            add(base_topic, max(selected_days, 90), intensity, "自动降低筛选强度")
    return attempts


def confidence_from_sources(sources: list[dict[str, str]]) -> str:
    usable = [item for item in sources if item.get("url")]
    if len(usable) >= 3:
        return "高"
    if len(usable) >= 1:
        return "中"
    return "低"


def confidence_note(confidence: str) -> str:
    if confidence == "高":
        return "至少找到多个可点击来源，可进行交叉核验。"
    if confidence == "中":
        return "已找到公开来源，但信息仍需进一步交叉核验。"
    return "公开来源不足，本报告以框架整理和假设标注为主。"


def normalize_sources(items: list[dict[str, Any]], limit: int = 20) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        url = str(item.get("url", "")).strip()
        title = str(item.get("title", "")).strip() or "未命名来源"
        if not url or url in seen:
            continue
        sources.append(
            {
                "title": title,
                "url": url,
                "source": str(item.get("source", "")).strip(),
                "date": str(item.get("date", "")).strip(),
            }
        )
        seen.add(url)
        if len(sources) >= limit:
            break
    return sources


def fallback_text(value: str, fallback: str) -> str:
    value = str(value or "").strip()
    return value if value else fallback


def report_prompt(payload: dict[str, Any], sources: list[dict[str, str]]) -> str:
    product = fallback_text(payload.get("product_name", ""), "未命名新品")
    brand = fallback_text(payload.get("brand_name", ""), "未填写品牌")
    category = fallback_text(payload.get("category_keyword", ""), "未填写品类")
    source_lines = "\n".join(
        f"- {item['title']} {item.get('date', '')} {item['url']}" for item in sources[:12]
    ) or "- 未找到可用来源"
    return f"""你是饮料行业商业分析师。请基于可验证公开来源，为新品生成商业分析补充。

新品：{product}
品牌：{brand}
品类关键词：{category}

可用来源：
{source_lines}

要求：
1. 不要虚构确定性事实；没有来源支撑时必须写“未找到可靠公开信息”或“基于公开信息推测”。
2. 按单价、供应链、渠道、定位、口味、五张牌、竞品、商业结论输出。
3. 结论要区分“已验证事实 / 公开信息推测 / 假设”。
"""


def call_llm_analysis(
    payload: dict[str, Any],
    sources: list[dict[str, str]],
    base_url: str,
    model: str,
    api_key: str,
    timeout: int = 45,
) -> dict[str, str]:
    if not base_url or not model or not api_key:
        return {"status": "disabled", "text": "高级分析未启用：缺少 LLM Base URL、模型或 API Key。"}

    url = base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你只根据用户提供的来源和明确假设做饮料新品商业分析。"},
            {"role": "user", "content": report_prompt(payload, sources)},
        ],
        "temperature": 0.2,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"status": "failed", "text": f"高级分析未启用：LLM 请求失败（{type(exc).__name__}）。"}

    content = ""
    try:
        content = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        content = ""
    return {"status": "ok" if content else "failed", "text": content or "高级分析未启用：LLM 没有返回可用内容。"}


def markdown_table(rows: list[list[str]]) -> str:
    escaped = [[cell.replace("|", "\\|") for cell in row] for row in rows]
    widths = [max(len(row[index]) for row in escaped) for index in range(len(escaped[0]))]
    lines = []
    for row_index, row in enumerate(escaped):
        lines.append("| " + " | ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)) + " |")
        if row_index == 0:
            lines.append("| " + " | ".join("-" * widths[index] for index in range(len(row))) + " |")
    return "\n".join(lines)


def build_report_markdown(
    payload: dict[str, Any],
    sources: list[dict[str, str]],
    llm_result: dict[str, str],
    run_outputs: list[dict[str, str]],
    fallback: dict[str, Any] | None = None,
) -> str:
    product = fallback_text(payload.get("product_name", ""), "未命名新品")
    brand = fallback_text(payload.get("brand_name", ""), "未填写")
    category = fallback_text(payload.get("category_keyword", ""), "未填写")
    confidence = confidence_from_sources(sources)
    generated_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source_rows = [["标题", "日期", "来源", "链接"]]
    for item in sources[:15]:
        source_rows.append([
            item.get("title", ""),
            item.get("date", ""),
            item.get("source", ""),
            item.get("url", ""),
        ])
    if len(source_rows) == 1:
        source_rows.append(["未找到可用来源", "", "", ""])

    output_rows = [["类型", "位置"]]
    for item in run_outputs:
        output_rows.append([item.get("label", ""), item.get("path", "")])
    fallback = fallback or {}
    attempt_rows = [["搜索词", "时间范围", "筛选强度", "触发原因"]]
    for item in fallback.get("attempts", []):
        attempt_rows.append([
            str(item.get("topic", "")),
            str(item.get("date_range", item.get("days", ""))),
            str(item.get("intensity", "")),
            str(item.get("reason", "")),
        ])
    if len(attempt_rows) == 1:
        attempt_rows.append(["未记录", "", "", ""])
    reason_rows = [["失败原因"]]
    for reason in fallback.get("failure_reasons", []):
        reason_rows.append([str(reason)])
    if len(reason_rows) == 1:
        reason_rows.append(["未记录明确失败原因"])
    filtered_rows = [["标题", "来源", "链接", "被过滤原因", "可手动恢复"]]
    for item in fallback.get("filtered_items", [])[:30]:
        filtered_rows.append([
            str(item.get("title", "")),
            str(item.get("source", "")),
            str(item.get("url", "")),
            str(item.get("reason", "")),
            "是" if item.get("recoverable", True) else "否",
        ])
    if len(filtered_rows) == 1:
        filtered_rows.append(["无", "", "", "", ""])
    report_type = fallback.get("report_type") or ("新品线索报告" if not sources else "新品文章报告")

    llm_text = llm_result.get("text", "").strip()
    if llm_result.get("status") != "ok":
        llm_text = llm_text or "高级分析未启用。以下内容为基础报告模板，所有无来源信息均已标注为未找到可靠公开信息或假设。"

    return f"""# 新品速递报告：{product}

- 生成时间：{generated_at}
- 品牌：{brand}
- 品类关键词：{category}
- 报告类型：{report_type}
- 数据可信度：{confidence}（{confidence_note(confidence)}）
- 高级分析状态：{llm_result.get("status", "disabled")}

## 0. 兜底和失败说明

- 微信公众号深度文章是否充足：{"是" if sources else "否，当前报告主要基于有限公开线索"}
- 自动兜底：已按关键词、时间范围和筛选强度进行尝试
- 人工确认提示：未找到可靠公开信息的字段需要人工确认

### 本次尝试过的条件

{markdown_table(attempt_rows)}

### 找不到结果或结果不足的原因

{markdown_table(reason_rows)}

### 被过滤文章

{markdown_table(filtered_rows)}

### 建议下一步

- 使用品牌名而不是具体产品名搜索
- 换更宽泛的品类关键词
- 扩大时间范围
- 降低筛选强度
- 在页面中使用“我有文章链接，手动补充”

## 1. 新品基础信息

- 产品名称：{product}
- 品牌：{brand}
- 母公司：未找到可靠公开信息
- 品类：{category}
- 上市时间：未找到可靠公开信息
- 规格：未找到可靠公开信息
- 口味：未找到可靠公开信息
- 包装形式：未找到可靠公开信息
- 产品图片：未找到公开产品图
- 信息来源：见“来源和可信度”
- 数据可信度：{confidence}

## 2. 价格信息

- 官方售价：未找到可靠公开价格
- 电商售价：未找到可靠公开价格
- 单瓶价格：未找到可靠公开价格
- 整箱价格：未找到可靠公开价格
- 促销价格：未找到可靠公开价格
- 不同平台价格差异：未找到可靠公开信息
- 价格带判断：基于公开信息不足，暂不做确定性判断

## 3. 供应链信息

- 生产商：未找到可靠公开信息
- 委托生产商：未找到可靠公开信息
- 产地：未找到可靠公开信息
- 工厂信息：未找到可靠公开信息
- 供应链线索：未找到可靠公开信息
- 是否品牌自有生产：未找到可靠公开信息
- 是否代工：未找到可靠公开信息

## 4. 渠道信息

- 天猫：未找到可靠公开信息
- 京东：未找到可靠公开信息
- 抖音：未找到可靠公开信息
- 小红书：未找到可靠公开信息
- 便利店：未找到可靠公开信息
- 商超：未找到可靠公开信息
- 零食量贩：未找到可靠公开信息
- 餐饮渠道：未找到可靠公开信息
- 渠道优先级判断：基于公开信息不足，暂不做确定性判断

## 5. 产品定位

- 目标人群：基于公开信息不足，暂不做确定性判断
- 消费场景：基于公开信息不足，暂不做确定性判断
- 价格定位：未找到可靠公开价格
- 功能定位：基于产品名和品类关键词推测，需人工确认
- 情绪价值：未找到可靠公开信息
- 品牌表达：未找到可靠公开信息
- 与原有产品线关系：未找到可靠公开信息
- 可能想解决的消费需求：基于公开信息推测，需人工确认

## 6. 口味和商品细节

- 口味名称：未找到可靠公开信息
- 配料亮点：未找到可靠公开信息
- 是否 0 糖：未找到可靠公开信息
- 是否低卡：未找到可靠公开信息
- 是否低脂 / 0 脂：未找到可靠公开信息
- 是否含电解质：未找到可靠公开信息
- 是否含维生素：未找到可靠公开信息
- 是否含膳食纤维：未找到可靠公开信息
- 包装设计特点：未找到可靠公开信息
- 容量规格：未找到可靠公开信息
- 箱规：未找到可靠公开信息
- 产品图片：未找到公开产品图

## 7. 产品五张牌分析

{llm_text}

### A. 五张牌评分

- 定位牌：假设，待人工确认
- 设计牌：假设，待人工确认
- 商标牌：假设，待人工确认
- 价值链牌：假设，待人工确认
- 口味牌：假设，待人工确认

### B. 均衡度判断

未找到足够公开信息完成确定性判断。

### C. 增长漏斗判断

- 能不能被看到：待人工确认
- 能不能被拿起：待人工确认
- 能不能被购买：待人工确认
- 能不能被复购：待人工确认
- 能不能被推荐 / 被想起：待人工确认

### D. 最终结论

当前公开信息不足以确认五张牌是否形成乘数效应，建议继续跟踪价格、渠道铺货、社媒声量和复购评价。

## 8. 竞品对比

未找到足够可靠公开信息自动确认竞品。建议人工补充 3-5 个竞品后再做横向对比。

## 9. 商业分析结论

- 核心看点：待基于更多公开来源确认
- 可能抢占的市场：基于公开信息不足，暂不做确定性判断
- 行业信号：待确认
- 是否值得持续跟踪：值得进入观察池，但需要补充价格、渠道和消费者反馈
- 后续重点关注：价格变化、铺货速度、电商销量、社媒声量、复购评价、渠道扩张、竞品反应

## 10. 来源和可信度

{markdown_table(source_rows)}

## 本地输出

{markdown_table(output_rows)}
"""


def markdown_to_html(markdown: str, title: str) -> str:
    body_lines = []
    for line in markdown.splitlines():
        if line.startswith("# "):
            body_lines.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            body_lines.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("### "):
            body_lines.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("- "):
            body_lines.append(f"<p class='bullet'>• {html.escape(line[2:])}</p>")
        elif line.startswith("| "):
            body_lines.append(f"<pre>{html.escape(line)}</pre>")
        elif line.strip():
            body_lines.append(f"<p>{html.escape(line)}</p>")
        else:
            body_lines.append("")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin: 0; padding: 32px; font-family: "Microsoft YaHei", Arial, sans-serif; color: #17211f; background: #f6f7f5; }}
    main {{ max-width: 960px; margin: 0 auto; padding: 28px; background: #fff; border: 1px solid #dbe2dd; border-radius: 8px; }}
    h1 {{ font-size: 28px; margin: 0 0 18px; }}
    h2 {{ margin-top: 30px; border-top: 1px solid #dbe2dd; padding-top: 18px; }}
    h3 {{ margin-top: 20px; }}
    p {{ line-height: 1.8; }}
    .bullet {{ margin: 6px 0; }}
    pre {{ white-space: pre-wrap; overflow-wrap: anywhere; background: #f3f7f5; padding: 8px 10px; border-radius: 6px; }}
  </style>
</head>
<body><main>{''.join(body_lines)}</main></body>
</html>
"""


def write_product_report(
    payload: dict[str, Any],
    job_data: dict[str, Any],
    llm_config: dict[str, str] | None = None,
) -> dict[str, Any]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    product = fallback_text(payload.get("product_name", ""), "未命名新品")
    report_id = f"{now_id()}-{safe_slug(product)}"
    report_dir = REPORTS_DIR / report_id
    report_dir.mkdir(parents=True, exist_ok=True)

    sources = normalize_sources(list(job_data.get("results") or []))
    outputs = list(job_data.get("outputs") or [])
    llm_config = llm_config or {}
    api_key = llm_config.get("api_key") or os.getenv("LLM_API_KEY", "")
    base_url = llm_config.get("base_url") or os.getenv("LLM_BASE_URL", "")
    model = llm_config.get("model") or os.getenv("LLM_MODEL", "")
    llm_result = call_llm_analysis(payload, sources, base_url, model, api_key) if api_key else {
        "status": "disabled",
        "text": "高级分析未启用：未配置 LLM API Key。",
    }

    fallback = dict(job_data.get("fallback") or {})
    markdown = build_report_markdown(payload, sources, llm_result, outputs, fallback)
    title = f"新品速递报告：{product}"
    html_text = markdown_to_html(markdown, title)

    md_path = report_dir / "report.md"
    html_path = report_dir / "report.html"
    json_path = report_dir / "report.json"
    md_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(html_text, encoding="utf-8")
    data = {
        "id": report_id,
        "product_name": product,
        "brand_name": fallback_text(payload.get("brand_name", ""), ""),
        "category_keyword": fallback_text(payload.get("category_keyword", ""), ""),
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "confidence": confidence_from_sources(sources),
        "confidence_note": confidence_note(confidence_from_sources(sources)),
        "source_count": len(sources),
        "sources": sources,
        "fallback": fallback,
        "failure_reasons": fallback.get("failure_reasons", []),
        "filtered_items": fallback.get("filtered_items", []),
        "report_type": fallback.get("report_type") or ("新品线索报告" if not sources else "新品文章报告"),
        "llm_status": llm_result.get("status", "disabled"),
        "sections": REPORT_SECTIONS,
        "paths": {
            "report_dir": str(report_dir),
            "markdown": str(md_path),
            "html": str(html_path),
            "json": str(json_path),
        },
        "search_job": {
            "id": job_data.get("id", ""),
            "status": job_data.get("status", ""),
            "summary": job_data.get("summary", ""),
        },
    }
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def update_discoveries(report: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = load_discoveries()
    items = [item for item in data.get("items", []) if item.get("id") != report.get("id")]
    items.insert(
        0,
        {
            "id": report.get("id", ""),
            "product_name": report.get("product_name", ""),
            "brand_name": report.get("brand_name", ""),
            "category": report.get("category_keyword", ""),
            "discovered_at": report.get("created_at", ""),
            "source_count": report.get("source_count", 0),
            "confidence": report.get("confidence", "低"),
            "summary": "已生成本地新品速递报告。",
            "report_path": report.get("paths", {}).get("markdown", ""),
        },
    )
    data["updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
    data["items"] = items[:50]
    DISCOVERY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_discoveries() -> dict[str, Any]:
    if not DISCOVERY_FILE.exists():
        return {
            "updated_at": "",
            "mode_note": "本地模式可使用 Chrome 完成搜狗验证；GitHub Actions 暂不支持需要人工验证的微信链接采集。",
            "items": [],
        }
    try:
        return json.loads(DISCOVERY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"updated_at": "", "items": []}


def report_payload(report_dir: Path) -> dict[str, Any] | None:
    json_path = report_dir / "report.json"
    if not json_path.exists():
        return None
    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def report_history(limit: int = 20) -> list[dict[str, Any]]:
    if not REPORTS_DIR.exists():
        return []
    dirs = sorted(
        [path for path in REPORTS_DIR.iterdir() if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    items: list[dict[str, Any]] = []
    for path in dirs[:limit]:
        data = report_payload(path)
        if data:
            items.append(data)
    return items
