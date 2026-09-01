"""Safely write AITDK metrics back to an existing product CSV.

The browser/extension step is intentionally outside this script. Claude Code or
OpenCode can read AITDK in the browser, then pass structured rows here. This
script only matches existing products and updates traffic fields without
touching other columns.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TABLE = ROOT / "pending-products.csv"
AITDK_FIELDS = ["AITDK月访问量", "Top Keywords", "Top Regions"]
INPUT_FIELDS = ["产品名", "官网域名", "AITDK月访问量", "Top Keywords", "Top Regions"]
EMPTY_VALUES = {"", "unavailable", "unknown", "n/a", "na", "none", "null"}


@dataclass
class AitdkRecord:
    name: str
    domain: str
    monthly_visits: str
    top_keywords: str
    top_regions: str


def normalize_domain(value: str) -> str:
    if not value:
        return ""
    candidate = value.strip()
    if "://" not in candidate:
        candidate = "https://" + candidate
    parsed = urlparse(candidate)
    host = (parsed.netloc or parsed.path).split("/")[0].lower()
    if "@" in host:
        host = host.rsplit("@", 1)[-1]
    if ":" in host:
        host = host.split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def normalize_name(value: str) -> str:
    return "".join(ch for ch in (value or "").strip().lower() if ch.isalnum())


def is_empty_metric(value: str) -> bool:
    return (value or "").strip().lower() in EMPTY_VALUES


def read_csv(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, headers: List[str], rows: Iterable[Dict[str, str]]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    tmp.replace(path)


def parse_pipe_record(line: str) -> Optional[AitdkRecord]:
    text = (line or "").strip()
    if not text or text.startswith("#"):
        return None
    parts = [part.strip() for part in text.split("|")]
    if len(parts) != 5:
        raise ValueError("AITDK row must be 产品名|官网域名|AITDK月访问量|Top Keywords|Top Regions")
    return AitdkRecord(
        name=parts[0],
        domain=normalize_domain(parts[1]),
        monthly_visits=parts[2],
        top_keywords=parts[3],
        top_regions=parts[4],
    )


def read_records(path: Path) -> List[AitdkRecord]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = []
            for row in reader:
                rows.append(
                    AitdkRecord(
                        name=(row.get("产品名") or "").strip(),
                        domain=normalize_domain(row.get("官网域名") or row.get("网址") or row.get("domain") or ""),
                        monthly_visits=(row.get("AITDK月访问量") or "").strip(),
                        top_keywords=(row.get("Top Keywords") or "").strip(),
                        top_regions=(row.get("Top Regions") or "").strip(),
                    )
                )
            return rows
    records = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        record = parse_pipe_record(line)
        if record:
            records.append(record)
    return records


def build_indexes(rows: List[Dict[str, str]]) -> Tuple[Dict[str, int], Dict[str, int]]:
    by_domain: Dict[str, int] = {}
    by_name: Dict[str, int] = {}
    for index, row in enumerate(rows):
        domain = normalize_domain(row.get("domain") or row.get("网址") or row.get("final_url") or "")
        name = normalize_name(row.get("产品名", ""))
        if domain:
            by_domain.setdefault(domain, index)
        if name:
            by_name.setdefault(name, index)
    return by_domain, by_name


def find_row(record: AitdkRecord, rows: List[Dict[str, str]], by_domain: Dict[str, int], by_name: Dict[str, int]) -> Optional[int]:
    domain = normalize_domain(record.domain)
    if domain and domain in by_domain:
        return by_domain[domain]
    name = normalize_name(record.name)
    if name and name in by_name:
        return by_name[name]
    return None


def validate_headers(headers: List[str]) -> None:
    missing = [field for field in AITDK_FIELDS if field not in headers]
    if missing:
        raise ValueError("target CSV missing AITDK fields: %s" % ", ".join(missing))


def apply_records(rows: List[Dict[str, str]], records: List[AitdkRecord], overwrite: bool = False) -> Tuple[int, int, List[str]]:
    by_domain, by_name = build_indexes(rows)
    updated = 0
    unmatched = 0
    messages: List[str] = []
    for record in records:
        row_index = find_row(record, rows, by_domain, by_name)
        if row_index is None:
            unmatched += 1
            messages.append("unmatched: %s | %s" % (record.name, record.domain))
            continue
        row = rows[row_index]
        changed = False
        updates = {
            "AITDK月访问量": record.monthly_visits,
            "Top Keywords": record.top_keywords,
            "Top Regions": record.top_regions,
        }
        for field, value in updates.items():
            if not value:
                continue
            if overwrite or is_empty_metric(row.get(field, "")):
                if row.get(field, "") != value:
                    row[field] = value
                    changed = True
        if changed:
            updated += 1
            messages.append("updated: %s | %s" % (row.get("产品名", record.name), normalize_domain(row.get("网址", record.domain))))
        else:
            messages.append("unchanged: %s | %s" % (row.get("产品名", record.name), normalize_domain(row.get("网址", record.domain))))
    return updated, unmatched, messages


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update AITDK metrics in an existing product CSV")
    parser.add_argument("--input-file", required=True, help="CSV or pipe-delimited text from browser AITDK extraction")
    parser.add_argument("--table", default=str(DEFAULT_TABLE), help="Target CSV. Defaults to pending-products.csv")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing non-empty AITDK fields")
    parser.add_argument("--dry-run", action="store_true", help="Validate and report without writing")
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    table = Path(args.table)
    input_file = Path(args.input_file)
    headers, rows = read_csv(table)
    validate_headers(headers)
    records = read_records(input_file)
    updated, unmatched, messages = apply_records(rows, records, overwrite=args.overwrite)
    if not args.dry_run:
        write_csv(table, headers, rows)
    print("table=%s" % table)
    print("input_file=%s" % input_file)
    print("records=%s" % len(records))
    print("updated=%s" % updated)
    print("unmatched=%s" % unmatched)
    print("dry_run=%s" % args.dry_run)
    for message in messages:
        print("- %s" % message)
    return 0 if unmatched == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
