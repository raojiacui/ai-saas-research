"""Candidate parsing for the MVP.

First version intentionally avoids bulk source crawling. Candidates are passed
explicitly as NAME|URL|SOURCE_URL so the workflow can be tested with tiny input.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class Candidate:
    name: str
    url: str
    source_url: str
    source: str = "manual-test"


def parse_candidate(value: str) -> Candidate:
    parts = [part.strip() for part in value.split("|")]
    if len(parts) < 2:
        raise ValueError("candidate must be NAME|URL|SOURCE_URL")
    name = parts[0]
    url = parts[1]
    source_url = parts[2] if len(parts) >= 3 and parts[2] else url
    source = parts[3] if len(parts) >= 4 and parts[3] else "manual-test"
    if not name or not url:
        raise ValueError("candidate name and url are required")
    return Candidate(name=name, url=url, source_url=source_url, source=source)


def parse_candidates(values: List[str]) -> List[Candidate]:
    return [parse_candidate(value) for value in values]
