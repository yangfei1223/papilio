# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Papilio (🦋) is a personal information aggregation station. It pulls from multiple sources (RSS, Hacker News, arXiv, GitHub), enriches items with AI, and serves a browsable feed. `PLAN.md` is the authoritative design doc — read it for architecture diagrams, the full schema, the cronjob schedule, MVP phases, and the explicit non-goals in §七 (no auth, no recommender, no auto-wiki, no mobile, no full-text search, no CI).

## Two-machine architecture (the core mental model)

Code is split across directories by *where it runs*, not by layer:

- **Mac mini ("brain", 7×24)** → runs everything in `collectors/` and `scripts/`: source collectors that fetch + normalize, and the AI processor.
- **NAS ("warehouse", 7×24)** → runs everything in `nas/`: FastAPI + SQLite + static Web UI, packaged as a Docker container.

The two machines talk **only over HTTP API** (`http://nas:8899` by default; override with `PAPILIO_NAS_URL`). No NFS mount, no direct filesystem access. This split is load-bearing: **the NAS does zero AI**. Collectors POST raw items (`status=new`); a separate Hermes cronjob (every 30 min, `scripts/process_items.py`) pulls `?status=new`, emits JSON for the LLM to enrich, and PATCHes summary/category/importance back. Keep that two-stage split when adding features.

## Commands

No `pyproject.toml`, no `package.json`, no tests, no linter, no CI (intentional — PLAN.md §七). Two separate `requirements.txt` files.

**NAS (deploy):**
```bash
cd nas && docker compose up -d     # → http://nas:8899
```

**NAS (local dev)** — must run from `nas/` because modules are imported flat:
```bash
cd nas && uvicorn app:app --host 0.0.0.0 --port 8000
# PAPILIO_DATA_DIR defaults to /data; point it somewhere writable when dev'ing on a Mac:
PAPILIO_DATA_DIR=./data uvicorn app:app --port 8000
```

**Collectors (Mac mini)** — install once, run from `collectors/` (flat imports again) or via the dispatcher:
```bash
cd collectors && pip install -r requirements.txt
python hackernews.py                      # run one directly
python ../scripts/run_collector.py hackernews   # or via dispatcher: hackernews|rss|arxiv|github|all
```

**Processor:** `python scripts/process_items.py` — prints JSON of new items + instructions for Hermes AI to consume and PATCH back.

**Smoke test:** `curl http://nas:8899/api/health`

## Code organization & conventions

- **Flat imports, run-from-cwd.** Neither `nas/` nor `collectors/` is a Python package. `app.py` does `from models import...` / `from templates import...`; collectors do `from base import...`. `scripts/run_collector.py` injects `collectors/` onto `sys.path` and dispatches by name. Don't introduce package-style imports without also fixing these entry points.
- **Collector pipeline** (`collectors/base.py`, `BaseCollector.run()`): `fetch() → _normalize() → _dedup() → _post()`. New sources implement only `fetch()`; the base class handles normalization, in-batch dedup by URL, and POSTing to `/api/items`.
- **Item identity & dedup:** `id = sha256(source|url|published_at)[:16]`; DB upsert matches on `url OR id`. Status lifecycle is `new → processed → saved` (`saving` is a transient state set when wiki save is triggered).
- **DB schema** lives in `models.py` — `SCHEMA` is auto-applied on `Database.__init__`. Two tables: `items` and `item_clusters`. JSON-ish fields (`tags`, `meta`) are stored as TEXT and (de)serialized by `to_db_row()` / `_deserialize_row()`.
- **Web UI is HTMX + server-rendered fragments, no Jinja2.** `templates.py` builds HTML from hand-rolled string templates with manual `_esc()` escaping. Routes `/ui/items` and `/ui/stats` return HTML fragments; `web/index.html` is the static shell. Infinite scroll uses `hx-trigger="revealed"`; the `[→ Wiki]` button `hx-post`s to `/api/items/:id/save`.
- **CORS is wide open** (`allow_origins=["*"]`) — intentional for LAN use; there is deliberately no auth.

## Gotchas

- **Env var is `PAPILIO_DATA_DIR`.** This project was renamed `butterfly → papillon → papilio` (visible in git history, so old branches/tags/tags may use the old names). The env var read by `app.py` and set in `docker-compose.yml` / `.env.example` is `PAPILIO_DATA_DIR`.
- `models.py` imports `uuid` but doesn't use it.
- Source-config collectors (`rss`, `arxiv`) read `collectors/config.yaml`; `rss` ships with an empty feed list, so it does nothing until feeds are added there.
- The GitHub collector prefers `gh` CLI and falls back to the GitHub search API.
