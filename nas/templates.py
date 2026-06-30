"""HTML templates for Papilio Cognition Dashboard (Phase 1).

纯字符串模板，不引入 Jinja2 依赖。
"""

from datetime import datetime, timezone
import re


SOURCE_META = {
    "hackernews": ("HN", "Hacker News", "amber"),
    "arxiv": ("arX", "arXiv", "purple"),
    "github": ("GH", "GitHub", "green"),
    "huggingface": ("HF", "HuggingFace", "blue"),
    "rss": ("RSS", "RSS", "orange"),
}

STATUS_META = {
    "new": ("NEW", "status-new"),
    "processed": ("PROCESSED", "status-processed"),
    "saved": ("SAVED", "status-saved"),
    "archived": ("ARCHIVED", "status-archived"),
}

ICONS = {
    "arrow-right": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M5 12h14M12 5l7 7-7 7"/></svg>'
    ),
    "check": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M4 12l6 6L20 6"/></svg>'
    ),
    "clock": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>'
    ),
    "cluster": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="6" cy="6" r="3"/><circle cx="18" cy="6" r="3"/>'
        '<circle cx="6" cy="18" r="3"/><circle cx="18" cy="18" r="3"/>'
        '<path d="M9 6h6M6 9v6M18 9v6M9 18h6"/></svg>'
    ),
    "dot": (
        '<svg viewBox="0 0 10 10" fill="currentColor">'
        '<circle cx="5" cy="5" r="4"/></svg>'
    ),
    "external": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M7 17h10M17 7v10M17 7H7v10"/></svg>'
    ),
    "document": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M4 7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z"/>'
        '<path d="M8 13h8"/></svg>'
    ),
    "tag": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M4 9V5a1 1 0 0 1 1-1h4a1 1 0 0 1 .71.29l8 8a1 1 0 0 1 0 1.42l-4 4a1 1 0 0 1-1.42 0l-8-8A1 1 0 0 1 4 9z"/>'
        '<circle cx="7.5" cy="7.5" r="1.5"/></svg>'
    ),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _icon(name: str) -> str:
    """Return inline SVG icon string."""
    return ICONS.get(name, "")


def _importance_dots(score) -> str:
    """Return a 5-point importance visual like ●●●●○."""
    try:
        score = max(0, min(5, int(score or 0)))
    except (TypeError, ValueError):
        score = 0
    return "●" * score + "○" * (5 - score)


