# 🦋 Papilio — 破茧成蝶计划

> 个人信息聚合站，部署于 NAS，由 Hermes Agent 驱动。打破信息茧房，主动定义你看到的世界。

---

## 一、项目概述

### 1.1 目标

搭建一个运行在 NAS 上的个人信息聚合站，从多源（RSS、Hacker News、arXiv、GitHub 等）定时拉取信息，经 Hermes AI 处理（摘要、分类、去重、关联），通过 Web UI 供浏览。支持手动沉淀到 LLM Wiki。

### 1.2 核心原则

| 原则 | 说明 |
|------|------|
| **你定义规则** | 不是你点过什么，是你配置了什么源 |
| **多源交叉** | 同一事件多源报道显式展示，不依赖单一叙事 |
| **手动沉淀** | 不自动灌 wiki，你来决定什么值得保存 |
| **零推荐算法** | 没有"猜你喜欢"，有随机扰动打破回音壁 |
| **局域网自托管** | 数据在自己 NAS 上，不外传 |

### 1.3 代码位置

```
~/Code/papilio/
```

---

## 二、架构总览

```
  Mac mini (大脑，7×24)              NAS (仓库，7×24)
┌──────────────────────────┐     ┌──────────────────────┐
│                           │     │                      │
│  Hermes cronjob           │     │  Docker              │
│   ├── collector/* (定时)   │POST │   ├── FastAPI        │
│   ├── processor (异步)    │───→ │   ├── SQLite         │
│   └── wiki-bridge (手动)  │←─── │   └── 静态 Web UI     │
│                           │ GET │                      │
│  Agent-Reach CLI          │     │  http://nas:8899     │
│  MinerU (论文)            │     │       ↑              │
│                           │     │  你的浏览器           │
└──────────────────────────┘     └──────────────────────┘
```

### 2.1 分工

| 层 | 在哪 | 做什么 |
|------|------|------|
| **Collector** | Mac mini | 定时拉取各源数据，标准化后 POST 到 NAS |
| **Processor** | Mac mini | Hermes 异步：摘要 → 分类 → 去重 → 评分 |
| **Storage** | NAS | SQLite，FastAPI 读写 |
| **Web UI** | NAS | 静态 HTML + HTMX，通过 FastAPI 提供 |
| **Wiki Bridge** | Mac mini | 用户手动触发，沉淀到 iCloud wiki |

### 2.2 通信

Mac mini 与 NAS 之间全部通过 HTTP API 通信。Mac mini 不直接操作 NAS 文件系统。不挂载 NFS。

---

## 三、NAS 端设计

### 3.1 部署

```bash
# NAS 上
mkdir -p ~/docker/papilio/data ~/docker/papilio/web
# 上传 docker-compose.yml + 代码，然后：
docker compose up -d
```

### 3.2 docker-compose.yml

```yaml
services:
  papilio:
    image: python:3.12-slim
    working_dir: /app
    volumes:
      - ./data:/data          # SQLite 持久化
      - ./web:/app/web        # 前端静态文件
      - ./.env:/app/.env
    ports:
      - "8899:8000"
    command: uvicorn app:app --host 0.0.0.0 --port 8000
    restart: always
```

### 3.3 FastAPI 路由

```
GET  /                    # 前端页面
GET  /api/items           # 列表，支持 ?status=&source=&category=&page=
GET  /api/items/:id       # 单条详情
POST /api/items           # collector 批量入库
PATCH /api/items/:id      # processor 更新字段
POST /api/items/:id/save  # 触发 wiki 沉淀
GET  /api/stats           # 统计：各源数量、分类分布
GET  /api/clusters        # 多源交叉聚合
```

### 3.4 SQLite Schema

