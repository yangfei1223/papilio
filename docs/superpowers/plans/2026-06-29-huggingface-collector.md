# HuggingFace Collector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增第 5 个源 collector（HuggingFace trending models），并打通调度入口与 Web UI sidebar。

**Architecture:** 镜像 `github.py` 的实现风格——`requests` 直打 HF Hub REST API（`/api/models?sort=trending`），无新依赖；复用 `BaseCollector` 的 `fetch → _normalize → _dedup → _post` 管线。trending 不可用时回退 `sort=likes`。

**Tech Stack:** Python 3.12/3.13 · requests · HF Hub REST API · HTMX（UI）

---

## 验证约定（本计划无测试框架 + HF 本地不可达）

- **项目刻意无 pytest**（PLAN §七），沿用 P0 plan 的 `curl`/手动验证风格。
- **⚠️ `huggingface.co` 在当前调试网络不可达**（CDN IP `103.42.176.244` 拒绝 TCP 443）。本计划的验证分两类：
  - **本地可验证**（代码正确性 + 接线）：import 检查、dispatch 检查、UI HTML 检查——这些**现在就能跑**。
  - **端到端验证**（真实拉数据）：Task 5，依赖网络恢复或在 Mac mini（生产机）上跑。计划里明确标注，不阻塞代码落地。
- **NAS 验证实例**（用于 UI 验证）：本地已在跑的 uvicorn（`http://localhost:8000`），静态文件即时刷新，无需重启。

## File Structure

| 文件 | 责任 | 本计划改动 |
|------|------|-----------|
| `collectors/huggingface.py` | HF trending models collector | **新增**：完整实现 |
| `scripts/run_collector.py` | collector 调度入口 | Modify：加 `huggingface` 分支 + `all` 列表 |
| `nas/web/index.html` | 静态前端壳 | Modify：sidebar nav 加 HuggingFace tab |
| `PLAN.md` | 项目设计权威文档 | Modify：§4.3 cron 表加一行 |

> `templates.py` 的 source badge 是通用的（按 `source` 文本渲染），**无需改**。
> `config.yaml` **无需改**（trending 是全局单一端点，YAGNI）。
> NAS 后端代码（`app.py` / `models.py`）**无需改**（source 是任意字符串，schema 不变）。

---

### Task 1: 新建 `collectors/huggingface.py`

**Files:**
- Create: `collectors/huggingface.py`

- [ ] **Step 1: 创建 collector 文件**

写入完整内容到 `collectors/huggingface.py`：

```python
"""HuggingFace collector — Trending models via HF Hub API."""

from datetime import datetime, timezone

import requests

from base import BaseCollector, content_hash

HF_API = "https://huggingface.co/api"
LIMIT = 25


class HuggingFaceCollector(BaseCollector):
    def fetch(self) -> list[dict]:
        repos = self._get_trending()
        items = []
        for repo in repos:
            model_id = repo.get("id", "")
            if not model_id:
                continue
            owner = model_id.split("/", 1)[0] if "/" in model_id else ""
            items.append({
                "source": "huggingface",
                "url": f"https://huggingface.co/{model_id}",
                "title": model_id,
                "summary": repo.get("pipeline_tag") or "",
                "author": owner,
                "published_at": repo.get("created_at") or datetime.now(timezone.utc).isoformat(),
                "content_hash": content_hash(model_id),
                "meta": {
                    "downloads": repo.get("downloads", 0),
                    "likes": repo.get("likes", 0),
                    "pipeline_tag": repo.get("pipeline_tag", ""),
                    "tags": (repo.get("tags") or [])[:10],
                },
            })
        return items

    def _get_trending(self) -> list[dict]:
        """拉 trending models。先 sort=trending，不可用回退 sort=likes。"""
        try:
            resp = requests.get(
                f"{HF_API}/models",
                params={"sort": "trending", "limit": LIMIT},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and data:
                    return data
        except Exception as e:
            print(f"[HuggingFace] trending fetch failed: {e}")

        try:
            resp = requests.get(
                f"{HF_API}/models",
                params={"sort": "likes", "direction": "-1", "limit": LIMIT},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"[HuggingFace] likes fallback failed: {e}")
            return []


if __name__ == "__main__":
    HuggingFaceCollector().run()
```

