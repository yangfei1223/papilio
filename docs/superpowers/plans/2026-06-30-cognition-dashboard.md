# Papilio Cognition Dashboard 实现方案

> Spec: [`docs/Papilio Web UI 设计规范（V1.0）.md`](../Papilio%20Web%20UI%20设计规范（V1.0）.md)
> Demo: [`docs/papilio_index.html`](../papilio_index.html)
> Date: 2026-06-30
> Status: 待执行

## 0. 目标

把 Papilio Web UI 从当前的 paper-style reading inbox **重构**为暗色三栏 **Personal Cognition Dashboard**（Bloomberg Terminal × Obsidian × Arc × Linear 气质）。

替换 `/`，旧 UI 不保留（git 历史可查）。范围：全做（视觉壳子 + 后端缺口 + processor 增强 + 命令面板 + 全部快捷键）。

## 1. 决策（已确认）

| # | 决策 | 选择 |
|---|---|---|
| 1 | 实现范围 | Phase 1+2+3+4 全做 |
| 2 | 路由 | 替换 `/`，旧 UI 删除 |
| 3 | Cognition 数据 | Phase 3 增强 processor，不留 placeholder |
| 4 | HF 源 | 保留（spec 没列但 collector 已就绪，作为第 5 个 source） |
| 5 | Brand mark | 沿用 demo 的 `◈`（暂不重做自定义 SVG 蝴蝶） |
| 6 | 渐变 | demo 里的 subtle radial/linear accent 保留（spec 禁的是"大面积"渐变） |

## 2. 执行阶段

### Phase 0 — 清场（5 分钟）

- `git checkout 8352215 -- nas/templates.py nas/web/index.html` 撤销 designer 三轮改动，回到你自己 `feat: redesign web ui as reading inbox` 的 baseline
- 不写 revert commit，直接让后续新代码覆盖
- NAS 仍跑在 :8000，无需重启

### Phase 1 — 视觉壳子（核心重写）

#### 1.1 `nas/web/index.html` 完全重写

按 demo 1:1 落地，加 HTMX 接线：

- `<head>`：dark theme CSS variables（按 spec §三 颜色）+ Google Fonts (Inter) + 内联 htmx 已存在
- `<body class="app">`：72px topbar + 3 列 grid (260 / 1fr / 390)
- **Topbar**：brand mark + search box (placeholder, ⌘K 触发) + 3 metrics (NEW/CLUSTERS/SAVED) HTMX 从 `/ui/stats` 拉
- **Sidebar (Perspective)**：3 个 section (Perspective / Sources / Status)，每项 HTMX `hx-get="/ui/items?..."` `hx-target="#timeline-content"`
- **Timeline**：`<h1>` "Today's Cognition Feed" + view tabs (Signal/Time/Cluster/Random) + `<div id="timeline-content">` 容器（HTMX swap 目标）
- **Cognition panel**：`<aside id="cognition-panel">` 空容器，初始加载首条 item 后 HTMX 填充
- **Footer hint**：键盘快捷键提示条（demo 已有）
- **Vanilla JS**：keyboard nav (J/K/O/C/W/R/Slash/ESC)、card selection state、command palette 模态触发
- **响应式**：1180px 断点隐藏 cognition panel（demo 已有）

#### 1.2 `nas/templates.py` 完全重写

删除旧的 `feed_page` / `item_row` / `stats_widget` / `item_side` / `_priority_label` / `_status_label`。新增：