```sql
-- 主条目表
CREATE TABLE items (
    id TEXT PRIMARY KEY,         -- hash(source+url)
    source TEXT NOT NULL,        -- "hackernews" | "rss/stripe-blog"
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,                -- AI 生成
    author TEXT,
    published_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    content_hash TEXT,           -- sha256，去重用

    -- Hermes 处理后填充
    category TEXT,               -- "ai" | "tech" | "finance" | ...
    importance INTEGER,          -- 1-5
    tags TEXT,                   -- JSON array
    status TEXT DEFAULT 'new',   -- new | processed | saved

    -- wiki 关联
    wiki_slug TEXT,
    wiki_saved_at TEXT,

    meta TEXT,                   -- 源特有字段，JSON
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- 去重聚合表
CREATE TABLE item_clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_hash TEXT NOT NULL,   -- 内容 hash
    item_id TEXT NOT NULL,
    FOREIGN KEY (item_id) REFERENCES items(id)
);

-- 索引
CREATE INDEX idx_items_source ON items(source);
CREATE INDEX idx_items_status ON items(status);
CREATE INDEX idx_items_published ON items(published_at DESC);
CREATE INDEX idx_items_category ON items(category);
```

### 3.5 Web UI

单文件 `web/index.html`。纯 HTML + HTMX（~15KB CDN），不引入构建工具：

- 顶部：源切换 tabs（全部 / HN / RSS / arXiv / GitHub）
- 主区域：时间线，每条显示标题、摘要、来源 badge、时间
- 侧边栏：分类筛选、重要性筛选、wiki 关联推荐
- 每条右侧：[→ Wiki] 按钮
- 底部：无限滚动（HTMX 触发）

---

## 四、Mac mini 端设计

### 4.1 Collector

每个源一个独立 Python 脚本，`~/Code/papilio/collectors/`：

```
collectors/
├── base.py           # BaseCollector 抽象类
├── rss.py            # RSS/Atom，feedparser
├── hackernews.py     # HN API：https://hacker-news.firebaseio.com/v0/
├── arxiv.py          # arXiv API：特定分类的新论文
├── github.py         # GitHub Trending，gh api
```

每个 collector 的职责：

```python
class BaseCollector:
    def fetch(self) -> list[RawItem]: ...
    # 唯一需要实现的方法
    # → 调 API/CLI 拉取原始数据
    # → 调用 self._normalize(raw) 标准化
    # → 调用 self._dedup(items) 本次去重
    # → 调用 self._post(items) POST 到 NAS
```

collector 脚本的最后一行把结果 POST 到 `http://nas:8899/api/items`。

### 4.2 Processor

Hermes cronjob，每 30 分钟触发：

```
GET /api/items?status=new
    ↓
Hermes AI 逐条处理：
    1. 生成中文摘要（200字）
    2. 分类（从预定义 taxonomy 中选）
    3. 重要性评分（1-5）
    4. 内容哈希去重（检查是否与已有条目聚类）
    ↓
PATCH /api/items/:id
```

### 4.3 Cronjob 配置

| 任务 | 频率 | 说明 |
|------|------|------|
| collect-rss | 每 2 小时 | 所有 RSS 源 |
| collect-hn | 每 2 小时 | HN top 50 |
| collect-arxiv | 每天 8:00, 20:00 | cs.AI + cs.CL |
| collect-github | 每天 10:00 | GitHub Trending |
| collect-huggingface | 每天 10:00 | HF trending models |
| process-items | 每 30 分钟 | AI 处理新条目 |
| clean-old | 每天 3:00 | 清理 90 天前未保存的低分条目 |

前 4 个用 `no_agent=true` + `script=` 跑 Python 脚本。process-items 用 LLM 驱动。

### 4.4 Wiki Bridge

Web UI 上点 [→ Wiki] → 触发 POST `/api/items/:id/save` → Hermes 接收 → 执行：

```
1. Agent-Reach 抓原文全文
2. 根据来源类型选择处理方式：
   - arXiv → MinerU 解析 PDF → raw/papers/
   - Web → raw/articles/
3. 创建 wiki entity page（entities/{slug}.md）
4. 关联 2+ 已有 concept 页面
5. 更新 wiki index.md + log.md
6. 回调 NAS API：PATCH item.wiki_status='saved'
```