- [ ] **Step 2: 验证 import（本地可验证）**

Run:
```bash
cd /Users/yangfei/Code/papilio/collectors && python3 -c "from huggingface import HuggingFaceCollector; print('huggingface ok'); print('LIMIT=', __import__('huggingface').LIMIT)"
```
Expected: 两行输出，第一行 `huggingface ok`，第二行 `LIMIT= 25`，无 `ImportError`/`AttributeError`。

- [ ] **Step 3: Commit**

```bash
git -C /Users/yangfei/Code/papilio add collectors/huggingface.py
git -C /Users/yangfei/Code/papilio commit -m "🦋 HF collector: 新增 HuggingFace trending models collector"
```

---

### Task 2: 调度入口接线（`scripts/run_collector.py`）

**Files:**
- Modify: `scripts/run_collector.py`

- [ ] **Step 1: 加 `huggingface` dispatch 分支**

在 `run()` 函数的 `elif name == "github":` 分支之后、`elif name == "all":` 之前，插入：

```python
    elif name == "huggingface":
        from huggingface import HuggingFaceCollector
        HuggingFaceCollector(NAS_URL).run()
```

- [ ] **Step 2: `all` 列表加入 `huggingface`**

把 `run()` 里这行：
```python
        for n in ["hackernews", "rss", "arxiv", "github"]:
```
改为：
```python
        for n in ["hackernews", "rss", "arxiv", "github", "huggingface"]:
```

- [ ] **Step 3: 验证 dispatch 接线（本地可验证）**

`huggingface.co` 本地不可达，所以 fetch 会失败，但**不该报 `Unknown collector`**——这证明 dispatch 接线正确。

Run:
```bash
PAPILIO_NAS_URL=http://localhost:8000 python3 /Users/yangfei/Code/papilio/scripts/run_collector.py huggingface 2>&1 | head -5
```
Expected: 看到 `[HuggingFaceCollector] Fetching...`，随后是 `[HuggingFace] trending fetch failed: ...` / `[HuggingFace] likes fallback failed: ...`（网络错误），**但绝不能出现 `Unknown collector: huggingface`**。

Run（确认 `all` 接线）:
```bash
python3 -c "
import sys, os
ROOT='/Users/yangfei/Code/papilio'
sys.path.insert(0, os.path.join(ROOT, 'collectors'))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import run_collector
# 不真的 run，只确认 run() 认得所有名字（靠源码检查）
import inspect, re
src = inspect.getsource(run_collector.run)
names = re.findall(r'name == \"([a-z]+)\"', src)
print('dispatch names:', names)
all_list = re.search(r'for n in \[([^\]]+)\]', src).group(1)
print('all list:', [n.strip().strip('\"') for n in all_list.split(',')])
assert 'huggingface' in names, 'huggingface not in dispatch'
assert 'huggingface' in all_list, 'huggingface not in all list'
print('dispatch wiring OK')
"
```
Expected: 末行 `dispatch wiring OK`，`dispatch names` 和 `all list` 都含 `huggingface`。

- [ ] **Step 4: Commit**

```bash
git -C /Users/yangfei/Code/papilio add scripts/run_collector.py
git -C /Users/yangfei/Code/papilio commit -m "🦋 HF collector: run_collector 接线 huggingface 分支与 all"
```

---

### Task 3: Web UI sidebar tab（`nas/web/index.html`）

**Files:**
- Modify: `nas/web/index.html:74`（GitHub 和 RSS 之间插入一行）

- [ ] **Step 1: 在 sidebar nav 插入 HuggingFace tab**