def _relative_time(published_at: str) -> str:
    """Return '4h ago', 'yesterday', etc."""
    if not published_at:
        return ""
    try:
        dt = datetime.fromisoformat(published_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        seconds = int((now - dt).total_seconds())
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            return f"{seconds // 60}m ago"
        if seconds < 86400:
            return f"{seconds // 3600}h ago"
        if seconds < 172800:
            return "yesterday"
        return f"{seconds // 86400}d ago"
    except Exception:
        return ""


def _slugify(text: str) -> str:
    """Simple kebab-case slug."""
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text or "untitled"


def _source_meta(source: str) -> tuple[str, str, str]:
    key = (source or "").split("/")[0].lower()
    return SOURCE_META.get(key, (source or "?", source or "Unknown", ""))


def _status_meta(status: str) -> tuple[str, str]:
    return STATUS_META.get(status or "new", (status.upper() if status else "NEW", "status-new"))


def _cluster_badge(count: int) -> str:
    if count > 1:
        return f'<span class="badge cluster">cluster ×{count}</span>'
    return ""


# ---------------------------------------------------------------------------
# Fragments
# ---------------------------------------------------------------------------

def timeline_page(
    items: list[dict],
    total: int,
    sort: str = "time",
    perspective: str = "",
    source: str = "",
    selected_id: str = "",
    clusters_by_item: dict | None = None,
) -> str:
    """Renders inside #timeline-content (no outer wrapper)."""
    clusters_by_item = clusters_by_item or {}

    active_tab = sort or "time"
    tabs = [
        ("signal", "Signal"),
        ("time", "Time"),
        ("cluster", "Cluster"),
        ("random", "Random"),
    ]
    tabs_html = ""
    for tab_key, tab_label in tabs:
        cls = "pill active" if active_tab == tab_key else "pill"
        tabs_html += (
            f'<button class="{cls}" hx-get="/ui/items?sort={tab_key}" '
            f'hx-target="#timeline-content" hx-swap="innerHTML">{tab_label}</button>'
        )

    if not items:
        return (
            '<div class="timeline-head">'
            '<div><h1>Today’s Cognition Feed</h1><p>No items match this view.</p></div>'
            f'<div class="view-tabs">{tabs_html}</div>'
            '</div>'
            '<div class="feed">' + empty_timeline() + '</div>'
        )

    cards = []
    for idx, item in enumerate(items):
        cards.append(
            item_card(
                item,
                selected=(selected_id == item.get("id")) or (idx == 0 and not selected_id),
                cluster_count=clusters_by_item.get(item.get("id"), 0),
            )
        )

    return (
        '<div class="timeline-head">'
        '<div>'
        '<h1>Today’s Cognition Feed</h1>'
        f'<p>Hermes processed {total} items from multiple sources.</p>'
        '</div>'
        f'<div class="view-tabs">{tabs_html}</div>'
        '</div>'
        f'<div class="feed">{"".join(cards)}</div>'
    )


def item_card(item: dict, selected: bool = False, cluster_count: int = 0) -> str:
    item_id = _esc(item.get("id", ""))
    url = _esc(item.get("url", ""))
    title = _esc(item.get("title", ""))
    summary = _esc(item.get("summary", ""))
    source = item.get("source", "")
    category = _esc(item.get("category", ""))
    tags = item.get("tags") or []
    importance = item.get("importance") or 0
    status = item.get("status", "new")
    published = item.get("published_at", "")
    cluster_hash = _esc(str(item.get("cluster_hash", "")))

    source_label, source_name, _ = _source_meta(source)
    status_label, status_class = _status_meta(status)

    selected_class = "card selected" if selected else "card"
    cluster_data = f'data-cluster="{cluster_hash}"' if cluster_hash else ""

    source_badge = f'<span class="badge source">{source_label}</span>'
    category_badge = f'<span class="badge">{category}</span>' if category else ""
    cluster_badge_html = _cluster_badge(cluster_count)

    tag_badges = "".join(f'<span class="badge">{_esc(t)}</span>' for t in tags[:3])

    time_text = _relative_time(published)

    card = (
        f'<article class="{selected_class}" data-id="{item_id}" data-url="{url}" '
        f'{cluster_data} id="card-{item_id}" '
        f'hx-get="/ui/cognition/{item_id}" hx-target="#cognition-panel" '
        f'hx-trigger="click" hx-swap="outerHTML">'
        '<div class="card-top">'
        f'<h2>{title}</h2>'
        f'<span class="status {status_class}">{status_label}</span>'
        '</div>'
        f'<p class="summary">{summary}</p>'
        '<div class="meta-row">'
        '<div class="badges">'
        f'{source_badge}{category_badge}{cluster_badge_html}{tag_badges}'
        '</div>'
        f'<span class="importance">{_importance_dots(importance)}</span>'
        '</div>'
        '<div class="action-row">'
        f'<span class="time">{time_text}</span>'
        '<div class="actions">'
        f'<button class="btn" onclick="event.stopPropagation(); window.open(\'{url}\', \'_blank\')">'
        f'{_icon("external")}Open</button>'
    )

    if cluster_count > 1:
        card += (
            f'<button class="btn" onclick="event.stopPropagation();" '
            f'hx-get="/ui/cluster/{cluster_hash}" hx-target="#timeline-content" '
            f'hx-swap="innerHTML">{_icon("cluster")}Cluster</button>'
        )

    card += (
        f'<button class="btn primary" onclick="event.stopPropagation();" '
        f'hx-post="/api/items/{item_id}/save" hx-target="closest .card" '
        f'hx-swap="outerHTML">{_icon("arrow-right")}Wiki</button>'
        '</div></div></article>'
    )
    return card


def cognition_panel(
    item: dict,
    related_items: list[dict] | None = None,
    cluster_info: dict | None = None,
) -> str:
    """Render the 5 sub-panels of the cognition panel."""
    title = _esc(item.get("title", ""))
    summary = _esc(item.get("summary", ""))
    judgment = item.get("hermes_judgment")
    concepts = item.get("concepts") or item.get("tags") or []
    source_divergence = item.get("source_divergence") or {}
    wiki_slug = item.get("wiki_candidate_slug") or _slugify(title)
    related_items = related_items or []
    cluster_info = cluster_info or {}

    # Why this matters
    if judgment:
        why_html = f'<p>{_esc(judgment)}</p>'
    else:
        why_html = (
            f'<p>{summary}</p>'
            '<p style="margin-top:8px;color:var(--muted-2);font-size:12px;">'
            "Hermes 判断待 processor 升级</p>"
        )

    # Related concepts
    concepts_html = "".join(f'<span class="concept">{_esc(c)}</span>' for c in concepts)

    # Source divergence
    divergence_html = ""
    if source_divergence and len(source_divergence) >= 2:
        divergence_items = "".join(
            f'<div class="diff-item"><strong>{_esc(source)}</strong>'
            f'<span>{_esc(text)}</span></div>'
            for source, text in source_divergence.items()
        )
        divergence_html = (
            '<div class="panel">'
            '<h3>Source Divergence</h3>'
            f'<div class="source-diff">{divergence_items}</div>'
            '</div>'
        )

    # Cluster map
    cluster_map_html = ""
    if related_items:
        mini_cards = "".join(
            f'<div class="mini-card"><b>{_esc(r.get("source", "?"))}</b>'
            f'{_esc(r.get("title", "")[:60])}</div>'
            for r in related_items[:4]
        )
        cluster_map_html = (
            '<div class="panel">'
            '<h3>Cluster Map</h3>'
            f'<div class="cluster-map">{mini_cards}</div>'
            '</div>'
        )

    # Wiki candidate
    wiki_concepts = item.get("concepts") or item.get("tags") or []
    wiki_concepts_text = ", ".join(_esc(c) for c in wiki_concepts[:5])
    wiki_html = (
        '<div class="panel">'
        '<h3>Wiki Candidate</h3>'
        f'<p>建议保存为 entity：<br><strong>{_esc(wiki_slug)}</strong><br><br>'
        f'关联 concepts：{wiki_concepts_text or "—"}</p>'
        '</div>'
    )

    return (
        '<aside class="cognition" id="cognition-panel">'
        '<div class="panel"><h3>Why this matters</h3>' + why_html + '</div>'
        '<div class="panel"><h3>Related Concepts</h3><div class="concepts">' + concepts_html + '</div></div>'
        + divergence_html
        + cluster_map_html
        + wiki_html
        + '</aside>'
    )


def palette_results(results: dict, q: str) -> str:
    """Render command palette results HTML."""
    items = results.get("items") or []
    concepts = results.get("concepts") or []
    clusters = results.get("clusters") or []
    if not items and not concepts and not clusters:
        return f'<div class="palette-empty">No matches for "{_esc(q)}"</div>'

    parts = []
    if items:
        parts.append('<div class="palette-group-title">Items</div>')
        for it in items:
            item_id = _esc(it.get("id", ""))
            title = _esc(it.get("title", ""))
            source = _esc(it.get("source", ""))
            parts.append(
                f'<a class="palette-item" href="/?selected={item_id}" data-type="item" data-id="{item_id}">'
                f'<span class="icon">{_icon("document")}</span>'
                f'<span class="primary">{title}</span>'
                f'<span class="secondary">{_esc(source)}</span>'
                '</a>'
            )

    if concepts:
        parts.append('<div class="palette-group-title">Concepts</div>')
        for c in concepts:
            name = _esc(c.get("name", ""))
            count = c.get("count", 0)
            parts.append(
                f'<a class="palette-item" href="/?perspective=ai-research" data-type="concept" data-name="{name}">'
                f'<span class="icon">{_icon("tag")}</span>'
                f'<span class="primary">{name}</span>'
                f'<span class="secondary">{count}</span>'
                '</a>'
            )

    if clusters:
        parts.append('<div class="palette-group-title">Clusters</div>')
        for c in clusters:
            cluster_hash = _esc(c.get("cluster_hash", ""))
            preview = _esc(c.get("preview", ""))
            count = c.get("member_count", 0)
            parts.append(
                f'<a class="palette-item" href="/?cluster={cluster_hash}" data-type="cluster" data-id="{cluster_hash}">'
                f'<span class="icon">{_icon("cluster")}</span>'
                f'<span class="primary">{preview}</span>'
                f'<span class="secondary">{count} items</span>'
                '</a>'
            )

    return f'<div class="palette-results">{ "".join(parts) }</div>'


def cluster_view(cluster: dict, member_items: list[dict]) -> str:
    """Cluster detail view replacing #timeline-content."""
    member_items = member_items or []

    # Event title and summary
    event_title = _esc(cluster.get("title") or (member_items[0].get("title") if member_items else "Cluster"))
    summary = _esc(cluster.get("summary") or "")

    # Sources represented in this cluster
    sources = list({m.get("source", "") for m in member_items if m.get("source")})

    # Hermes summary: use cluster-level if available, else first member judgment, else first member summary
    hermes_summary = _esc(cluster.get("hermes_summary") or "")
    if not hermes_summary and member_items:
        first_judgment = member_items[0].get("hermes_judgment")
        if first_judgment:
            hermes_summary = _esc(first_judgment)
        else:
            hermes_summary = _esc(member_items[0].get("summary", ""))

    # Source divergence: cluster-level or first member
    divergence = cluster.get("source_divergence") or (member_items[0].get("source_divergence") if member_items else {}) or {}

    # Concepts: union across members
    all_concepts = set()
    for m in member_items:
        for c in (m.get("concepts") or m.get("tags") or []):
            if c:
                all_concepts.add(c)

    source_badges = "".join(f'<span class="badge source">{_esc(s)}</span>' for s in sources if s)

    # Hermes summary panel
    summary_html = (
        f'<div class="panel"><h3>Hermes Summary</h3><p>{hermes_summary}</p></div>'
        if hermes_summary else ""
    )

    # Different opinions panel
    divergence_html = ""
    if divergence:
        divergence_items = "".join(
            f'<div class="diff-item"><strong>{_esc(source)}</strong>'
            f'<span>{_esc(text)}</span></div>'
            for source, text in divergence.items()
        )
        divergence_html = (
            '<div class="panel"><h3>Different Opinions</h3>'
            f'<div class="source-diff">{divergence_items}</div></div>'
        )

    # Related items: reuse item_card so they remain clickable
    member_cards = "".join(
        item_card(m, selected=False, cluster_count=0)
        for m in member_items[:6]
    )

    # Related wiki concepts
    wiki_html = "".join(f'<span class="concept">{_esc(c)}</span>' for c in list(all_concepts)[:12])

    return (
        '<div class="timeline-head">'
        '<div><h1>Cluster Detail</h1><p>Multi-source view of a single event.</p></div>'
        '</div>'
        '<div class="feed">'
        '<div class="panel">'
        f'<h2 style="font-size:18px;margin:0 0 10px;font-weight:600;line-height:1.3;">{event_title}</h2>'
        + (f'<p>{summary}</p>' if summary else '')
        + f'<div class="badges" style="margin-top:12px;">{source_badges}</div>'
        + '</div>'
        + summary_html
        + divergence_html
        + '<div class="panel"><h3>Related Items</h3><div class="feed">' + (member_cards or '<p>No related items.</p>') + '</div></div>'
        + '<div class="panel"><h3>Related Wiki</h3><div class="concepts">' + (wiki_html or '<span class="concept">—</span>') + '</div></div>'
        + '</div>'
    )


def topbar_metrics(stats: dict) -> str:
    new = (stats.get("by_status") or {}).get("new", 0) if stats else 0
    clusters = stats.get("clusters_count", 0) if stats else 0
    saved = (stats.get("by_status") or {}).get("saved", 0) if stats else 0
    return (
        '<div class="metrics" id="topbar-metrics">'
        f'<span class="metric">NEW <b>{new}</b></span>'
        f'<span class="metric">CLUSTERS <b>{clusters}</b></span>'
        f'<span class="metric">SAVED <b>{saved}</b></span>'
        '</div>'
    )


def sidebar_content(stats: dict) -> str:
    by_perspective = stats.get("by_perspective") if stats else {}
    by_source = stats.get("by_source") if stats else {}
    by_status = stats.get("by_status") if stats else {}

    def nav_item(label: str, href: str, hx: str, count, active: bool = False) -> str:
        cls = "nav-item active" if active else "nav-item"
        return (
            f'<a class="{cls}" href="{href}" hx-get="{hx}" hx-target="#timeline-content" '
            f'hx-swap="innerHTML" hx-push-url="true">'
            f'<span>{label}</span><span class="count">{count}</span></a>'
        )

    # Source dots
    def source_dot(color: str) -> str:
        return f'<i class="source-dot {color}"></i>'

    return (
        '<div>'
        '<div class="section-title">Perspective</div>'
        f'{nav_item("Today", "/?perspective=today", "/ui/items?perspective=today", by_perspective.get("today", 0), active=True)}'
        f'{nav_item("Clusters", "/?perspective=clusters", "/ui/items?perspective=clusters", by_perspective.get("clusters", 0))}'
        f'{nav_item("AI / Research", "/?perspective=ai-research", "/ui/items?perspective=ai-research", by_perspective.get("ai-research", 0))}'
        f'{nav_item("Engineering", "/?perspective=engineering", "/ui/items?perspective=engineering", by_perspective.get("engineering", 0))}'
        f'{nav_item("Markets", "/?perspective=markets", "/ui/items?perspective=markets", by_perspective.get("markets", 0))}'
        f'{nav_item("Random Drift", "/?perspective=random", "/ui/items?view=random", "∞")}'
        f'{nav_item("Saved Candidates", "/?perspective=saved", "/ui/items?perspective=saved", by_perspective.get("saved", 0))}'

        '<div class="section-title">Sources</div>'
        f'<a class="nav-item" href="/?source=hackernews" hx-get="/ui/items?source=hackernews" hx-target="#timeline-content" hx-swap="innerHTML" hx-push-url="true">'
        f'<span>{source_dot("")}Hacker News</span><span class="count">{by_source.get("hackernews", 0)}</span></a>'
        f'<a class="nav-item" href="/?source=arxiv" hx-get="/ui/items?source=arxiv" hx-target="#timeline-content" hx-swap="innerHTML" hx-push-url="true">'
        f'<span>{source_dot("purple")}arXiv</span><span class="count">{by_source.get("arxiv", 0)}</span></a>'
        f'<a class="nav-item" href="/?source=github" hx-get="/ui/items?source=github" hx-target="#timeline-content" hx-swap="innerHTML" hx-push-url="true">'
        f'<span>{source_dot("green")}GitHub</span><span class="count">{by_source.get("github", 0)}</span></a>'
        f'<a class="nav-item" href="/?source=huggingface" hx-get="/ui/items?source=huggingface" hx-target="#timeline-content" hx-swap="innerHTML" hx-push-url="true">'
        f'<span>{source_dot("purple")}HuggingFace</span><span class="count">{by_source.get("huggingface", 0)}</span></a>'
        f'<a class="nav-item" href="/?source=rss" hx-get="/ui/items?source=rss" hx-target="#timeline-content" hx-swap="innerHTML" hx-push-url="true">'
        f'<span>{source_dot("orange")}RSS</span><span class="count">{by_source.get("rss", 0)}</span></a>'

        '<div class="section-title">Status</div>'
        f'{nav_item("New", "/?status=new", "/ui/items?status=new", by_status.get("new", 0))}'
        f'{nav_item("Processed", "/?status=processed", "/ui/items?status=processed", by_status.get("processed", 0))}'
        f'{nav_item("Saved", "/?status=saved", "/ui/items?status=saved", by_status.get("saved", 0))}'
        f'{nav_item("Archived", "/?status=archived", "/ui/items?status=archived", by_status.get("archived", 0))}'
        '</div>'
    )


def empty_timeline(message: str = "No items", hint: str = "") -> str:
    return (
        '<div class="empty-state" style="padding:48px 24px;text-align:center;color:var(--muted);">'
        '<h2 style="margin:0 0 8px;color:var(--text);font-size:18px;font-weight:600;">' + _esc(message) + '</h2>'
        f'<p style="margin:0;font-size:13px;">{_esc(hint or "Run a collector or try a different perspective.")}</p>'
        '</div>'
    )