---

## 五、数据流全景

```
┌────────┐     ┌──────────┐     ┌──────────┐     ┌────────┐
│ 外部源  │ ──→ │ Collector│ ──→ │   NAS    │ ──→ │  Web UI│
│ HN·RSS │     │ (Mac mini)│     │ API+SQL  │     │        │
└────────┘     └──────────┘     └────┬─────┘     └───┬────┘
                                     │               │
                               ┌─────▼─────┐   ┌────▼─────┐
                               │ Processor │←──│ 手动点    │
                               │ (Hermes)  │   │ [→ Wiki] │
                               └─────┬─────┘   └────┬─────┘
                                     │              │
                               AI 摘要/分类     Hermes wiki
                               去重/评分         沉淀流程
```

---

## 六、MVP 实施计划

### Phase 1 — 基础设施（先做）

| # | 任务 | 产出 |
|---|------|------|
| 1.1 | 项目结构初始化 | `~/Code/papilio/` 目录树 |
| 1.2 | NAS 端 FastAPI + SQLite | `app.py` + schema |
| 1.3 | Docker 打包 | `docker-compose.yml` + `Dockerfile` |
| 1.4 | 测试 NAS 端可访问 | `curl http://nas:8899/api/items` |

### Phase 2 — Collector

| # | 任务 | 产出 |
|---|------|------|
| 2.1 | BaseCollector 抽象类 | `collectors/base.py` |
| 2.2 | Hacker News collector | 拉 top 50，POST 入库 |
| 2.3 | RSS collector | 支持多源配置 |
| 2.4 | arXiv collector | 拉 cs.AI + cs.CL |
| 2.5 | Hermes cronjob 注册 | 4 个定时任务 |

### Phase 3 — Processor

| # | 任务 | 产出 |
|---|------|------|
| 3.1 | Hermes processor cronjob | 摘要 + 分类 + 评分 |
| 3.2 | 内容去重逻辑 | content_hash + 聚类 |

### Phase 4 — Web UI

| # | 任务 | 产出 |
|---|------|------|
| 4.1 | 基础时间线页面 | HTML + HTMX |
| 4.2 | 筛选功能 | 按源/分类/状态 |
| 4.3 | [→ Wiki] 按钮 + API | 触发沉淀流程 |

### Phase 5 — Wiki Bridge

| # | 任务 | 产出 |
|---|------|------|
| 5.1 | 手动沉淀接口 | NAS API → Hermes → wiki |
| 5.2 | arXiv 自动沉淀 | 论文自动走 paper-ingest |

---

## 七、不做的事

- ❌ 用户系统 / 登录（局域网内自用，不需要）
- ❌ 推荐算法（跟你现有的兴趣点无关，靠你配置规则）
- ❌ 自动化灌 wiki（手动沉淀是核心设计）
- ❌ 移动端适配（先做桌面版）
- ❌ 全文搜索（SQLite 够用，后续加 FTS5）
- ❌ CI/CD（直接 git push + 手动 compose up）

---

## 八、文件结构

```
~/Code/papilio/
├── README.md
├── PLAN.md                     # 本文档
│
├── nas/                        # NAS 部署文件
│   ├── docker-compose.yml
│   ├── Dockerfile
│   ├── app.py                  # FastAPI
│   ├── models.py               # SQLite schema
│   ├── web/
│   │   └── index.html          # 前端
│   └── .env.example
│
├── collectors/                 # Mac mini 上运行
│   ├── base.py
│   ├── hackernews.py
│   ├── rss.py
│   ├── arxiv.py
│   ├── github.py
│   └── config.yaml             # 源配置（RSS 列表等）
│
└── scripts/                    # cronjob 脚本
    ├── run_collector.py        # 调度入口
    └── process_items.py        # Hermes processor 入口
```