把 `nas/web/index.html` 的这段（原第 71–75 行附近）：
```html
    <a href="/?source=hackernews" hx-get="/ui/items?source=hackernews&per_page=50" hx-target="#feed" hx-swap="innerHTML" hx-push-url="true">Hacker News</a>
    <a href="/?source=arxiv" hx-get="/ui/items?source=arxiv&per_page=50" hx-target="#feed" hx-swap="innerHTML" hx-push-url="true">arXiv</a>
    <a href="/?source=github" hx-get="/ui/items?source=github&per_page=50" hx-target="#feed" hx-swap="innerHTML" hx-push-url="true">GitHub</a>
    <a href="/?source=rss" hx-get="/ui/items?source=rss&per_page=50" hx-target="#feed" hx-swap="innerHTML" hx-push_url="true">RSS</a>
```
改为（在 GitHub 后、RSS 前插入 HuggingFace 行）：
```html
    <a href="/?source=hackernews" hx-get="/ui/items?source=hackernews&per_page=50" hx-target="#feed" hx-swap="innerHTML" hx-push-url="true">Hacker News</a>
    <a href="/?source=arxiv" hx-get="/ui/items?source=arxiv&per_page=50" hx-target="#feed" hx-swap="innerHTML" hx-push-url="true">arXiv</a>
    <a href="/?source=github" hx-get="/ui/items?source=github&per_page=50" hx-target="#feed" hx-swap="innerHTML" hx-push-url="true">GitHub</a>
    <a href="/?source=huggingface" hx-get="/ui/items?source=huggingface&per_page=50" hx-target="#feed" hx-swap="innerHTML" hx-push-url="true">HuggingFace</a>
    <a href="/?source=rss" hx-get="/ui/items?source=rss&per_page=50" hx-target="#feed" hx-swap="innerHTML" hx-push-url="true">RSS</a>
```
（注意：保留所有原行的 `hx-push-url` 不变，只新增一行。）

- [ ] **Step 2: 验证 UI tab 已渲染（本地可验证）**

NAS 在跑，静态文件即时刷新。

Run:
```bash
curl -s http://localhost:8000/ | grep -c "HuggingFace"
curl -s http://localhost:8000/ | grep -o 'source=huggingface[^"]*' | head -1
```
Expected: 第一条 `grep -c` 输出 `1`（恰好一个 HuggingFace tab）；第二条输出形如 `source=huggingface&per_page=50`。

- [ ] **Step 3: 浏览器确认（人工）**

打开 `http://localhost:8000`，侧边栏应出现 `HuggingFace`（位于 GitHub 与 RSS 之间）。点击它，feed 区域切换（当前会显示空态「🦋 还没有内容」，因为本地拉不到 HF 数据——这是预期的，待 Task 5 网络恢复后会有数据）。

- [ ] **Step 4: Commit**

```bash
git -C /Users/yangfei/Code/papilio add nas/web/index.html
git -C /Users/yangfei/Code/papilio commit -m "🦋 HF collector: Web UI sidebar 加 HuggingFace tab"
```

---

### Task 4: PLAN.md cron 表更新

**Files:**
- Modify: `PLAN.md`（§4.3 Cronjob 配置表）

- [ ] **Step 1: 在 cron 表加一行**

在 `PLAN.md` 的 `### 4.3 Cronjob 配置` 表格里，`collect-github` 行之后插入一行。把：

```markdown
| collect-github | 每天 10:00 | GitHub Trending |
| process-items | 每 30 分钟 | AI 处理新条目 |
```
改为：

```markdown
| collect-github | 每天 10:00 | GitHub Trending |
| collect-huggingface | 每天 10:00 | HF trending models |
| process-items | 每 30 分钟 | AI 处理新条目 |
```

- [ ] **Step 2: 验证表格渲染**

Run:
```bash
grep -n "collect-huggingface" /Users/yangfei/Code/papilio/PLAN.md
```
Expected: 命中一行，位于 §4.3 表格内（行号在 `collect-github` 之后）。

