#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chunked conservative writer for AITDK月访问量 / Top Keywords.

Usage:
    python scripts/revenue-products/write_aitdk_chunk.py --rows 1-20

Reads collected batch JSONs under runs/aitdk_collected/, matches domains to
revenue-products.csv rows via runs/_aitdk_domains.json, and applies ONLY the
two target columns for rows in the given 1-based data-row range.

Rules (per user decisions):
  - Only fill AITDK月访问量 and Top Keywords; never touch other columns.
  - Only write into empty/placeholder cells; never overwrite existing values.
  - Collected traffic == "0" -> leave blank + note (never write "0").
  - Collected keywords: write as many real ones as found (1-5), never invent.
  - status not ok -> leave blank + note.
  - Creates a timestamped backup before each write.
  - Accumulates into a running report CSV in runs/.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "revenue-products.csv"
DOMAINS_JSON = ROOT / "runs" / "_aitdk_domains.json"
COLLECTED_DIR = ROOT / "runs" / "aitdk_collected"
REPORT_PATH = ROOT / "runs" / "aitdk-fill-report.csv"

PRODUCT_COL = "产品名"
URL_COL = "网址"
TRAFFIC_COL = "AITDK月访问量"
KEYWORDS_COL = "Top Keywords"

BAD_MARKERS = ("未核验", "待核验", "未知", "unknown", "unavailable", "n/a", "na", "暂无", "空")

# Template/generic keyword strings previously batch-generated; treat as placeholder
# and replace with real collected keywords when available.
GENERIC_KEYWORDS = {
    "ai saas, ai automation, productivity",
    "ai video, ai content creation, ai marketing",
    "ai marketing, ai seo, lead generation",
    "ai developer tools, ai chatbot, automation",
    "ai education, ai resume, ai interview",
}
REPORT_FIELDS = [
    "row", "产品名", "domain",
    "AITDK月访问量_before", "AITDK月访问量_after",
    "Top Keywords_before", "Top Keywords_after",
    "status", "note",
]


def clean(v) -> str:
    if v is None:
        return ""
    return str(v).replace("\ufeff", "").strip()


def is_empty_or_placeholder(v: str) -> bool:
    if not v:
        return True
    low = v.lower()
    return any(m in low for m in BAD_MARKERS)


def load_collected() -> dict:
    collected = {}
    for f in sorted(glob.glob(str(COLLECTED_DIR / "batch*.json"))):
        for rec in json.load(open(f, encoding="utf-8")):
            collected[rec["domain"].lower()] = rec
    return collected


def load_domains() -> dict:
    meta = {}
    for r in json.load(open(DOMAINS_JSON, encoding="utf-8")):
        key = r.get("resolved_domain") or r.get("domain") or ""
        meta[int(r["row"])] = {
            "product": r["product"],
            "match_key": key.lower() if key else "",
            "source": r.get("source", ""),
        }
    return meta


def read_csv():
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    return fieldnames, rows


def write_csv(fieldnames, rows):
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def append_report(entries):
    new = not REPORT_PATH.exists()
    with REPORT_PATH.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_FIELDS, extrasaction="ignore")
        if new:
            writer.writeheader()
        writer.writerows(entries)


