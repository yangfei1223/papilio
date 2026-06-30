#!/usr/bin/env python3
"""Papilio Processor — 批量富化 status=new 条目（摘要/判断/概念/wiki候选/聚类视角差异）.

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

PROMPT_TEMPLATE = """你是信息聚合站 Papilio 的富化 agent。对下面每一条条目生成完整的富化信息。

## 输出格式

返回 JSON 对象（严格只返回 JSON，不要任何解释文字），包含 items 和可选的 clusters：

### items[] — 每条条目的富化数据
[
  {{
    "id": str,              // 条目 ID，原样返回
    "summary": str,         // 客观摘要，1-2 句
    "judgment": str,        // Hermes 判断：为什么值得注意、长期影响
    "importance": int,      // 1-5，5 最重要
    "category": str,        // 小写连字符层级，如 ai/llm, dev/rust, market/crypto
    "concepts": [str],      // 抽象概念标签，可跨 item 关联
    "tags": [str],          // 具体 topical 标签
    "duplicate_of": str | null,  // 同一事件的 primary item id
    "wiki_candidate": {{    // 建议 wiki entity
      "slug": str,          // kebab-case 文件名
      "concepts": [str]     // 该 entity 关联的 concepts
    }}
  }}
]

### clusters[] — 可选，仅当有跨源重复时
[
  {{
    "primary_id": str,      // cluster 的 primary item id（与 duplicate_of 一致）
    "source_divergence": {{  // 每源独特视角，只含实际存在的源
      "HN": str,
      "arXiv": str,
      "GitHub": str,
      "RSS": str
    }}
  }}
]

## 字段语义区分
- summary: 客观描述，如 "OpenAI 发布了 o3 模型，性能提升 30%"
- judgment: 主观判断，如 "推理成本将下降，长期影响 Agent 部署经济性"
- concepts: 抽象概念（跨 item 关联），如 ["Reasoning", "Inference Cost"]
- tags: 具体标签，如 ["openai", "o3", "benchmark"]
- category: 主分类，如 "ai/llm"
- wiki_candidate.slug: 建议 wiki entity 文件名，如 "openai-o3-reasoning-model"
- source_divergence: 不同源对同一事件的视角差异

## 规则
- 严格只返回 JSON，不要任何解释文字
- 信息不足以生成 judgment/concepts 时用空字符串或空数组
- source_divergence 只包含 cluster 内实际存在的源，不编造
- 单源 cluster 不输出 source_divergence

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


def _strip_code_fence(text: str) -> str:
    """若 text 被 markdown code fence 包裹（```json ... ```），去掉围栏。
    LLM 常无视"只返回 JSON"指令仍加 fence，这里兜底。"""
    s = text.strip()
    if s.startswith("```"):
        nl = s.find("\n")
        if nl != -1:
            s = s[nl + 1:]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    return s.strip()


def parse_llm_response(text: str, expected_ids: set) -> dict:
    """解析 agent 返回的 JSON，返回 {items: [...], clusters: [...]}.

    支持旧格式（JSON 数组）和新格式（JSON 对象含 items/clusters 键）。
    丢弃 id 不在 expected_ids 里的条目。不存在的字段/空字符串安全兜底。
    """
    text = _strip_code_fence(text)
    data = json.loads(text)

    if isinstance(data, list):
        items_data = data
        clusters_data = []
    elif isinstance(data, dict):
        items_data = data.get("items", [])
        clusters_data = data.get("clusters", [])
    else:
        raise ValueError(f"agent 返回类型异常: {type(data).__name__}")

    items = []
    for entry in items_data:
        eid = entry.get("id")
        if eid not in expected_ids:
            continue

        wc = entry.get("wiki_candidate") or {}

        items.append({
            "id": eid,
            "summary": str(entry.get("summary", ""))[:400],
            "judgment": str(entry.get("judgment", "")),
            "category": (str(entry.get("category", "")).strip().lower() or None),
            "importance": _clamp(entry.get("importance"), 1, 5),
            "tags": entry.get("tags", []),
            "concepts": entry.get("concepts", []),
            "duplicate_of": entry.get("duplicate_of"),
            "wiki_candidate_slug": (
                str(wc.get("slug", "")).strip() or None
            ) if isinstance(wc, dict) else None,
        })

    clusters = []
    for ce in (clusters_data or []):
        pid = ce.get("primary_id")
        sd = ce.get("source_divergence")
        if pid and sd and isinstance(sd, dict) and sd:
            clusters.append({"primary_id": pid, "source_divergence": sd})

    return {"items": items, "clusters": clusters}


