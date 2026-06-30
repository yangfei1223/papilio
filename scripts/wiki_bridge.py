#!/usr/bin/env python3
"""Papilio Wiki Bridge — 从 NAS 拉取 status=saving 的条目，沉淀到 LLM Wiki.

触发方式：
  手动（你在 UI 点 [→ Wiki] 后）：python3 scripts/wiki_bridge.py
  cron 巡检：挂 Hermes cronjob，每 10 分钟扫一次

依赖：
  PAPILIO_NAS_URL — NAS API 地址
  WIKI_PATH / WIKI_ATLAS_PATH — wiki 目录
"""

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

NAS_URL = os.getenv("PAPILIO_NAS_URL", "http://nas:8899")

# Wiki 路径
WIKI_RESEARCH = Path(
    os.getenv(
        "WIKI_PATH",
        os.path.expanduser(
            "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/LLM_WIKI_RESEARCH"
        ),
    )
)
WIKI_ATLAS = Path(
    os.getenv(
        "WIKI_ATLAS_PATH",
        os.path.expanduser(
            "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/LLM_WIKI_ATLAS"
        ),
    )
)

# Agent-Reach CLI（如果装了）
AGENT_REACH_CLI = "agent-reach"  # 后续用


def fetch_full_content(url: str) -> str:
    """获取网页全文。优先 Agent-Reach CLI，回退 curl。"""
    # 尝试 mcp_web_reader_webReader — Hermes 内置
    # 这里用 curl + Jina Reader 做备选
    try:
        resp = requests.get(
            f"https://r.jina.ai/{url}",
            headers={"Accept": "text/markdown"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.text[:10000]  # 截断
    except Exception as e:
        print(f"  [fetch] Jina Reader failed: {e}")
        # 纯 curl 回退
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "Papilio/0.1"})
            resp.raise_for_status()
            # 简单去标签
            text = re.sub(r"<[^>]+>", " ", resp.text)
            text = re.sub(r"\s+", " ", text)
            return text[:10000]
        except Exception as e2:
            print(f"  [fetch] curl fallback failed: {e2}")
            return ""


def classify_wiki(item: dict) -> Path:
    """根据条目分类判断存入哪个 wiki."""
    category = (item.get("category") or "").lower()
    source = (item.get("source") or "").lower()
    tags = item.get("tags") or []
    title = (item.get("title") or "").lower()

    # RESEARCH 信号
    research_signals = [
        "ai/", "llm", "ml", "arxiv", "huggingface", "model",
        "transformer", "diffusion", "training", "attention",
        "deepseek", "qwen", "gemini", "claude", "copilot",
        "langchain", "agent", "rag", "vector", "embedding",
        "paper", "benchmark", "dataset",
    ]
    if source == "arxiv" or source == "huggingface":
        return WIKI_RESEARCH

    for sig in research_signals:
        if sig in category or sig in title:
            return WIKI_RESEARCH

    # 默认 ATLAS（通识/阅读/兴趣）
    return WIKI_ATLAS


def slugify(title: str) -> str:
    """生成 wiki slug."""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    return slug[:60]


def create_entity_page(item: dict, content: str, wiki: Path) -> str:
    """创建 wiki entity page，返回 slug."""
    slug = slugify(item.get("title", "untitled"))
    title = item.get("title", "Untitled")
    url = item.get("url", "")
    source = item.get("source", "")
    category = item.get("category", "")
    summary = item.get("summary", "")
    importance = item.get("importance") or 0
    author = item.get("author", "")
    published = (item.get("published_at") or "")[:10]
    arxiv_id = ""
    if source == "arxiv" and item.get("meta"):
        try:
            meta = json.loads(item["meta"]) if isinstance(item["meta"], str) else item["meta"]
            arxiv_id = meta.get("arxiv_id", "")
        except Exception:
            pass

    # Save raw source
    raw_dir = wiki / "raw" / "articles"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_file = raw_dir / f"{slug}.md"
    raw_file.write_text(
        f"# {title}\n\nURL: {url}\n\n{content}"
    )

    # Entity page
    entities_dir = wiki / "entities"
    entities_dir.mkdir(parents=True, exist_ok=True)
    entity_path = entities_dir / f"{slug}.md"

    tags = ["book-note"] if wiki == WIKI_ATLAS else ["paper", category] if category else ["paper"]

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    entity_md = f"""---
title: "{title}"
created: {today}
updated: {today}
type: entity
tags: {json.dumps(tags)}
sources: [raw/articles/{slug}.md]
confidence: medium
---

# {title}

"""

    if author:
        entity_md += f"**{author}** · " if author else ""
    if published:
        entity_md += f"{published}"
    if importance >= 4:
        entity_md += f" · ★{'★' * (importance - 1)}"
    entity_md += "\n"
    if url:
        entity_md += f"\n[原文]({url})"
    if arxiv_id:
        entity_md += f" · [arXiv](https://arxiv.org/abs/{arxiv_id})"

    entity_md += "\n\n## 摘要\n\n"
    entity_md += f">{summary}\n\n" if summary else ""
    entity_md += "## 来源\n\n"
    entity_md += f"`raw/articles/{slug}.md`\n"

    entity_path.write_text(entity_md)
    return slug


