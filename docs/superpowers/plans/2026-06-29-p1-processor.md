# P1 Processor (AI 富化) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重写 `scripts/process_items.py` 为批量 AI 富化 processor（摘要 / 分类 / 重要性 / 跨源去重），agent 后端可配（`claude` 默认 / `hermes` 占位）；在 NAS 加 `POST /api/clusters` 端点让去重结果落地。

**Architecture:** processor 子进程调外部 agent CLI（`claude -p --output-format json`），一次批量富化 ≤`PAPILIO_PROCESS_LIMIT` 条 `status=new` 条目 → 解析 JSON 数组 → 逐条 PATCH（new→processed）；`duplicate_of` 聚类后 POST 到 NAS 新端点写入 `item_clusters`。触发以手动为主、cron 可选可配。

**Tech Stack:** Python 3.12/3.13 · subprocess · requests · Claude Code CLI (`claude -p`) · FastAPI（NAS 新端点）

---

## 验证约定（无测试框架 + 真实 claude 调用）

- **项目刻意无 pytest**（PLAN §七），沿用 P0/HF plan 的 `curl`/手动验证风格。
- **NAS 验证实例**：本地在跑的 uvicorn（`http://localhost:8000`）。改 NAS 代码后若用 `--reload` 会因 DB 写入抖动（已知 smell），本计划假设 NAS 跑**不带 reload** 的稳定模式；若 NAS 没起，用：
  ```bash
  PAPILIO_DATA_DIR=/Users/yangfei/Code/papilio/nas/data \
    uvicorn app:app --app-dir /Users/yangfei/Code/papilio/nas --host 127.0.0.1 --port 8000
  ```
  （后台跑，`disown` 释放终端。）
- **真实 API 调用**：Task 3 端到端验证会 fork 真 `claude`（产生 API 费用）。用 `PAPILIO_PROCESS_LIMIT=5` 控制单次 5 条、1 次 claude 调用，token 开销可控。
- **claude CLI 已就位**：`which claude` → `/Users/yangfei/.nvm/.../claude`，v2.1.195，`-p --output-format json` 模式已实测可返回结构化结果。

## File Structure

| 文件 | 责任 | 本计划改动 |
|------|------|-----------|
| `nas/app.py` | FastAPI 路由 | Modify：新增 `POST /api/clusters` 路由（复用现有 `Database.create_cluster`），约 10 行 |
| `scripts/process_items.py` | processor 入口 | **重写**：从骨架升级为完整批量富化 processor（config + BACKENDS + invoke_agent + build_prompt + parse + PATCH + cluster） |
| `PLAN.md` | 设计权威文档 | Modify：§4.3 把 `process-items` cadence 从「每 30 分钟」放宽为可配 + 默认低频，标注 cron 可选 |

> `nas/models.py` 不动（`create_cluster` 已实现，本计划首次通过 HTTP 调用它）。
> `nas/templates.py` / `nas/web/` / `collectors/` 不动。

---

### Task 1: NAS 新增 `POST /api/clusters` 端点

**Files:**
- Modify: `nas/app.py`（在现有 `GET /api/clusters` 路由附近插入 POST 路由）

- [ ] **Step 1: 在 `nas/app.py` 加 POST 路由**

在现有 `@app.get("/api/clusters")` 路由（约第 138-141 行）**之后**插入：

```python
@app.post("/api/clusters")
def create_cluster(payload: dict):
    """processor 检测到跨源重复时写入聚类。"""
    cluster_hash = payload.get("cluster_hash")
    item_ids = payload.get("item_ids", [])
    if not cluster_hash or not item_ids:
        raise HTTPException(400, "cluster_hash and item_ids required")
    get_db().create_cluster(cluster_hash, item_ids)
    return {"ok": True, "cluster_hash": cluster_hash, "count": len(item_ids)}
```

> `HTTPException` 已在 app.py 顶部 import（`update_item` 路由用过），无需新 import。

- [ ] **Step 2: 重启 NAS 让路由生效**

若 NAS 跑的是不带 reload 的稳定模式，需手动重启（杀旧进程 + 重新起）。若不确定怎么起的：
```bash
# 杀掉占用 8000 的进程
lsof -ti :8000 | xargs kill 2>/dev/null; sleep 1
# 起稳定版（后台）
nohup env PAPILIO_DATA_DIR=/Users/yangfei/Code/papilio/nas/data \
  /opt/miniconda3/bin/uvicorn app:app --app-dir /Users/yangfei/Code/papilio/nas --host 127.0.0.1 --port 8000 \
  > /tmp/papilio-logs/uvicorn.log 2>&1 &
disown
sleep 2
curl -s http://localhost:8000/api/health
```
Expected: `{"status":"ok","db":"..."}`。

