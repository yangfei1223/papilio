# Web UI Reading Inbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign Papilio's Web UI into a medium-high-density reading inbox with lightweight source iconography.

**Architecture:** Keep the current FastAPI + HTMX + server-rendered template architecture. Update `nas/templates.py` to emit richer item-row markup and update `nas/web/index.html` to provide the reading inbox layout and visual system.

**Tech Stack:** FastAPI, HTMX, hand-written Python string templates, static HTML/CSS, SQLite-backed local sample data.

## Global Constraints

- Do not add React, Vue, Tailwind, or any build tooling.
- Do not add schema fields such as `image_url` or `favicon_url`.
- Do not implement real article thumbnails in this pass.
- Do not change collector behavior.
- Do not add authentication, recommendations, full-text search, or mobile-first behavior.
- Keep manual escaping through `_esc()`.
- Avoid adding new dependencies.

---

## File Structure

- Modify `nas/templates.py`
  - Owns feed fragment markup for item rows, stats, empty state, and pagination.
  - Adds small helper functions for source visual labels/classes, status labels, and priority labels.

- Modify `nas/web/index.html`
  - Owns the static shell, sidebar navigation, layout CSS, responsive behavior, and shared visual tokens.
  - Keeps existing HTMX endpoints and `#feed` replacement behavior.

No other files should be changed for the UI implementation.

---

### Task 1: Template Markup And Helpers

**Files:**
- Modify: `nas/templates.py`

**Interfaces:**
- Consumes: Existing item dictionaries returned by `Database.list_items()`.
- Produces:
  - `item_row(item: dict) -> str` with source icon tile, metadata, priority, and wiki action markup.
  - `feed_page(items: list[dict], total: int, page: int, pages: int, source: str = "", category: str = "") -> str` preserving infinite scroll behavior.
  - `stats_widget(stats: dict) -> str` with compact inbox stats markup.

- [ ] **Step 1: Inspect current template behavior**

Run: `sed -n '1,260p' nas/templates.py`

Expected: See existing `item_row`, `feed_page`, `stats_widget`, and `_esc`.

- [ ] **Step 2: Add helper functions before `item_row`**

Add these helpers near the top of `nas/templates.py` after the module docstring:

```python
SOURCE_META = {
    "hackernews": ("HN", "Hacker News", "source-hackernews"),
    "arxiv": ("arX", "arXiv", "source-arxiv"),
    "github": ("GH", "GitHub", "source-github"),
    "huggingface": ("HF", "HuggingFace", "source-huggingface"),
    "rss": ("RSS", "RSS", "source-rss"),
}


def _source_meta(source: str) -> tuple[str, str, str]:
    key = (source or "").split("/")[0].lower()
    label, name, cls = SOURCE_META.get(key, ("•", source or "Source", "source-generic"))
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
    if score >= 5:
        return "P1", "priority-high"
    if score == 4:
        return "P2", "priority-medium"
    if score == 3:
        return "P3", "priority-low"
    return "P-", "priority-none"
```

- [ ] **Step 3: Replace `item_row` with reading inbox markup**

Replace the existing `item_row` function with:

```python
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
        parts.append('<span class="wiki-action wiki-action-saved">Saved</span>')
    elif status == "saving":
        parts.append('<span class="wiki-action wiki-action-saving">Saving</span>')
    else:
        parts.append(
            f'<button class="wiki-action wiki-action-button" hx-post="/api/items/{item_id}/save" '
            f'hx-swap="outerHTML" hx-target="#item-{item_id} .item-side">Save</button>'
        )
    parts.append('</div>')

    parts.append('</article>')
    return "\n".join(parts)
```

- [ ] **Step 4: Update `feed_page` empty, header, and pagination markup**

Replace `feed_page` with:

```python
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
```

- [ ] **Step 5: Update `stats_widget` markup**

Replace `stats_widget` with:

```python
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
```

- [ ] **Step 6: Run Python compile check**

Run: `python -m py_compile nas/templates.py`

Expected: command exits with status 0 and no output.

---

### Task 2: Static Shell And Reading Inbox CSS

**Files:**
- Modify: `nas/web/index.html`