```python
# 源元数据（保留并扩展）
SOURCE_META = {
    "hackernews": ("HN", "Hacker News", "amber"),
    "arxiv":      ("arX", "arXiv", "purple"),
    "github":     ("GH", "GitHub", "green"),
    "huggingface":("HF", "HuggingFace", "blue"),
    "rss":        ("RSS", "RSS", "orange"),
}

# 状态元数据（4 态）
STATUS_META = {
    "new":       ("NEW",       "gray"),
    "processed": ("PROCESSED", "blue"),
    "saved":     ("SAVED",     "green"),
    "archived":  ("ARCHIVED",  "dark-gray"),
}

# 视图 helpers
def _esc(text) -> str  # 保留
def _icon(name: str) -> str  # SVG icon 库（arrow-right, check, cluster, dot 等）
def _importance_dots(score: int) -> str  # ●●●●○ 形式
def _relative_time(published_at: str) -> str  # "4h ago" / "yesterday"
def _cluster_badge(item, clusters_map) -> str  # "cluster ×3" 或空

# 片段函数
def timeline_page(items, total, sort, perspective, selected_id, clusters_by_item) -> str
    # 渲染 #timeline-content 的 innerHTML
    # 含 timeline-head (h1 + view-tabs) + feed (cards)

def item_card(item, selected: bool, clusters_count: int) -> str
    # 单卡片，所有 spec §六 字段
    # htmx: hx-get="/ui/cognition/{id}" hx-target="#cognition-panel" hx-swap="outerHTML"
    # 触发: hx-trigger="click"

def cognition_panel(item, related_items, cluster_info) -> str
    # 右栏 5 个 panel:
    # 1. Why this matters (hermes_judgment)
    # 2. Related Concepts (concepts[])
    # 3. Source Divergence (source_divergence, 仅 cluster 项)
    # 4. Cluster Map (related_items in same cluster)
    # 5. Wiki Candidate (wiki_candidate_slug + concepts)

def sidebar_perspectives(stats) -> str
    # Perspective section + Sources section + Status section
    # 含 active 状态、count badges

def topbar_metrics(stats) -> str
    # NEW / CLUSTERS / SAVED 三个数字

def cluster_view(cluster, member_items) -> str
    # Cluster detail：title + Hermes Summary + Sources + Different Opinions + Related Wiki
    # 替换 timeline-content，单独模板
```

#### 1.3 临时数据映射（Phase 3 前的过渡）

Phase 1 完成时，cognition 字段（`hermes_judgment`, `concepts`, `source_divergence`, `wiki_candidate_slug`）DB 里还没有。模板按以下规则优雅降级：

- Why this matters: 字段为空 → 显示 importance + 一句话 summary；右下角小字 "Hermes 判断待 processor 升级"
- Related Concepts: 优先用 `concepts[]`，空则 fallback 到 `tags`，再空则不渲染该 panel
- Source Divergence: 仅当 item 在 cluster 中且 cluster 有 ≥2 源时渲染，否则隐藏
- Cluster Map: 从 `item_clusters` 表查
- Wiki Candidate: slug 从 title slugify 生成；concepts 从 tags

### Phase 2 — 后端缺口

#### 2.1 DB migration (`nas/models.py`)

`SCHEMA` 增 5 列（`Database.__init__` 自动 ALTER TABLE 兼容旧库）：

```python
# items 表新增
"hermes_judgment TEXT",
"concepts TEXT",          # JSON array
"source_divergence TEXT", # JSON, per-cluster
"wiki_candidate_slug TEXT",
"archived_at TEXT",
```

`to_db_row()` / `_deserialize_row()` / `list_items()` / `update_item()` 同步支持新字段。

#### 2.2 `/api/items` 扩展 (`nas/app.py`)

新增 query params：

| 参数 | 取值 | 含义 |
|---|---|---|
| `sort` | `time` (默认) / `signal` / `cluster` | 排序：时间倒序 / importance+created / 按 cluster_hash 分组 |
| `view` | `random` | Random Drift：`WHERE importance <= 2 ORDER BY RANDOM() LIMIT 50` |
| `perspective` | `today` / `ai-research` / `engineering` / `markets` / `saved` / `archived` | perspective 维度过滤（多对一映射到 source/category/status 组合）|
| `status` | `new` / `processed` / `saved` / `archived` | 已存在，补 `archived` |

