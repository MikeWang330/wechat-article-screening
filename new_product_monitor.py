#!/usr/bin/env python3
"""Scheduled framework for beverage new-product discovery.

GitHub Actions cannot complete Sogou/WeChat flows that require manual Chrome
verification. This script therefore writes a clear structured data file and can
push a Feishu summary, while leaving verified WeChat collection to the local web
mode or to a future search provider that does not require manual verification.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import product_express


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DISCOVERY_FILE = DATA_DIR / "new_product_discoveries.json"


def existing_report_items(limit: int = 20) -> list[dict[str, Any]]:
    items = []
    for report in product_express.report_history(limit):
        items.append(
            {
                "id": report.get("id", ""),
                "product_name": report.get("product_name", ""),
                "brand_name": report.get("brand_name", ""),
                "category": report.get("category_keyword", ""),
                "discovered_at": report.get("created_at", ""),
                "source_count": report.get("source_count", 0),
                "confidence": report.get("confidence", "低"),
                "summary": "来自本地新品报告历史。",
                "report_path": report.get("paths", {}).get("markdown", ""),
            }
        )
    return items


def build_payload(cloud_safe: bool) -> dict[str, Any]:
    now = dt.datetime.now().isoformat(timespec="seconds")
    note = (
        "GitHub Actions 暂不支持需要人工验证的微信链接采集；"
        "云端模式只处理已验证 URL、历史缓存或未来接入的无需验证搜索 API。"
    )
    return {
        "updated_at": now,
        "mode": "cloud-safe" if cloud_safe else "local-framework",
        "mode_note": note,
        "keywords": product_express.DEFAULT_PRODUCT_KEYWORDS,
        "exclude_hints": product_express.EXCLUDE_HINTS,
        "items": existing_report_items(),
        "todos": [
            "接入无需人工验证码的公开搜索 API 后，可在这里写入真实新品发现。",
            "本地网页模式继续使用 Chrome 完成搜狗验证。",
            "无法访问的链接必须写入失败原因，不能计入可信来源。",
        ],
    }


def write_discovery_file(payload: dict[str, Any]) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DISCOVERY_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return DISCOVERY_FILE


def feishu_text(payload: dict[str, Any]) -> str:
    items = payload.get("items", [])
    lines = ["饮料行业新品速递", f"更新时间：{payload.get('updated_at', '')}"]
    if not items:
        lines.append("本轮没有新增可验证新品报告。")
    for item in items[:8]:
        lines.append(
            f"- {item.get('product_name') or '未命名新品'}｜"
            f"{item.get('brand_name') or '品牌待确认'}｜"
            f"{item.get('category') or '品类待确认'}｜"
            f"可信度 {item.get('confidence', '待确认')}｜"
            f"{item.get('source_count', 0)} 条来源"
        )
    lines.append(payload.get("mode_note", ""))
    return "\n".join(lines)


def push_feishu(payload: dict[str, Any]) -> bool:
    webhook = os.getenv("FEISHU_WEBHOOK_URL", "").strip()
    if not webhook:
        print("FEISHU_WEBHOOK_URL is not set; skip push.")
        return False
    body = {"msg_type": "text", "content": {"text": feishu_text(payload)}}
    request = urllib.request.Request(
        webhook,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            print(response.read().decode("utf-8", errors="replace"))
        return True
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        print(f"Feishu push failed: {type(exc).__name__}: {exc}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Beverage new-product discovery framework")
    parser.add_argument("--cloud-safe", action="store_true", help="Do not run manual-verification collection.")
    parser.add_argument("--push-feishu", action="store_true", help="Push summary to FEISHU_WEBHOOK_URL if configured.")
    args = parser.parse_args()

    payload = build_payload(cloud_safe=args.cloud_safe)
    path = write_discovery_file(payload)
    print(f"Wrote {path}")
    if args.push_feishu:
        push_feishu(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
