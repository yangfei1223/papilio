# HuggingFace Collector — 设计文档

> Papilio 新增第 5 个源：HuggingFace trending models。
> 日期：2026-06-29

## 背景

Papilio 当前有 4 个 collector（HN / RSS / arXiv / GitHub），覆盖技术资讯、论文、开源项目。AI 模型生态（开源 LLM、图像/音频/多模态模型）目前缺一个专门源。HuggingFace 是开源 AI 模型的事实中心，其 "trending models" 能反映当下哪些模型受关注。补上这个源后，信息聚合覆盖更完整。

## 目标 / 非目标

- **目标**：新增 `collectors/huggingface.py`，拉取 HF trending models，标准化后 POST 到 NAS；Web UI 侧边栏增加 `HuggingFace` 源切换。
- **非目标**：
  - 不拉 Spaces / Datasets / Daily Papers（用户已确认只要 trending models；后续可扩）。
  - 不引入 `huggingface_hub` 库（杀鸡用牛刀，与现有 collector 的轻量 `requests` 风格不一致）。
  - 不读 `config.yaml`（trending 是全局单一端点，无需源配置；数量先硬编码常量，YAGNI）。
  - 不做 auth token（trending 公开可读；rate limit 不紧张，单次 1 个请求）。
  - 不改 schema、不改 API 契约、不改 status 生命周期。

## 设计

### 方案：HF Hub REST API（`requests` 直连）

与现有 4 个 collector 完全一致的实现风格：`requests` 直打 HTTP API，无新依赖，BaseCollector 复用 `fetch → _normalize → _dedup → _post` 管线。

### Collector 结构（`collectors/huggingface.py`）

镜像 `github.py` 的近 7 天高星模式（同样是"近期高 N"语义）：

- `HF_API = "https://huggingface.co/api"`
- 模块常量 `LIMIT = 25`（trending 本身量不大，不需要 50）
- `fetch()`：
  - 调 `GET {HF_API}/models?sort=trending&limit={LIMIT}` 拉取 trending models
  - 若 `sort=trending` 不可用（HTTP 非 200 或返回异常），回退 `sort=likes&direction=-1`（按点赞降序，近似热门）
  - 逐条构造 item dict
- `_get_trending()`：实际请求 + fallback，返回 raw repo 列表（与 `github.py._get_trending` 同形）

### Item 字段映射

| Papilio Item 字段 | 来源 |
|---|---|
| `source` | 固定 `"huggingface"` |
| `url` | `https://huggingface.co/{model_id}` |
| `title` | `model_id`（如 `meta-llama/Llama-3.1-8B`） |
| `summary` | 模型 `pipeline_tag`（如 `text-generation`），无则空 |
| `author` | `model_id` 的 owner 部分（`/` 前的 namespace） |
| `published_at` | 模型 `created_at`（仓库创建时间，UTC ISO，可能 `Z`/`+00:00` 混合 → 经 `base._normalize` 统一） |
| `content_hash` | `content_hash(model_id)`（`base.py` 的工具函数） |
| `meta` | `{downloads, likes, pipeline_tag, tags}`（`tags` 截断前 10 个） |

身份/dedup 由 `BaseCollector` 处理：`id = sha256(source\|url\|published_at)[:16]`，`_dedup` 按本批 URL 去重，NAS upsert 按 `url OR id`。

### Web UI 改动（`nas/web/index.html`）

侧边栏 `<nav>` 当前 5 个 `<a>`（全部 / HN / arXiv / GitHub / RSS），在 GitHub 和 RSS 之间插入一个：

```html
<a href="/?source=huggingface" hx-get="/ui/items?source=huggingface&per_page=50"
   hx-target="#feed" hx-swap="innerHTML" hx-push-url="true">HuggingFace</a>
```

`templates.py` 的 source badge 已经是通用的（按 `source` 文本渲染），无需改。

### 调度入口（`scripts/run_collector.py`）

`run()` 函数加 `elif name == "huggingface"` 分支，`all` 分支的列表加 `"huggingface"`。

### Cron 调度（PLAN §4.3 cron 表新增一行）

| 任务 | 频率 | 说明 |
|---|---|---|
| collect-huggingface | 每天 10:00 | HF trending models |

与 GitHub 同档（trending 日级变化足够，无需更高频）。

## 验证策略

项目无测试框架（PLAN §七）。手动验证：

1. **Collector 单跑**：`PAPILIO_NAS_URL=http://localhost:8000 python3 scripts/run_collector.py huggingface` → 输出 `Done: {'created': N, ...}`（N>0）。
2. **入库校验**：`curl 'localhost:8000/api/items?source=huggingface&per_page=5'` → 返回的 item：`source=huggingface`、`published_at` 以 `+00:00` 结尾、`url` 形如 `https://huggingface.co/<id>`。
3. **UI 可见**：浏览器打开 `localhost:8000`，侧边栏出现 `HuggingFace` tab，点击后 feed 切换为 HF 条目。
4. **`all` 调度**：`python3 scripts/run_collector.py all` 不报 `Unknown collector`。

### ⚠️ 本地网络限制

当前调试环境 `huggingface.co` 不可达（CDN IP `103.42.176.244` 拒绝 TCP 443）。**实现完成后本地无法端到端验证**。两个出路：
- 等 Mac mini（生产机，网络独立）部署后跑真实验证；
- 或本地网络恢复后补跑。

代码层面会先保证 import 正常、字段映射正确、fallback 路径存在。

## 影响范围

- **新增文件**：`collectors/huggingface.py`
- **改动文件**：`scripts/run_collector.py`（加 dispatch 分支）、`nas/web/index.html`（加 sidebar tab）
- **无 schema 变更**，无 API 契约变更，无新依赖。
- 不动 `config.yaml`、`templates.py`、NAS 后端代码。

## 后续（非本期）

- 若需要 Spaces / Datasets / Daily Papers：扩 `fetch()` 拉多类，`meta.type` 区分。
- 若需要按 `pipeline_tag` 筛选（只要 LLM / 只要图像）：加 `config.yaml` 的 `hf_tags` 配置。
- 若 trending 排序语义不满意：可换 weekly trending 或自定义窗口。
