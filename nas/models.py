"""SQLite schema and database operations."""

import hashlib
import json
import sqlite3
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


def _normalize_published(ts):
    """归一化时间戳为 UTC ISO8601（+00:00 结尾）。"""
    if not ts:
        return datetime.now(timezone.utc).isoformat()
    try:
        s = ts[:-1] + "+00:00" if ts.endswith("Z") else ts
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        return datetime.now(timezone.utc).isoformat()


class Item:
    """标准化条目."""

    __slots__ = (
        "id", "source", "url", "title", "summary", "author",
        "published_at", "fetched_at", "content_hash",
        "category", "importance", "tags", "status",
        "wiki_slug", "wiki_saved_at", "meta",
        "hermes_judgment", "concepts", "source_divergence",
        "wiki_candidate_slug", "archived_at",
    )

    def __init__(self, **kwargs):
        for k in self.__slots__:
            setattr(self, k, kwargs.get(k))
        if not self.id:
            self.id = self._gen_id()
        if not self.fetched_at:
            self.fetched_at = datetime.now(timezone.utc).isoformat()

    def _gen_id(self):
        raw = f"{self.source}|{self.url}|{self.published_at}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @classmethod
    def from_raw(cls, raw: dict) -> "Item":
        return cls(
            source=raw.get("source", ""),
            url=raw.get("url", ""),
            title=raw.get("title", ""),
            summary=raw.get("summary"),
            author=raw.get("author"),
            published_at=_normalize_published(raw.get("published_at")),
            content_hash=raw.get("content_hash"),
            category=raw.get("category"),
            importance=raw.get("importance"),
            tags=raw.get("tags"),
            status=raw.get("status", "new"),
            meta=raw.get("meta", {}),
            hermes_judgment=raw.get("hermes_judgment"),
            concepts=raw.get("concepts"),
            source_divergence=raw.get("source_divergence"),
            wiki_candidate_slug=raw.get("wiki_candidate_slug"),
            archived_at=raw.get("archived_at"),
        )

    def to_dict(self) -> dict:
        d = {}
        for k in self.__slots__:
            v = getattr(self, k)
            if v is not None:
                d[k] = v
        # Ensure meta is serialisable
        if "meta" in d and isinstance(d["meta"], str):
            d["meta"] = json.loads(d["meta"])
        return d

    def to_db_row(self) -> dict:
        d = self.to_dict()
        if "meta" in d and not isinstance(d["meta"], str):
            d["meta"] = json.dumps(d["meta"], ensure_ascii=False)
        if "tags" in d and not isinstance(d["tags"], str):
            d["tags"] = json.dumps(d["tags"], ensure_ascii=False)
        if "concepts" in d and isinstance(d["concepts"], list):
            d["concepts"] = json.dumps(d["concepts"], ensure_ascii=False)
        if "source_divergence" in d and isinstance(d["source_divergence"], dict):
            d["source_divergence"] = json.dumps(d["source_divergence"], ensure_ascii=False)
        if "importance" in d and d["importance"] is None:
            d["importance"] = "NULL"
        return d


SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    author TEXT,
    published_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    content_hash TEXT,
    category TEXT,
    importance INTEGER,
    tags TEXT,
    status TEXT DEFAULT 'new',
    wiki_slug TEXT,
    wiki_saved_at TEXT,
    meta TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    hermes_judgment TEXT,
    concepts TEXT,
    source_divergence TEXT,
    wiki_candidate_slug TEXT,
    archived_at TEXT
);

CREATE TABLE IF NOT EXISTS item_clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_hash TEXT NOT NULL,
    item_id TEXT NOT NULL,
    FOREIGN KEY (item_id) REFERENCES items(id)
);

