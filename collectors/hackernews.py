"""Hacker News collector — Top stories via official Firebase API."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

from base import BaseCollector, content_hash

HN_API = "https://hacker-news.firebaseio.com/v0"


class HackerNewsCollector(BaseCollector):
    def fetch(self) -> list[dict]:
        ids = self._get_top_stories()[:50]
        if not ids:
            return []
        # 并发拉取：HN Firebase 限速时单 item 可能 >10s，串行 50 个会超时。
        with ThreadPoolExecutor(max_workers=10) as ex:
            results = list(ex.map(self._fetch_one, ids))
        return [r for r in results if r]

    def _fetch_one(self, story_id: int) -> dict | None:
        """拉单个 story 并标准化。"""
        story = self._get_item(story_id)
        if not story:
            return None
        if "url" not in story:
            # Ask HN / Show HN 可能没有 url
            if story.get("title"):
                story["url"] = f"https://news.ycombinator.com/item?id={story_id}"
            else:
                return None

        ts = story.get("time", 0)
        published_at = (
            datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            if ts
            else datetime.now(timezone.utc).isoformat()
        )

        return {
            "source": "hackernews",
            "url": story.get("url", ""),
            "title": story.get("title", ""),
            "author": story.get("by"),
            "published_at": published_at,
            "content_hash": content_hash(story.get("title", "")),
            "meta": {
                "hn_id": story_id,
                "points": story.get("score", 0),
                "comments": story.get("descendants", 0),
                "type": story.get("type", "story"),
            },
        }

    def _get_top_stories(self) -> list[int]:
        try:
            resp = requests.get(f"{HN_API}/topstories.json", timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"[HackerNews] Failed to get top stories: {e}")
            return []

    def _get_item(self, item_id: int) -> dict | None:
        try:
            resp = requests.get(f"{HN_API}/item/{item_id}.json", timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None


if __name__ == "__main__":
    c = HackerNewsCollector()
    c.run()
