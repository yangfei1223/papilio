# Papilio Web UI Reading Inbox Redesign

## Goal

Redesign the current Papilio Web UI into a high-quality reading inbox: dense enough for daily scanning, calm enough for reading summaries, and visually richer through lightweight source/category iconography.

This is a UI-only redesign for the existing NAS Web surface. It keeps the current FastAPI + HTMX + server-rendered string-template architecture and does not add a frontend build step.

## Direction

Use the "Compact Inbox" approach:

- A warm, light reading surface instead of the current default dark dashboard look.
- A fixed left navigation rail for source filters and compact stats.
- A main feed optimized for medium-high density.
- Each item gets a visual anchor through a source icon tile, not a real image thumbnail.
- The item body keeps title, summary, source, category, date, status, importance, and wiki action visible without feeling crowded.

## Non-Goals

- Do not add React, Vue, Tailwind, or any build tooling.
- Do not add schema fields such as `image_url` or `favicon_url`.
- Do not implement real article thumbnails in this pass.
- Do not change collector behavior.
- Do not add authentication, recommendations, full-text search, or mobile-first behavior.

## Layout

The page remains a two-region interface:

1. Sidebar navigation
   - Papilio brand mark and short product label.
   - Source filter links: All, Hacker News, arXiv, GitHub, HuggingFace, RSS.
   - A compact stats block loaded from `/ui/stats`.
   - Visual treatment should feel like an inbox control rail, not a marketing sidebar.

2. Feed area
   - Constrained reading width so titles and summaries do not stretch too wide.
   - A compact feed header that frames the current view.
   - Continuous item rows with soft separators.
   - Rows should look grouped and intentional without becoming a heavy card wall.

On narrow screens, the sidebar can stack above the feed. The project does not target mobile as a primary surface, but the layout must not break.

## Item Row

Each item row should include:

- Source icon tile
  - Stable visual anchor based on `source`.
  - Examples: `HN`, `arX`, GitHub mark text, `HF`, `RSS`.
  - CSS classes should allow source-specific color accents.
  - The tile also acts as the future placeholder for real media if `meta.image_url` is added later.

- Main content
  - Title as the primary scan target.
  - Summary below the title when available.
  - Metadata row with source, category, date, and status.
  - Category should be visible but secondary.

- Right actions
  - Importance shown as a quiet priority pill or marker, not a star row.
  - Wiki action shown as a clear save/deposit action.
  - Saved and saving states should have distinct, calm labels.

## Visual Language

- Use warm off-white and soft gray backgrounds.
- Use white or near-white feed surfaces with subtle borders.
- Avoid large gradients, decorative blobs, and heavy card nesting.
- Use multiple restrained accent colors for different sources so the UI does not become one-note.
- Use small, stable dimensions for icon tiles, pills, and actions to prevent layout shifts.
- Keep text sizes modest and suited to an operational reading tool.

## Interaction

Keep existing HTMX behavior:

- Source links call `/ui/items?...` and replace `#feed`.
- Stats load from `/ui/stats`.
- Infinite scroll continues through the `revealed` trigger.
- Wiki action continues to POST `/api/items/:id/save`.

Improve the visual feedback of the wiki action:

- `new` or `processed`: show a concise action button.
- `saving`: show a muted in-progress state.
- `saved`: show a saved state.

## Implementation Scope

Expected files:

- `nas/web/index.html`
  - Replace global styling with the reading inbox visual system.
  - Adjust sidebar and feed shell markup only as needed.

- `nas/templates.py`
  - Update item row markup for icon tile, metadata, priority, and action states.
  - Add small helper functions for source labels/classes and status labels if useful.
  - Keep manual escaping through `_esc()`.

No changes are expected in `nas/app.py`, `nas/models.py`, collectors, or processor code.

## Verification

Manual/local checks:

- Start NAS locally with `PAPILIO_DATA_DIR=./data uvicorn app:app --port 8000` from `nas/`.
- Open the Web UI and verify the initial feed renders.
- Check source filter clicks still replace the feed.
- Check infinite scroll markup still exists when more pages are available.
- Check `new`, `processed`, `saving`, and `saved` rows have sane visual states where sample data allows.
- Inspect at desktop and narrow viewport widths for overlap, clipped text, or broken buttons.

Code checks:

- Run Python compile checks for touched Python files.
- Avoid adding new dependencies.