**Interfaces:**
- Consumes: Markup emitted by `nas/templates.py` from Task 1.
- Produces: Static shell with `#feed`, HTMX navigation, responsive reading inbox styling, and source/status/priority visual classes.

- [ ] **Step 1: Inspect current shell**

Run: `sed -n '1,280p' nas/web/index.html`

Expected: See current dark CSS, sidebar links, stats HTMX target, and feed HTMX target.

- [ ] **Step 2: Replace the `<style>` block**

Replace the full existing `<style>...</style>` block in `nas/web/index.html` with a CSS system that defines:

```css
:root {
  --bg: #f4f1ea;
  --surface: #fffdf8;
  --surface-strong: #ffffff;
  --text: #24211d;
  --muted: #766f66;
  --faint: #9b948a;
  --border: #ded7cb;
  --border-soft: #ebe5db;
  --accent: #2f6f73;
  --accent-ink: #18464a;
  --amber: #a66218;
  --green: #4d7f45;
  --red: #a94b42;
  --purple: #6f5b9a;
  --blue: #496fa8;
  --shadow: 0 18px 50px rgba(49, 42, 32, .08);
}

* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  min-height: 100vh;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  line-height: 1.5;
}
a { color: inherit; }
.layout { display: grid; grid-template-columns: 248px minmax(0, 1fr); max-width: 1280px; min-height: 100vh; margin: 0 auto; }
.sidebar { position: sticky; top: 0; height: 100vh; padding: 28px 18px; border-right: 1px solid var(--border); }
.brand { display: flex; align-items: center; gap: 10px; margin-bottom: 28px; color: var(--text); text-decoration: none; }
.brand-mark { width: 38px; height: 38px; border: 1px solid var(--border); border-radius: 8px; display: grid; place-items: center; background: var(--surface); color: var(--accent-ink); font-weight: 800; }
.brand-copy strong { display: block; font-size: 15px; }
.brand-copy span { display: block; font-size: 12px; color: var(--muted); }
.nav-label { margin: 22px 10px 8px; color: var(--faint); font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .08em; }
.sidebar nav { display: grid; gap: 4px; }
.sidebar nav a { display: flex; align-items: center; justify-content: space-between; min-height: 36px; padding: 8px 10px; border-radius: 8px; color: var(--muted); text-decoration: none; font-size: 14px; }
.sidebar nav a:hover, .sidebar nav a.active { background: rgba(255, 255, 255, .68); color: var(--text); box-shadow: inset 0 0 0 1px var(--border-soft); }
.nav-dot { width: 8px; height: 8px; border-radius: 99px; background: var(--border); }
.nav-dot.hn { background: var(--amber); }
.nav-dot.arxiv { background: var(--red); }
.nav-dot.github { background: var(--text); }
.nav-dot.hf { background: var(--purple); }
.nav-dot.rss { background: var(--green); }
.stats-slot { margin-top: 22px; }
.stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.stats-grid div { min-height: 58px; padding: 10px; border: 1px solid var(--border-soft); border-radius: 8px; background: rgba(255, 253, 248, .7); }
.stats-grid span { display: block; font-size: 18px; font-weight: 750; }
.stats-grid small { display: block; margin-top: 2px; color: var(--muted); font-size: 11px; }
.main { padding: 28px 34px 48px; }
.feed-panel { max-width: 940px; margin: 0 auto; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); box-shadow: var(--shadow); overflow: hidden; }
.feed-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; padding: 22px 24px 18px; border-bottom: 1px solid var(--border-soft); background: rgba(255, 255, 255, .56); }
.eyebrow { margin-bottom: 3px; color: var(--accent); font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: .1em; }
.feed-heading h1 { font-size: 24px; line-height: 1.15; letter-spacing: 0; }
.feed-count { flex-shrink: 0; color: var(--muted); font-size: 13px; }
.item-list { display: grid; }
.item-row { display: grid; grid-template-columns: 48px minmax(0, 1fr) 86px; gap: 14px; padding: 16px 18px; border-bottom: 1px solid var(--border-soft); }
.item-row:hover { background: #fffaf0; }
.source-tile { width: 44px; height: 44px; border-radius: 8px; display: grid; place-items: center; border: 1px solid currentColor; background: #f8f4ec; color: var(--accent); font-size: 12px; font-weight: 850; }
.source-hackernews .source-tile, .source-tile.source-hackernews { color: var(--amber); background: #fff3df; }
.source-arxiv .source-tile, .source-tile.source-arxiv { color: var(--red); background: #fff0ed; }
.source-github .source-tile, .source-tile.source-github { color: var(--text); background: #efede8; }
.source-huggingface .source-tile, .source-tile.source-huggingface { color: var(--purple); background: #f3efff; }
.source-rss .source-tile, .source-tile.source-rss { color: var(--green); background: #edf7ea; }
.item-main { min-width: 0; }
.item-title { font-size: 16px; line-height: 1.34; font-weight: 720; letter-spacing: 0; }
.item-title a { color: var(--text); text-decoration: none; }
.item-title a:hover { color: var(--accent-ink); text-decoration: underline; text-decoration-thickness: 1px; text-underline-offset: 3px; }
.item-summary { margin-top: 7px; color: var(--muted); font-size: 13px; line-height: 1.55; }
.item-meta { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.meta-chip { display: inline-flex; align-items: center; min-height: 22px; padding: 2px 7px; border: 1px solid var(--border-soft); border-radius: 999px; color: var(--muted); background: rgba(255, 255, 255, .6); font-size: 11px; white-space: nowrap; }
.category-chip { color: var(--accent-ink); }
.status-processed { color: var(--green); }
.status-saving { color: var(--amber); }
.status-saved { color: var(--purple); }
.wiki-link { margin-top: 8px; color: var(--purple); font-size: 12px; }
.wiki-link a { color: var(--purple); text-decoration: none; }
.item-side { display: flex; flex-direction: column; align-items: flex-end; gap: 8px; }
.priority-pill, .wiki-action { min-width: 54px; min-height: 28px; display: inline-flex; align-items: center; justify-content: center; border-radius: 8px; font-size: 12px; font-weight: 750; }
.priority-pill { border: 1px solid var(--border-soft); color: var(--muted); background: #fbf8f1; }
.priority-high { color: var(--red); background: #fff0ed; border-color: #f0c7c0; }
.priority-medium { color: var(--amber); background: #fff3df; border-color: #ecd3ad; }
.priority-low { color: var(--blue); background: #eef3ff; border-color: #cbd8f0; }
.wiki-action { border: 1px solid var(--border); background: var(--surface-strong); color: var(--text); text-decoration: none; }
.wiki-action-button { cursor: pointer; font-family: inherit; }
.wiki-action-button:hover { border-color: var(--accent); color: var(--accent-ink); background: #eef7f5; }
.wiki-action-saving { color: var(--amber); }
.wiki-action-saved { color: var(--green); }
.empty-state { padding: 64px 24px; text-align: center; color: var(--muted); }
.empty-icon { width: 52px; height: 52px; margin: 0 auto 14px; border-radius: 10px; display: grid; place-items: center; background: #eef7f5; color: var(--accent-ink); font-weight: 850; }
.empty-state h2 { color: var(--text); font-size: 18px; margin-bottom: 4px; }
.loading { padding: 24px; text-align: center; color: var(--muted); font-size: 13px; }
@media (max-width: 760px) {
  .layout { display: block; }
  .sidebar { position: static; height: auto; border-right: 0; border-bottom: 1px solid var(--border); }
  .sidebar nav { grid-template-columns: 1fr 1fr; }
  .main { padding: 18px 12px 32px; }
  .feed-heading { align-items: flex-start; flex-direction: column; }
  .item-row { grid-template-columns: 42px minmax(0, 1fr); }
  .source-tile { width: 38px; height: 38px; }
  .item-side { grid-column: 2; flex-direction: row; align-items: center; justify-content: flex-start; }
}
```

