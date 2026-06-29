# 🦋 Papilio — 破茧成蝶

个人信息聚合站。从 RSS / Hacker News / arXiv / GitHub / HuggingFace 多源拉取，AI 批量富化（摘要 + 分类 + 重要性 + 聚类去重），Web UI 浏览，手动沉淀进个人 wiki。打破信息茧房，主动定义你看到的世界。

## 架构

双机模型——代码按**运行位置**而不是分层拆分：

```
Mac mini (大脑, 7×24)             NAS (仓库, 7×24)
├── collectors/  ← 5 源抓取        ├── FastAPI + SQLite
├── scripts/                       │   ├── REST API (/api/*)
│   ├── run_collector.py           │   └── HTMX Web UI (/ui/*)
│   └── process_items.py ← AI 富化 ├── Docker (docker compose)
└── Hermes cronjob                 └── 零 AI，只做存储和渲染
```

两机**只通过 HTTP 通信**（默认 `http://nas:8899`，可用 `PAPILIO_NAS_URL` 覆盖）。NAS 不跑 AI——所有富化在 Mac mini 完成。

## 数据流

```
collector.fetch() → normalize → dedup → POST /api/items (status=new)
                                              │
                                              ▼
                    process_items.py (Mac mini) 拉取 status=new
                                              │
                            Claude/Hermes CLI 批量富化（≤ LIMIT 条/批）
                                              │
                            PATCH summary/category/importance/tags
                                              │
                            POST /api/clusters（跨源聚类去重）
                                              ▼
                                     status=processed
                                              │
                            手动点 [→ Wiki] → status=saved
```

Item 身份：`id = sha256(source|url|published_at)[:16]`；DB upsert 按 `url OR id`。状态机 `new → processed → saved`（`saving` 为 wiki 触发瞬态）。

## 快速开始

### NAS 端

```bash
cd nas
docker compose up -d          # → http://nas:8899
```

本地开发：

```bash
cd nas
PAPILIO_DATA_DIR=./data uvicorn app:app --host 0.0.0.0 --port 8000
```

> ⚠️ **不要**用 `uvicorn --reload`：会监视 `data/*.db-wal`，每次写入触发重启，导致 collector POST 失败。

### Mac mini 端（collectors）

```bash
cd collectors
pip install -r requirements.txt

# 单独跑一个
python hackernews.py
python huggingface.py

# 或通过调度器：hackernews | rss | arxiv | github | huggingface | all
cd ..
python scripts/run_collector.py all
```

源配置：`collectors/config.yaml`（RSS / arXiv 用）。RSS 默认空，需要自己加订阅。

### Mac mini 端（AI 富化 processor）

```bash
# 默认走本地 claude CLI（claude -p --output-format json）
PAPILIO_NAS_URL=http://nas:8899 python scripts/process_items.py

# 控成本：限制单批最多处理多少条
PAPILIO_PROCESS_LIMIT=20 PAPILIO_NAS_URL=... python scripts/process_items.py

# 切换 agent 后端（默认 claude；hermes 占位待 Mac mini 部署时填）
PAPILIO_AGENT=claude python scripts/process_items.py
```

Processor 一次 prompt 批量处理 ≤ LIMIT 条，支持跨源去重聚类。**手动触发为主**，cron 可选可配（建议 ≥6 小时一次，按 token 预算定）。

## 定时任务（Hermes cronjob 参考）

详见 `PLAN.md` §4.3。简化版：

| 任务 | 频率 | 备注 |
|------|------|------|
| collect-rss | 每 2 小时 | 所有 RSS 源 |
| collect-hn | 每 2 小时 | HN top 50（10 线程并发） |
| collect-arxiv | 每天 8:00 / 20:00 | cs.AI + cs.CL |
| collect-github | 每天 10:00 | GitHub Trending |
| collect-huggingface | 每天 10:00 | HF trending models |
| process-items | 手动 / ≥6h | AI 富化，`PAPILIO_PROCESS_LIMIT` 控批量 |
| clean-old | 每天 3:00 | 清 90 天前未保存低分条目 |

## 环境变量

| 变量 | 默认 | 用途 |
|------|------|------|
| `PAPILIO_NAS_URL` | `http://nas:8899` | Mac mini → NAS API 地址 |
| `PAPILIO_DATA_DIR` | `/data` | NAS SQLite + 静态资源目录 |
| `PAPILIO_AGENT` | `claude` | processor 用哪个 agent CLI（`claude` / `hermes`） |
| `PAPILIO_PROCESS_LIMIT` | `20` | processor 单批最多处理多少条 |
| `HF_ENDPOINT` | `https://huggingface.co` | HF collector 端点；区域屏蔽可切 `https://hf-mirror.com` |

## 项目结构

```
collectors/        # 5 源抓取器 + base.py（fetch→normalize→dedup→post 流水线）
  base.py          # BaseCollector.run() 公共流水线
  hackernews.py    # HN top 50（ThreadPoolExecutor 并发）
  rss.py           # RSS 订阅（config.yaml 配置）
  arxiv.py         # arXiv cs.AI + cs.CL
  github.py        # GitHub Trending（优先 gh CLI）
  huggingface.py   # HF trending models
scripts/
  run_collector.py # 调度器：collectors/<name> | all
  process_items.py # P1 AI 富化 processor（批量 + 聚类）
nas/
  app.py           # FastAPI 路由（/api/items, /api/clusters, /ui/*, /api/health）
  models.py        # SQLite schema（items, item_clusters）+ Database
  templates.py     # HTMX 服务端渲染片段（手工 _esc() 转义）
  web/index.html   # 静态外壳（HTMX + infinite scroll）
  docker-compose.yml
PLAN.md            # 权威设计文档（架构图、完整 schema、cron 表、Phase 计划、§七 非目标）
AGENTS.md          # 给 Codex / opencode 的工作约定
```

## 设计原则

- **NAS 零 AI**：所有 AI 在 Mac mini，NAS 只做存储 + 渲染。
- **批量富化**：一次 prompt 处理多条，支持跨源去重聚类，比逐条调用省 token。
- **手动沉淀进 wiki**：[→ Wiki] 按钮触发，不做自动灌 wiki（§七 非目标）。
- **自由分类**：category 是自由文本小写连字符（如 `ai/llm`、`dev/rust`），后续按分布收敛成 taxonomy。
- **CORS 全开 + 无 auth**：局域网自用，故意如此（§七）。
- **无测试 / 无 lint / 无 CI**：故意如此（§七）。

## Smoke test

```bash
curl http://nas:8899/api/health
```

## 更多

完整架构图、DB schema、Phase 路线图、明确不做的事见 [`PLAN.md`](PLAN.md)。
