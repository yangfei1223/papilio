"""HuggingFace collector — Trending models via HF Hub API."""

import os
from datetime import datetime, timezone

import requests

from base import BaseCollector, content_hash

# HF_ENDPOINT 可覆盖 API 基址（默认官方）。区域网络屏蔽 huggingface.co 时，
# 设 HF_ENDPOINT=https://hf-mirror.com 走镜像。仅影响 API 拉取；item.url 仍用
# canonical huggingface.co（稳定身份 + 生产机 Mac mini 可达）。
HF_API = os.getenv("HF_ENDPOINT", "https://huggingface.co") + "/api"
LIMIT = 25


class HuggingFaceCollector(BaseCollector):
    def fetch(self) -> list[dict]:
        repos = self._get_trending()
        items = []
        for repo in repos:
            model_id = repo.get("id", "")
            if not model_id:
                continue
            owner = model_id.split("/", 1)[0] if "/" in model_id else ""
            items.append({
                "source": "huggingface",
                "url": f"https://huggingface.co/{model_id}",
                "title": model_id,
                "summary": repo.get("pipeline_tag") or "",
                "author": owner,
                "published_at": repo.get("created_at") or datetime.now(timezone.utc).isoformat(),
                "content_hash": content_hash(model_id),
                "meta": {
                    "downloads": repo.get("downloads", 0),
                    "likes": repo.get("likes", 0),
                    "pipeline_tag": repo.get("pipeline_tag", ""),
                    "tags": (repo.get("tags") or [])[:10],
                },
            })
        return items

    def _get_trending(self) -> list[dict]:
        """拉 trending models。先 sort=trending，不可用回退 sort=likes。"""
        try:
            resp = requests.get(
                f"{HF_API}/models",
                params={"sort": "trending", "limit": LIMIT},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and data:
                    return data
        except Exception as e:
            print(f"[HuggingFace] trending fetch failed: {e}")

        try:
            resp = requests.get(
                f"{HF_API}/models",
                params={"sort": "likes", "direction": "-1", "limit": LIMIT},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"[HuggingFace] likes fallback failed: {e}")
            return []


if __name__ == "__main__":
    HuggingFaceCollector().run()