- [ ] **Step 3: Update sidebar shell markup**

Keep `<script src="/htmx.min.js"></script>` and the `#feed` target. Replace the body layout markup with:

```html
<div class="layout">
  <aside class="sidebar">
    <a class="brand" href="/">
      <span class="brand-mark">PX</span>
      <span class="brand-copy">
        <strong>Papilio</strong>
        <span>Reading inbox</span>
      </span>
    </a>

    <p class="nav-label">Sources</p>
    <nav>
      <a href="/?source=" class="active" hx-get="/ui/items?per_page=50" hx-target="#feed" hx-swap="innerHTML" hx-push-url="true">All <span class="nav-dot"></span></a>
      <a href="/?source=hackernews" hx-get="/ui/items?source=hackernews&per_page=50" hx-target="#feed" hx-swap="innerHTML" hx-push-url="true">Hacker News <span class="nav-dot hn"></span></a>
      <a href="/?source=arxiv" hx-get="/ui/items?source=arxiv&per_page=50" hx-target="#feed" hx-swap="innerHTML" hx-push-url="true">arXiv <span class="nav-dot arxiv"></span></a>
      <a href="/?source=github" hx-get="/ui/items?source=github&per_page=50" hx-target="#feed" hx-swap="innerHTML" hx-push-url="true">GitHub <span class="nav-dot github"></span></a>
      <a href="/?source=huggingface" hx-get="/ui/items?source=huggingface&per_page=50" hx-target="#feed" hx-swap="innerHTML" hx-push-url="true">HuggingFace <span class="nav-dot hf"></span></a>
      <a href="/?source=rss" hx-get="/ui/items?source=rss&per_page=50" hx-target="#feed" hx-swap="innerHTML" hx-push-url="true">RSS <span class="nav-dot rss"></span></a>
    </nav>

    <p class="nav-label">State</p>
    <div class="stats-slot" hx-get="/ui/stats" hx-trigger="load" hx-swap="innerHTML"></div>
  </aside>

  <main class="main">
    <div id="feed" hx-get="/ui/items?per_page=50" hx-trigger="load" hx-swap="innerHTML">
      <section class="feed-panel">
        <div class="loading">Loading Papilio inbox...</div>
      </section>
    </div>
  </main>
</div>
```

