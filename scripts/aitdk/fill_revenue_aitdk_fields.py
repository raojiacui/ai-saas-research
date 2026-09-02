#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fill AITDK monthly visits and Top Keywords in revenue-products.csv.

The script is intentionally conservative:
- It only edits "AITDK月访问量" and "Top Keywords".
- It creates a timestamped backup before in-place writes.
- It does not overwrite verified-looking values unless --force is used.
- It writes a separate report so unresolved rows are easy to review.

AITDK does not expose a stable public CSV/API endpoint in the project files, so
this script uses public web pages/search results and only writes values when a
clear monthly-traffic or keyword pattern is found.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen


PRODUCT_COL = "产品名"
URL_COL = "网址"
TRAFFIC_COL = "AITDK月访问量"
KEYWORDS_COL = "Top Keywords"

BAD_TRAFFIC_SUBSTRINGS = ("未核验", "待核验", "unknown", "unavailable", "暂无")
BAD_KEYWORD_SUBSTRINGS = ("未核验", "待核验", "unknown", "unavailable", "暂无")
BAD_EXACT_VALUES = {"n/a", "na", "-", "--", "空"}

GENERIC_KEYWORD_VALUES = {
    "ai saas, ai automation, productivity",
    "ai video, ai content creation, ai marketing",
    "ai marketing, ai seo, lead generation",
    "ai developer tools, ai chatbot, automation",
}

SKIP_DOMAINS = {
    "trustmrr.com",
    "www.trustmrr.com",
    "a.trustmrr.com",
    "apps.apple.com",
    "itunes.apple.com",
    "pbs.twimg.com",
    "images.unsplash.com",
    "cdn.prod.website-files.com",
    "x.com",
    "twitter.com",
    "linkedin.com",
    "youtube.com",
    "youtu.be",
    "github.com",
    "producthunt.com",
}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


@dataclass
class Enrichment:
    traffic: str = ""
    keywords: str = ""
    source: str = ""
    status: str = "not_found"
    note: str = ""


def clean_cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("\ufeff", "").strip()


def normalize_domain(domain: str) -> str:
    domain = domain.lower().strip()
    domain = re.sub(r"^www\.", "", domain)
    return domain.strip("/")


def is_skipped_domain(domain: str) -> bool:
    d = normalize_domain(domain)
    return d in SKIP_DOMAINS or d.endswith(".trustmrr.com") or d.endswith(".twimg.com")


def domain_from_url(url: str) -> str:
    url = clean_cell(url)
    if not url:
        return ""
    if not re.match(r"^[a-z]+://", url, flags=re.I):
        url = "https://" + url
    try:
        return normalize_domain(urlparse(url).netloc)
    except Exception:
        return ""


def should_fill_traffic(value: str, force: bool) -> bool:
    if force:
        return True
    v = clean_cell(value)
    if not v:
        return True
    low = v.lower()
    return low in BAD_EXACT_VALUES or any(marker in low for marker in BAD_TRAFFIC_SUBSTRINGS)


def should_fill_keywords(value: str, force: bool, replace_generic: bool) -> bool:
    if force:
        return True
    v = clean_cell(value)
    if not v:
        return True
    low = v.lower()
    if low in BAD_EXACT_VALUES or any(marker in low for marker in BAD_KEYWORD_SUBSTRINGS):
        return True
    return replace_generic and low in GENERIC_KEYWORD_VALUES


