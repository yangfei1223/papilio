# P0 地基修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复审查发现的 5 个实现问题（时间戳排序、SQL 拼接、htmx CDN、死代码、GitHub trending 语义），为 P1–P5 铺路。

**Architecture:** 纯修复，不改架构/数据流/依赖。时间戳归一化集中在 collector `base._normalize` + NAS `Item.from_raw` 兜底；SQL 防御用列名白名单；htmx 本地化；GitHub 用「近 7 天高星」近似 trending。

**Tech Stack:** Python 3.12/3.13 · FastAPI · SQLite · HTMX 2.0.4 · requests · gh CLI

---

## 验证约定（本计划无测试框架）

- **NAS 验证实例**：实现/验证阶段用带 `--reload` 的 uvicorn，改 NAS 代码自动重载：
  ```bash
  PAPILIO_DATA_DIR=/Users/yangfei/Code/papilio/nas/data \
  uvicorn app:app --app-dir /Users/yangfei/Code/papilio/nas --port 8000 --reload
  ```
  （若已有不带 reload 的 NAS 进程在 8000 端口，先停掉再用上面命令。）
- **Collector 验证**：`PAPILIO_NAS_URL=http://localhost:8000 python3 scripts/run_collector.py <name>`
- 所有 `curl` 针对 `localhost:8000`。

## File Structure

| 文件 | 责任 | 本计划改动 |
|------|------|-----------|
| `nas/web/htmx.min.js` | htmx 库（本地） | **新增**：下载 2.0.4 |
| `nas/web/index.html` | 静态前端壳 | 改 htmx 引用为本地 |
| `nas/models.py` | SQLite schema + Item + Database | 删 `import uuid`；`Item.from_raw` 归一化 `published_at`；`Database` 加白名单 |
| `nas/app.py` | FastAPI 路由 | `on_event` → `lifespan` |
| `collectors/base.py` | BaseCollector | 删 `source_name`；`_normalize` 归一化 `published_at` + source fallback |
| `collectors/github.py` | GitHub collector | 近 7 天高星 + `published_at` 用 `created_at` |

> `hackernews.py` / `rss.py` / `arxiv.py` **无需改**：它们的 `published_at` 经 `base._normalize` 统一归一化。

---

### Task 1: htmx 本地化

**Files:**
- Create: `nas/web/htmx.min.js`
- Modify: `nas/web/index.html:7`

- [ ] **Step 1: 下载 htmx.min.js 到 web 目录**

Run:
```bash
curl -L https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js -o /Users/yangfei/Code/papilio/nas/web/htmx.min.js
```
Expected: 文件下载成功，`ls -la nas/web/htmx.min.js` 显示 ~14KB。

- [ ] **Step 2: 改 index.html 引用为本地**

把 `nas/web/index.html` 第 7 行：
```html
<script src="https://unpkg.com/htmx.org@2.0.4"></script>
```
改为：
```html
<script src="/htmx.min.js"></script>
```

- [ ] **Step 3: 验证本地可加载**

Run: `curl -s -o /dev/null -w "%{http_code} %{size_download}\n" localhost:8000/htmx.min.js`
Expected: `200 14xxx`（HTTP 200，非 0 字节）。

- [ ] **Step 4: Commit**

```bash
git -C /Users/yangfei/Code/papilio add nas/web/htmx.min.js nas/web/index.html
git -C /Users/yangfei/Code/papilio commit -m "🦋 P0: 本地化 htmx，去掉 CDN 依赖"
```

---

### Task 2: 清死代码（`import uuid` + `source_name`）

**Files:**
- Modify: `nas/models.py:6`
- Modify: `collectors/base.py:66-68` 和 `_normalize` 的 source 行

- [ ] **Step 1: models.py 删未使用的 uuid 导入**

删除 `nas/models.py` 第 6 行 `import uuid`。

- [ ] **Step 2: base.py 改 _normalize 的 source fallback**

`collectors/base.py` 的 `_normalize` 中（各 collector 都显式传 `source`，`source_name` 是无用 fallback）。把：
```python
            "source": raw.get("source", self.source_name),
```
改为：
```python
            "source": raw.get("source", ""),
```