- [ ] **Step 4: Verify HTMX endpoint references are preserved**

Run: `rg -n "hx-get|hx-post|hx-target|id=\"feed\"" nas/web/index.html nas/templates.py`

Expected:
- `nas/web/index.html` includes `id="feed"`.
- Source links use `/ui/items`.
- Stats uses `/ui/stats`.
- Template save button uses `/api/items/{item_id}/save`.
- Template pagination uses `/ui/items`.

---

### Task 3: Local Verification And Polish Pass

**Files:**
- Modify only if verification reveals small layout or syntax issues: `nas/templates.py`, `nas/web/index.html`

**Interfaces:**
- Consumes: Completed Tasks 1 and 2.
- Produces: Verified local UI with no Python syntax errors and no obvious responsive overlap.

- [ ] **Step 1: Run compile check**

Run: `python -m py_compile nas/templates.py nas/app.py nas/models.py`

Expected: command exits with status 0 and no output.

- [ ] **Step 2: Start local NAS dev server**

Run from `nas/`: `PAPILIO_DATA_DIR=./data uvicorn app:app --host 127.0.0.1 --port 8000`

Expected: uvicorn starts and reports it is serving on `http://127.0.0.1:8000`.

- [ ] **Step 3: Smoke test API and UI fragments**

Run:

```bash
curl -s http://127.0.0.1:8000/api/health
curl -s "http://127.0.0.1:8000/ui/items?per_page=5"
curl -s http://127.0.0.1:8000/ui/stats
```

Expected:
- Health response contains `"status":"ok"`.
- `/ui/items` response contains `feed-panel`.
- `/ui/stats` response contains `stats-grid`.

- [ ] **Step 4: Browser visual check**

Open `http://127.0.0.1:8000` and inspect:

- Desktop width around 1280px: sidebar, feed panel, item rows, icon tiles, priority pills, and save actions are aligned.
- Narrow width around 390px: sidebar stacks above feed, item rows do not clip text, action controls remain visible.
- Source filters still replace the feed.

- [ ] **Step 5: Final diff review**

Run: `git diff -- nas/templates.py nas/web/index.html`

Expected:
- Diff only touches the UI template/shell files.
- No new dependency files.
- Existing HTMX routes are preserved.