def http_get(url: str, timeout: int = 8) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.8,zh-CN;q=0.7"})
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    for enc in ("utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def compact_visits(raw: str) -> str:
    raw = raw.strip().replace(",", "")
    m = re.match(r"([0-9]+(?:\.[0-9]+)?)([kKmMbB]?)", raw)
    if not m:
        return ""
    num = float(m.group(1))
    suffix = m.group(2).upper()
    if suffix:
        return f"{num:g}{suffix}"
    if num >= 1_000_000:
        return f"{num / 1_000_000:.2f}".rstrip("0").rstrip(".") + "M"
    if num >= 1_000:
        return f"{num / 1_000:.2f}".rstrip("0").rstrip(".") + "K"
    return str(int(num))


def parse_monthly_visits(text: str) -> str:
    patterns = [
        r"(?:Monthly\s+Visits?|monthly\s+traffic|total\s+visits?|月访问量|每月访问量)\s*[:：]?\s*([0-9][0-9,]*(?:\.[0-9]+)?\s*[KkMmBb]?)",
        r"([0-9][0-9,]*(?:\.[0-9]+)?\s*[KkMmBb]?)\s+(?:monthly\s+visits?|visits\s+per\s+month|月访问量)",
        r"visits\s+([0-9][0-9,]*(?:\.[0-9]+)?\s*[KkMmBb]?)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.I)
        if m:
            return compact_visits(m.group(1))
    return ""


def split_keywords(raw: str) -> List[str]:
    raw = unescape(raw)
    raw = re.sub(r"\s+", " ", raw)
    bits = re.split(r"[,，;；|/]|(?:\s{2,})", raw)
    out: List[str] = []
    seen = set()
    for bit in bits:
        kw = bit.strip(" .:：-–—\t\r\n\"'“”‘’[]()（）")
        if not kw:
            continue
        if len(kw) > 60:
            continue
        low = kw.lower()
        if low in seen:
            continue
        if low in {"top keywords", "keywords", "keyword", "search keyword", "organic keywords"}:
            continue
        if re.fullmatch(r"[0-9.,]+[kmbKMB]?", kw):
            continue
        seen.add(low)
        out.append(kw)
        if len(out) >= 5:
            break
    return out


def parse_top_keywords(text: str, product_name: str = "") -> str:
    candidates: List[str] = []
    semrush_match = re.search(
        r"Top Organic Keywords.*?Keyword\s+Intent\s+Position\s+Volume\s+CPC\(USD\)\s+Traffic\s*%(.*?)(?:See all keywords|Backlink)",
        text,
        flags=re.I | re.S,
    )
    if semrush_match:
        table = semrush_match.group(1)
        rows = re.findall(
            r"(.+?)\s+(?:[NCIT]\s+)+\d+\s+[\d,]+(?:\s+[\d.]+)?\s+[\d.]+%",
            table,
            flags=re.I,
        )
        candidates.extend([r.strip() for r in rows])

    patterns = [
        r"(?:Top\s+Keywords?|Organic\s+Keywords?|热门关键词|关键词)\s*[:：]\s*([^。.!?\n]{5,260})",
        r"(?:top\s+search\s+terms?)\s*[:：]\s*([^。.!?\n]{5,260})",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, text, flags=re.I):
            candidates.extend(split_keywords(m.group(1)))

    # Search snippets often put keyword chips near the domain without a label.
    if not candidates and product_name:
        name = re.escape(product_name.lower())
        lowered = text.lower()
        idx = lowered.find(product_name.lower())
        if idx >= 0:
            window = text[max(0, idx - 300) : idx + 500]
            candidates.extend(split_keywords(window))

    cleaned: List[str] = []
    seen = set()
    blocked = {
        "aitdk",
        "traffic",
        "monthly visits",
        "similarweb",
        "hypestat",
        "seo",
        "website",
        "domain",
    }
    for kw in candidates:
        low = kw.lower()
        if low in blocked:
            continue
        if low not in seen:
            seen.add(low)
            cleaned.append(kw)
        if len(cleaned) >= 5:
            break
    return ", ".join(cleaned)


def extract_domains_from_html(html: str) -> List[str]:
    text = html_to_text(html)
    domains = re.findall(r"\b([a-z0-9][a-z0-9-]{1,62}(?:\.[a-z0-9-]{2,63})+\.[a-z]{2,24})\b", text, flags=re.I)
    links = re.findall(r"https?://([^/\"'?#\s<>]+)", html, flags=re.I)
    domains.extend(links)
    out: List[str] = []
    seen = set()
    for domain in domains:
        d = normalize_domain(domain)
        if is_skipped_domain(d) or d in seen:
            continue
        if "." not in d:
            continue
        seen.add(d)
        out.append(d)
    return out


def resolve_product_domain(row: Dict[str, str], cache: Dict[str, str], sleep: float) -> str:
    url = clean_cell(row.get(URL_COL, ""))
    product = clean_cell(row.get(PRODUCT_COL, ""))
    key = url or product
    if key in cache:
        cached = cache[key]
        if not is_skipped_domain(cached):
            return cached

    domain = domain_from_url(url)
    if domain and not is_skipped_domain(domain):
        cache[key] = domain
        return domain

    if "trustmrr.com" in domain and url:
        try:
            html = http_get(url)
            choices = extract_domains_from_html(html)
            if choices:
                cache[key] = choices[0]
                time.sleep(sleep)
                return choices[0]
        except (HTTPError, URLError, TimeoutError, OSError):
            pass

    cache[key] = domain
    return domain


def candidate_urls(
    domain: str,
    allow_fallback: bool,
    skip_aitdk: bool = False,
    providers: Optional[set] = None,
) -> Iterable[Tuple[str, str]]:
    encoded_domain = quote_plus(domain)
    aitdk_queries = [
        f"https://www.bing.com/search?q=site%3Aaitdk.com+{encoded_domain}+%22Monthly+Visits%22+%22Top+Keywords%22",
        f"https://www.bing.com/search?q=site%3Aaitdk.com+{encoded_domain}+%22AITDK%22+%22keywords%22",
    ]
    direct = [
        f"https://aitdk.com/traffic/{domain}",
        f"https://aitdk.com/website/{domain}",
        f"https://aitdk.com/domain/{domain}",
        f"https://aitdk.com/analyze/{domain}",
        f"https://aitdk.com/seo/{domain}",
    ]
    def allowed(name: str) -> bool:
        return providers is None or name in providers

    if not skip_aitdk and allowed("aitdk"):
        for url in direct:
            yield "aitdk-direct", url
        for url in aitdk_queries:
            yield "aitdk-search", url
    if allow_fallback:
        if allowed("semrush"):
            yield "semrush", f"https://www.semrush.com/website/{domain}/overview/"
        if allowed("ahrefs"):
            yield "ahrefs", f"https://ahrefs.com/websites/{domain}"
        if allowed("hypestat"):
            yield "hypestat", f"https://hypestat.com/info/{domain}"
        if allowed("explodingtopics"):
            yield "explodingtopics", f"https://analytics.explodingtopics.com/website/{domain}"
        if allowed("search"):
            yield "fallback-search", f"https://www.bing.com/search?q={encoded_domain}+monthly+visits+top+keywords"


def enrich_domain(
    domain: str,
    product_name: str,
    allow_fallback: bool,
    sleep: float,
    skip_aitdk: bool = False,
    providers: Optional[set] = None,
) -> Enrichment:
    if not domain or is_skipped_domain(domain):
        return Enrichment(status="skipped", note="missing or unsupported product domain")

    best = Enrichment()
    errors: List[str] = []
    for source, url in candidate_urls(domain, allow_fallback, skip_aitdk=skip_aitdk, providers=providers):
        try:
            html = http_get(url)
            text = html_to_text(html)
            if normalize_domain(domain) not in normalize_domain(text):
                # Search pages can return unrelated snippets. Do not extract from
                # a page that does not visibly mention the requested domain.
                traffic = ""
                keywords = ""
            else:
                traffic = parse_monthly_visits(text)
                keywords = "" if source.endswith("search") else parse_top_keywords(text, product_name)
            time.sleep(sleep)
            if traffic or keywords:
                status = "found"
                if source.startswith("fallback") or source == "hypestat":
                    status = "found_fallback"
                return Enrichment(traffic=traffic, keywords=keywords, source=url, status=status)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            errors.append(f"{source}:{type(exc).__name__}")
            time.sleep(sleep)
            continue

    if errors:
        best.note = "; ".join(errors[:4])
    return best


def load_cache(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_cache(path: Path, cache: Dict[str, str]) -> None:
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def read_csv(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []
    missing = [c for c in (PRODUCT_COL, URL_COL, TRAFFIC_COL, KEYWORDS_COL) if c not in fieldnames]
    if missing:
        raise SystemExit(f"CSV缺少字段: {', '.join(missing)}")
    return fieldnames, rows


def write_csv(path: Path, fieldnames: List[str], rows: List[Dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, rows: List[Dict[str, str]]) -> None:
    fieldnames = [
        "row",
        "产品名",
        "domain",
        "AITDK月访问量_before",
        "AITDK月访问量_after",
        "Top Keywords_before",
        "Top Keywords_after",
        "status",
        "source",
        "note",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="补齐 revenue-products.csv 的 AITDK月访问量 和 Top Keywords 字段。"
    )
    parser.add_argument("--csv", default=r"D:\ai-saas-research\revenue-products.csv", help="目标CSV路径")
    parser.add_argument("--out", default="", help="输出CSV路径。默认生成 .aitdk-filled.csv；配合 --in-place 可原地覆盖")
    parser.add_argument("--in-place", action="store_true", help="原地更新，并自动创建备份")
    parser.add_argument("--force", action="store_true", help="覆盖已有值")
    parser.add_argument(
        "--replace-generic-keywords",
        action="store_true",
        default=True,
        help="替换明显模板化的 Top Keywords（默认开启）",
    )
    parser.add_argument(
        "--keep-generic-keywords",
        action="store_false",
        dest="replace_generic_keywords",
        help="不替换模板化 Top Keywords，只补空白/未核验",
    )
    parser.add_argument("--allow-fallback", action="store_true", help="AITDK找不到时允许用公开网页/搜索结果补")
    parser.add_argument("--skip-aitdk", action="store_true", help="跳过慢速AITDK探测，直接使用公开流量页")
    parser.add_argument("--providers", default="", help="逗号分隔的数据源: aitdk,semrush,ahrefs,hypestat,explodingtopics,search")
    parser.add_argument("--limit", type=int, default=0, help="只处理前N条待补记录，0表示全部")
    parser.add_argument("--sleep", type=float, default=0.4, help="每次请求后的等待秒数")
    parser.add_argument("--dry-run", action="store_true", help="只生成报告，不写CSV")
    parser.add_argument("--cache", default="", help="域名解析缓存JSON路径")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"找不到CSV: {csv_path}", file=sys.stderr)
        return 1

    fieldnames, rows = read_csv(csv_path)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = Path(args.out) if args.out else csv_path.with_name(csv_path.stem + ".aitdk-filled.csv")
    report_path = csv_path.with_name(csv_path.stem + f".aitdk-report-{ts}.csv")
    cache_path = Path(args.cache) if args.cache else csv_path.with_name("aitdk-domain-cache.json")
    cache = load_cache(cache_path)
    providers = {x.strip() for x in args.providers.split(",") if x.strip()} or None

    targets: List[Tuple[int, Dict[str, str], bool, bool]] = []
    for idx, row in enumerate(rows, start=2):
        need_traffic = should_fill_traffic(row.get(TRAFFIC_COL, ""), args.force)
        need_keywords = should_fill_keywords(row.get(KEYWORDS_COL, ""), args.force, args.replace_generic_keywords)
        if need_traffic or need_keywords:
            targets.append((idx, row, need_traffic, need_keywords))

    if args.limit > 0:
        targets = targets[: args.limit]

    report_rows: List[Dict[str, str]] = []
    changed = 0
    print(f"待处理记录: {len(targets)}", flush=True)

    for n, (idx, row, need_traffic, need_keywords) in enumerate(targets, start=1):
        product = clean_cell(row.get(PRODUCT_COL, ""))
        before_traffic = clean_cell(row.get(TRAFFIC_COL, ""))
        before_keywords = clean_cell(row.get(KEYWORDS_COL, ""))
        domain = resolve_product_domain(row, cache, args.sleep)
        print(f"[{n}/{len(targets)}] {product} -> {domain}", flush=True)
        result = enrich_domain(
            domain,
            product,
            args.allow_fallback,
            args.sleep,
            skip_aitdk=args.skip_aitdk,
            providers=providers,
        )

        after_traffic = before_traffic
        after_keywords = before_keywords
        row_changed = False
        if need_traffic and result.traffic:
            after_traffic = result.traffic
            row[TRAFFIC_COL] = after_traffic
            row_changed = True
        if need_keywords and result.keywords:
            after_keywords = result.keywords
            row[KEYWORDS_COL] = after_keywords
            row_changed = True
        if row_changed:
            changed += 1

        report_rows.append(
            {
                "row": idx,
                "产品名": product,
                "domain": domain,
                "AITDK月访问量_before": before_traffic,
                "AITDK月访问量_after": after_traffic,
                "Top Keywords_before": before_keywords,
                "Top Keywords_after": after_keywords,
                "status": result.status if row_changed else "not_written",
                "source": result.source,
                "note": result.note,
            }
        )

    save_cache(cache_path, cache)
    write_report(report_path, report_rows)

    if args.dry_run:
        print(f"dry-run完成，报告: {report_path}")
        print(f"可写入变更行数: {changed}")
        return 0

    if args.in_place:
        backup_path = csv_path.with_name(csv_path.name + f".before-aitdk-fill-{ts}.bak")
        shutil.copy2(csv_path, backup_path)
        write_csv(csv_path, fieldnames, rows)
        print(f"已原地更新: {csv_path}")
        print(f"备份: {backup_path}")
    else:
        write_csv(out_path, fieldnames, rows)
        print(f"已写入新文件: {out_path}")

    print(f"报告: {report_path}")
    print(f"实际更新行数: {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
