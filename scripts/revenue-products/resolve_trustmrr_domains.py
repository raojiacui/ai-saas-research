#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Resolve the real website domain for revenue-products.csv rows whose 网址
points to a trustmrr.com/startup/{slug} page.

TrustMRR startup pages contain a link to the product's own website (usually
marked with ?ref=trustmrr). We fetch each page, prefer that link, and fall
back to the first plausible external domain.

Writes runs/_aitdk_domains.json (domain map merged with row metadata) so the
browser-based traffic.cv collection can consume it.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "revenue-products.csv"
OUT_PATH = ROOT / "runs" / "_aitdk_domains.json"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

REFER_MARKER = "ref=trustmrr"
SKIP_DOMAINS = {
    "trustmrr.com",
    "www.trustmrr.com",
    "t.me",
    "x.com",
    "twitter.com",
    "newsletter.marclou.com",
    "codefa.st",
    "shipfa.st",
    "datafa.st",
    "buymeacoffee.com",
    "github.com",
    "discord.com",
}


def domain_from_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not re.match(r"^[a-z]+://", url, flags=re.I):
        url = "https://" + url
    try:
        netloc = urlparse(url).netloc.lower()
    except Exception:
        return ""
    return netloc.removeprefix("www.").strip("/")


def http_get(url: str, timeout: int = 20) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.8"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def extract_links(html: str):
    return re.findall(r'href="(https?://[^"#\s<>]+)"', html, flags=re.I)


def pick_domain(html: str) -> str:
    links = extract_links(html)
    # 1) prefer product links carrying ?ref=trustmrr
    for link in links:
        if REFER_MARKER in link and "pbs.twimg.com" not in link:
            d = domain_from_url(link)
            if d and d not in SKIP_DOMAINS:
                return d
    # 2) fall back to any plausible external domain
    for link in links:
        d = domain_from_url(link)
        if d and d not in SKIP_DOMAINS and "." in d:
            return d
    return ""


def main() -> int:
    import csv

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    out = []
    for i, r in enumerate(rows, start=1):
        url = (r.get("网址") or "").strip()
        entry = {
            "row": i,
            "product": (r.get("产品名") or "").strip(),
            "url": url,
            "domain": domain_from_url(url),
            "resolved_domain": "",
            "traffic_before": (r.get("AITDK月访问量") or "").strip(),
            "keywords_before": (r.get("Top Keywords") or "").strip(),
        }
        if entry["domain"] == "trustmrr.com":
            try:
                html = http_get(url)
                entry["resolved_domain"] = pick_domain(html)
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                entry["resolved_domain"] = f"ERROR:{type(exc).__name__}"
            time.sleep(0.35)
        out.append(entry)

    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    resolved = sum(1 for e in out if e["resolved_domain"] and not e["resolved_domain"].startswith("ERROR:"))
    errors = [e for e in out if e["resolved_domain"].startswith("ERROR:")]
    print(f"trustmrr rows resolved: {resolved}/{sum(1 for e in out if e['domain']=='trustmrr.com')}")
    print(f"resolution errors: {len(errors)}")
    for e in errors[:20]:
        print("  ", e["row"], e["product"], e["url"], "->", e["resolved_domain"])
    print(f"written: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
