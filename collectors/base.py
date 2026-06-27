"""Collector 基类."""

import hashlib
import json
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import requests


class BaseCollector(ABC):
    """所有 collector 的基类.

    子类只需实现 fetch() 方法，返回 list[RawItem]。
    基类负责标准化、去重、POST 到 NAS。
    """

    def __init__(self, nas_url: str | None = None):
        self.nas_url = nas_url or os.getenv(
            "BUTTERFLY_NAS_URL", "http://nas:8899"
        )

    @abstractmethod
    def fetch(self) -> list[dict]:
        """拉取原始数据，返回标准化前的 dict 列表."""
        ...

    def run(self) -> dict:
        """完整执行流程."""
        print(f"[{self.__class__.__name__}] Fetching...")
        raw_items = self.fetch()
        print(f"[{self.__class__.__name__}] Fetched {len(raw_items)} items")

        items = [self._normalize(r) for r in raw_items]
        items = [i for i in items if i]  # 过滤无效

        items = self._dedup(items)

        print(f"[{self.__class__.__name__}] Posting {len(items)} items...")
        result = self._post(items)
        print(f"[{self.__class__.__name__}] Done: {result}")
        return result

    def _normalize(self, raw: dict) -> dict | None:
        """标准化为 API 格式。子类可覆盖."""
        url = raw.get("url", "")
        title = raw.get("title", "")
        if not url or not title:
            return None

        return {
            "source": raw.get("source", self.source_name),
            "url": url,
            "title": title,
            "summary": raw.get("summary"),
            "author": raw.get("author"),
            "published_at": raw.get(
                "published_at", datetime.now(timezone.utc).isoformat()
            ),
            "content_hash": raw.get("content_hash"),
            "meta": raw.get("meta", {}),
        }

    @property
    def source_name(self) -> str:
        return self.__class__.__name__.lower().replace("collector", "")

    def _dedup(self, items: list[dict]) -> list[dict]:
        """当前批次内去重（按 URL）."""
        seen = set()
        result = []
        for item in items:
            url = item.get("url", "")
            if url in seen:
                continue
            seen.add(url)
            result.append(item)
        return result

    def _post(self, items: list[dict]) -> dict:
        """POST 到 NAS API."""
        try:
            resp = requests.post(
                f"{self.nas_url}/api/items",
                json=items,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            print(f"[{self.__class__.__name__}] POST failed: {e}")
            return {"error": str(e)}


def content_hash(text: str) -> str:
    """计算内容的 sha256."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]
