"""Product and domain dedupe helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Set
from urllib.parse import urlparse


TRACKING_PARAMS = {
    "ref",
    "ref_src",
    "referral",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
}


def normalize_name(name: str) -> str:
    text = (name or "").strip().lower()
    text = re.sub(r"\b(ai|app|studio|labs?)\b", "", text)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text)
    return text


def normalize_domain(url: str) -> str:
    if not url:
        return ""
    candidate = url.strip()
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


def is_marker_row(name: str) -> bool:
    text = (name or "").strip()
    return not text or "Agent" in text or "自动化" in text


@dataclass
class DedupeIndex:
    names: Set[str]
    domains: Set[str]
    name_to_raw: Dict[str, str]
    domain_to_raw: Dict[str, str]

    def check(self, name: str, url: str) -> Optional[str]:
        norm_name = normalize_name(name)
        domain = normalize_domain(url)
        if domain and domain in self.domains:
            return "duplicate_domain:%s" % self.domain_to_raw.get(domain, domain)
        if norm_name and norm_name in self.names:
            return "duplicate_name:%s" % self.name_to_raw.get(norm_name, name)
        return None


def build_index(rows: Iterable[dict]) -> DedupeIndex:
    names: Set[str] = set()
    domains: Set[str] = set()
    name_to_raw: Dict[str, str] = {}
    domain_to_raw: Dict[str, str] = {}
    for row in rows:
        name = row.get("产品名", "")
        url = row.get("网址", "")
        if is_marker_row(name):
            continue
        norm_name = normalize_name(name)
        domain = normalize_domain(url)
        if norm_name:
            names.add(norm_name)
            name_to_raw.setdefault(norm_name, name)
        if domain:
            domains.add(domain)
            domain_to_raw.setdefault(domain, name or domain)
    return DedupeIndex(names, domains, name_to_raw, domain_to_raw)
