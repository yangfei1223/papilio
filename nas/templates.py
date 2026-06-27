"""HTML templates for Butterfly Web UI.

纯字符串模板，不引入 Jinja2 依赖。
"""


def item_row(item: dict) -> str:
    """渲染单条 item."""
    title = _esc(item.get("title", ""))
    url = _esc(item.get("url", ""))
    source = item.get("source", "")
    category = item.get("category", "")
    summary = item.get("summary", "")
    published = item.get("published_at", "")[:10] if item.get("published_at") else ""
    importance = item.get("importance") or 0
    item_id = item.get("id", "")
    status = item.get("status", "new")
    wiki_slug = item.get("wiki_slug", "")

    score_class = f"score-{importance}" if importance >= 3 else "score-2"

    parts = [f'<div class="item" id="item-{item_id}">']

    # importance score
    parts.append(f'<div class="item-score {score_class}">{"★★★★★"[:importance]}{"☆"*(5-importance) if importance else "·"}</div>')

    # body
    parts.append('<div class="item-body">')

    # title
    if url:
        parts.append(f'<div class="item-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></div>')
    else:
        parts.append(f'<div class="item-title">{title}</div>')

    # meta
    meta_parts = []
    if source:
        meta_parts.append(f'<span class="badge badge-source">{_esc(source)}</span>')
    if category:
        meta_parts.append(f'<span class="badge badge-category">{_esc(category)}</span>')
    if published:
        meta_parts.append(f'<span>{published}</span>')
    parts.append(f'<div class="item-meta">{" ".join(meta_parts)}</div>')

    # summary
    if summary:
        parts.append(f'<div class="item-summary">{_esc(summary)}</div>')

    # wiki related
    if wiki_slug:
        parts.append(f'<div class="wiki-related">📚 Wiki: <a href="#">{_esc(wiki_slug)}</a></div>')

    parts.append('</div>')  # item-body

    # actions
    parts.append('<div class="item-actions">')
    if status == "saved":
        parts.append('<span class="btn btn-saved">✓ 已保存</span>')
    else:
        parts.append(f'<button class="btn btn-save" hx-post="/api/items/{item_id}/save" hx-swap="outerHTML" hx-target="#item-{item_id} .item-actions">→ Wiki</button>')
    parts.append('</div>')

    parts.append('</div>')  # item
    return "\n".join(parts)


def feed_page(items: list[dict], total: int, page: int, pages: int, source: str = "", category: str = "") -> str:
    """渲染整个 feed 区域."""
    if not items:
        return '<div class="empty">🦋 还没有内容。等 collector 跑起来就有了。</div>'

    html = []

    # filter bar
    if source:
        html.append(f'<h2>{_esc(source)}</h2>')
    if category:
        html.append(f'<h2>{_esc(category)}</h2>')

    # items
    for item in items:
        html.append(item_row(item))

    # pagination hint
    if page < pages:
        html.append(
            f'<div class="loading" hx-get="/ui/items?source={_esc(source)}&category={_esc(category)}&page={page+1}" '
            f'hx-trigger="revealed" hx-swap="afterend" hx-target="this">加载更多...</div>'
        )

    return "\n".join(html)


def stats_widget(stats: dict) -> str:
    """侧边栏统计."""
    if not stats:
        return ""
    total = stats.get("total", 0)
    by_status = stats.get("by_status", {})
    saved = by_status.get("saved", 0)

    parts = [f'<div class="stats">']
    parts.append(f'<div>📊 {total} 条</div>')
    parts.append(f'<div>📌 {saved} 已保存</div>')
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
