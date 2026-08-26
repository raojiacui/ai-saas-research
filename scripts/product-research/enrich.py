"""Fetch and deterministic extraction for product homepages."""

from __future__ import annotations

import html
import os
import re
import shutil
import ssl
import subprocess
import tempfile
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


USER_AGENT = "Mozilla/5.0 product-research-mvp/0.1"


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    html: str
    used_playwright: bool
    fetcher: str
    error: str = ""
    retry_count: int = 0


class PageExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.meta_description = ""
        self.anchors: List[Dict[str, str]] = []
        self._current_tag = ""
        self._anchor_href = ""
        self._anchor_text: List[str] = []
        self._title_text: List[str] = []
        self._text: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        attrs_dict = {k.lower(): v for k, v in attrs if k}
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        self._current_tag = tag
        if tag == "meta":
            name = (attrs_dict.get("name") or attrs_dict.get("property") or "").lower()
            if name in {"description", "og:description"} and not self.meta_description:
                self.meta_description = attrs_dict.get("content", "") or ""
        if tag == "a":
            self._anchor_href = attrs_dict.get("href", "") or ""
            self._anchor_text = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title" and not self.title:
            self.title = clean_text(" ".join(self._title_text))
        if tag == "a" and self._anchor_href:
            text = clean_text(" ".join(self._anchor_text))
            self.anchors.append({"href": self._anchor_href, "text": text})
            self._anchor_href = ""
            self._anchor_text = []
        self._current_tag = ""

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = clean_text(data)
        if not text:
            return
        if self._current_tag == "title":
            self._title_text.append(text)
        if self._anchor_href:
            self._anchor_text.append(text)
        if self._current_tag in {"h1", "h2", "h3", "p", "li", "button", "a", "span"}:
            self._text.append(text)

    def body_text(self, limit: int = 6000) -> str:
        deduped: List[str] = []
        seen = set()
        total = 0
        for item in self._text:
            if item not in seen:
                deduped.append(item)
                seen.add(item)
                total += len(item)
            if total >= limit:
                break
        return "\n".join(deduped)[:limit]


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def has_playwright_cli() -> bool:
    return bool(shutil.which("playwright") or shutil.which("playwright.cmd"))


def fetch_url(url: str, timeout: int = 12, max_retries: int = 1) -> FetchResult:
    last_error = ""
    for retry in range(max_retries + 1):
        result = fetch_url_once(url, timeout=timeout, fetcher="urllib", ssl_context=None, retry_count=retry)
        if result.status or not should_retry(result.error):
            return result
        last_error = result.error
        if retry < max_retries:
            time.sleep(1)

    probe_error = ""
    used_playwright = False
    if has_playwright_cli():
        probe_error = playwright_probe_url(url, timeout=timeout)
        used_playwright = not bool(probe_error)

    insecure_fetcher = "playwright_cli_probe+urllib_insecure_ssl" if used_playwright else "urllib_insecure_ssl"
    insecure = fetch_url_once(
        url,
        timeout=timeout,
        fetcher=insecure_fetcher,
        ssl_context=ssl._create_unverified_context(),
        retry_count=max_retries,
    )
    insecure.used_playwright = used_playwright
    if insecure.status:
        if probe_error:
            insecure.error = "playwright_probe_error=%s" % probe_error
        return insecure
    last_error = insecure.error
    if probe_error:
        last_error = "%s; playwright_probe_error=%s" % (last_error, probe_error)

    return FetchResult(
        url=url,
        final_url=url,
        status=0,
        html="",
        used_playwright=has_playwright_cli(),
        fetcher="failed",
        error=last_error,
        retry_count=max_retries,
    )


def should_retry(error: str) -> bool:
    return bool(error)


def fetch_url_once(url: str, timeout: int, fetcher: str, ssl_context: Optional[ssl.SSLContext], retry_count: int) -> FetchResult:
    try:
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
        kwargs = {"timeout": timeout}
        if ssl_context is not None:
            kwargs["context"] = ssl_context
        with urlopen(request, **kwargs) as response:
            raw = response.read(1_500_000)
            charset = response.headers.get_content_charset() or "utf-8"
            text = raw.decode(charset, errors="replace")
            return FetchResult(
                url=url,
                final_url=response.geturl(),
                status=getattr(response, "status", 200),
                html=text,
                used_playwright=fetcher.startswith("playwright"),
                fetcher=fetcher,
                retry_count=retry_count,
            )
    except HTTPError as exc:
        try:
            body = exc.read(200_000).decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return FetchResult(
            url=url,
            final_url=exc.geturl() or url,
            status=exc.code,
            html=body,
            used_playwright=fetcher.startswith("playwright"),
            fetcher=fetcher,
            error=str(exc),
            retry_count=retry_count,
        )
    except (URLError, TimeoutError, OSError, ssl.SSLError) as exc:
        return FetchResult(
            url=url,
            final_url=url,
            status=0,
            html="",
            used_playwright=fetcher.startswith("playwright"),
            fetcher=fetcher,
            error=str(exc),
            retry_count=retry_count,
        )


def playwright_probe_url(url: str, timeout: int) -> str:
    fd, screenshot = tempfile.mkstemp(prefix="product-research-probe-", suffix=".png")
    os.close(fd)
    try:
        cmd = [
            "playwright",
            "screenshot",
            "--ignore-https-errors",
            "--wait-for-timeout",
            "1000",
            "--timeout",
            str(max(timeout, 5) * 1000),
            "--user-agent",
            USER_AGENT,
            url,
            screenshot,
        ]
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=max(timeout + 5, 10))
        except Exception as exc:
            return str(exc)
        if completed.returncode != 0:
            return (completed.stderr or completed.stdout or "playwright screenshot failed")[:500]
        if not os.path.exists(screenshot) or os.path.getsize(screenshot) == 0:
            return "playwright screenshot produced no file"
        return ""
    finally:
        try:
            os.remove(screenshot)
        except OSError:
            pass


def extract_page(html_text: str, base_url: str) -> Dict[str, str]:
    parser = PageExtractor()
    parser.feed(html_text or "")
    pricing_url = find_pricing_url(parser.anchors, base_url)
    return {
        "page_title": parser.title,
        "meta_description": parser.meta_description,
        "pricing_url": pricing_url,
        "trimmed_text": trim_for_llm(parser.title, parser.meta_description, parser.body_text()),
    }


def find_pricing_url(anchors: List[Dict[str, str]], base_url: str) -> str:
    pricing_words = ("pricing", "price", "plans", "upgrade", "料金", "价格", "定价")
    for anchor in anchors:
        text = (anchor.get("text") or "").lower()
        href = anchor.get("href") or ""
        joined = urljoin(base_url, href)
        haystack = text + " " + joined.lower()
        if any(word in haystack for word in pricing_words):
            return joined
    return ""


def trim_for_llm(title: str, meta_description: str, body_text: str, limit: int = 5000) -> str:
    parts = [
        "TITLE: %s" % clean_text(title),
        "META: %s" % clean_text(meta_description),
        "TEXT:",
        clean_text(body_text),
    ]
    return "\n".join([p for p in parts if p]).strip()[:limit]


