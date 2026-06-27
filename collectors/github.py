"""GitHub Trending collector — 通过 GitHub API."""

import json
import subprocess
from datetime import datetime, timezone

import requests

from base import BaseCollector, content_hash


class GitHubCollector(BaseCollector):
    def fetch(self) -> list[dict]:
        items = []
        repos = self._get_trending()
        for repo in repos:
            items.append({
                "source": "github",
                "url": repo.get("html_url", ""),
                "title": repo.get("full_name", ""),
                "summary": repo.get("description", ""),
                "author": repo.get("owner", {}).get("login", ""),
                "published_at": datetime.now(timezone.utc).isoformat(),
                "content_hash": content_hash(repo.get("full_name", "")),
                "meta": {
                    "stars": repo.get("stargazers_count", 0),
                    "language": repo.get("language", ""),
                    "topics": repo.get("topics", []),
                },
            })
        return items

    def _get_trending(self) -> list[dict]:
        """获取 trending repos。先用 gh CLI，失败则用搜索 API."""
        try:
            result = subprocess.run(
                [
                    "gh", "search", "repos",
                    "stars:>500", "sort:stars",
                    "--limit", "25",
                    "--json",
                    "full_name,description,html_url,stargazers_count,language,topics,owner",
                ],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception as e:
            print(f"[GitHub] gh CLI failed: {e}")

        # Fallback: GitHub search API
        try:
            resp = requests.get(
                "https://api.github.com/search/repositories",
                params={"q": "stars:>500", "sort": "stars", "per_page": 25},
                headers={"Accept": "application/vnd.github+json"},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json().get("items", [])
        except Exception as e:
            print(f"[GitHub] API fallback failed: {e}")
            return []


if __name__ == "__main__":
    c = GitHubCollector()
    c.run()
