# P0 地基修复 — 设计文档

> Papilio 子项目 P0。**纯修复**——不改架构、不改数据流、不引入新依赖。
> 日期：2026-06-29

## 背景

本地调试跑通链路（NAS + collector 入库 + Web UI）后，代码审查发现 5 个实现问题。这些问题在后续子项目（P1 Processor、P2 去重、P3 前端筛选）启动前清理，避免在新功能上踩旧坑。

## 目标 / 非目标

- **目标**：修复 5 个已识别的实现问题。
- **非目标**：不改架构、不改数据流、不引入新依赖（含测试框架）、不做功能新增。

## 修复项

### 1. `published_at` 归一化（修复排序）

- **问题**：各源 `published_at` 时区格式不统一（HN/RSS 为 `+00:00`，arXiv 为 `...Z`）。`ORDER BY published_at DESC` 是字符串字典序，而 `Z`(0x5A) > `+`(0x2B)，导致 arXiv 条目异常置顶。
- **方案**：
  - collector 端统一：各 collector 构造 item 时把 `published_at` 转成 `datetime.astimezone(timezone.utc).isoformat()`（`+00:00`）。
  - `arxiv.py`：解析 atom `published` 时把 `Z` 转成 `+00:00`。
  - NAS 兜底：`models.Item.from_raw` 对 `published_at` 做轻量归一化（`Z` 结尾或不可解析时统一成 `+00:00`），防御漏网。
- **验证**：入库后 `curl /api/items`，所有 `published_at` 均以 `+00:00` 结尾；混合源时排序正确。

### 2. `update_item` SQL 防御

- **问题**：`Database.update_item` 用 `f"{k}=?"` 拼接列名，安全性完全依赖 `app.py` route 的白名单。
- **方案**：`Database` 内加 `ALLOWED_COLUMNS` 集合，`update_item` 丢弃非白名单 key。route 层过滤保留作纵深防御。
- **验证**：`curl PATCH` 一个非法字段，确认被忽略、不抛 SQL 错。

### 3. htmx 本地化

- **问题**：`index.html` 从 `unpkg.com` CDN 加载 htmx，NAS 无外网时所有 `hx-*` 交互失效。
- **方案**：下载 `htmx.min.js@2.0.4` 到 `nas/web/htmx.min.js`；`index.html` 改 `<script src="/htmx.min.js">`。`Dockerfile` 已 `COPY web/`，无需改动。
- **验证**：断网下访问 `localhost:8000`，无限滚动 / 源切换仍工作。

### 4. 清死代码 + lifespan

- `models.py`：删 `import uuid`（未使用）。
- `base.py`：删 `source_name` property（无人调用）。
- `app.py`：`@app.on_event("startup"/"shutdown")` → FastAPI `lifespan` async context manager（旧 API 已弃用）。
- **验证**：NAS 正常启停，无 import 报错。

### 5. GitHub collector 近期高星（方案 A）

- **问题**：`gh search repos stars:>500` 拉的是历史高星仓库，并非 trending。
- **方案**：
  - `github.py`：`gh search repos --created=>YYYY-MM-DD --sort=stars`（最近 7 天内新仓库按星排序），近似 trending；search API fallback 同步加 `created:>=YYYY-MM-DD`。
  - `published_at` 改用仓库 `created_at`（不再用 `now`，时间线才有意义）。
  - 时间窗口 7 天，提取为模块常量，可调。
- **验证**：重跑 github collector，入库条目的 `published_at` 分散在近 7 天，而非全是 `now`。

## 验证策略（整体）

项目刻意无测试框架（PLAN §七）。P0 全部靠手动验证（上述每项的「验证」小节）。**不引入 pytest**，保持 minimalist。

## 影响范围

- **改动文件**：`models.py`、`app.py`、`collectors/base.py`、`collectors/arxiv.py`、`collectors/github.py`、`collectors/hackernews.py`、`collectors/rss.py`、`nas/web/index.html`；新增 `nas/web/htmx.min.js`。
- **无 schema 变更**，无 API 契约变更（PATCH 行为更严格但不破坏合法用法）。

## 后续

P0 完成并验证后，进入 **P1（Processor AI 处理）** 的 brainstorm。
