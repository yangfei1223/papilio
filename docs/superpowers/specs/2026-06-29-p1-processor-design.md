# P1 Processor（AI 富化） — 设计文档

> Papilio 子项目 P1。把 collector 入库的原始条目（`status=new`）经 AI 富化（摘要 / 分类 / 评分 / 去重）转为 `status=processed`。
> 日期：2026-06-29

## 背景

P0 地基修复 + 5 个 collector（HN / arXiv / GitHub / HuggingFace / RSS）完成后，NAS 持续接收原始条目，但全部停在 `status=new`，没有摘要 / 分类 / 重要性，无法按分类筛选、无法识别跨源重复。`scripts/process_items.py` 现在只是个骨架——拉 new 条目、输出 JSON、留一段 instruction 字符串让"Hermes"处理，但 Python 自身不做任何 AI 编排，也从未真正跑通。

PLAN §4.2 定义 processor 为 Hermes cronjob（每 30 分钟），NAS 不跑任何 AI。本设计沿用 PLAN 的批量四合一富化思路，唯一改动是把 agent 后端**可配置化**：本地用 `claude`（Claude Code CLI）调试，生产用 `hermes`，差别只是 subprocess 命令。

## 目标 / 非目标

- **目标**：
  - 重写 `scripts/process_items.py` 为可独立运行的批量富化 processor：拉 new → 组 prompt → 调外部 agent CLI → 解析结构化响应 → PATCH 回 NAS（status: new→processed）+ 记录重复聚类。
  - agent 后端可配置（`PAPILIO_AGENT=claude|hermes`），prompt 契约与管线对后端无关。
  - 接上现成但闲置的 `item_clusters` 表 + `Database.create_cluster`。
- **非目标**：
  - 不在 Python 里写 LLM 编排 / 重试 / 流式（agent 自己管上下文与 reasoning）。
  - 不改 NAS schema（`items` / `item_clusters` 已够用）。
  - 不改 NAS 后端代码（`create_cluster` / `get_clusters` 已有）。
  - 不做逐条富化（批量是核心设计，单 prompt 看全批才能跨源去重）。
  - 不实现 hermes 真实 CLI 命令（模板留占位，部署 Mac mini 时填）。
  - 不锁定 category taxonomy（自由文本，见下）。
  - 不动 Web UI（category 筛选 UI 已存在；自由文本 taxonomy 下前期值不可预测，后期归纳）。

## 设计

### 1. 数据流（每 30 分钟一次，一次跑一批）

```
Mac mini (processor cronjob)
  GET {NAS}/api/items?status=new&per_page=20      ← 拉
        ↓
  build_prompt(items)                              ← 组一个批量 prompt
        ↓
  invoke_agent(prompt)   [PAPILIO_AGENT=claude|hermes]  ← 子进程调外部 agent
        ↓
  parse JSON array: [{id, summary, category, importance, duplicate_of}, ...]
        ↓
  逐条 PATCH {NAS}/api/items/{id}                  ← status: new→processed
  重复组：create_cluster(cluster_hash, member_ids)  ← 写 item_clusters
```

### 2. 富化契约（agent 输入 → 输出）

**输入**（prompt 内嵌的条目数组）：
```json
[{"id":"abc123","source":"hackernews","title":"...","url":"...","summary":"<原始 summary 或空>"}, ...]
```

**输出**（agent 必须只返回该结构的 JSON 数组，no prose）：
```json
[{
  "id": "abc123",
  "summary": "中文摘要，≤200 字",
  "category": "自由文本 label",
  "importance": 4,
  "duplicate_of": "def456" | null
}, ...]
```

字段语义：
- `summary`：中文，≤200 字，浓缩标题 + 原始 summary 的信息。
- `category`：**自由文本**，不锁 enum。soft nudge：prompt 要求"小写、单词或连字符、英文"（如 `ai` / `llm` / `devops` / `security` / `research`），减少 `AI` vs `ai` 碎片化，但不强制固定集合。
- `importance`：整数 1-5（5 最重要）。
- `duplicate_of`：本批 20 条内，若当前条与另一条是**同一事件**（如 HN 和 RSS 报同一条新闻），填那条的 `id`；否则 `null`。agent 一次看全批所以能跨源识别。

### 3. Agent 后端抽象（核心可配置点）

```python
BACKENDS = {
    "claude": {
        "cmd": ["claude", "-p", "--output-format", "json",
                "--dangerously-skip-permissions", "{prompt}"],
        # claude -p --output-format json 返回 {result: "<文本>", ...}
        # 需从 .result 取文本再 JSON.parse
        "extract": lambda resp: json.loads(resp)["result"],
    },
    "hermes": {
        # 占位：部署到 Mac mini 时填 Hermes 真实 CLI
        "cmd": ["hermes", "run", "--prompt", "{prompt}"],
        "extract": lambda resp: resp,   # 假设 hermes 直接返回文本
    },
}
```

