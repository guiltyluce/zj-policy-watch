---
name: zj-policy-watch
description: 浙江政策雷达：定时监测浙江省、杭州、绍兴、金华、台州、温州及杭州重点区县的经信、科技、商务等政策更新，生成新增清单，并可写入飞书文档和多维表格。
---

# 浙江政策雷达

用于日常跟踪浙江省内产业政策更新，重点覆盖：

- 部门：经信、科技、商务（可包含发改/政府通知）
- 地域：浙江省、杭州、绍兴、金华、台州、温州
- 杭州下钻：上城、拱墅、西湖、滨江、萧山、余杭、临平、钱塘、富阳、临安、桐庐、淳安、建德

脚本优先保留政府站点结果。企知道、媒体和门户结果可以作为补充线索，输出时会标注来源类型，便于后续核验。

# 触发场景

用户出现以下意图时使用：

- 用户要“定时跟踪/每日巡检/周报”政策变化。
- 用户要“浙江/杭州/绍兴/金华/台州/温州”的科技产业政策更新。
- 用户要“经信/科技/商务”部门政策通知、申报、公示。
- 用户要求结果同步到飞书文档或飞书多维表。

# 执行流程

1. 在仓库根目录运行监测脚本：

```bash
python3 scripts/policy_watch_zj.py \
  --config config/zj_policy_sources.json \
  --output-dir output/policy_watch \
  --state-file output/policy_watch/state_seen.json \
  --days 7
```

2. 需要生成飞书文档时增加 `--feishu-doc`：

```bash
python3 scripts/policy_watch_zj.py \
  --config config/zj_policy_sources.json \
  --output-dir output/policy_watch \
  --state-file output/policy_watch/state_seen.json \
  --days 7 \
  --feishu-doc
```

3. 需要写入飞书多维表时增加 `--feishu-bitable` 并配置字段映射：

```bash
python3 scripts/policy_watch_zj.py \
  --config config/zj_policy_sources.json \
  --output-dir output/policy_watch \
  --state-file output/policy_watch/state_seen.json \
  --days 7 \
  --feishu-bitable \
  --bitable-app-token "$FEISHU_BITABLE_APP_TOKEN" \
  --bitable-table-id "$FEISHU_BITABLE_TABLE_ID" \
  --bitable-field-map config/feishu_bitable_field_map.example.json
```

# 输出文件

- 本次目录：`output/policy_watch/{YYYYMMDD-HHMMSS}/`
- `report.md`：新增政策摘要
- `items_all.json`：本次命中全量
- `items_new.json`：本次新增（基于 `state_seen.json` 去重）
- `run_summary.json`：本次统计与飞书回写结果

# 环境变量

飞书文档或飞书多维表写入至少需要以下之一：

- `FEISHU_TENANT_ACCESS_TOKEN`
- `FEISHU_APP_ID` + `FEISHU_APP_SECRET`

多维表额外需要：

- `FEISHU_BITABLE_APP_TOKEN`
- `FEISHU_BITABLE_TABLE_ID`

# 注意事项

- 对“平台/媒体来源”结论做线索标注，不直接等价为政策原文。
- 同一条线索多来源命中时优先保留官方站点版本。
- 输出中不编造发布日期；缺失时标注为空，建议二次核验。