- [ ] **Step 3: base.py 删 source_name property**

删除 `collectors/base.py` 中的整个 property（原第 66–68 行）：
```python
    @property
    def source_name(self) -> str:
        return self.__class__.__name__.lower().replace("collector", "")
```

- [ ] **Step 4: 验证无 import/属性错误**

Run:
```bash
cd /Users/yangfei/Code/papilio/nas && python3 -c "import models; print('models ok')"
cd /Users/yangfei/Code/papilio/collectors && python3 -c "from base import BaseCollector; print('base ok')"
```
Expected: 两行 `... ok`，无 `AttributeError`/`ImportError`。

- [ ] **Step 5: Commit**

```bash
git -C /Users/yangfei/Code/papilio add nas/models.py collectors/base.py
git -C /Users/yangfei/Code/papilio commit -m "🦋 P0: 清理死代码（uuid 导入、source_name）"
```

---

### Task 3: `@app.on_event` → lifespan

**Files:**
- Modify: `nas/app.py:9-56`（imports + startup/shutdown）

- [ ] **Step 1: 加 contextlib 导入**

`nas/app.py` 顶部 import 区，在 `from pathlib import Path` 后加：
```python
from contextlib import asynccontextmanager
```

- [ ] **Step 2: 用 lifespan 替换 on_event**

把 `app = FastAPI(...)` 及其后的 `startup`/`shutdown` 两个 `@app.on_event` 函数，整体替换为：
```python
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
```
注意：`get_db` / `db` / `DB_PATH` 的定义（原 29–41 行）保留在 `lifespan` 之上。`CORSMiddleware` 的 `app.add_middleware(...)` 保留在 `app` 定义之后。

- [ ] **Step 3: 验证 NAS 启停正常**

重启 NAS（用「验证约定」里的 `--reload` 命令）。
Run: `curl -s localhost:8000/api/health`
Expected: `{"status":"ok","db":"..."}`，无启动报错（日志里不应出现 on_event deprecation warning）。

- [ ] **Step 4: Commit**

```bash
git -C /Users/yangfei/Code/papilio add nas/app.py
git -C /Users/yangfei/Code/papilio commit -m "🦋 P0: on_event 迁移到 lifespan"
```

---

### Task 4: `published_at` 归一化（修复排序）

**Files:**
- Modify: `collectors/base.py`（加归一化函数 + `_normalize` 调用）
- Modify: `nas/models.py`（加归一化函数 + `Item.from_raw` 兜底）

- [ ] **Step 1: base.py 加归一化函数并用于 _normalize**

在 `collectors/base.py` 顶部 imports 之后、`BaseCollector` 之前，加模块级函数：
```python
def _normalize_published(ts: str | None) -> str:
    """归一化时间戳为 UTC ISO8601（+00:00 结尾）。无法解析则返回当前 UTC 时间。"""
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
```
然后把 `_normalize` 里的：
```python
            "published_at": raw.get(
                "published_at", datetime.now(timezone.utc).isoformat()
            ),
```
改为：
```python
            "published_at": _normalize_published(raw.get("published_at")),
```

- [ ] **Step 2: models.py 加同名兜底函数**

在 `nas/models.py` 的 `Item` 类之前加同一个 `_normalize_published` 函数（NAS 与 collector 是分离的部署单元，不共享 import，各自保留一份）：
```python
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
```

- [ ] **Step 3: models.py Item.from_raw 调用归一化**

把 `Item.from_raw` 里的：
```python
            published_at=raw.get("published_at", datetime.now(timezone.utc).isoformat()),
```
改为：
```python
            published_at=_normalize_published(raw.get("published_at")),
```

- [ ] **Step 4: 验证 Z 结尾被归一化**

NAS 用 `--reload` 重启后，直接 POST 一条 `Z` 结尾的测试数据：
Run:
```bash
curl -s -X POST localhost:8000/api/items -H 'Content-Type: application/json' \
  -d '[{"source":"test","url":"https://t/z","title":"Z test","published_at":"2026-06-01T12:00:00Z"}]'
curl -s 'localhost:8000/api/items?source=test&per_page=1' | python3 -c "import sys,json;print(json.load(sys.stdin)['items'][0]['published_at'])"
```
Expected: 第二条命令输出以 `+00:00` 结尾（如 `2026-06-01T12:00:00+00:00`），不再是 `Z`。