`Database.list_items()` 同步加 sort/view/perspective 分支。

#### 2.3 `/api/stats` 扩展

返回结构升级：

```json
{
  "total": 176,
  "by_status": {"new": 170, "processed": 5, "saved": 1, "archived": 0},
  "by_source": {"hackernews": 50, "arxiv": 50, "github": 50, "huggingface": 25, "rss": 1},
  "by_perspective": {
    "today": 12,
    "ai-research": 18,
    "engineering": 11,
    "markets": 4,
    "saved": 1,
    "archived": 0,
    "random": "∞"
  },
  "clusters_count": 2
}
```

`by_perspective.today` = 今日 published_at 的 item 数；`ai-research/engineering/markets` 按 category 前缀分组（待你确认 taxonomy 映射，见 §5 未决）。

#### 2.4 新 UI 端点

```python
@app.get("/ui/cognition/{item_id}", response_class=HTMLResponse)
def ui_cognition(item_id: str):
    # 返回 cognition_panel(...) HTML
    # 查 item + related cluster items + cluster info

@app.get("/ui/cluster/{cluster_hash}", response_class=HTMLResponse)
def ui_cluster(cluster_hash: str):
    # 返回 cluster_view(...) HTML
    # 替换 #timeline-content

@app.get("/ui/stats", response_class=HTMLResponse)
def ui_stats():  # 已存在，扩展输出
@app.get("/ui/items", response_class=HTMLResponse)
def ui_items(...):  # 已存在，参数扩展
```

#### 2.5 PATCH 支持 archived

`/api/items/{id}` PATCH 已支持任意字段更新，只需补 `archived_at` 自动写入逻辑（在 update_item 内部 if status == "archived" set archived_at = now()）。

### Phase 3 — Processor 增强

#### 3.1 重写 prompt (`scripts/process_items.py`)

每个 item 输出 JSON：

```json
{
  "id": "<id>",
  "summary": "<客观摘要，1-2 句>",
  "judgment": "<Hermes 判断：为什么重要，长期影响>",
  "importance": 1-5,
  "category": "<自由小写连字符>",
  "concepts": ["<concept 1>", "<concept 2>", ...],
  "tags": ["<tag 1>", ...],
  "wiki_candidate": {
    "slug": "<kebab-case-slug>",
    "concepts": ["<concept 1>", "<concept 2>"]
  }
}
```

Cluster 级别（每个 cluster 一条）：

```json
{
  "cluster_hash": "<hash>",
  "source_divergence": {
    "HN": "<HN 视角一句话>",
    "arXiv": "<arXiv 视角一句话>",
    ...
  }
}
```

#### 3.2 PATCH 回写

扩展现有 PATCH 调用：item-level 写 5 个新字段；cluster-level 调用新端点 `POST /api/clusters/{hash}/divergence` 写 source_divergence。

#### 3.3 重跑现有数据

`PAPILIO_PROCESS_LIMIT=5 PAPILIO_AGENT=claude python scripts/process_items.py` — 把现有 5 条 processed 重新跑获得新字段。

### Phase 4 — Power features

#### 4.1 命令面板 ⌘K

- 全局快捷键 `Cmd+K` 或 `/` 触发模态
- 后端：`GET /api/search?q=...&limit=10` 返回 JSON `{items: [...], concepts: [...], clusters: [...]}`
  - items: `WHERE title LIKE %q% OR summary LIKE %q%`
  - concepts: `SELECT DISTINCT json_extract(concepts, '$') FROM items WHERE ...`
  - clusters: `SELECT * FROM item_clusters WHERE ...`（按 hash 模糊无意义，可能跳过）
- 前端：vanilla JS 模态，结果列表键盘上下选择，回车跳转
- 也支持 HTMX 风格：`GET /ui/search?q=...` 返回 HTML 片段，避免写客户端模板

选 HTMX 风格，跟项目一致。

#### 4.2 Cluster detail 完整页