def get_new_items() -> list[dict]:
    resp = requests.get(f"{NAS_URL}/api/items",
                        params={"status": "new", "per_page": LIMIT}, timeout=15)
    resp.raise_for_status()
    return resp.json().get("items", [])


def patch_item(item_id: str, fields: dict) -> None:
    requests.patch(f"{NAS_URL}/api/items/{item_id}", json=fields, timeout=10).raise_for_status()


def record_clusters(enriched: list[dict]) -> dict:
    """对 duplicate_of 聚类，POST 到 NAS /api/clusters.

    返回 {primary_id: (cluster_hash, [member_ids])} 映射，供后续 source_divergence 匹配用。
    """
    groups: dict = {}
    for e in enriched:
        dup = e.get("duplicate_of")
        if dup:
            groups.setdefault(dup, [dup]).append(e["id"])

    result = {}
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
            result[primary] = (cluster_hash, unique)
        except requests.RequestException as ex:
            print(f"[processor] cluster 写入失败 {cluster_hash}: {ex}")
    return result


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
        parsed = parse_llm_response(raw, expected_ids={i["id"] for i in items})
        enriched = parsed["items"]
        cluster_divergences = parsed["clusters"]
    except Exception as e:
        # 解析成功前失败：整批保持 new，下次重跑重试。
        print(f"[processor] agent 调用/解析失败，整批保持 new：{e}", file=sys.stderr)
        sys.exit(1)

    print(f"[processor] 解析得到 {len(enriched)} 条富化结果，开始 PATCH...")

    # LLM output key → DB column name mapping
    FIELD_MAP = {
        "summary": "summary",
        "judgment": "hermes_judgment",
        "importance": "importance",
        "category": "category",
        "tags": "tags",
        "concepts": "concepts",
        "wiki_candidate_slug": "wiki_candidate_slug",
    }

    patched = 0
    for e in enriched:
        fields = {"status": "processed"}
        for llm_key, db_col in FIELD_MAP.items():
            val = e.get(llm_key)
            if val is None:
                continue
            if isinstance(val, list):
                # JSON-serialize list fields for TEXT storage in SQLite
                fields[db_col] = json.dumps(val, ensure_ascii=False)
            elif val != "":
                fields[db_col] = val
            # Empty string → skip (leave DB field as NULL)

        try:
            patch_item(e["id"], fields)
            patched += 1
        except requests.RequestException as ex:
            # best-effort：漏的条目 status 仍 new，下次重拾。
            print(f"[processor] PATCH {e['id']} 失败（best-effort 跳过）：{ex}")

    # Create clusters from duplicate_of
    cluster_map = record_clusters(enriched)

    # PATCH source_divergence for clusters
    for cd in cluster_divergences:
        pid = cd["primary_id"]
        divergence = cd["source_divergence"]
        if pid not in cluster_map:
            print(f"[processor] cluster divergence primary_id={pid} 未匹配到 cluster，跳过")
            continue
        _, member_ids = cluster_map[pid]
        div_json = json.dumps(divergence, ensure_ascii=False)
        for mid in member_ids:
            try:
                patch_item(mid, {"source_divergence": div_json})
            except requests.RequestException as ex:
                print(f"[processor] source_divergence PATCH {mid} 失败：{ex}")

    print(f"[processor] Processed {patched}/{len(enriched)} items, "
          f"{len(cluster_map)} clusters, {len(cluster_divergences)} divergences")


if __name__ == "__main__":
    main()
