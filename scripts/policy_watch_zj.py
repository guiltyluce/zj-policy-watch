#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import html
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

DUCKDUCKGO_HTML_TEMPLATE = "https://duckduckgo.com/html/?q={query}"
BING_RSS_TEMPLATE = "https://www.bing.com/search?format=rss&mkt=zh-CN&setlang=zh-hans&q={query}"
FEISHU_API_BASE = "https://open.feishu.cn/open-apis"

DEFAULT_STATE_MAX = 8000
DEFAULT_BATCH_SIZE = 100


@dataclass
class PolicyItem:
    item_id: str
    title: str
    link: str
    publish_date: str
    source_name: str
    source_domain: str
    source_type: str
    region: str
    department: str
    query: str
    summary: str
    confidence: float


def http_json(
    method: str,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    body = None
    effective_headers = headers.copy()
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        effective_headers["Content-Type"] = "application/json; charset=utf-8"

    req = urllib.request.Request(url=url, data=body, headers=effective_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {url}\\n{detail}") from exc


def get_tenant_access_token() -> str:
    direct = os.getenv("FEISHU_TENANT_ACCESS_TOKEN")
    if direct:
        return direct

    app_id = os.getenv("FEISHU_APP_ID") or os.getenv("LARK_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET") or os.getenv("LARK_APP_SECRET")
    if not app_id or not app_secret:
        raise RuntimeError(
            "Missing Feishu credentials. Set FEISHU_TENANT_ACCESS_TOKEN, or FEISHU_APP_ID + FEISHU_APP_SECRET."
        )

    res = http_json(
        "POST",
        f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal",
        headers={},
        payload={"app_id": app_id, "app_secret": app_secret},
    )
    if res.get("code") != 0:
        raise RuntimeError(f"Failed to get tenant token: {res}")
    token = res.get("tenant_access_token")
    if not token:
        raise RuntimeError(f"Missing tenant_access_token in response: {res}")
    return token


def create_feishu_doc(token: str, title: str) -> str:
    res = http_json(
        "POST",
        f"{FEISHU_API_BASE}/docx/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        payload={"title": title},
    )
    if res.get("code") != 0:
        raise RuntimeError(f"Failed to create Feishu doc: {res}")
    return res["data"]["document"]["document_id"]


def markdown_to_doc_lines(markdown_text: str) -> list[str]:
    lines: list[str] = []
    for raw in markdown_text.splitlines():
        line = raw.rstrip()
        if not line:
            lines.append(" ")
        elif line.startswith("### "):
            lines.append(f"[H3] {line[4:]}")
        elif line.startswith("## "):
            lines.append(f"[H2] {line[3:]}")
        elif line.startswith("# "):
            lines.append(f"[H1] {line[2:]}")
        elif line.startswith("- "):
            lines.append(f"* {line[2:]}")
        else:
            lines.append(line)
    return lines


def append_doc_blocks(token: str, document_id: str, lines: list[str]) -> None:
    step = 40
    for idx in range(0, len(lines), step):
        chunk = lines[idx : idx + step]
        children = []
        for line in chunk:
            text = line[:1200]
            block: dict[str, Any]
            if text.startswith("[H1] "):
                block = {
                    "block_type": 3,
                    "heading1": {
                        "elements": [{"text_run": {"content": text[5:]}}],
                    },
                }
            elif text.startswith("[H2] "):
                block = {
                    "block_type": 4,
                    "heading2": {
                        "elements": [{"text_run": {"content": text[5:]}}],
                    },
                }
            elif text.startswith("[H3] "):
                block = {
                    "block_type": 5,
                    "heading3": {
                        "elements": [{"text_run": {"content": text[5:]}}],
                    },
                }
            elif text.startswith("* "):
                block = {
                    "block_type": 12,
                    "bullet": {
                        "elements": [{"text_run": {"content": text[2:]}}],
                    },
                }
            else:
                block = {
                    "block_type": 2,
                    "text": {
                        "elements": [{"text_run": {"content": text}}],
                    },
                }
            children.append(block)

        res = http_json(
            "POST",
            f"{FEISHU_API_BASE}/docx/v1/documents/{document_id}/blocks/{document_id}/children",
            headers={"Authorization": f"Bearer {token}"},
            payload={"children": children},
        )
        if res.get("code") != 0:
            raise RuntimeError(f"Failed to append document blocks at offset {idx}: {res}")


def write_items_to_bitable(
    token: str,
    app_token: str,
    table_id: str,
    items: list[PolicyItem],
    field_map: dict[str, str],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    endpoint = f"{FEISHU_API_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create"
    headers = {"Authorization": f"Bearer {token}"}

    created = 0
    captured_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for i in range(0, len(items), batch_size):
        batch = items[i : i + batch_size]
        payload_records = []
        for item in batch:
            fields = {
                field_map["title"]: item.title,
                field_map["link"]: item.link,
                field_map["publish_date"]: item.publish_date,
                field_map["region"]: item.region,
                field_map["department"]: item.department,
                field_map["source_name"]: item.source_name,
                field_map["source_type"]: item.source_type,
                field_map["query"]: item.query,
                field_map["captured_at"]: captured_at,
            }
            payload_records.append({"fields": fields})

        res = http_json("POST", endpoint, headers=headers, payload={"records": payload_records})
        if res.get("code") != 0:
            raise RuntimeError(f"Failed writing to Feishu bitable: {res}")

        created += len(payload_records)

    return created


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_domain(url: str) -> str:
    try:
        netloc = urllib.parse.urlparse(url).netloc.strip().lower()
    except Exception:
        return ""
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def canonicalize_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url

    query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    kept: list[tuple[str, str]] = []
    for key, value in query_pairs:
        key_lower = key.lower()
        if key_lower.startswith("utm_") or key_lower in {"spm", "from", "source", "ref"}:
            continue
        kept.append((key, value))

    new_query = urllib.parse.urlencode(kept)
    rebuilt = urllib.parse.urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            "",
        )
    )
    return rebuilt


def parse_pub_date(raw: str) -> tuple[str, dt.datetime | None]:
    if not raw:
        return "", None

    raw = raw.strip()
    try:
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        local_dt = parsed.astimezone()
        return local_dt.strftime("%Y-%m-%d"), local_dt
    except Exception:
        pass

    m = re.search(r"(20\\d{2})[-/年](\\d{1,2})[-/月](\\d{1,2})", raw)
    if m:
        y, mon, day = m.groups()
        try:
            parsed = dt.datetime(int(y), int(mon), int(day))
            return parsed.strftime("%Y-%m-%d"), parsed
        except Exception:
            return "", None

    return "", None


def parse_pub_date_from_url(url: str) -> tuple[str, dt.datetime | None]:
    m = re.search(r"/(20\d{2})/(\d{1,2})/(\d{1,2})/", url)
    if not m:
        m = re.search(r"(20\d{2})(\d{2})(\d{2})", url)
    if not m:
        return "", None

    y, mon, day = m.groups()
    try:
        parsed = dt.datetime(int(y), int(mon), int(day))
    except Exception:
        return "", None
    return parsed.strftime("%Y-%m-%d"), parsed


def strip_html_tags(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", "", text)
    return html.unescape(cleaned).strip()


def decode_duckduckgo_redirect(raw_link: str) -> str:
    link = html.unescape(raw_link.strip())
    if link.startswith("//"):
        link = "https:" + link
    elif link.startswith("/"):
        link = urllib.parse.urljoin("https://duckduckgo.com", link)

    parsed = urllib.parse.urlparse(link)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        params = urllib.parse.parse_qs(parsed.query)
        uddg = params.get("uddg")
        if uddg and uddg[0]:
            return urllib.parse.unquote(uddg[0])
    return link


def fetch_duckduckgo_html(query: str, timeout: int = 20) -> list[dict[str, str]]:
    url = DUCKDUCKGO_HTML_TEMPLATE.format(query=urllib.parse.quote_plus(query))
    req = urllib.request.Request(url=url, headers={"User-Agent": "Mozilla/5.0"})

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        html_text = resp.read().decode("utf-8", errors="replace")

    title_pattern = re.compile(
        r'<a rel="nofollow" class="result__a" href="(?P<link>[^"]+)">(?P<title>.*?)</a>',
        re.S,
    )
    snippet_pattern = re.compile(r'<a class="result__snippet"[^>]*>(?P<snippet>.*?)</a>', re.S)

    title_matches = list(title_pattern.finditer(html_text))
    out: list[dict[str, str]] = []

    for idx, match in enumerate(title_matches):
        link = decode_duckduckgo_redirect(match.group("link"))
        title = strip_html_tags(match.group("title"))

        # Keep parsing local to this result chunk to avoid snippet misalignment.
        start = match.end()
        end = title_matches[idx + 1].start() if idx + 1 < len(title_matches) else len(html_text)
        chunk = html_text[start:end]
        snippet_match = snippet_pattern.search(chunk)
        snippet = strip_html_tags(snippet_match.group("snippet")) if snippet_match else ""

        if title and link:
            out.append({"title": title, "link": link, "description": snippet, "pubDate": ""})

    return out


def fetch_bing_rss(query: str, timeout: int = 20) -> list[dict[str, str]]:
    url = BING_RSS_TEMPLATE.format(query=urllib.parse.quote_plus(query))
    req = urllib.request.Request(url=url, headers={"User-Agent": "Mozilla/5.0"})

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        xml_text = resp.read().decode("utf-8", errors="replace")

    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    if channel is None:
        return []

    out: list[dict[str, str]] = []
    for node in channel.findall("item"):
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        desc = (node.findtext("description") or "").strip()
        pub = (node.findtext("pubDate") or "").strip()
        if not title or not link:
            continue
        out.append({"title": title, "link": link, "description": desc, "pubDate": pub})
    return out


def pick_first_match(candidates: list[str], text: str, fallback: str = "未识别") -> str:
    for name in sorted(candidates, key=len, reverse=True):
        if name and name in text:
            return name
    return fallback


def infer_department(text: str) -> str:
    rules: list[tuple[str, str]] = [
        (r"经信|经济和信息化|经信局|经信厅", "经信"),
        (r"科技|科学技术|科技局|科技厅", "科技"),
        (r"商务|商务局|商务厅", "商务"),
        (r"发改|发展改革|发改委", "发改"),
        (r"财政|财政局|财政厅", "财政"),
    ]
    for pattern, dept in rules:
        if re.search(pattern, text):
            return dept
    return "其他"


def is_recent(pub_dt: dt.datetime | None, days: int) -> bool:
    if pub_dt is None:
        return True
    now = dt.datetime.now(pub_dt.tzinfo) if pub_dt.tzinfo else dt.datetime.now()
    return pub_dt >= now - dt.timedelta(days=days)


def score_confidence(domain: str, source_type: str, text: str) -> float:
    score = 0.45
    if source_type == "official":
        score += 0.35
    if source_type == "portal":
        score += 0.15
    if any(k in text for k in ["通知", "公告", "政策", "实施", "申报"]):
        score += 0.1
    if domain.endswith("gov.cn"):
        score += 0.05
    return min(0.99, round(score, 2))


def classify_source(domain: str, portal_domains: list[str]) -> str:
    if domain.endswith("gov.cn"):
        return "official"
    if any(domain == d or domain.endswith(f".{d}") for d in portal_domains):
        return "portal"
    return "other"


def has_policy_signal(title: str, summary: str, link: str) -> bool:
    noise_words = [
        "信用信息公示系统",
        "投资项目在线审批监管平台",
        "政务服务网",
        "人民政府",
    ]
    decisive_words = ["通知", "公告", "申报", "政策", "办法", "细则", "印发", "征集", "名单", "指南", "发布"]
    if any(word in title for word in noise_words) and not any(word in title for word in decisive_words):
        return False

    strong_words = [
        "通知",
        "公告",
        "公示",
        "申报",
        "政策",
        "办法",
        "细则",
        "实施",
        "印发",
        "征集",
        "名单",
        "指南",
        "发布",
    ]
    if any(word in title for word in strong_words):
        return True

    link_signals = ["/art/", "/article", "/news", "/detail", "/zcwj", "index.html"]
    if any(word in summary for word in strong_words) and any(sig in link.lower() for sig in link_signals):
        return True

    # Allow policy list pages when title clearly indicates policy columns.
    if any(word in title for word in ["政策文件", "政策解读", "公告公示"]):
        return True

    return False


def build_queries(config: dict[str, Any], max_queries: int) -> list[str]:
    regions = list(config.get("regions", []))
    districts = list(config.get("hangzhou_districts", []))
    departments = list(config.get("departments", []))
    keywords = list(config.get("policy_keywords", []))
    extra_queries = list(config.get("extra_queries", []))

    all_regions = []
    for r in regions + districts:
        if r and r not in all_regions:
            all_regions.append(r)

    generated: list[str] = []
    for region in all_regions:
        for dept in departments:
            generated.append(f"{region} {dept} 政策 通知")
            generated.append(f"{region} {dept} 项目 申报")
            generated.append(f"site:gov.cn {region} {dept} 公示")
        for kw in keywords[:3]:
            generated.append(f"{region} 科技 {kw}")

    for q in extra_queries:
        generated.append(q)

    deduped: list[str] = []
    seen: set[str] = set()
    for q in generated:
        norm = re.sub(r"\\s+", " ", q).strip()
        if not norm or norm in seen:
            continue
        seen.add(norm)
        deduped.append(norm)
        if len(deduped) >= max_queries:
            break
    return deduped


def load_seen_keys(state_file: Path) -> list[str]:
    if not state_file.exists():
        return []
    try:
        data = read_json(state_file)
    except Exception:
        return []
    keys = data.get("seen_keys")
    if not isinstance(keys, list):
        return []
    return [str(k) for k in keys if isinstance(k, str)]


def save_seen_keys(state_file: Path, seen_keys: list[str]) -> None:
    payload = {
        "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "seen_keys": seen_keys,
    }
    write_json(state_file, payload)


def make_item_id(url_or_title: str) -> str:
    return hashlib.sha1(url_or_title.encode("utf-8")).hexdigest()


def default_config_candidates() -> list[Path]:
    here = Path(__file__).resolve()
    return [
        Path("policy_watch_kit/config/zj_policy_sources.json"),
        here.parent.parent / "config" / "zj_policy_sources.json",
        here.parent.parent / "references" / "config" / "zj_policy_sources.json",
        Path("references/config/zj_policy_sources.json"),
    ]


def resolve_config_path(cli_value: str | None) -> Path:
    if cli_value:
        return Path(cli_value)
    for candidate in default_config_candidates():
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "No config file found. Pass --config or place zj_policy_sources.json under policy_watch_kit/config or references/config."
    )


def generate_report(items_all: list[PolicyItem], items_new: list[PolicyItem], query_count: int, days: int) -> str:
    now_text = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    region_counter: dict[str, int] = {}
    dept_counter: dict[str, int] = {}
    source_counter: dict[str, int] = {}

    for item in items_new:
        region_counter[item.region] = region_counter.get(item.region, 0) + 1
        dept_counter[item.department] = dept_counter.get(item.department, 0) + 1
        source_counter[item.source_type] = source_counter.get(item.source_type, 0) + 1

    lines: list[str] = []
    lines.append("# Zhejiang Policy Watch Report")
    lines.append("")
    lines.append(f"- Run time: {now_text}")
    lines.append(f"- Query count: {query_count}")
    lines.append(f"- Window: last {days} days")
    lines.append(f"- Total matched items: {len(items_all)}")
    lines.append(f"- New items: {len(items_new)}")
    lines.append("")

    lines.append("## New Items By Region")
    if region_counter:
        for k, v in sorted(region_counter.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"- {k}: {v}")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## New Items By Department")
    if dept_counter:
        for k, v in sorted(dept_counter.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"- {k}: {v}")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## New Items By Source Type")
    if source_counter:
        for k, v in sorted(source_counter.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"- {k}: {v}")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## New Item List")
    if not items_new:
        lines.append("- none")
    else:
        for idx, item in enumerate(items_new, start=1):
            date_text = item.publish_date or "unknown"
            lines.append(
                f"{idx}. [{item.title}]({item.link}) | date={date_text} | region={item.region} | dept={item.department} | source={item.source_name} ({item.source_type})"
            )

    lines.append("")
    lines.append("## Notes")
    lines.append("- Prefer official government sites when duplicates exist.")
    lines.append("- Portal/news results are kept as clues and should be verified before use.")

    return "\n".join(lines) + "\n"


def load_field_map(path: Path | None) -> dict[str, str]:
    default_map = {
        "title": "标题",
        "link": "链接",
        "publish_date": "发布日期",
        "region": "地区",
        "department": "部门",
        "source_name": "来源",
        "source_type": "来源类型",
        "query": "命中查询",
        "captured_at": "抓取时间",
    }

    if path is None or not path.exists():
        return default_map

    data = read_json(path)
    merged = default_map.copy()
    for k, v in data.items():
        if k in merged and isinstance(v, str) and v.strip():
            merged[k] = v.strip()
    return merged


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Watch latest Zhejiang science/industry/business policies.")
    parser.add_argument("--config", default="", help="Path to source config JSON.")
    parser.add_argument("--output-dir", default="output/policy_watch", help="Output directory.")
    parser.add_argument("--state-file", default="output/policy_watch/state_seen.json", help="Seen item state JSON.")
    parser.add_argument("--days", type=int, default=7, help="Only keep items within recent N days when date is known.")
    parser.add_argument("--max-queries", type=int, default=120, help="Maximum number of generated search queries.")
    parser.add_argument(
        "--max-per-query",
        type=int,
        default=20,
        help="Maximum search items to keep per query.",
    )
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout seconds.")
    parser.add_argument("--include-seen", action="store_true", help="Include already seen items in new-item output.")
    parser.add_argument("--state-max", type=int, default=DEFAULT_STATE_MAX, help="Max seen keys kept in state file.")
    parser.add_argument(
        "--allow-other-sources",
        action="store_true",
        help="Keep non-official and non-portal domains.",
    )
    parser.add_argument("--feishu-doc", action="store_true", help="Create a Feishu doc from the report.")
    parser.add_argument("--feishu-doc-title", default="", help="Feishu doc title. Auto-generated when empty.")
    parser.add_argument("--feishu-bitable", action="store_true", help="Write new items to Feishu Bitable.")
    parser.add_argument("--bitable-app-token", default=os.getenv("FEISHU_BITABLE_APP_TOKEN", ""))
    parser.add_argument("--bitable-table-id", default=os.getenv("FEISHU_BITABLE_TABLE_ID", ""))
    parser.add_argument(
        "--bitable-field-map",
        default="",
        help="JSON file mapping logical fields to Bitable column names.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print per-query fetch status.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    config_path = resolve_config_path(args.config or None)
    config = read_json(config_path)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    state_file = Path(args.state_file)

    queries = build_queries(config=config, max_queries=args.max_queries)
    if not queries:
        raise RuntimeError("No queries generated from config.")

    region_candidates = list(config.get("regions", [])) + list(config.get("hangzhou_districts", []))
    policy_keywords = list(config.get("policy_keywords", []))
    portal_domains = list(config.get("portal_domains", []))

    seen_keys = set(load_seen_keys(state_file))

    merged: dict[str, PolicyItem] = {}

    for i, query in enumerate(queries, start=1):
        if args.verbose:
            print(f"[{i}/{len(queries)}] query={query}", file=sys.stderr)
        try:
            rss_items = fetch_duckduckgo_html(query=query, timeout=args.timeout)
            if not rss_items:
                # Fallback for environments where DuckDuckGo HTML endpoint is unavailable.
                rss_items = fetch_bing_rss(query=query, timeout=args.timeout)
        except Exception as exc:
            if args.verbose:
                print(f"  failed: {exc}", file=sys.stderr)
            continue

        for raw in rss_items[: args.max_per_query]:
            title = raw.get("title", "").strip()
            link = canonicalize_url(raw.get("link", "").strip())
            summary = raw.get("description", "").strip()
            pub_text = raw.get("pubDate", "")
            if not title or not link:
                continue

            domain = normalize_domain(link)
            if not domain:
                continue

            combined = f"{title} {summary}"
            if policy_keywords and not any(kw in combined for kw in policy_keywords):
                continue
            if not has_policy_signal(title=title, summary=summary, link=link):
                continue

            date_hint = pub_text if pub_text else combined
            pub_date, pub_dt = parse_pub_date(date_hint)
            if not pub_date:
                pub_date, pub_dt = parse_pub_date_from_url(link)
            if not is_recent(pub_dt, args.days):
                continue

            region = pick_first_match(region_candidates, combined)
            if region == "未识别":
                region = pick_first_match(region_candidates, query)
            department = infer_department(combined)
            if department == "其他":
                department = infer_department(query)
            source_type = classify_source(domain, portal_domains)
            if source_type == "other" and not args.allow_other_sources:
                continue
            source_name = domain
            confidence = score_confidence(domain, source_type, combined)

            key_basis = link if link else title
            item_id = make_item_id(key_basis)

            item = PolicyItem(
                item_id=item_id,
                title=title,
                link=link,
                publish_date=pub_date,
                source_name=source_name,
                source_domain=domain,
                source_type=source_type,
                region=region,
                department=department,
                query=query,
                summary=summary,
                confidence=confidence,
            )

            old = merged.get(item_id)
            if old is None:
                merged[item_id] = item
            else:
                # Prefer official source when duplicate title/url hits multiple channels.
                if old.source_type != "official" and item.source_type == "official":
                    merged[item_id] = item

    items_all = sorted(
        merged.values(),
        key=lambda x: ((x.publish_date or "0000-00-00"), x.confidence, x.title),
        reverse=True,
    )

    if args.include_seen:
        items_new = items_all
    else:
        items_new = [item for item in items_all if item.item_id not in seen_keys]

    run_at = dt.datetime.now()
    run_key = run_at.strftime("%Y%m%d-%H%M%S")
    run_dir = output_dir / run_key
    run_dir.mkdir(parents=True, exist_ok=True)

    report_md = generate_report(items_all=items_all, items_new=items_new, query_count=len(queries), days=args.days)
    report_path = run_dir / "report.md"
    report_path.write_text(report_md, encoding="utf-8")

    all_path = run_dir / "items_all.json"
    new_path = run_dir / "items_new.json"
    write_json(all_path, [asdict(it) for it in items_all])
    write_json(new_path, [asdict(it) for it in items_new])

    summary_payload: dict[str, Any] = {
        "run_at": run_at.strftime("%Y-%m-%d %H:%M:%S"),
        "config": str(config_path),
        "query_count": len(queries),
        "total_items": len(items_all),
        "new_items": len(items_new),
        "output_dir": str(run_dir),
        "report_path": str(report_path),
        "feishu_doc_url": "",
        "bitable_records_created": 0,
    }

    if args.feishu_doc:
        token = get_tenant_access_token()
        doc_title = args.feishu_doc_title.strip() or f"浙江科技政策监测 {run_at.strftime('%Y-%m-%d %H:%M')}"
        doc_id = create_feishu_doc(token, doc_title)
        append_doc_blocks(token, doc_id, markdown_to_doc_lines(report_md))
        summary_payload["feishu_doc_url"] = f"https://feishu.cn/docx/{doc_id}"

    if args.feishu_bitable and items_new:
        app_token = args.bitable_app_token.strip()
        table_id = args.bitable_table_id.strip()
        if not app_token or not table_id:
            raise RuntimeError(
                "--feishu-bitable requires --bitable-app-token and --bitable-table-id (or env FEISHU_BITABLE_APP_TOKEN / FEISHU_BITABLE_TABLE_ID)."
            )
        field_map_path = Path(args.bitable_field_map) if args.bitable_field_map else None
        field_map = load_field_map(field_map_path)
        token = get_tenant_access_token()
        created = write_items_to_bitable(token, app_token, table_id, items_new, field_map)
        summary_payload["bitable_records_created"] = created

    new_seen = list(seen_keys)
    for item in items_new:
        new_seen.append(item.item_id)
    if len(new_seen) > args.state_max:
        new_seen = new_seen[-args.state_max :]
    save_seen_keys(state_file, new_seen)

    summary_path = run_dir / "run_summary.json"
    write_json(summary_path, summary_payload)

    print(json.dumps(summary_payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
