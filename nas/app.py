"""Butterfly — 个人信息聚合站后端.

NAS 上运行：uvicorn app:app --host 0.0.0.0 --port 8000
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from models import Database, Item
from templates import feed_page, stats_widget

app = FastAPI(title="Butterfly", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------- database ---------------

DATA_DIR = Path(os.getenv("BUTTERFLY_DATA_DIR", "/data"))
DB_PATH = DATA_DIR / "butterfly.db"

db: Database | None = None


def get_db() -> Database:
    global db
    if db is None:
        db = Database(DB_PATH)
    return db


# --------------- startup / shutdown ---------------

@app.on_event("startup")
async def startup():
    get_db()


@app.on_event("shutdown")
async def shutdown():
    global db
    if db:
        db.close()
        db = None


# --------------- API routes ---------------

@app.get("/api/items")
def list_items(
    status: str | None = Query(None),
    source: str | None = Query(None),
    category: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """获取条目列表，支持按状态、来源、分类筛选和分页."""
    return get_db().list_items(
        status=status,
        source=source,
        category=category,
        page=page,
        per_page=per_page,
    )


@app.get("/api/items/{item_id}")
def get_item(item_id: str):
    """获取单条详情."""
    item = get_db().get_item(item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    return item


@app.post("/api/items")
def create_items(items: list[dict]):
    """批量入库。collector POST 的数据."""
    created = []
    updated = []
    for raw in items:
        item = Item.from_raw(raw)
        result = get_db().upsert_item(item)
        if result == "created":
            created.append(item.id)
        else:
            updated.append(item.id)
    return {"created": len(created), "updated": len(updated), "ids": created}


@app.patch("/api/items/{item_id}")
def update_item(item_id: str, updates: dict):
    """更新条目字段。processor 用."""
    allowed = {
        "summary", "category", "importance", "tags",
        "status", "wiki_slug", "wiki_saved_at", "meta",
    }
    safe = {k: v for k, v in updates.items() if k in allowed}
    if not safe:
        raise HTTPException(400, "No valid fields to update")
    get_db().update_item(item_id, safe)
    return {"ok": True}


@app.post("/api/items/{item_id}/save")
def save_to_wiki(item_id: str):
    """触发 wiki 沉淀。Hermes 收到后处理."""
    item = get_db().get_item(item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    get_db().update_item(item_id, {"status": "saving"})
    return {
        "ok": True,
        "item": item,
        "message": "Hermes will process this item and save to wiki",
    }


@app.get("/api/stats")
def get_stats():
    """聚合统计."""
    return get_db().get_stats()


@app.get("/api/clusters")
def get_clusters(limit: int = Query(20, ge=1, le=100)):
    """多源交叉聚合."""
    return get_db().get_clusters(limit)


@app.get("/api/health")
def health():
    return {"status": "ok", "db": str(DB_PATH)}


# --------------- UI routes (HTML) ---------------

@app.get("/ui/items", response_class=HTMLResponse)
def ui_items(
    source: str | None = Query(None),
    category: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """HTML feed 渲染."""
    result = get_db().list_items(
        source=source, category=category,
        page=page, per_page=per_page,
    )
    html = feed_page(
        items=result["items"],
        total=result["total"],
        page=result["page"],
        pages=result["pages"],
        source=source or "",
        category=category or "",
    )
    return HTMLResponse(content=html)


@app.get("/ui/stats", response_class=HTMLResponse)
def ui_stats():
    """HTML 侧边栏统计."""
    stats = get_db().get_stats()
    return HTMLResponse(content=stats_widget(stats))


# --------------- static files (Web UI) ---------------

WEB_DIR = Path(os.path.join(os.path.dirname(__file__), "web"))
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="static")
