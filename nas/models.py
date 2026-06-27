"""SQLite schema and database operations."""

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


class Item:
    """标准化条目."""

    __slots__ = (
        "id", "source", "url", "title", "summary", "author",
        "published_at", "fetched_at", "content_hash",
        "category", "importance", "tags", "status",
        "wiki_slug", "wiki_saved_at", "meta",
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
            published_at=raw.get("published_at", datetime.now(timezone.utc).isoformat()),
            content_hash=raw.get("content_hash"),
            category=raw.get("category"),
            importance=raw.get("importance"),
            tags=raw.get("tags"),
            status=raw.get("status", "new"),
            meta=raw.get("meta", {}),
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
    updated_at TEXT DEFAULT (datetime('now'))
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
    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    # -------------- CRUD --------------

    def get_item(self, item_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        return dict(row) if row else None

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
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        set_clause = ", ".join(f"{k}=?" for k in updates)
        values = list(updates.values()) + [item_id]
        self.conn.execute(
            f"UPDATE items SET {set_clause} WHERE id = ?",
            values,
        )
        self.conn.commit()

    def list_items(
        self,
        status: str | None = None,
        source: str | None = None,
        category: str | None = None,
        page: int = 1,
        per_page: int = 50,
    ) -> dict:
        conditions = []
        params = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if source:
            conditions.append("source = ?")
            params.append(source)
        if category:
            conditions.append("category = ?")
            params.append(category)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        # total count
        total = self.conn.execute(
            f"SELECT COUNT(*) FROM items {where}", params
        ).fetchone()[0]

        # paginated results
        offset = (page - 1) * per_page
        rows = self.conn.execute(
            f"SELECT * FROM items {where} ORDER BY published_at DESC LIMIT ? OFFSET ?",
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
        by_source = {
            r["source"]: r["count"]
            for r in self.conn.execute(
                "SELECT source, COUNT(*) as count FROM items GROUP BY source ORDER BY count DESC LIMIT 20"
            ).fetchall()
        }
        by_category = {
            r["category"]: r["count"]
            for r in self.conn.execute(
                "SELECT category, COUNT(*) as count FROM items WHERE category IS NOT NULL GROUP BY category ORDER BY count DESC"
            ).fetchall()
        }
        return {
            "total": total,
            "by_status": by_status,
            "by_source": by_source,
            "by_category": by_category,
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
    for field in ("tags", "meta"):
        if field in d and isinstance(d[field], str):
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return d
