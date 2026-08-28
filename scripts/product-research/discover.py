"""Candidate discovery for the product-research MVP.

Manual candidates are still supported. The first automated source is Toolify,
kept deliberately small and bounded so the workflow can be tested before any
batch run.
"""

from __future__ import annotations

import html
import re
import shutil
import ssl
import subprocess
import sys
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Iterable, List, Tuple
from urllib.parse import quote_plus, urljoin, urlparse
from urllib.request import Request, urlopen


USER_AGENT = "Mozilla/5.0 product-research-mvp/0.1"
TOOLIFY_BASE_URL = "https://www.toolify.ai"
DEFAULT_TOOLIFY_QUERIES = [
    "reference to video ai",
    "video to video ai",
    "image to video ai",
    "text to video ai",
    "ai video generator",
    "ai video editor",
    "ai video ads",
    "ai avatar video",
    "ai lip sync video",
    "motion transfer video ai",
    "video style transfer ai",
    "product to video ads ai",
]
DEFAULT_TOOLIFY_QUERY = DEFAULT_TOOLIFY_QUERIES[0]
AI_VIDEO_KEYWORDS = (
    "ai video",
    "video ai",
    "video generator",
    "text to video",
    "image to video",
    "reference to video",
    "video to video",
    "motion transfer",
    "avatar video",
    "lip sync",
    "video editing",
    "video ads",
)
NON_VIDEO_EXCLUSION_KEYWORDS = (
    "meeting notes",
    "notetaker",
    "note taker",
    "transcription",
    "audio transcription",
    "architecture",
    "interior design",
    "crm",
    "sales assistant",
    "email",
    "spreadsheet",
    "pdf",
    "resume",
)
BLOCKED_EXTERNAL_HOSTS = (
    "toolify.ai",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "youtube.com",
    "youtu.be",
    "discord.gg",
    "discord.com",
    "tiktok.com",
    "github.com",
    "apps.apple.com",
    "play.google.com",
)


@dataclass
class Candidate:
    name: str
    url: str
    source_url: str
    source: str = "manual-test"


@dataclass
class DiscoveryResult:
    candidates: List[Candidate]
    diagnostics: List[str]


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


class LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: List[dict] = []
        self._href = ""
        self._text: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag == "a":
            attrs_dict = {k.lower(): v for k, v in attrs if k}
            self._href = attrs_dict.get("href", "") or ""
            self._text = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "a" and self._href:
            text = clean_text(" ".join(self._text))
            self.links.append({"href": self._href, "text": text})
            self._href = ""
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth or not self._href:
            return
        text = clean_text(data)
        if text:
            self._text.append(text)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def is_probable_toolify_product_link(href: str) -> bool:
    parsed = urlparse(href)
    path = parsed.path.lower()
    if not path or path == "/":
        return False
    blocked_prefixes = (
        "/category",
        "/categories",
        "/best",
        "/search",
        "/login",
        "/submit",
        "/pricing",
        "/blog",
        "/news",
        "/features",
        "/alternatives",
    )
    if any(path.startswith(prefix) for prefix in blocked_prefixes):
        return False
    return path.startswith("/tool/") or path.count("/") <= 2


def looks_ai_video_candidate(text: str, href: str) -> bool:
    haystack = ("%s %s" % (text, href)).lower()
    return any(keyword in haystack for keyword in AI_VIDEO_KEYWORDS)


def looks_obviously_non_video(text: str, href: str) -> bool:
    haystack = ("%s %s" % (text, href)).lower()
    return any(keyword in haystack for keyword in NON_VIDEO_EXCLUSION_KEYWORDS)


def has_ai_video_context(source_url: str) -> bool:
    decoded = source_url.replace("+", " ").replace("%20", " ").lower()
    return any(keyword in decoded for keyword in AI_VIDEO_KEYWORDS) or "ai-video" in decoded


def is_generic_link_text(text: str) -> bool:
    cleaned = clean_text(text).lower()
    generic = {
        "visit",
        "website",
        "visit website",
        "open",
        "try",
        "get started",
        "pricing",
        "login",
        "sign up",
        "submit",
        "view more",
    }
    return cleaned in generic or len(cleaned) < 3


def discover_from_toolify_html(html_text: str, source_url: str, limit: int) -> List[Candidate]:
    parser = LinkExtractor()
    parser.feed(html_text or "")
    candidates: List[Candidate] = []
    seen_urls = set()
    for link in parser.links:
        text = clean_text(link.get("text", ""))
        href = link.get("href", "")
        if not text or is_generic_link_text(text):
            continue
        if not is_probable_toolify_product_link(href):
            continue
        if looks_obviously_non_video(text, href):
            continue
        if not has_ai_video_context(source_url) and not looks_ai_video_candidate(text, href):
            continue
        url = urljoin(TOOLIFY_BASE_URL, href)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        candidates.append(Candidate(name=text, url=url, source_url=source_url, source="toolify"))
        if limit and len(candidates) >= limit:
            break
    return candidates


def host_matches_blocked(host: str) -> bool:
    normalized = (host or "").lower()
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return any(normalized == blocked or normalized.endswith("." + blocked) for blocked in BLOCKED_EXTERNAL_HOSTS)


def is_external_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc) and not host_matches_blocked(parsed.netloc)


def find_official_url(html_text: str, detail_url: str) -> str:
    parser = LinkExtractor()
    parser.feed(html_text or "")
    fallback = ""
    for link in parser.links:
        href = link.get("href", "")
        text = clean_text(link.get("text", ""))
        url = urljoin(detail_url, href)
        if not is_external_url(url):
            continue
        haystack = ("%s %s" % (text, url)).lower()
        if any(word in haystack for word in ("visit", "website", "official", "open", "try", "get started")):
            return url
        if not fallback:
            fallback = url
    return fallback