CREATE INDEX IF NOT EXISTS idx_items_source ON items(source);
CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
CREATE INDEX IF NOT EXISTS idx_items_published ON items(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
CREATE INDEX IF NOT EXISTS idx_items_url ON items(url);
CREATE INDEX IF NOT EXISTS idx_clusters_hash ON item_clusters(cluster_hash);
"""


class Database:
    ALLOWED_COLUMNS = {
        "summary", "category", "importance", "tags",
        "status", "wiki_slug", "wiki_saved_at", "meta",
        "hermes_judgment", "concepts", "source_divergence",
        "wiki_candidate_slug", "archived_at",
    }

    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.executescript(SCHEMA)
        # Migration: add new columns to existing tables
        for col in ("hermes_judgment", "concepts", "source_divergence",
                     "wiki_candidate_slug", "archived_at"):
            try:
                self.conn.execute(f"ALTER TABLE items ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
        self.conn.commit()

    def close(self):
        self.conn.close()

    # -------------- CRUD --------------

    def get_item(self, item_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        return _deserialize_row(dict(row)) if row else None

    def upsert_item(self, item: Item) -> str:
        """返回 'created' 或 'updated'."""
        existing = self.conn.execute(
            "SELECT id FROM items WHERE url = ? OR id = ?",
            (item.url, item.id)
        ).fetchone()

        data = item.to_db_row()
        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        values = list(data.values())

        if existing:
            set_clause = ", ".join(f"{k}=excluded.{k}" for k in data if k != "id")
            self.conn.execute(
                f"UPDATE items SET {set_clause}, updated_at=datetime('now') WHERE id = ?",
                values + [existing["id"]],
            )
            self.conn.commit()
            return "updated"
        else:
            self.conn.execute(
                f"INSERT INTO items ({columns}) VALUES ({placeholders})",
                values,
            )
            self.conn.commit()
            return "created"

    def update_item(self, item_id: str, updates: dict):
        safe = {k: v for k, v in updates.items() if k in self.ALLOWED_COLUMNS}
        if not safe:
            return
        # Auto-set archived_at when status becomes "archived"
        if safe.get("status") == "archived":
            safe["archived_at"] = datetime.now(timezone.utc).isoformat()
        safe["updated_at"] = datetime.now(timezone.utc).isoformat()
        set_clause = ", ".join(f"{k}=?" for k in safe)
        values = list(safe.values()) + [item_id]
        self.conn.execute(
            f"UPDATE items SET {set_clause} WHERE id = ?",
            values,
        )
        self.conn.commit()

    def list_items(
        self,
        source: str | None = None,
        category: str | None = None,
        status: str | None = None,
        perspective: str | None = None,
        sort: str = "time",
        view: str | None = None,
        page: int = 1,
        per_page: int = 50,
    ) -> dict:
        conditions = []
        params = []

        if status:
            conditions.append("i.status = ?")
            params.append(status)
        if source:
            conditions.append("i.source = ?")
            params.append(source)
        if category:
            conditions.append("i.category = ?")
            params.append(category)

        # Perspective mapping
        if perspective == "random":
            view = "random"
            perspective = None
        if perspective:
            if perspective == "today":
                tz = ZoneInfo("Asia/Shanghai")
                today_start = datetime.combine(
                    datetime.now(tz).date(), time.min, tzinfo=tz
                ).astimezone(timezone.utc).isoformat()
                conditions.append("i.published_at >= ?")
                params.append(today_start)
            elif perspective == "ai-research":
                conditions.append(
                    "(i.category LIKE 'ai/%' OR i.source IN ('arxiv', 'huggingface'))"
                )
            elif perspective == "engineering":
                conditions.append(
                    "(i.category LIKE 'dev/%' OR i.source = 'github')"
                )
            elif perspective == "markets":
                conditions.append(
                    "(i.category LIKE 'market/%' OR i.category LIKE 'biz/%')"
                )
            elif perspective == "saved":
                conditions.append("i.status = 'saved'")
            elif perspective == "archived":
                conditions.append("i.status = 'archived'")

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        # view=random: low-signal random sampling
        if view == "random":
            random_where = (
                f"{where} AND i.importance <= 2" if conditions
                else "WHERE i.importance <= 2"
            )
            rows = self.conn.execute(
                f"SELECT i.* FROM items i {random_where} "
                f"ORDER BY RANDOM() LIMIT ?",
                params + [per_page],
            ).fetchall()
            items = [_deserialize_row(dict(r)) for r in rows]
            return {
                "items": items,
                "total": len(items),
                "page": 1,
                "per_page": per_page,
                "pages": 1,
            }

        # Build query with optional cluster join
        if sort == "cluster":
            order_clause = "cg.cluster_hash DESC NULLS LAST, i.published_at DESC"
            from_clause = (
                "items i LEFT JOIN ("
                "SELECT item_id, MAX(cluster_hash) as cluster_hash "
                "FROM item_clusters GROUP BY item_id"
                ") cg ON i.id = cg.item_id"
            )
        else:
            order_clause = (
                "i.importance DESC, i.published_at DESC"
                if sort == "signal"
                else "i.published_at DESC"
            )
            from_clause = "items i"

        # total count
        total = self.conn.execute(
            f"SELECT COUNT(*) FROM {from_clause} {where}", params
        ).fetchone()[0]

        # paginated results
        offset = (page - 1) * per_page
        rows = self.conn.execute(
            f"SELECT i.* FROM {from_clause} {where} ORDER BY {order_clause} LIMIT ? OFFSET ?",
            params + [per_page, offset],
        ).fetchall()

        return {
            "items": [_deserialize_row(dict(r)) for r in rows],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        }

    # -------------- stats --------------

    def get_stats(self) -> dict:
        total = self.conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        by_status = {
            r["status"]: r["count"]
            for r in self.conn.execute(
                "SELECT status, COUNT(*) as count FROM items GROUP BY status"
            ).fetchall()
        }
        # Ensure all four statuses are present
        for s in ("new", "processed", "saved", "archived"):
            by_status.setdefault(s, 0)
        by_source = {
            r["source"]: r["count"]
            for r in self.conn.execute(
                "SELECT source, COUNT(*) as count FROM items GROUP BY source ORDER BY count DESC LIMIT 20"
            ).fetchall()
        }
        # Today start in Asia/Shanghai
        tz = ZoneInfo("Asia/Shanghai")
        today_start = datetime.combine(
            datetime.now(tz).date(), time.min, tzinfo=tz
        ).astimezone(timezone.utc).isoformat()

        def _count(sql, params=None):
            return self.conn.execute(sql, params or []).fetchone()[0]

        by_perspective = {
            "today": _count(
                "SELECT COUNT(*) FROM items WHERE published_at >= ?", [today_start]
            ),
            "ai-research": _count(
                "SELECT COUNT(*) FROM items WHERE category LIKE 'ai/%' "
                "OR source IN ('arxiv', 'huggingface')"
            ),
            "engineering": _count(
                "SELECT COUNT(*) FROM items WHERE category LIKE 'dev/%' "
                "OR source = 'github'"
            ),
            "markets": _count(
                "SELECT COUNT(*) FROM items WHERE category LIKE 'market/%' "
                "OR category LIKE 'biz/%'"
            ),
            "saved": _count(
                "SELECT COUNT(*) FROM items WHERE status = 'saved'"
            ),
            "archived": _count(
                "SELECT COUNT(*) FROM items WHERE status = 'archived'"
            ),
            "random": "∞",
        }
        clusters_count = self.conn.execute(
            "SELECT COUNT(DISTINCT cluster_hash) FROM item_clusters"
        ).fetchone()[0]
        return {
            "total": total,
            "by_status": by_status,
            "by_source": by_source,
            "by_perspective": by_perspective,
            "clusters_count": clusters_count,
        }

    # -------------- clusters --------------

    def get_clusters(self, limit: int = 20) -> list:
        rows = self.conn.execute(
            """
            SELECT cluster_hash, COUNT(*) as cnt
            FROM item_clusters
            GROUP BY cluster_hash
            HAVING COUNT(*) > 1
            ORDER BY cnt DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        result = []
        for row in rows:
            members = self.conn.execute(
                """
                SELECT i.id, i.title, i.source, i.published_at
                FROM item_clusters c
                JOIN items i ON c.item_id = i.id
                WHERE c.cluster_hash = ?
                ORDER BY i.published_at DESC
                """,
                (row["cluster_hash"],),
            ).fetchall()
            result.append({
                "cluster_hash": row["cluster_hash"],
                "count": row["cnt"],
                "items": [dict(m) for m in members],
            })
        return result

    def create_cluster(self, cluster_hash: str, item_ids: list[str]):
        for iid in item_ids:
            self.conn.execute(
                "INSERT OR IGNORE INTO item_clusters (cluster_hash, item_id) VALUES (?, ?)",
                (cluster_hash, iid),
            )
        self.conn.commit()

    def get_item_clusters(self, item_id: str) -> list[dict]:
        """Return all clusters this item belongs to."""
        rows = self.conn.execute(
            """
            SELECT c.cluster_hash,
                   (SELECT COUNT(*) FROM item_clusters c3
                    WHERE c3.cluster_hash = c.cluster_hash) as member_count
            FROM item_clusters c
            WHERE c.item_id = ?
            """,
            (item_id,),
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            # Get all item_ids in this cluster
            ids = self.conn.execute(
                "SELECT item_id FROM item_clusters WHERE cluster_hash = ?",
                (d["cluster_hash"],),
            ).fetchall()
            d["item_ids"] = [r["item_id"] for r in ids]
            result.append(d)
        return result

    def get_cluster(self, cluster_hash: str) -> dict | None:
        """Return cluster metadata."""
        members = self.conn.execute(
            "SELECT item_id FROM item_clusters WHERE cluster_hash = ?",
            (cluster_hash,),
        ).fetchall()
        if not members:
            return None
        item_ids = [r["item_id"] for r in members]
        return {
            "cluster_hash": cluster_hash,
            "item_ids": item_ids,
            "member_count": len(item_ids),
        }

    def get_cluster_members(self, cluster_hash: str) -> list[dict]:
        """Return all items in a cluster."""
        rows = self.conn.execute(
            """
            SELECT i.* FROM item_clusters c
            JOIN items i ON c.item_id = i.id
            WHERE c.cluster_hash = ?
            ORDER BY i.published_at DESC
            """,
            (cluster_hash,),
        ).fetchall()
        return [_deserialize_row(dict(r)) for r in rows]

    def search_all(self, q: str, limit: int = 10) -> dict:
        """Search across items, concepts, and clusters."""
        q = (q or "").strip()
        like = f"%{q}%"

        # Items by title or summary
        rows = self.conn.execute(
            "SELECT id, title, source, url FROM items "
            "WHERE title LIKE ? OR summary LIKE ? "
            "ORDER BY published_at DESC LIMIT ?",
            (like, like, limit),
        ).fetchall()
        items = [dict(r) for r in rows]

        # Concepts: try JSON table, fall back to text LIKE
        concepts = []
        try:
            rows = self.conn.execute(
                "SELECT value AS concept, COUNT(*) as cnt "
                "FROM items, json_each(items.concepts) "
                "WHERE concept LIKE ? "
                "GROUP BY concept "
                "ORDER BY cnt DESC "
                "LIMIT ?",
                (like, limit),
            ).fetchall()
            concepts = [{"name": r["concept"], "count": r["cnt"]} for r in rows]
        except sqlite3.OperationalError:
            # Fallback for older SQLite without json_each
            rows = self.conn.execute(
                "SELECT concepts FROM items WHERE concepts LIKE ? LIMIT ?",
                (like, limit),
            ).fetchall()
            seen = {}
            for row in rows:
                try:
                    cs = json.loads(row["concepts"]) if row["concepts"] else []
                    for c in (cs or []):
                        if q.lower() in c.lower():
                            seen[c] = seen.get(c, 0) + 1
                except Exception:
                    pass
            concepts = [{"name": k, "count": v} for k, v in seen.items()]

        # Clusters with member titles/summaries matching
        rows = self.conn.execute(
            "SELECT c.cluster_hash, COUNT(*) as member_count, MIN(i.title) as preview "
            "FROM item_clusters c JOIN items i ON c.item_id = i.id "
            "WHERE i.title LIKE ? OR i.summary LIKE ? "
            "GROUP BY c.cluster_hash "
            "HAVING COUNT(*) > 1 "
            "ORDER BY member_count DESC "
            "LIMIT ?",
            (like, like, limit),
        ).fetchall()
        clusters = [
            {"cluster_hash": r["cluster_hash"], "member_count": r["member_count"], "preview": r["preview"]}
            for r in rows
        ]

        return {"items": items, "concepts": concepts, "clusters": clusters}


    def find_similar_title(self, title: str, threshold: float = 0.7) -> list[dict]:
        """Simple prefix-based fuzzy match. For advanced dedup, Hermes handles it."""
        words = title.lower().split()[:5]
        if not words:
            return []
        patterns = " OR ".join(["title LIKE ?" for _ in words])
        params = [f"%{w}%" for w in words]
        rows = self.conn.execute(
            f"SELECT id, title FROM items WHERE {patterns} LIMIT 20",
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def _deserialize_row(d: dict) -> dict:
    """Convert JSON strings back to Python objects."""
    for field in ("tags", "meta", "concepts", "source_divergence"):
        if field in d and isinstance(d[field], str):
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return d