- [ ] **Step 5: 清理测试数据并 Commit**

Run:
```bash
curl -s -X POST localhost:8000/api/items -H 'Content-Type: application/json' \
  -d '[{"source":"test","url":"https://t/z","title":"Z test","published_at":"2026-06-01T12:00:00Z"}]' >/dev/null
```
（test 数据不入 git；DB 在 nas/data，已被 .gitignore。无需清理 DB。）
```bash
git -C /Users/yangfei/Code/papilio add collectors/base.py nas/models.py
git -C /Users/yangfei/Code/papilio commit -m "🦋 P0: published_at 归一化为 UTC，修复排序"
```

---

### Task 5: `update_item` SQL 防御

**Files:**
- Modify: `nas/models.py`（`Database` 类加白名单 + `update_item` 过滤）

- [ ] **Step 1: Database 加 ALLOWED_COLUMNS 并过滤**

在 `nas/models.py` 的 `class Database:` 内、`__init__` 之前加类属性，并重写 `update_item`：
```python
    ALLOWED_COLUMNS = {
        "summary", "category", "importance", "tags",
        "status", "wiki_slug", "wiki_saved_at", "meta",
    }

    def update_item(self, item_id: str, updates: dict):
        safe = {k: v for k, v in updates.items() if k in self.ALLOWED_COLUMNS}
        if not safe:
            return
        safe["updated_at"] = datetime.now(timezone.utc).isoformat()
        set_clause = ", ".join(f"{k}=?" for k in safe)
        values = list(safe.values()) + [item_id]
        self.conn.execute(
            f"UPDATE items SET {set_clause} WHERE id = ?",
            values,
        )
        self.conn.commit()
```
（`app.py` route 层的白名单过滤保留，作纵深防御，不改。）

- [ ] **Step 2: 验证非法字段被忽略、不抛 SQL 错**

先用一个已知 item id（从 `curl localhost:8000/api/items?per_page=1` 取一个 `id`，下面用 `<ID>` 占位，执行时替换）。NAS `--reload` 重启后：
Run:
```bash
ID=$(curl -s 'localhost:8000/api/items?per_page=1' | python3 -c "import sys,json;print(json.load(sys.stdin)['items'][0]['id'])")
curl -s -X PATCH localhost:8000/api/items/$ID -H 'Content-Type: application/json' \
  -d '{"summary":"ok","evil_col":"DROP TABLE items"}'
curl -s "localhost:8000/api/items/$ID" | python3 -c "import sys,json;d=json.load(sys.stdin);print('summary=',d.get('summary'))"
```
Expected: PATCH 不报 500；`summary` 更新为 `ok`；`evil_col` 被忽略（schema 未变，表完好）。

- [ ] **Step 3: Commit**

```bash
git -C /Users/yangfei/Code/papilio add nas/models.py
git -C /Users/yangfei/Code/papilio commit -m "🦋 P0: update_item 加列名白名单防御"
```

---

### Task 6: GitHub collector 近 7 天高星（近似 trending）

**Files:**
- Modify: `collectors/github.py`（整体重写 fetch + _get_trending）

- [ ] **Step 1: 重写 github.py**