def toolify_search_urls(query: str) -> List[str]:
    encoded = quote_plus(query or DEFAULT_TOOLIFY_QUERY)
    return [
        "%s/search?q=%s" % (TOOLIFY_BASE_URL, encoded),
        "%s/category/ai-video-generator" % TOOLIFY_BASE_URL,
    ]


def fetch_text_once(url: str, timeout: int, ssl_context=None) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    kwargs = {"timeout": timeout}
    if ssl_context is not None:
        kwargs["context"] = ssl_context
    with urlopen(request, **kwargs) as response:
        raw = response.read(1_000_000)
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def fetch_text(url: str, timeout: int, max_retries: int) -> str:
    last_error = ""
    for retry in range(max_retries + 1):
        try:
            return fetch_text_once(url, timeout=timeout)
        except Exception as exc:
            last_error = str(exc)
            if retry < max_retries:
                time.sleep(1)
    try:
        return fetch_text_once(url, timeout=timeout, ssl_context=ssl._create_unverified_context())
    except Exception as exc:
        last_error = "%s; insecure_ssl_error=%s" % (last_error, exc)
    playwright_html, playwright_error = fetch_text_with_playwright(url, timeout=timeout)
    if playwright_html:
        return playwright_html
    if playwright_error:
        last_error = "%s; playwright_error=%s" % (last_error, playwright_error[:500])
    raise RuntimeError(last_error or "fetch failed")


def fetch_text_with_playwright(url: str, timeout: int) -> Tuple[str, str]:
    code = (
        "import sys\n"
        "from playwright.sync_api import sync_playwright\n"
        "url=sys.argv[1]\n"
        "timeout=int(sys.argv[2]) * 1000\n"
        "with sync_playwright() as p:\n"
        "    browser=p.chromium.launch(headless=True)\n"
        "    page=browser.new_page(user_agent='Mozilla/5.0 product-research-mvp/0.1')\n"
        "    page.goto(url, wait_until='domcontentloaded', timeout=timeout)\n"
        "    page.wait_for_timeout(1000)\n"
        "    print(page.content())\n"
        "    browser.close()\n"
    )
    commands = [[sys.executable, "-c", code, url, str(timeout)]]
    if shutil.which("py"):
        commands.append(["py", "-3.10", "-c", code, url, str(timeout)])
    last_error = ""
    for cmd in commands:
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=max(timeout + 5, 10),
            )
        except Exception as exc:
            last_error = str(exc)
            continue
        if completed.returncode == 0 and completed.stdout.strip():
            return completed.stdout, ""
        last_error = (completed.stderr or completed.stdout or "playwright failed")[:500]
    return "", last_error


def discover_toolify(query: str, limit: int, timeout: int, max_retries: int, diagnostics: List[str]) -> List[Candidate]:
    candidates: List[Candidate] = []
    seen = set()
    for source_url in toolify_search_urls(query):
        try:
            html_text = fetch_text(source_url, timeout=timeout, max_retries=max_retries)
        except Exception as exc:
            diagnostics.append("toolify fetch failed | query=%s | source_url=%s | error=%s" % (query, source_url, str(exc)[:250]))
            continue
        list_candidates = discover_from_toolify_html(html_text, source_url, limit=limit)
        diagnostics.append("toolify list parsed | query=%s | source_url=%s | html_chars=%s | list_candidates=%s" % (query, source_url, len(html_text), len(list_candidates)))
        for candidate in list_candidates:
            detail_url = candidate.url
            official_url = ""
            try:
                detail_html = fetch_text(detail_url, timeout=timeout, max_retries=max_retries)
                official_url = find_official_url(detail_html, detail_url)
            except Exception as exc:
                diagnostics.append("toolify detail failed | query=%s | detail_url=%s | error=%s" % (query, detail_url, str(exc)[:250]))
                official_url = ""
            if not official_url:
                diagnostics.append("toolify official url missing | query=%s | detail_url=%s | name=%s" % (query, detail_url, candidate.name[:80]))
                continue
            key = official_url.lower()
            if key in seen:
                continue
            seen.add(key)
            candidates.append(Candidate(name=candidate.name, url=official_url, source_url=detail_url, source="toolify"))
            if limit and len(candidates) >= limit:
                return candidates
    return candidates


def normalize_queries(queries: Iterable[str]) -> List[str]:
    cleaned: List[str] = []
    seen = set()
    for query in queries:
        text = (query or "").strip()
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        cleaned.append(text)
    return cleaned or list(DEFAULT_TOOLIFY_QUERIES)


def discover_candidates_with_diagnostics(sources: Iterable[str], queries: Iterable[str], limit: int, timeout: int, max_retries: int) -> DiscoveryResult:
    candidates: List[Candidate] = []
    diagnostics: List[str] = []
    normalized_queries = normalize_queries(queries)
    seen = set()
    for source in sources:
        normalized = (source or "").strip().lower()
        if normalized != "toolify":
            raise ValueError("unsupported discover source: %s" % source)
        for query in normalized_queries:
            for candidate in discover_toolify(query, limit=limit, timeout=timeout, max_retries=max_retries, diagnostics=diagnostics):
                key = candidate.url.lower()
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(candidate)
                if limit and len(candidates) >= limit:
                    return DiscoveryResult(candidates=candidates[:limit], diagnostics=diagnostics)
    return DiscoveryResult(candidates=candidates, diagnostics=diagnostics)


def discover_candidates(sources: Iterable[str], queries: Iterable[str], limit: int, timeout: int, max_retries: int) -> List[Candidate]:
    return discover_candidates_with_diagnostics(sources, queries, limit, timeout, max_retries).candidates
