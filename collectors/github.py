"""GitHub collector — 近 N 天内新建、按星排序的仓库（近似 trending）。"""

import json
import subprocess
from datetime import datetime, timedelta, timezone

import requests

from base import BaseCollector, content_hash

WINDOW_DAYS = 7


class GitHubCollector(BaseCollector):
    def fetch(self) -> list[dict]:
        since = (datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
        items = []
        for repo in self._get_trending(since):
            owner = repo.get("owner")
            owner_login = owner.get("login", "") if isinstance(owner, dict) else (owner or "")
            created = repo.get("created_at") or datetime.now(timezone.utc).isoformat()
            items.append({
                "source": "github",
                "url": repo.get("html_url", ""),
                "title": repo.get("full_name", ""),
                "summary": repo.get("description", ""),
                "author": owner_login,
                "published_at": created,
                "content_hash": content_hash(repo.get("full_name", "")),
                "meta": {
                    "stars": repo.get("stargazers_count", 0),
                    "language": repo.get("language", ""),
                    "topics": repo.get("topics", []),
                },
            })
        return items

    def _get_trending(self, since: str) -> list[dict]:
        """近 N 天新建、按星排序。先用 gh CLI，失败回退 search API。"""
        try:
            result = subprocess.run(
                [
                    "gh", "search", "repos",
                    f"created:>{since}",
                    "--sort=stars",
                    "--limit", "25",
                    "--json", "full_name,description,html_url,stargazers_count,language,topics,owner,created_at",
                ],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception as e:
            print(f"[GitHub] gh CLI failed: {e}")

        try:
            resp = requests.get(
                "https://api.github.com/search/repositories",
                params={"q": f"created:>{since}", "sort": "stars", "per_page": 25},
                headers={"Accept": "application/vnd.github+json"},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json().get("items", [])
        except Exception as e:
            print(f"[GitHub] API fallback failed: {e}")
            return []


if __name__ == "__main__":
    GitHubCollector().run()
