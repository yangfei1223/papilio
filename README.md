# 🦋 Butterfly — 破茧成蝶

个人信息聚合站。部署于 NAS，由 Hermes Agent 驱动。打破信息茧房，主动定义你看到的世界。

## 架构

```
Mac mini (大脑)          NAS (仓库)
├── collectors/          ├── FastAPI + SQLite
├── scripts/             └── Web UI (HTMX)
└── Hermes cronjob
```

## 快速开始

### NAS 端

```bash
cd nas
docker compose up -d
```

访问 `http://nas:8899`

### Mac mini 端

```bash
cd collectors
pip install -r requirements.txt

# 手动运行 collector
python hackernews.py

# 或通过调度脚本
cd ..
python scripts/run_collector.py hackernews
python scripts/run_collector.py all
```

### Hermes cronjob

配置 4 个定时 collector + 1 个 AI processor。

详见 `PLAN.md`。
