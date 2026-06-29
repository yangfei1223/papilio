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