把 `collectors/github.py` 整体替换为：
```python
"""GitHub collector — 近 N 天内新建、按星排序的仓库（近似 trending）。"""

import json
import subprocess
from datetime import datetime, timedelta, timezone

import requests

from base import BaseCollector, content_hash

WINDOW_DAYS = 7


class GitHubCollector(BaseCollector):
    def fetch(self) -> list[dict]:
        since = (datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
        items = []
        for repo in self._get_trending(since):
            owner = repo.get("owner")
            owner_login = owner.get("login", "") if isinstance(owner, dict) else (owner or "")
            created = repo.get("created_at") or datetime.now(timezone.utc).isoformat()
            items.append({
                "source": "github",
                "url": repo.get("html_url", ""),
                "title": repo.get("full_name", ""),
                "summary": repo.get("description", ""),
                "author": owner_login,
                "published_at": created,
                "content_hash": content_hash(repo.get("full_name", "")),
                "meta": {
                    "stars": repo.get("stargazers_count", 0),
                    "language": repo.get("language", ""),
                    "topics": repo.get("topics", []),
                },
            })
        return items

    def _get_trending(self, since: str) -> list[dict]:
        """近 N 天新建、按星排序。先用 gh CLI，失败回退 search API。"""
        try:
            result = subprocess.run(
                [
                    "gh", "search", "repos",
                    f"created:>{since}",
                    "--sort=stars",
                    "--limit", "25",
                    "--json", "full_name,description,html_url,stargazers_count,language,topics,owner,created_at",
                ],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception as e:
            print(f"[GitHub] gh CLI failed: {e}")

        try:
            resp = requests.get(
                "https://api.github.com/search/repositories",
                params={"q": f"created:>{since}", "sort": "stars", "per_page": 25},
                headers={"Accept": "application/vnd.github+json"},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json().get("items", [])
        except Exception as e:
            print(f"[GitHub] API fallback failed: {e}")
            return []


if __name__ == "__main__":
    GitHubCollector().run()
```

- [ ] **Step 2: 验证入库条目时间分散在近 7 天**

Run:
```bash
PAPILIO_NAS_URL=http://localhost:8000 python3 /Users/yangfei/Code/papilio/scripts/run_collector.py github 2>&1 | tail -2
curl -s 'localhost:8000/api/items?source=github&per_page=50' | \
  python3 -c "import sys,json;ds=sorted({i['published_at'][:10] for i in json.load(sys.stdin)['items']});print('distinct dates:',len(ds),ds[:3],'...',ds[-3:])"
```
Expected: `Done: {'created': N, ...}`（N>0）；distinct dates 显示多个不同日期（分布在近 7 天），而非全是今天。

- [ ] **Step 3: Commit**

```bash
git -C /Users/yangfei/Code/papilio add collectors/github.py
git -C /Users/yangfei/Code/papilio commit -m "🦋 P0: GitHub collector 改为近 7 天高星（近似 trending）"
```

---

### Task 7: 端到端验证 + 收尾

**Files:** 无（纯验证）

- [ ] **Step 1: 确认 NAS 用最终代码运行（停 --reload，正常起或保留均可）**

Run: `curl -s localhost:8000/api/health` → Expected `{"status":"ok",...}`

- [ ] **Step 2: 汇总验证 5 项修复**

```bash
# (a) htmx 本地可加载
curl -s -o /dev/null -w "htmx: %{http_code}\n" localhost:8000/htmx.min.js
# (b) published_at 均为 +00:00
curl -s 'localhost:8000/api/items?per_page=50' | python3 -c "import sys,json;ps=[i['published_at'] for i in json.load(sys.stdin)['items']];print('all +00:00:', all(p.endswith('+00:00') for p in ps))"
# (c) GitHub 时间分散（见 Task 6 Step 2 命令）
# (d) lifespan：启动日志无 on_event deprecation warning
# (e) 死代码：grep 确认
grep -rn "import uuid" nas/models.py; grep -n "source_name" collectors/base.py
```
Expected: (a) `htmx: 200`；(b) `all +00:00: True`；(d) 无 warning；(e) 两个 grep 均无输出。

- [ ] **Step 3: P0 完成**

P0 全部修复落地并验证。可 push，然后进入 P1（Processor AI 处理）的 brainstorm。

---

## Self-Review（计划作者自检）

- **Spec coverage**：spec 5 项 → Task 1(htmx) / Task 2+3(死代码+lifespan) / Task 4(published_at) / Task 5(SQL) / Task 6(GitHub)，全覆盖；Task 7 端到端验证。✓
- **Placeholder scan**：无 TBD/TODO；每步含完整代码或确切命令 + 预期。✓
- **Type/naming consistency**：`_normalize_published` 在 base.py 与 models.py 同名同行为；`ALLOWED_COLUMNS` 与 route 白名单一致；`WINDOW_DAYS`、`_get_trending(since)` 前后一致。✓
