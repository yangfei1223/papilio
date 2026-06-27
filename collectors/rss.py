"""RSS/Atom collector — 通用 feed 解析."""

from datetime import datetime, timezone

import feedparser

from base import BaseCollector, content_hash

DEFAULT_FEEDS = [
    # 填写你的 RSS 源
    # {"name": "stripe-blog", "url": "https://stripe.com/blog/feed.rss"},
]


class RSSCollector(BaseCollector):
    def __init__(self, feeds: list[dict] | None = None, nas_url: str | None = None):
        super().__init__(nas_url)
        self.feeds = feeds or DEFAULT_FEEDS

    def fetch(self) -> list[dict]:
        items = []
        for feed_cfg in self.feeds:
            feed_name = feed_cfg["name"]
            feed_url = feed_cfg["url"]
            try:
                parsed = feedparser.parse(feed_url)
                for entry in parsed.entries[:20]:
                    items.append(self._parse_entry(feed_name, entry))
            except Exception as e:
                print(f"[RSS] Failed to parse {feed_name}: {e}")
        return items

    def _parse_entry(self, feed_name: str, entry: dict) -> dict:
        published = (
            datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).isoformat()
            if hasattr(entry, "published_parsed") and entry.published_parsed
            else datetime.now(timezone.utc).isoformat()
        )

        title = entry.get("title", "").strip()
        link = entry.get("link", "")
        summary = entry.get("summary", "") or entry.get("description", "")

        return {
            "source": f"rss/{feed_name}",
            "url": link,
            "title": title,
            "summary": _strip_html(summary)[:500] if summary else None,
            "author": entry.get("author"),
            "published_at": published,
            "content_hash": content_hash(title),
            "meta": {"feed": feed_name},
        }


def _strip_html(text: str) -> str:
    """简单去除 HTML 标签."""
    import re
    return re.sub(r"<[^>]+>", "", text).strip()


if __name__ == "__main__":
    c = RSSCollector()
    c.run()
