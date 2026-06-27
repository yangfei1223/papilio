"""arXiv collector — 特定分类的最新论文."""

import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

from base import BaseCollector, content_hash

DEFAULT_CATEGORIES = ["cs.AI", "cs.CL", "cs.CV", "cs.LG"]


class ArxivCollector(BaseCollector):
    def __init__(
        self,
        categories: list[str] | None = None,
        max_results: int = 50,
        nas_url: str | None = None,
    ):
        super().__init__(nas_url)
        self.categories = categories or DEFAULT_CATEGORIES
        self.max_results = max_results

    def fetch(self) -> list[dict]:
        cat_query = "+OR+".join(f"cat:{c}" for c in self.categories)
        url = (
            "https://export.arxiv.org/api/query"
            f"?search_query={cat_query}"
            "&sortBy=submittedDate&sortOrder=descending"
            f"&max_results={self.max_results}"
        )

        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            return self._parse(resp.text)
        except Exception as e:
            print(f"[arXiv] API failed: {e}")
            return []

    def _parse(self, xml_text: str) -> list[dict]:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(xml_text)
        items = []

        for entry in root.findall("a:entry", ns):
            title_el = entry.find("a:title", ns)
            title = (
                title_el.text.strip().replace("\n", " ")
                if title_el is not None and title_el.text
                else ""
            )

            id_el = entry.find("a:id", ns)
            arxiv_id = ""
            if id_el is not None and id_el.text:
                arxiv_id = id_el.text.strip().split("/abs/")[-1]

            url = f"https://arxiv.org/abs/{arxiv_id}"

            published_el = entry.find("a:published", ns)
            published_at = (
                published_el.text if published_el is not None else ""
            )

            authors = [
                a.find("a:name", ns).text
                for a in entry.findall("a:author", ns)
                if a.find("a:name", ns) is not None
            ]

            summary_el = entry.find("a:summary", ns)
            summary = (
                summary_el.text.strip()[:500]
                if summary_el is not None and summary_el.text
                else None
            )

            cats = [
                c.get("term", "")
                for c in entry.findall("a:category", ns)
            ]

            items.append({
                "source": "arxiv",
                "url": url,
                "title": title,
                "summary": summary,
                "author": ", ".join(authors[:3]),
                "published_at": published_at,
                "content_hash": content_hash(title),
                "meta": {
                    "arxiv_id": arxiv_id,
                    "categories": cats,
                    "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
                },
            })

        return items


if __name__ == "__main__":
    c = ArxivCollector()
    c.run()
