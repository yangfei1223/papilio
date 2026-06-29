"""HTML templates for Papilio Web UI.

纯字符串模板，不引入 Jinja2 依赖。
"""


SOURCE_META = {
    "hackernews": ("HN", "Hacker News", "source-hackernews"),
    "arxiv": ("arX", "arXiv", "source-arxiv"),
    "github": ("GH", "GitHub", "source-github"),
    "huggingface": ("HF", "HuggingFace", "source-huggingface"),
    "rss": ("RSS", "RSS", "source-rss"),
}


def _source_meta(source: str) -> tuple[str, str, str]:
    key = (source or "").split("/")[0].lower()
    label, name, cls = SOURCE_META.get(key, ("PX", source or "Source", "source-generic"))
    return label, name, cls


def _status_label(status: str) -> tuple[str, str]:
    labels = {
        "new": ("New", "status-new"),
        "processed": ("Ready", "status-processed"),
        "saving": ("Saving", "status-saving"),
        "saved": ("Saved", "status-saved"),
    }
    return labels.get(status or "new", ((status or "new").title(), "status-new"))


def _priority_label(importance) -> tuple[str, str]:
    try:
        score = int(importance or 0)
    except (TypeError, ValueError):
        score = 0
    stars = "⭐️" * score if score else "·"
    if score >= 5:
        return stars, "priority-high"
    if score == 4:
        return stars, "priority-medium"
    if score == 3:
        return stars, "priority-low"
    return stars, "priority-none"


def item_row(item: dict) -> str:
    """渲染单条 item."""
    title = _esc(item.get("title", ""))
    url = _esc(item.get("url", ""))
    source = item.get("source", "")
    category = item.get("category", "")
    summary = item.get("summary", "")
    published = item.get("published_at", "")[:10] if item.get("published_at") else ""
    importance = item.get("importance") or 0
    item_id = _esc(item.get("id", ""))
    status = item.get("status", "new")
    wiki_slug = item.get("wiki_slug", "")

    source_label, source_name, source_class = _source_meta(source)
    status_label, status_class = _status_label(status)
    priority_label, priority_class = _priority_label(importance)

    parts = [f'<article class="item-row {source_class}" id="item-{item_id}">']
    parts.append(
        f'<div class="source-tile {source_class}" title="{_esc(source_name)}">'
        f'<span>{_esc(source_label)}</span></div>'
    )

    parts.append('<div class="item-main">')
    if url:
        parts.append(f'<h2 class="item-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></h2>')
    else:
        parts.append(f'<h2 class="item-title">{title}</h2>')

    if summary:
        parts.append(f'<p class="item-summary">{_esc(summary)}</p>')

    meta_parts = []
    if source:
        meta_parts.append(f'<span class="meta-chip source-chip">{_esc(source)}</span>')
    if category:
        meta_parts.append(f'<span class="meta-chip category-chip">{_esc(category)}</span>')
    if published:
        meta_parts.append(f'<time class="meta-chip date-chip" datetime="{_esc(item.get("published_at", ""))}">{published}</time>')
    meta_parts.append(f'<span class="meta-chip status-chip {status_class}">{_esc(status_label)}</span>')
    parts.append(f'<div class="item-meta">{"".join(meta_parts)}</div>')

    if wiki_slug:
        parts.append(f'<div class="wiki-link">Wiki: <a href="#">{_esc(wiki_slug)}</a></div>')

    parts.append('</div>')

    parts.append('<div class="item-side">')
    parts.append(f'<span class="priority-pill {priority_class}">{priority_label}</span>')
    if status == "saved":
        parts.append('<span class="wiki-action wiki-action-saved">✓ Wiki</span>')
    elif status == "saving":
        parts.append('<span class="wiki-action wiki-action-saving">… Wiki</span>')
    else:
        parts.append(
            f'<button class="wiki-action wiki-action-button" hx-post="/api/items/{item_id}/save" '
            f'hx-swap="outerHTML" hx-target="#item-{item_id} .item-side">➡ Wiki</button>'
        )
    parts.append('</div>')

    parts.append('</article>')
    return "\n".join(parts)


def feed_page(items: list[dict], total: int, page: int, pages: int, source: str = "", category: str = "") -> str:
    """渲染整个 feed 区域."""
    view_label = category or source or "All sources"
    if not items:
        return (
            '<section class="feed-panel">'
            '<div class="feed-heading"><div><p class="eyebrow">Papilio Inbox</p>'
            f'<h1>{_esc(view_label)}</h1></div><span class="feed-count">0 items</span></div>'
            '<div class="empty-state"><div class="empty-icon">PX</div>'
            '<h2>No items yet</h2><p>Run a collector and new entries will appear here.</p></div>'
            '</section>'
        )

    html = ['<section class="feed-panel">']
    html.append(
        '<div class="feed-heading"><div><p class="eyebrow">Papilio Inbox</p>'
        f'<h1>{_esc(view_label)}</h1></div>'
        f'<span class="feed-count">{total} items</span></div>'
    )

    html.append('<div class="item-list">')
    for item in items:
        html.append(item_row(item))
    html.append('</div>')

    if page < pages:
        html.append(
            f'<div class="loading" hx-get="/ui/items?source={_esc(source)}&category={_esc(category)}&page={page+1}" '
            f'hx-trigger="revealed" hx-swap="afterend" hx-target="this">Loading more...</div>'
        )

    html.append('</section>')
    return "\n".join(html)


def stats_widget(stats: dict) -> str:
    """侧边栏统计."""
    if not stats:
        return ""
    total = stats.get("total", 0)
    by_status = stats.get("by_status", {})
    new = by_status.get("new", 0)
    processed = by_status.get("processed", 0)
    saved = by_status.get("saved", 0)

    parts = ['<div class="stats-grid">']
    parts.append(f'<div><span>{total}</span><small>Total</small></div>')
    parts.append(f'<div><span>{new}</span><small>New</small></div>')
    parts.append(f'<div><span>{processed}</span><small>Ready</small></div>')
    parts.append(f'<div><span>{saved}</span><small>Saved</small></div>')
    parts.append('</div>')
    return "\n".join(parts)


def _esc(text: str) -> str:
    """HTML 转义."""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
