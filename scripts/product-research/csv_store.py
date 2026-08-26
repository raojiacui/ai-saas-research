"""CSV IO helpers that never mutate the official products.csv."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, List

from schemas import PENDING_HEADERS, PRODUCT_HEADERS


def read_csv(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_products(path: Path) -> List[dict]:
    rows = read_csv(path)
    if not rows:
        raise FileNotFoundError("products.csv is missing or empty: %s" % path)
    headers = list(rows[0].keys())
    if headers != PRODUCT_HEADERS:
        raise ValueError("products.csv header mismatch: %s" % headers)
    return rows


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_headers(path: Path) -> List[str]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            return next(reader)
        except StopIteration:
            return []


def ensure_csv(path: Path, headers: List[str]) -> None:
    ensure_parent(path)
    current = read_headers(path)
    if not current:
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
        return
    if current == headers:
        return
    rows = read_csv(path)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            for header in headers:
                row.setdefault(header, "")
            writer.writerow(row)


def append_rows(path: Path, headers: List[str], rows: Iterable[dict]) -> int:
    materialized = list(rows)
    ensure_csv(path, headers)
    if not materialized:
        return 0
    with path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        for row in materialized:
            writer.writerow(row)
    return len(materialized)


def append_pending(path: Path, rows: Iterable[dict]) -> int:
    return append_rows(path, PENDING_HEADERS, rows)


def validate_csv_shape(path: Path) -> None:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        rows = list(reader)
    if not rows:
        return
    expected = len(rows[0])
    for line_no, row in enumerate(rows, start=1):
        if len(row) != expected:
            raise ValueError("%s line %s has %s columns, expected %s" % (path, line_no, len(row), expected))


def atomic_write_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")