def update_wiki_nav(wiki: Path, slug: str, title: str):
    """更新 wiki index.md 和 log.md."""
    # index.md
    index_path = wiki / "index.md"
    if index_path.exists():
        index = index_path.read_text()
        entry = f"- [[{slug}]] — {title}"
        if entry not in index:
            # 插入到 ## Entities 段
            if "## Entities" in index:
                parts = index.split("## Entities")
                before = parts[0] + "## Entities"
                after = parts[1] if len(parts) > 1 else "\n\n"
                # 找到下一段 ## 开头
                next_section = re.search(r"\n## [A-Z]", after)
                if next_section:
                    entities_section = after[: next_section.start()]
                    rest = after[next_section.start() :]
                else:
                    entities_section = after
                    rest = ""
                entities_section += f"\n- [[{slug}]] — {title}"
                new_index = before + entities_section + rest
            else:
                new_index = index.rstrip() + f"\n\n## Entities\n\n- [[{slug}]] — {title}\n"
            # update total count
            new_index = re.sub(
                r"总页面数：(\d+)",
                lambda m: f"总页面数：{int(m.group(1)) + 1}",
                new_index,
            )
            new_index = re.sub(
                r"最后更新：\d{4}-\d{2}-\d{2}",
                f"最后更新：{datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
                new_index,
            )
            index_path.write_text(new_index)

    # log.md
    log_path = wiki / "log.md"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_entry = (
        f"\n## [{today}] ingest | {title}\n"
        f"- 从 Papilio [→ Wiki] 触发\n"
        f"- 创建 entities/{slug}.md\n"
        f"- 更新 index.md\n"
    )
    if log_path.exists():
        log = log_path.read_text()
        # 插入到文件开头第一个 ## 之后
        first_h2 = log.index("\n## ")
        if first_h2 > 0:
            log = log[: first_h2 + 1] + log_entry + "\n" + log[first_h2 + 1 :]
        log_path.write_text(log)


def save_to_nas(item_id: str, slug: str, wiki_name: str):
    """回写 NAS：标记 saved。"""
    requests.patch(
        f"{NAS_URL}/api/items/{item_id}",
        json={
            "status": "saved",
            "wiki_slug": slug,
            "wiki_saved_at": datetime.now(timezone.utc).isoformat(),
        },
        timeout=10,
    ).raise_for_status()


def process_item(item_id: str):
    """处理单条 wiki 沉淀."""
    # 从 NAS 拉条目
    resp = requests.get(f"{NAS_URL}/api/items/{item_id}", timeout=10)
    resp.raise_for_status()
    item = resp.json()

    print(f"\n🦋 [{item_id[:8]}] {item.get('title', '')[:60]}")

    # 1. 抓原文
    print("  → 抓原文...")
    content = fetch_full_content(item.get("url", ""))
    if content:
        print(f"  ✓ {len(content)} chars")

    # 2. 分类 wiki
    wiki = classify_wiki(item)
    wiki_name = "RESEARCH" if wiki == WIKI_RESEARCH else "ATLAS"
    print(f"  → wiki: {wiki_name}")

    # 3. 创建 entity page
    slug = create_entity_page(item, content, wiki)
    print(f"  → entity: entities/{slug}.md")

    # 4. 更新 wiki 导航
    update_wiki_nav(wiki, slug, item.get("title", ""))
    print(f"  → index.md + log.md updated")

    # 5. 回写 NAS
    save_to_nas(item_id, slug, wiki_name)
    print(f"  ✓ saved → {wiki_name}")


def main():
    """拉取所有 status=saving 的条目，逐一处理."""
    resp = requests.get(
        f"{NAS_URL}/api/items",
        params={"status": "saving", "per_page": 50},
        timeout=10,
    )
    resp.raise_for_status()
    items = resp.json().get("items", [])

    if not items:
        print("[wiki_bridge] 没有待沉淀的条目。")
        return

    print(f"[wiki_bridge] 发现 {len(items)} 条待沉淀")
    for item in items:
        try:
            process_item(item["id"])
        except Exception as e:
            print(f"  ✗ 失败: {e}")
            continue

    print(f"\n[wiki_bridge] 完成。")


if __name__ == "__main__":
    main()