- 配置：`PAPILIO_AGENT` 环境变量，默认 `claude`（本地调试）。
- `invoke_agent(prompt) -> str`：按 `PAPILIO_AGENT` 取模板 → `subprocess.run` → 调对应 `extract` 取出 agent 回复文本。
- `{prompt}` 占位由 shell-safe 的字符串注入（prompt 含 JSON，避免 shell 解析问题——用 `subprocess.run(list, ...)` 不走 shell）。
- **关键不变量**：prompt 模板、响应解析、PATCH、聚类逻辑全部后端无关；换 agent 只换 `BACKENDS` 里一条。

### 4. 去重（接上闲置的 `item_clusters`）

- agent 在同一 prompt 内对每条输出 `duplicate_of`。
- processor 聚合：对每个"被指向"的 primary id，收集所有指向它的 id + 它自己 → 形成一个 member 列表。
- `cluster_hash = sha256("|".join(sorted(member_ids)))[:16]`（确定性，同一组成员哈希一致；纯分组键，无语义）。
- 调用现有 `Database.create_cluster(cluster_hash, member_ids)`（`models.py` 已实现，目前无人调用）。
- 重复条目本身仍正常富化（summary/category/importance）+ `status=processed`；"这是重复"的信息只活在 `item_clusters`，可通过 `/api/clusters` 查询。**不改 schema**。
- 无重复时（常见）：不写 cluster，正常 PATCH 完事。

### 5. Prompt 模板（claude/hermes 共用）

固定结构，写死在 processor 代码里：

```
你是信息聚合站的富化 agent。对下面每一条条目生成富化信息。

对每条返回：
- summary: 中文摘要 ≤200 字
- category: 自由文本标签，小写、单词或连字符、英文（如 ai/llm/devops/security/research/product/tool）
- importance: 1-5 整数（5 最重要）
- duplicate_of: 若本批内另一条是同一事件，填那条的 id；否则 null

严格只返回 JSON 数组，不要任何解释文字。schema:
[{"id": str, "summary": str, "category": str, "importance": int, "duplicate_of": str | null}]

条目：
<注入 JSON 数组>
```

### 6. 状态生命周期

- 条目经 processor PATCH 后：`new → processed`。
- `saving`（wiki 触发的瞬态）/ `saved` 不变，与 P1 无关。
- **原子性边界**：processor 的顺序是「拉 → 组 prompt → 调 agent → **解析 JSON 数组** → 开始 PATCH」。**解析成功前**任何一步失败（agent 超时 / 返回非 JSON / 字段缺失），整批不动 status（保持 new），下次 cron 重试——这是主要失败模式，严格整批隔离。**解析成功后**进入 PATCH 阶段，逐条 PATCH；个别 PATCH 失败（如网络抖动）按 best-effort 记日志，因 status 仍为 new，下次 cron 自动重试漏的几条，不会丢数据也不会重复富化（已 processed 的不会被再次拉进 batch）。

## 验证策略

项目无测试框架（PLAN §七）。本地端到端验证（用户已确认走真实 claude 调用）：

1. **单跑 processor**：
   ```bash
   PAPILIO_AGENT=claude PAPILIO_NAS_URL=http://localhost:8000 \
     python3 scripts/process_items.py
   ```
   预期：输出 `Processed N items, M clusters`，N>0。
2. **stats 分布**：`curl localhost:8000/api/stats` → `by_category` 出现非空分布（自由文本 label 的实际形态），`by_status.processed` > 0。
3. **抽样校验**：`curl 'localhost:8000/api/items?status=processed&per_page=3'` → 每条有 summary（中文）/ category（小写英文）/ importance（1-5）。
4. **聚类**：`curl localhost:8000/api/clusters` → 若本批有跨源重复，返回非空聚类（无重复则空，正常）。
5. **失败隔离**：临时把 `PAPILIO_AGENT` 设成不存在的后端 → processor 报错退出，DB 里 status 全保持 new（无半富化）。

## 影响范围

- **重写**：`scripts/process_items.py`（现为骨架，重写为完整 processor；保留入口名以便 cronjob 注册不变）。
- **不动**：`nas/`（app.py / models.py / templates.py / web/）、`collectors/`、`PLAN.md`（cron 表 process-items 行已存在）。
- **无 schema 变更**，无 API 契约变更，无新依赖（仅标准库 `subprocess` / `json` / `hashlib`，`requests` 已在）。

## 后续（非本期）

- **hermes 后端落地**：部署到 Mac mini 时，填 `BACKENDS["hermes"]["cmd"]` 为真实 Hermes CLI；prompt 模板与管线零改动。
- **category taxonomy 归纳**：跑若干天后看 `by_category` 分布，把高频 label 收敛成固定集合，届时 UI 的 category 筛选才真正可用。
- **P2 去重已在本期实现**（duplicate_of + cluster），原 PLAN Phase 3.2 不再单独开。
- **prompt 调优**：根据 summary 质量 / category 一致性迭代 prompt 模板。