`/ui/cluster/{hash}` 已在 Phase 2.4。Cluster detail 内容（spec §七）：

- Event title (取 cluster 内首条 item title 或 LLM 生成的事件名)
- Sources: 列出所有源 badges
- Hermes Summary: 集合级 summary（Phase 3 cluster-level prompt 增字段）
- Different Opinions: source_divergence 直接渲染
- Related Wiki: cluster 关联 concepts

#### 4.3 Random Drift 端点

`/api/items?view=random` 已在 Phase 2.2。UI 上：
- 选中 "Random Drift" perspective → URL `?perspective=random`
- 视图 tab 切到 "Random"
- 显示提示 "Low-signal items, refreshed each visit" 和手动刷新按钮

#### 4.4 键盘快捷键完整接线（`index.html` 内联 JS）

| 键 | 行为 | 实现 |
|---|---|---|
| `J` | 下一条 | `selectCard(currentIndex + 1)` |
| `K` | 上一条 | `selectCard(currentIndex - 1)` |
| `O` | 打开原文 | `window.open(currentCard.url, '_blank')` |
| `C` | 打开 Cluster | HTMX `GET /ui/cluster/{hash}` → swap #timeline-content |
| `W` | 保存 Wiki | HTMX `POST /api/items/{id}/save` |
| `R` | Random Drift | `window.location = '/?perspective=random'` |
| `/` | 聚焦搜索 | `focusSearch()` |
| `Cmd+K` | 命令面板 | `openCommandPalette()` |
| `ESC` | 返回/关闭 | 关 modal 或回 Today |

卡片 url 要 `data-url="..."` 暴露给 JS。Cluster hash 要 `data-cluster="..."` 暴露。

### Phase 5 — 验证

1. 重启 NAS，浏览器打开 http://localhost:8000
2. 手动 smoke test：每个 perspective、每个 view tab、每个快捷键
3. 处理 5 条 + 重跑 processor
4. Vision MCP 复检（如果它今天稳定的话）
5. 提交 + 推送

## 3. 文件改动概览

### 重写
- `nas/web/index.html`（~700 行，1:1 对齐 demo + HTMX 接线）
- `nas/templates.py`（~400 行，新模板函数集）
- `scripts/process_items.py`（prompt 重写 + 新字段 PATCH）

### 修改
- `nas/app.py`（新路由 + 现有路由扩展）
- `nas/models.py`（schema migration + 新字段处理）

### 不动
- `collectors/*`
- `PLAN.md`（可能后续补一段对齐 spec，本次不动）

## 4. 关键架构决策

| 决策点 | 选择 | 原因 |
|---|---|---|
| Cognition 更新机制 | HTMX `GET /ui/cognition/{id}` + outerHTML swap | 跟项目一致，无需客户端模板 |
| Cluster 视图 | 替换 `#timeline-content`，URL `?cluster={hash}` | 保持 3 栏 shell 一致 |
| 视图 tab 切换 | URL params `?sort=...&view=...` | 可分享、可前进后退 |
| 键盘状态 | vanilla JS `window.selectedItemId` | 无需框架 |
| 命令面板 | HTMX-driven `GET /ui/search?q=...` | 跟项目一致 |
| Random Drift | SQL `ORDER BY RANDOM() WHERE importance <= 2` | 简单，DB 够用 |
| status enum 扩展 | 加 `archived`，PATCH 时自动写 archived_at | 数据完整性 |
| 新字段存储 | TEXT + JSON 序列化（跟现有 tags/meta 一致） | 跟项目约定一致 |

## 5. 未决 / 待你确认

### 5.1 Perspective → category 映射

`ai-research / engineering / markets` 三个 perspective 需要映射到 category。当前 5 条 processed 数据的 category 是 `ai/image-gen` 和 `ai/llm`。建议映射：