- [ ] **Step 3: Commit**

```bash
git -C /Users/yangfei/Code/papilio add PLAN.md
git -C /Users/yangfei/Code/papilio commit -m "🦋 HF collector: PLAN §4.3 cron 表加 collect-huggingface"
```

---

### Task 5: 端到端验证（⚠️ 依赖网络恢复或 Mac mini）

**Files:** 无（纯验证）

> 本 task 在当前调试网络**无法完成**（`huggingface.co` 不可达）。代码落地（Task 1–4）不依赖本 task。等到下列任一条件满足时执行：
> - 本地网络恢复对 `huggingface.co` 的访问；或
> - 部署到 Mac mini（生产机，网络独立）。

- [ ] **Step 1: 前置——确认 HF 可达**

Run:
```bash
curl -s -m 10 -o /dev/null -w "huggingface.co: HTTP %{http_code}\n" 'https://huggingface.co/api/models?limit=1'
```
Expected: `huggingface.co: HTTP 200`。若仍是 `000`，本 task 暂停，代码已就绪待命。

- [ ] **Step 2: 跑 collector 入库**

Run:
```bash
PAPILIO_NAS_URL=http://localhost:8000 python3 /Users/yangfei/Code/papilio/scripts/run_collector.py huggingface 2>&1 | tail -3
```
Expected: `[HuggingFaceCollector] Done: {'created': N, 'updated': 0, ...}`，N>0（若 trending 端点返回空，fallback 会拉 liked 模型，仍应有数据）。

- [ ] **Step 3: 入库字段校验**

Run:
```bash
curl -s 'http://localhost:8000/api/items?source=huggingface&per_page=3' | python3 -c "
import sys, json
items = json.load(sys.stdin)['items']
assert items, 'no hf items'
for i in items:
    assert i['source']=='huggingface'
    assert i['url'].startswith('https://huggingface.co/'), i['url']
    assert i['published_at'].endswith('+00:00'), i['published_at']
    print(f\"  {i['title'][:50]} | downloads={i.get('meta',{}).get('downloads')} | {i['published_at']}\")
print('field check OK, count=', len(items))
"
```
Expected: 末行 `field check OK, count= 3`（或更多），每个 item 的 source/url/published_at 都符合断言。

- [ ] **Step 4: 浏览器确认有数据**

打开 `http://localhost:8000`，点 sidebar 的 `HuggingFace`，feed 应显示 trending models（不再是空态）。点 `全部`，HF 条目和其他源混排。

- [ ] **Step 5: HF collector 收尾**

Task 1–5 全部完成。可 push（若 Task 1–4 已 push，本 task 无代码改动，无需再 push）。

---

## Self-Review（计划作者自检）

- **Spec coverage**：spec 各节 → Task 1（collector 实现 + item 映射 + fallback）/ Task 2（run_collector dispatch + all）/ Task 3（UI sidebar tab）/ Task 4（PLAN cron 表）/ Task 5（验证策略的 4 项：单跑/入库校验/UI 可见/all 调度）。spec 提到的"不动 templates.py / config.yaml / NAS 后端"在 File Structure 注释里明确。✓
- **Placeholder scan**：无 TBD/TODO；每步含完整代码或确切命令 + 预期。Task 5 诚实标注网络依赖，不假装可本地完成。✓
- **Type/naming consistency**：`HuggingFaceCollector` / `HF_API` / `LIMIT` / `_get_trending()` 前后一致；`source="huggingface"` 在 collector、UI tab、dispatch、验证脚本里全部统一拼写。dispatch 分支结构与现有 `github` 分支一致（`from X import Y; Y(NAS_URL).run()`）。✓
- **YAGNI**：未引入 config.yaml 配置、未引入 huggingface_hub 库、未加 auth token、未做多类内容——均与 spec 非目标一致。✓