def compact(traffic: str) -> str:
    """Compact collected traffic string to a clean K/M value; '' if not numeric or zero."""
    t = clean(traffic).replace(",", "").replace(" ", "")
    if not t:
        return ""
    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)([kKmMbB]?)$", t)
    if not m:
        return ""
    num = float(m.group(1))
    suffix = m.group(2).upper()
    if num == 0:
        return ""
    if suffix:
        return f"{num:g}{suffix}"
    if num >= 1_000_000:
        return f"{num / 1_000_000:.2f}".rstrip("0").rstrip(".") + "M"
    if num >= 1_000:
        return f"{num / 1_000:.2f}".rstrip("0").rstrip(".") + "K"
    return str(int(num))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True, help="数据行范围，如 1-20")
    args = ap.parse_args()
    m = re.match(r"^(\d+)-(\d+)$", args.rows.strip())
    if not m:
        print("--rows 需为 start-end 格式", file=sys.stderr)
        return 1
    start, end = int(m.group(1)), int(m.group(2))
    if start < 1 or end < start:
        print("无效行范围", file=sys.stderr)
        return 1

    collected = load_collected()
    meta = load_domains()
    fieldnames, rows = read_csv()
    total = len(rows)
    if end > total:
        print(f"end 超过总行数 {total}，已截断为 {start}-{total}")
        end = total

    entries = []
    changed = 0
    filled_traffic = 0
    filled_kw = 0
    for i in range(start, end + 1):
        row = rows[i - 1]
        info = meta.get(i, {})
        product = clean(row.get(PRODUCT_COL, ""))
        match_key = info.get("match_key", "")
        before_t = clean(row.get(TRAFFIC_COL, ""))
        before_k = clean(row.get(KEYWORDS_COL, ""))
        entry = {
            "row": i,
            "产品名": product,
            "domain": match_key,
            "AITDK月访问量_before": before_t,
            "AITDK月访问量_after": before_t,
            "Top Keywords_before": before_k,
            "Top Keywords_after": before_k,
            "status": "",
            "note": "",
        }
        if not match_key or match_key in ("trustmrr.com", "www.trustmrr.com", "apps.apple.com"):
            if before_k.lower() in GENERIC_KEYWORDS:
                row[KEYWORDS_COL] = ""
                entry["Top Keywords_after"] = ""
                entry["status"] = "cleared_template"
                entry["note"] = "域名未解析，清空模板词"
                row_changed = True
                changed += 1
            else:
                entry["status"] = "no_match_key"
                entry["note"] = "域名未解析"
            entries.append(entry)
            continue

        rec = collected.get(match_key)
        if not rec:
            entry["status"] = "not_collected"
            entry["note"] = "尚未采集到 traffic.cv 数据"
            entries.append(entry)
            continue

        status = rec.get("status", "")
        if status != "ok":
            entry["status"] = status
            entry["note"] = "采集失败/无数据"
            entries.append(entry)
            continue

        notes = []
        row_changed = False
        # --- traffic ---
        tv = compact(rec.get("traffic", ""))
        if is_empty_or_placeholder(before_t):
            if tv:
                row[TRAFFIC_COL] = tv
                entry["AITDK月访问量_after"] = tv
                filled_traffic += 1
                row_changed = True
            else:
                if before_t:
                    # collected shows 0/no traffic but cell held an unverified
                    # marker -> clear it to blank per "0流量留空" decision.
                    row[TRAFFIC_COL] = ""
                    entry["AITDK月访问量_after"] = ""
                    notes.append("已核验无流量，清空原标记")
                    row_changed = True
                elif clean(rec.get("traffic", "")) == "0":
                    notes.append("流量0，留空")
                else:
                    notes.append("无流量数值，留空")
        else:
            notes.append(f"已有值({before_t})，保留")
        # --- keywords ---
        kws = [k for k in rec.get("keywords", []) if k]
        need_kw = (
            is_empty_or_placeholder(before_k)
            or before_k.lower() in GENERIC_KEYWORDS
            or "、" in before_k
        )
        if need_kw:
            if kws:
                joined = ", ".join(kws[:5])
                row[KEYWORDS_COL] = joined
                entry["Top Keywords_after"] = joined
                filled_kw += 1
                row_changed = True
                if before_k:
                    notes.append("替换模板词为真实关键词")
            else:
                if before_k:
                    row[KEYWORDS_COL] = ""
                    entry["Top Keywords_after"] = ""
                    notes.append("模板词，但无真实关键词，清空")
                    row_changed = True
                else:
                    notes.append("无关键词，留空")
        else:
            notes.append(f"已有值({before_k[:20]}…)，保留")

        if row_changed:
            changed += 1
        entry["status"] = "written" if row_changed else "no_change"
        entry["note"] = "; ".join(notes)
        entries.append(entry)

    # Backup + write only if something changed in this chunk
    if changed > 0:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = CSV_PATH.with_name(CSV_PATH.name + f".before-chunk{start}-{end}-{ts}.bak")
        shutil.copy2(CSV_PATH, backup_path)
        write_csv(fieldnames, rows)
        print(f"已写入 {start}-{end} 行，变更 {changed} 行 (流量 {filled_traffic}，关键词 {filled_kw})")
        print(f"备份: {backup_path.name}")
    else:
        print(f"{start}-{end} 行无变更，未写文件")

    append_report(entries)
    print(f"report 已追加: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