| Perspective | 匹配规则 |
|---|---|
| `ai-research` | category LIKE `ai/%` OR source IN (arxiv, huggingface) |
| `engineering` | category LIKE `dev/%` OR source = github |
| `markets` | category LIKE `market/%` OR `biz/%` |

后续 processor 跑多了 category 自然收敛，可调整映射。

### 5.2 "Today" 定义

`perspective=today` 我打算用 `published_at >= today_00:00_local`。你时区是 Asia/Shanghai？还是用 UTC？建议本地时区（NAS 跑在你局域网）。

### 5.3 已存在 1 个真实 cluster 重跑

`ControlNet+ControlNet-v1-1` cluster 现在有 source_divergence 数据吗？Phase 3 重跑后这个 cluster 应该会获得 divergence 字段。如果你想要先看效果，可以先手动重跑这个 cluster 的两条 item。

### 5.4 PLAN.md 是否同步更新

spec §九 Wiki Workflow（弹窗 Save to Wiki 表单）比 PLAN.md §4.4 Wiki Bridge 详细很多。本次实现是否要把 PLAN.md §4.4 也更新对齐 spec？还是 PLAN.md 留旧版当历史，spec 当现状？建议：本次实现不动 PLAN.md，后续单独一次 commit 同步。

## 6. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| processor 增强 prompt token 增长 | 单批处理成本上升 | 暂不调 LIMIT，跑一次看实际 token 消耗再决定 |
| 170 条 new 数据未处理 | cognition 面板对 new item 没有 judgment/concepts | new item 显示降级版（用 summary + tags），不阻塞 UI |
| HF 数据缺 created_at | "Today" perspective 把所有 HF 当今天 | 仅影响本地 dev DB，Mac mini 部署后用真实日期 |
| Cluster 数据稀缺 | Source Divergence / Cluster Map 多数时间空 | 可接受，随着数据积累自然丰富 |
| 命令面板搜索性能 | SQLite LIKE 无索引慢 | 数据量 < 10K 不需要 FTS5，先用 LIKE；PLAN.md §七 已留 FTS5 升级口子 |
| 视觉对齐 demo | 实现可能偏离 demo 美感 | Phase 5 vision MCP 复检 + 你眼睛最终判定 |

## 7. 验证清单

Phase 1 完成：
- [ ] http://localhost:8000 显示 3 栏 dark dashboard
- [ ] sidebar 3 section 渲染、count 正确
- [ ] timeline cards 渲染、status/importance/source/tags 显示
- [ ] 点击卡片 → cognition panel 联动更新
- [ ] J/K 键盘导航可用

Phase 2 完成：
- [ ] view tab 切换（Signal/Time/Cluster/Random）实际改 sort
- [ ] perspective 切换（Today/AI/Eng/Markets/Saved/Archived/Random Drift）实际过滤
- [ ] Cluster detail 页可访问
- [ ] archived 状态可设置
- [ ] metrics topbar 实时更新

Phase 3 完成：
- [ ] processor 输出含 judgment/concepts/wiki_candidate
- [ ] cognition panel 显示真实 Why this matters + Related Concepts
- [ ] cluster source_divergence 显示

Phase 4 完成：
- [ ] Cmd+K 打开命令面板
- [ ] 搜索返回 items + concepts + clusters
- [ ] 所有快捷键 O/C/W/R/Slash/ESC 工作
- [ ] Random Drift 显示低权重随机条目

---

## 执行节奏建议

不要并行——各 Phase 有依赖（Phase 2 DB 字段要先于 Phase 3 PATCH；Phase 1 模板要先于 Phase 2 端点）。顺序执行：

```
Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5
```

每个 Phase 完成后 smoke test 一次再进下一个。预计总工作量约 1500-2000 行代码改动（index.html ~700 + templates.py ~400 + process_items.py ~150 + app.py ~150 + models.py ~80 + 调试）。

可以分多个 commit（每 Phase 一个），也可以最后一个总 commit。建议分 commit 方便回滚。

