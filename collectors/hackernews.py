"""Hacker News collector — Top stories via official Firebase API."""

from datetime import datetime, timezone

import requests

from base import BaseCollector, content_hash

HN_API = "https://hacker-news.firebaseio.com/v0"


class HackerNewsCollector(BaseCollector):
    def fetch(self) -> list[dict]:
        items = []
        ids = self._get_top_stories()[:50]

        for story_id in ids:
            story = self._get_item(story_id)
            if not story or "url" not in story:
                # Ask HN / Show HN 可能没有 url
                if story and story.get("title"):
                    story["url"] = f"https://news.ycombinator.com/item?id={story_id}"
                else:
                    continue

            ts = story.get("time", 0)
            published_at = (
                datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                if ts
                else datetime.now(timezone.utc).isoformat()
            )

            items.append({
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
            })

        return items

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
