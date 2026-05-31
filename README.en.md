# Zhejiang Policy Radar / zj-policy-watch

[中文](README.md) | English

`zj-policy-watch` is a lightweight automation tool for tracking industrial policy updates in Zhejiang, China. It monitors Zhejiang Province, Hangzhou, Shaoxing, Jinhua, Taizhou, Wenzhou, and key Hangzhou districts, then generates a reviewable local report.

The repository includes:

- A runnable Python script for fetching, deduplicating, classifying, and reporting policy leads.
- A Codex/OpenClaw-style Skill that tells an agent when and how to use the workflow.

The output keeps title, URL, publish date, region, department, source type, matched query, and confidence. Official government sources are preferred; portals and media are treated as leads for later verification.

## Use Cases

- Run daily or weekly checks on Zhejiang technology, industry, and commerce policies.
- Track applications, subsidies, public lists, implementation rules, and related notices.
- Prepare policy leads for investment promotion, industry services, client operations, and government affairs.
- Sync new items to Feishu Docs or Feishu Bitable for team follow-up.

## Repository Layout

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

## Quick Start

The project only uses the Python standard library. Python 3.10 or newer is recommended.

```bash
python3 scripts/policy_watch_zj.py \
  --config config/zj_policy_sources.json \
  --output-dir output/policy_watch \
  --state-file output/policy_watch/state_seen.json \
  --days 7 \
  --max-queries 40
```

Each run creates a timestamped output directory with `report.md`, `items_all.json`, `items_new.json`, and `run_summary.json`. `state_seen.json` records previously seen leads so the next run can keep only new items.

## Feishu Export

Create a Feishu document:

```bash
export FEISHU_APP_ID="cli_xxx"
export FEISHU_APP_SECRET="xxx"

python3 scripts/policy_watch_zj.py \
  --config config/zj_policy_sources.json \
  --feishu-doc \
  --feishu-doc-title "Zhejiang Policy Radar"
```

Write new items into Feishu Bitable:

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

## Skill Packaging And Installation

Build the distributable Skill zip:

```bash
python3 scripts/validate_skill_package.py --zip
```

Generated file:

```text
skill/zj-policy-watch/zj-policy-watch.zip
```

Install it into a local Skill directory:

```bash
mkdir -p ~/.codex/skills
unzip -o skill/zj-policy-watch/zj-policy-watch.zip -d ~/.codex/skills/
```

## Result Policy

The script filters by title, summary, URL, and source domain. It does not invent missing dates; portal and media results are labeled by source type; duplicate leads prefer government-site versions.

Policy monitoring can be affected by search-index delays, website changes, withdrawn notices, and missing dates. Use this project for routine monitoring and lead collection; always verify formal applications against the original authority notice.

## License

MIT