- [ ] **Step 3: 验证 POST 端点工作**

```bash
# 写一个测试 cluster
curl -s -X POST http://localhost:8000/api/clusters \
  -H 'Content-Type: application/json' \
  -d '{"cluster_hash":"test-cluster-0001","item_ids":["nonexistent-aaa","nonexistent-bbb"}'
echo
# 误用：缺字段应返 400
curl -s -o /dev/null -w "missing fields -> HTTP %{http_code}\n" -X POST http://localhost:8000/api/clusters \
  -H 'Content-Type: application/json' -d '{"cluster_hash":"x"}'
# 读回确认（即使 item_ids 不存在，cluster 行也写入了）
curl -s 'http://localhost:8000/api/clusters?limit=5' | python3 -m json.tool | head -20
```
Expected: 第一条返回 `{"ok":true,"cluster_hash":"test-cluster-0001","count":2}`；第二条 `HTTP 400`；第三条 `GET /api/clusters` 能查到（members 为空数组因 id 不存在，但 cluster_hash 列出）。

- [ ] **Step 4: Commit**

```bash
git -C /Users/yangfei/Code/papilio add nas/app.py
git -C /Users/yangfei/Code/papilio commit -m "🦋 P1: NAS 新增 POST /api/clusters 端点（复用 create_cluster）"
```

---

### Task 2: 重写 `scripts/process_items.py`

**Files:**
- Modify: `scripts/process_items.py`（整体替换）

- [ ] **Step 1: 整体替换 process_items.py**

把 `scripts/process_items.py` 整体替换为：

