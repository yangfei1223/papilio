"""Papilio — 个人信息聚合站后端.

NAS 上运行：uvicorn app:app --host 0.0.0.0 --port 8000
"""

import hashlib
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from models import Database, Item
from templates import (
    timeline_page, item_card, cognition_panel, cluster_view,
    topbar_metrics, sidebar_content, empty_timeline, palette_results,
)

# --------------- database ---------------

DATA_DIR = Path(os.getenv("PAPILIO_DATA_DIR", "/data"))
DB_PATH = DATA_DIR / "papilio.db"

db: Database | None = None


def get_db() -> Database:
    global db
    if db is None:
        db = Database(DB_PATH)
    return db


# --------------- startup / shutdown ---------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    get_db()
    yield
    # shutdown
    global db
    if db:
        db.close()
        db = None


app = FastAPI(title="Papilio", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------- API routes ---------------

@app.get("/api/items")
def list_items(
    source: str | None = Query(None),
    category: str | None = Query(None),
    status: str | None = Query(None),
    perspective: str | None = Query(None),
    sort: str = Query("time"),
    view: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """获取条目列表，支持筛选、排序、视角和分页."""
    return get_db().list_items(
        source=source, category=category, status=status,
        perspective=perspective, sort=sort, view=view,
        page=page, per_page=per_page,
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
    """更新条目字段。processor 用。"""
    safe = {k: v for k, v in updates.items()
            if k in get_db().ALLOWED_COLUMNS}
    if not safe:
        raise HTTPException(400, "No valid fields to update")
    get_db().update_item(item_id, safe)
    return {"ok": True}


@app.post("/api/items/{item_id}/save", response_class=HTMLResponse)
def save_to_wiki(item_id: str):
    """触发 wiki 沉淀。Hermes 收到后处理。返回卡片 HTML 供 HTMX swap。"""
    item = get_db().get_item(item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    get_db().update_item(item_id, {"status": "saving"})
    item["status"] = "saving"
    cluster_count = len(get_db().get_item_clusters(item_id))
    html = item_card(item=item, cluster_count=cluster_count)
    return HTMLResponse(content=html)


@app.get("/api/stats")
def get_stats():
    """聚合统计."""
    return get_db().get_stats()


@app.get("/api/clusters")
def get_clusters(limit: int = Query(20, ge=1, le=100)):
    """多源交叉聚合."""
    return get_db().get_clusters(limit)


@app.post("/api/clusters")
def create_cluster(payload: dict):
    """processor 检测到跨源重复时写入聚类。"""
    cluster_hash = payload.get("cluster_hash")
    item_ids = payload.get("item_ids", [])
    if not cluster_hash or not item_ids:
        raise HTTPException(400, "cluster_hash and item_ids required")
    get_db().create_cluster(cluster_hash, item_ids)
    return {"ok": True, "cluster_hash": cluster_hash, "count": len(item_ids)}


@app.get("/api/health")
def health():
    return {"status": "ok", "db": str(DB_PATH)}


# --------------- UI routes (HTML) ---------------

@app.get("/ui/items", response_class=HTMLResponse)
def ui_items(
    source: str | None = Query(None),
    category: str | None = Query(None),
    status: str | None = Query(None),
    perspective: str | None = Query(None),
    sort: str = Query("time"),
    view: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    selected_id: str = Query(""),
):
    """HTML timeline 渲染。"""
    result = get_db().list_items(
        source=source, category=category, status=status,
        perspective=perspective, sort=sort, view=view,
        page=page, per_page=per_page,
    )
    # Build clusters_by_item: {item_id: cluster_count}
    clusters_by_item = {}
    for item in result["items"]:
        clusters_by_item[item["id"]] = len(
            get_db().get_item_clusters(item["id"])
        )
    if not result["items"]:
        # 让 timeline_page 内部处理 empty（保留 head + view tabs）
        html = timeline_page(
            items=[], total=0,
            sort=sort, perspective=perspective or "",
            source=source or "", selected_id=selected_id,
            clusters_by_item={},
        )
    else:
        html = timeline_page(
            items=result["items"], total=result["total"],
            sort=sort, perspective=perspective or "",
            source=source or "", selected_id=selected_id,
            clusters_by_item=clusters_by_item,
        )
    return HTMLResponse(content=html)


@app.get("/ui/stats", response_class=HTMLResponse)
def ui_stats(part: str = Query("all")):
    """HTML 统计片段。part=topbar 返回顶部指标，part=sidebar 返回侧边栏内容，
    part=all（默认）返回侧边栏内容。"""
    stats = get_db().get_stats()
    if part == "topbar":
        html = topbar_metrics(stats)
    else:
        html = sidebar_content(stats)
    return HTMLResponse(content=html)


@app.get("/ui/cognition/{item_id}", response_class=HTMLResponse)
def ui_cognition(item_id: str):
    """返回认知面板 HTML。"""
    item = get_db().get_item(item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    clusters = get_db().get_item_clusters(item_id)
    related_items = []
    cluster_info = None
    if clusters:
        cluster_info = clusters[0]
        related_items = [
            it for it in get_db().get_cluster_members(cluster_info["cluster_hash"])
            if it["id"] != item_id
        ][:4]
    html = cognition_panel(
        item=item, related_items=related_items, cluster_info=cluster_info,
    )
    return HTMLResponse(content=html)


@app.get("/ui/cluster/{cluster_hash}", response_class=HTMLResponse)
def ui_cluster(cluster_hash: str):
    """返回聚类详情页 HTML（替换 timeline-content）。"""
    cluster = get_db().get_cluster(cluster_hash)
    if not cluster:
        raise HTTPException(404, "Cluster not found")
    members = get_db().get_cluster_members(cluster_hash)
    html = cluster_view(cluster=cluster, member_items=members)
    return HTMLResponse(content=html)


@app.get("/ui/search", response_class=HTMLResponse)
def ui_search(q: str = Query("", min_length=0)):
    """Return command palette search results HTML."""
    q = q.strip()
    if len(q) < 2:
        return HTMLResponse(content="")
    results = get_db().search_all(q, limit=10)
    return HTMLResponse(content=palette_results(results, q))


# --------------- static files (Web UI) ---------------

WEB_DIR = Path(os.path.join(os.path.dirname(__file__), "web"))
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="static")
