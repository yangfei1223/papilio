#!/usr/bin/env python3
"""Processor 入口 — 拉取新条目交给 Hermes AI 处理.

配合 Hermes cronjob 使用:
  cronjob(action='create', name='papillon-process',
    schedule='every 30m',
    script='scripts/process_items.py',
    prompt='...AI处理指令...',
    notify_on_complete=true)

脚本模式（非 Hermes）：拉取新条目，输出 JSON，由调用方（Hermes）AI 处理。
"""

import json
import os
import sys

import requests

NAS_URL = os.getenv("PAPILLON_NAS_URL", "http://nas:8899")


def get_new_items(limit: int = 20) -> list[dict]:
    """获取待处理的新条目."""
    try:
        resp = requests.get(
            f"{NAS_URL}/api/items",
            params={"status": "new", "per_page": limit},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("items", [])
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        return []


def update_item(item_id: str, updates: dict):
    """回写处理结果."""
    try:
        resp = requests.patch(
            f"{NAS_URL}/api/items/{item_id}",
            json=updates,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Failed to update {item_id}: {e}")
        return None


if __name__ == "__main__":
    items = get_new_items()
    # 输出给 Hermes，AI 会处理每一条然后 PATCH 回去
    print(json.dumps({
        "total": len(items),
        "items": [
            {
                "id": i["id"],
                "title": i["title"],
                "source": i["source"],
                "url": i["url"],
                "summary": i.get("summary"),
            }
            for i in items
        ],
        "instruction": (
            "For each item above, generate a Chinese summary (≤200 chars), "
            "assign a category (ai/tech/finance/science/politics/other), "
            "rate importance 1-5, and PATCH to NAS API."
        ),
    }, ensure_ascii=False))