```python
#!/usr/bin/env python3
"""Papilio Processor — 批量富化 status=new 条目（摘要/分类/重要性/去重）.

触发：
  手动（主推）：PAPILIO_AGENT=claude PAPILIO_NAS_URL=http://localhost:8000 python3 scripts/process_items.py
  cron（可选，频率部署侧定，PLAN §4.3）：同上命令挂 Hermes cronjob。

可配置：
  PAPILIO_AGENT          agent 后端，默认 claude（本地调试）；hermes 占位待部署填
  PAPILIO_NAS_URL        NAS API 基址，默认 http://nas:8899
  PAPILIO_PROCESS_LIMIT  单次拉取/富化条目数，默认 20（控 token 成本）
"""

import hashlib
import json
import os
import subprocess
import sys

import requests

NAS_URL = os.getenv("PAPILIO_NAS_URL", "http://nas:8899")
AGENT = os.getenv("PAPILIO_AGENT", "claude")
LIMIT = int(os.getenv("PAPILIO_PROCESS_LIMIT", "20"))

# --------------- agent backends ---------------
# 每个 backend：cmd 是 subprocess 命令模板（{prompt} 占位）；extract 是从 stdout 提取 agent 回复文本的函数名。
BACKENDS = {
    "claude": {
        "cmd": ["claude", "-p", "--output-format", "json",
                "--dangerously-skip-permissions", "{prompt}"],
        "extract": "_extract_claude",
    },
    "hermes": {
        # 占位：部署到 Mac mini 时填真实 Hermes CLI。
        "cmd": ["hermes", "run", "--prompt", "{prompt}"],
        "extract": "_extract_raw",
    },
}

PROMPT_TEMPLATE = """你是信息聚合站的富化 agent。对下面每一条条目生成富化信息。

对每条返回：
- summary: 中文摘要 ≤200 字
- category: 自由文本标签，小写、单词或连字符、英文（如 ai/llm/devops/security/research/product/tool）
- importance: 1-5 整数（5 最重要）
- duplicate_of: 若本批内另一条是同一事件，填那条的 id；否则 null

严格只返回 JSON 数组，不要任何解释文字。schema:
[{{"id": str, "summary": str, "category": str, "importance": int, "duplicate_of": str | null}}]

条目：
{items_json}"""


def _extract_claude(stdout: str) -> str:
    """claude -p --output-format json 返回 {result: '...', ...}；取 result 字段。"""
    try:
        wrapper = json.loads(stdout)
        return wrapper.get("result", "").strip()
    except json.JSONDecodeError:
        return stdout.strip()  # 兜底：非 JSON wrapper 时原样返回


def _extract_raw(stdout: str) -> str:
    """hermes 等假设直接返回文本。"""
    return stdout.strip()


def build_prompt(items: list[dict]) -> str:
    slim = [
        {"id": i["id"], "source": i.get("source", ""),
         "title": i.get("title", ""), "url": i.get("url", ""),
         "summary": i.get("summary") or ""}
        for i in items
    ]
    return PROMPT_TEMPLATE.format(items_json=json.dumps(slim, ensure_ascii=False))


def invoke_agent(prompt: str) -> str:
    """按 PAPILIO_AGENT 调对应 backend，返回 agent 回复文本。"""
    if AGENT not in BACKENDS:
        raise RuntimeError(f"Unknown PAPILIO_AGENT={AGENT!r}; supported: {list(BACKENDS)}")
    backend = BACKENDS[AGENT]
    cmd = [prompt if arg == "{prompt}" else arg for arg in backend["cmd"]]
    # 不走 shell（prompt 含 JSON 与特殊字符）。
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        raise RuntimeError(
            f"agent {AGENT!r} exited {result.returncode}: {result.stderr.strip()[:500]}"
        )
    extract_fn = globals()[backend["extract"]]
    return extract_fn(result.stdout)


def _clamp(v, lo: int, hi: int):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return None


def parse_response(text: str, expected_ids: set) -> list[dict]:
    """解析 agent 返回的 JSON 数组，丢弃 id 不在 expected_ids 里的条目。"""
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(f"agent 返回非数组: {type(data).__name__}")
    cleaned = []
    for entry in data:
        eid = entry.get("id")
        if eid not in expected_ids:
            continue
        cleaned.append({
            "id": eid,
            "summary": str(entry.get("summary", ""))[:400],
            "category": (str(entry.get("category", "")).strip().lower() or None),
            "importance": _clamp(entry.get("importance"), 1, 5),
            "duplicate_of": entry.get("duplicate_of"),
        })
    return cleaned


def get_new_items() -> list[dict]:
    resp = requests.get(f"{NAS_URL}/api/items",
                        params={"status": "new", "per_page": LIMIT}, timeout=15)
    resp.raise_for_status()
    return resp.json().get("items", [])


def patch_item(item_id: str, fields: dict) -> None:
    requests.patch(f"{NAS_URL}/api/items/{item_id}", json=fields, timeout=10).raise_for_status()


def record_clusters(enriched: list[dict]) -> int:
    """对 duplicate_of 聚类，POST 到 NAS /api/clusters。"""
    groups: dict = {}
    for e in enriched:
        dup = e.get("duplicate_of")
        if dup:
            groups.setdefault(dup, [dup]).append(e["id"])
    written = 0
    for primary, members in groups.items():
        unique = sorted(set(members))
        if len(unique) < 2:
            continue
        cluster_hash = hashlib.sha256("|".join(unique).encode()).hexdigest()[:16]
        try:
            r = requests.post(f"{NAS_URL}/api/clusters",
                              json={"cluster_hash": cluster_hash, "item_ids": unique},
                              timeout=10)
            r.raise_for_status()
            written += 1
        except requests.RequestException as ex:
            print(f"[processor] cluster 写入失败 {cluster_hash}: {ex}")
    return written


def main():
    print(f"[processor] AGENT={AGENT} LIMIT={LIMIT} NAS={NAS_URL}")
    items = get_new_items()
    if not items:
        print("[processor] 没有 status=new 的条目，退出。")
        return
    print(f"[processor] 拉到 {len(items)} 条 new，组 prompt 调 agent...")

    prompt = build_prompt(items)
    try:
        raw = invoke_agent(prompt)
        enriched = parse_response(raw, expected_ids={i["id"] for i in items})
    except Exception as e:
        # 解析成功前失败：整批保持 new，下次重跑重试。
        print(f"[processor] agent 调用/解析失败，整批保持 new：{e}", file=sys.stderr)
        sys.exit(1)

    print(f"[processor] 解析得到 {len(enriched)} 条富化结果，开始 PATCH...")
    patched = 0
    for e in enriched:
        fields = {
            "summary": e["summary"],
            "category": e["category"],
            "importance": e["importance"],
            "status": "processed",
        }
        try:
            patch_item(e["id"], fields)
            patched += 1
        except requests.RequestException as ex:
            # best-effort：漏的条目 status 仍 new，下次重拾。
            print(f"[processor] PATCH {e['id']} 失败（best-effort 跳过）：{ex}")

    clusters = record_clusters(enriched)
    print(f"[processor] Processed {patched}/{len(enriched)} items, {clusters} clusters")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 验证 import + 配置默认值**

```bash
cd /Users/yangfei/Code/papilio/scripts && python3 -c "
import process_items as p
print('import ok')
print('BACKENDS:', list(p.BACKENDS))
print('LIMIT=', p.LIMIT, 'AGENT=', p.AGENT)
# build_prompt / parse_response 单元级 smoke（不调 agent）
items = [{'id':'x1','source':'test','title':'t','url':'u','summary':None}]
pr = p.build_prompt(items)
assert 'x1' in pr and '条目' in pr
parsed = p.parse_response('[{\"id\":\"x1\",\"summary\":\"s\",\"category\":\"ai\",\"importance\":7,\"duplicate_of\":null}]', {'x1'})
assert parsed[0]['importance'] == 5  # 7 被 clamp 到 5
assert parsed[0]['category'] == 'ai'
print('build_prompt + parse_response OK (importance clamped, category lowercased)')
"
```
Expected: `import ok` / `BACKENDS: ['claude', 'hermes']` / `LIMIT= 20 AGENT= claude` / `build_prompt + parse_response OK ...`。

- [ ] **Step 3: 验证失败隔离（agent 调用前失败时整批不动）**

```bash
# 用不存在的后端，确认 processor 在调 agent 前报错退出，且 DB 无 status 改动
curl -s 'http://localhost:8000/api/stats' | python3 -c "import sys,json;print('before processed:', json.load(sys.stdin)['by_status'].get('processed',0))"
PAPILIO_AGENT=ghost PAPILIO_NAS_URL=http://localhost:8000 python3 /Users/yangfei/Code/papilio/scripts/process_items.py 2>&1 | tail -3
echo "exit=$?"
curl -s 'http://localhost:8000/api/stats' | python3 -c "import sys,json;print('after processed:', json.load(sys.stdin)['by_status'].get('processed',0))"
```
Expected: processor 输出 `agent 调用/解析失败，整批保持 new：Unknown PAPILIO_AGENT='ghost'...`，`exit=1`；`before processed` 与 `after processed` **相等**（无 status 变化）。

- [ ] **Step 4: Commit**

```bash
git -C /Users/yangfei/Code/papilio add scripts/process_items.py
git -C /Users/yangfei/Code/papilio commit -m "🦋 P1: 重写 process_items.py 为批量 AI 富化 processor"
```

---

### Task 3: 端到端验证（真实 claude，小批量）

**Files:** 无（纯验证）

> 本 task fork 真 `claude`，产生 API 调用。用 `PAPILIO_PROCESS_LIMIT=5` 限到 5 条、1 次调用。

- [ ] **Step 1: 确认前置**

```bash
echo "NAS health:"; curl -s -m 5 http://localhost:8000/api/health; echo
echo "claude CLI:"; claude --version 2>&1 | head -1
echo "current new items:"; curl -s 'http://localhost:8000/api/stats' | python3 -c "import sys,json;print(json.load(sys.stdin)['by_status'].get('new',0))"
```
Expected: NAS ok / claude 版本号 / `new` 条目数 > 0（应 ≥150，P0/HF 留下的库存）。

- [ ] **Step 2: 跑 processor（5 条）**

```bash
PAPILIO_PROCESS_LIMIT=5 PAPILIO_AGENT=claude PAPILIO_NAS_URL=http://localhost:8000 \
  python3 /Users/yangfei/Code/papilio/scripts/process_items.py 2>&1 | tail -5
