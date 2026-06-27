#!/usr/bin/env python3
"""Collector 调度入口.

用法:
  python scripts/run_collector.py hackernews
  python scripts/run_collector.py rss
  python scripts/run_collector.py arxiv
  python scripts/run_collector.py github
  python scripts/run_collector.py all
"""

import sys
import os

# 项目根目录
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "collectors"))

# NAS 地址（默认 nas.local，可通过环境变量覆盖）
NAS_URL = os.getenv("PAPILIO_NAS_URL", "http://nas:8899")


def run(name: str):
    if name == "hackernews":
        from hackernews import HackerNewsCollector
        HackerNewsCollector(NAS_URL).run()
    elif name == "rss":
        from rss import RSSCollector
        import yaml
        config_path = os.path.join(ROOT, "collectors", "config.yaml")
        if os.path.exists(config_path):
            with open(config_path) as f:
                config = yaml.safe_load(f)
            feeds = config.get("feeds", [])
        else:
            feeds = []
        RSSCollector(feeds=feeds, nas_url=NAS_URL).run()
    elif name == "arxiv":
        from arxiv import ArxivCollector
        import yaml
        config_path = os.path.join(ROOT, "collectors", "config.yaml")
        if os.path.exists(config_path):
            with open(config_path) as f:
                config = yaml.safe_load(f)
            categories = config.get("arxiv_categories", None)
        else:
            categories = None
        ArxivCollector(categories=categories, nas_url=NAS_URL).run()
    elif name == "github":
        from github import GitHubCollector
        GitHubCollector(NAS_URL).run()
    elif name == "all":
        for n in ["hackernews", "rss", "arxiv", "github"]:
            try:
                run(n)
            except Exception as e:
                print(f"[run_collector] {n} failed: {e}")
    else:
        print(f"Unknown collector: {name}")
        print("Available: hackernews, rss, arxiv, github, all")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/run_collector.py <name>")
        sys.exit(1)
    run(sys.argv[1])
