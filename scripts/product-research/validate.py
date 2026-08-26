"""Validation helpers for product research outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from csv_store import validate_csv_shape
from dedupe import normalize_domain
from schemas import PENDING_HEADERS, PRODUCT_HEADERS


def validate_product_row(row: Dict[str, str]) -> List[str]:
    errors: List[str] = []
    for header in PRODUCT_HEADERS:
        if header not in row:
            errors.append("missing field: %s" % header)
    if not (row.get("产品名") or "").strip():
        errors.append("missing product name")
    if not normalize_domain(row.get("网址", "")):
        errors.append("missing or invalid website url")
    if not (row.get("source_url") or "").strip():
        errors.append("missing source_url")
    for header in PENDING_HEADERS:
        if "\n" in str(row.get(header, "")):
            row[header] = str(row.get(header, "")).replace("\r", " ").replace("\n", " / ")
    return errors


def validate_outputs(paths: List[Path]) -> None:
    for path in paths:
        validate_csv_shape(path)