```
Expected: 输出 `[processor] Processed 5/5 items, M clusters`（M ≥ 0，本批无跨源重复就是 0）。耗时通常 30-90s（claude 一次调用）。

- [ ] **Step 3: 校验富化字段**

```bash
curl -s 'http://localhost:8000/api/items?status=processed&per_page=5' | python3 -c "
import sys, json
items = json.load(sys.stdin)['items']
assert items, 'no processed items'
for i in items:
    print(f\"  cat={i.get('category'):15} imp={i.get('importance')} | {i['title'][:50]}\")
    assert i.get('summary'), f\"empty summary: {i['id']}\"
    assert i.get('category'), f\"empty category: {i['id']}\"
    assert i.get('importance') in (1,2,3,4,5), f\"bad importance: {i.get('importance')}\"
print('all processed items have summary/category/importance OK, count=', len(items))
"
```
Expected: 每条都有中文 summary、小写英文 category、1-5 importance；末行 `... OK, count= 5`。

- [ ] **Step 4: 校验 stats 分布 + clusters**

```bash
echo "=== stats by_category（自由文本 label 实际形态）==="
curl -s http://localhost:8000/api/stats | python3 -c "
import sys, json
s = json.load(sys.stdin)
print('by_status:', s['by_status'])
print('by_category:', s['by_category'])
assert s['by_status'].get('processed',0) >= 5, 'processed 应至少 5'
assert s['by_category'], 'by_category 不应为空'
"
echo "=== clusters（本批若无跨源重复会是空，正常）==="
curl -s 'http://localhost:8000/api/clusters?limit=5' | python3 -m json.tool | head -15
```
Expected: `by_status.processed ≥ 5`；`by_category` 非空（能看到 agent 实际打的标签）；clusters 可能有 Task 1 测试数据 + 本批若有的真聚类。

- [ ] **Step 5: 无代码改动，跳过 commit**

Task 3 是纯验证，无 commit。

---

### Task 4: PLAN.md §4.3 cadence 放宽

**Files:**
- Modify: `PLAN.md`（§4.3 Cronjob 配置表 + 紧跟表的说明）

- [ ] **Step 1: 改 process-items 行的 cadence**

把 `PLAN.md` §4.3 表格里这行：
```markdown
| process-items | 每 30 分钟 | AI 处理新条目 |
```
改为：
```markdown
| process-items | 可配（默认每 6 小时或手动） | AI 处理新条目；processor 不含调度，频率由 Hermes cronjob 定，手动触发为主 |
```

- [ ] **Step 2: 在 §4.3 表格下补一句说明**

在 §4.3 表格后的那段（原写"前 4 个用 `no_agent=true`..."）之前，插入一行说明：
```markdown
> `process-items` 默认**手动触发**（`python3 scripts/process_items.py`）；若挂 cron，频率按 token 预算定（建议 ≥6 小时，避免 claude API 浪费）。批量大小由 `PAPILIO_PROCESS_LIMIT` 控制（默认 20）。
```

- [ ] **Step 3: 验证**

```bash
grep -n -A1 "process-items" /Users/yangfei/Code/papilio/PLAN.md | head -6
```
Expected: 命中改后的 process-items 行（cadence 列不再写"每 30 分钟"）。

- [ ] **Step 4: Commit**

```bash
git -C /Users/yangfei/Code/papilio add PLAN.md
git -C /Users/yangfei/Code/papilio commit -m "🦋 P1: PLAN §4.3 process-items cadence 放宽为可配+手动为主"
git -C /Users/yangfei/Code/papilio push origin main 2>&1 | tail -1
```

---

## Self-Review（计划作者自检）

- **Spec coverage**：spec 各节 → Task 1（POST /api/clusters 端点，落地 §4 cluster 写入）/ Task 2（重写 processor，覆盖 §1 数据流 / §2 富化契约 / §3 agent 后端 / §5 prompt / §6 原子性）/ Task 3（验证策略 6 项中的 1-5；第 6 项"全量清库存"是可选后续，不在本计划主路径）/ Task 4（PLAN cadence，§影响范围）。✓
- **Placeholder scan**：无 TBD/TODO；hermes backend cmd 是**有意占位**（spec 非目标明确"不实现 hermes 真实 CLI"），不是计划缺陷。每步含完整代码或确切命令 + 预期。✓
- **Type/naming consistency**：`BACKENDS` / `invoke_agent` / `build_prompt` / `parse_response` / `record_clusters` / `get_new_items` / `patch_item` 在 Task 2 代码与 Task 3 验证引用中一致；`PAPILIO_AGENT` / `PAPILIO_NAS_URL` / `PAPILIO_PROCESS_LIMIT` 三个 env var 与 spec §1.1/§3 一致；`POST /api/clusters` 的 body 形态（`{cluster_hash, item_ids}`）在 Task 1 路由与 Task 2 `record_clusters` 完全对齐；`cluster_hash = sha256("|".join(sorted(unique)))[:16]` 与 spec §4 一致。✓
- **YAGNI**：未加 `--dry-run`（用户没要求）；未引入新依赖（subprocess/json/hashlib 标准库 + requests 已在）；未实现 hermes CLI（占位）；未改 schema；未锁 taxonomy。✓
- **依赖顺序**：Task 1（NAS 端点）先于 Task 2（processor）→ Task 2 的 `record_clusters` 在 Task 3 验证时端点已存在可调；Task 3 依赖 Task 1+2；Task 4 独立。✓
