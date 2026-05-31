# 浙江政策雷达 / zj-policy-watch

`zj-policy-watch` 是一个面向浙江省产业政策跟踪的小型自动化工具。它会围绕浙江省、杭州、绍兴、金华、台州、温州，以及杭州重点区县，检索经信、科技、商务等部门的政策线索，生成一份可复查的本地报告。

项目包含两部分：

- 一个可直接运行的 Python 脚本，用来抓取、去重、分类并生成报告。
- 一个 Codex/OpenClaw 风格的 Skill，让智能体知道什么时候该调用这套流程。

输出会保留标题、链接、发布日期、地区、部门、来源类型、命中查询和置信度。官方政府站点会被优先保留，平台和媒体来源只作为线索，重要政策仍建议回到原文核验。

## 适合场景

- 每天或每周巡检浙江省内科技、经信、商务政策。
- 跟踪项目申报、补贴、名单公示、实施细则等更新。
- 为招商、产业服务、客户经营、政府事务准备政策线索。
- 将新增政策同步到飞书文档或飞书多维表，方便团队继续处理。

## 目录

```text
.
├── README.md
├── LICENSE
├── config/
│   ├── zj_policy_sources.json
│   └── feishu_bitable_field_map.example.json
├── scripts/
│   ├── policy_watch_zj.py
│   └── validate_skill_package.py
└── skill/
    └── zj-policy-watch/
        ├── SKILL.md
        └── zj-policy-watch.zip
```

## 快速运行

项目只依赖 Python 标准库，建议使用 Python 3.10 或更高版本。

```bash
python3 scripts/policy_watch_zj.py \
  --config config/zj_policy_sources.json \
  --output-dir output/policy_watch \
  --state-file output/policy_watch/state_seen.json \
  --days 7 \
  --max-queries 40
```

运行完成后会生成一个时间戳目录：

```text
output/policy_watch/YYYYMMDD-HHMMSS/
├── report.md
├── items_all.json
├── items_new.json
└── run_summary.json
```

`state_seen.json` 会记录已见过的政策线索。下一次运行时，`items_new.json` 只保留新增项。

## 常用参数

```bash
# 打印每条查询的执行状态
python3 scripts/policy_watch_zj.py --verbose

# 扩大最近窗口
python3 scripts/policy_watch_zj.py --days 30

# 限制查询数量，适合本地调试
python3 scripts/policy_watch_zj.py --max-queries 5 --max-per-query 5

# 保留非官方、非门户来源
python3 scripts/policy_watch_zj.py --allow-other-sources

# 忽略历史去重，把本次命中的结果都写入新增列表
python3 scripts/policy_watch_zj.py --include-seen
```

## 飞书写入

创建飞书文档：

```bash
export FEISHU_APP_ID="cli_xxx"
export FEISHU_APP_SECRET="xxx"

python3 scripts/policy_watch_zj.py \
  --config config/zj_policy_sources.json \
  --feishu-doc \
  --feishu-doc-title "浙江政策雷达"
```

写入飞书多维表：

```bash
export FEISHU_APP_ID="cli_xxx"
export FEISHU_APP_SECRET="xxx"
export FEISHU_BITABLE_APP_TOKEN="bascn..."
export FEISHU_BITABLE_TABLE_ID="tbl..."

python3 scripts/policy_watch_zj.py \
  --config config/zj_policy_sources.json \
  --feishu-bitable \
  --bitable-field-map config/feishu_bitable_field_map.example.json
```

也可以直接提供 `FEISHU_TENANT_ACCESS_TOKEN`。多维表字段名可以在 `config/feishu_bitable_field_map.example.json` 中调整。

## Skill 打包与安装

生成可上传的 Skill zip：

```bash
python3 scripts/validate_skill_package.py --zip
```

生成文件：

```text
skill/zj-policy-watch/zj-policy-watch.zip
```

如果你的运行时支持本地 Skill 目录，可以复制 `skill/zj-policy-watch`：

```bash
mkdir -p ~/.codex/skills
unzip -o skill/zj-policy-watch/zj-policy-watch.zip -d ~/.codex/skills/
```

安装后，智能体在遇到“浙江政策监测”“杭州科技政策申报”“经信政策周报”“写入飞书多维表”等需求时，可以按 `SKILL.md` 中的流程调用脚本。

## 配置范围

默认配置覆盖：

- 地域：浙江省、杭州、绍兴、金华、台州、温州。
- 杭州区县：上城、拱墅、西湖、滨江、萧山、余杭、临平、钱塘、富阳、临安、桐庐、淳安、建德。
- 部门：经信、科技、商务、发改、人民政府。
- 关键词：政策、通知、公告、申报、公示、实施办法、资金、补助、项目等。

可以直接编辑 `config/zj_policy_sources.json` 增减地区、部门、关键词和补充查询。

## 结果口径

脚本会根据标题、摘要、链接和来源域名做初筛。发布日期缺失时不会编造日期；平台和媒体结果会标注来源类型；同一线索多处命中时优先保留政府站点版本。

政策监测很容易遇到搜索引擎延迟、站点改版、公告撤回、日期缺失等情况。这个项目适合作为日常巡检和线索收集工具，正式申报前请以主管部门原文为准。

## License

MIT
