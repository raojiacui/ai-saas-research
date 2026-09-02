from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "revenue-products.csv"
RUNS_DIR = ROOT / "runs"
HEADERS = [
    "产品名",
    "网址",
    "做什么",
    "MRR",
    "近30天收入",
    "价格",
    "目标用户",
    "输入",
    "输出",
    "AITDK月访问量",
    "Top Keywords",
    "为什么有人愿意付钱",
]
USER_AGENT = "Mozilla/5.0 revenue-products-research/0.1"
MONEY_RE = re.compile(r"\$\s*\d[\d,]*(?:\.\d+)?")


@dataclass
class Page:
    url: str
    final_url: str
    status: int
    text: str
    links: list[tuple[str, str]]
    error: str = ""


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.texts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._skip = 0
        self._href = ""
        self._anchor: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {k.lower(): v or "" for k, v in attrs if k}
        if tag in {"script", "style", "svg", "noscript"}:
            self._skip += 1
        if tag == "a":
            self._href = attrs_dict.get("href", "")
            self._anchor = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "svg", "noscript"} and self._skip:
            self._skip -= 1
        if tag == "a" and self._href:
            label = clean(" ".join(self._anchor))
            self.links.append((label, self._href))
            self._href = ""
            self._anchor = []

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = clean(data)
        if not text:
            return
        self.texts.append(text)
        if self._href:
            self._anchor.append(text)

    def text(self, limit: int = 12000) -> str:
        seen: set[str] = set()
        out: list[str] = []
        total = 0
        for item in self.texts:
            if item in seen:
                continue
            seen.add(item)
            out.append(item)
            total += len(item)
            if total >= limit:
                break
        return "\n".join(out)[:limit]


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def slugify(name: str) -> str:
    text = name.lower()
    text = re.sub(r"\([^)]*\)|（[^）]*）", "", text)
    text = text.replace("/", " ").replace("+", " ")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    aliases = {
        "cursor-anysphere": "cursor",
        "bolt-new-stackblitz": "bolt-new",
        "captions-mirage": "captions",
        "wondershare-virbo-filmora": "wondershare-virbo-filmora",
    }
    return aliases.get(text, text)


def read_rows() -> list[dict]:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_rows(rows: list[dict]) -> None:
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS, extrasaction="ignore", quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)


def fetch(url: str, timeout: int = 20) -> Page:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"})
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read(2_000_000)
            charset = response.headers.get_content_charset() or "utf-8"
            body = raw.decode(charset, errors="replace")
            parser = TextExtractor()
            parser.feed(body)
            return Page(url, response.geturl(), getattr(response, "status", 200), parser.text(), parser.links)
    except HTTPError as exc:
        body = exc.read(300_000).decode("utf-8", errors="replace") if exc.fp else ""
        parser = TextExtractor()
        parser.feed(body)
        return Page(url, exc.geturl() or url, exc.code, parser.text(), parser.links, str(exc))
    except (URLError, TimeoutError, OSError) as exc:
        return Page(url, url, 0, "", [], str(exc))


def find_pricing_url(page: Page) -> str:
    words = ("pricing", "price", "plans", "billing", "upgrade", "定价", "价格")
    for label, href in page.links:
        joined = urljoin(page.final_url or page.url, href)
        hay = (label + " " + joined).lower()
        if any(word in hay for word in words):
            return joined
    parsed = urlparse(page.final_url or page.url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}/pricing"
    return ""


def extract_trust_revenue(text: str) -> tuple[str, str]:
    normalized = clean(text)
    mrr = ""
    last30 = ""
    patterns = [
        ("mrr", r"(?:MRR|Monthly Recurring Revenue)[^$]{0,80}(\$\s*\d[\d,]*(?:\.\d+)?)"),
        ("last30", r"(?:Last\s*30\s*days|Revenue\s*last\s*30\s*days|30\s*days)[^$]{0,100}(\$\s*\d[\d,]*(?:\.\d+)?)"),
    ]
    for key, pat in patterns:
        match = re.search(pat, normalized, re.I)
        if match and key == "mrr":
            mrr = normalize_money(match.group(1))
        if match and key == "last30":
            last30 = normalize_money(match.group(1))
    if not (mrr and last30):
        # Fallback for pages/cards where values appear near labels after text extraction changed order.
        dollars = [normalize_money(x) for x in MONEY_RE.findall(normalized)]
        labels = normalized.lower()
        if "mrr" in labels and dollars and not mrr:
            mrr = dollars[0]
        if ("last 30" in labels or "30 days" in labels) and len(dollars) > 1 and not last30:
            last30 = dollars[1]
    return mrr, last30


def normalize_money(value: str) -> str:
    text = re.sub(r"\s+", "", value or "")
    text = text.replace("$", "$")
    return text


def trust_urls(row: dict) -> Iterable[str]:
    url = row.get("网址", "")
    name = row.get("产品名", "")
    candidates = []
    if "trustmrr.com/startup/" in url:
        candidates.append(url)
    candidates.append(f"https://trustmrr.com/startup/{slugify(name)}")
    candidates.append(f"https://trustmrr.com/?q={quote(name)}")
    seen = set()
    for item in candidates:
        if item and item not in seen:
            seen.add(item)
            yield item


def concise_pricing(text: str) -> str:
    lines = [x for x in text.splitlines() if re.search(r"\$|free|starter|pro|business|enterprise|team|creator|price|month|year|月|年|免费|定制", x, re.I)]
    joined = " / ".join(lines[:80])
    joined = re.sub(r"\s+", " ", joined).strip()
    return joined[:2500]


def call_deepseek(prompt: str, timeout: int) -> dict | None:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return None
    import urllib.request

    body = json.dumps({
        "model": os.environ.get("PRODUCT_RESEARCH_LLM_MODEL", "deepseek-v4-flash"),
        "messages": [
            {"role": "system", "content": "你是严格的 CSV 字段抽取助手，只返回 JSON，不要编造网页没有支持的信息。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "stream": False,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/") + "/chat/completions",
        data=body,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return parse_json(payload["choices"][0]["message"]["content"])


def call_claude(prompt: str, timeout: int, budget: str) -> dict | None:
    if not shutil.which("claude"):
        return None
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "text",
        "--permission-mode", "dontAsk",
        "--max-budget-usd", budget,
    ]
    completed = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout)[:1000])
    return parse_json(completed.stdout)


def parse_json(text: str) -> dict:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        cleaned = cleaned[start:end + 1]
    return json.loads(cleaned)


def build_llm_prompt(row: dict, homepage: Page, pricing_text: str) -> str:
    sample = """参考前 6 条的写法：
- 做什么：中文描述这个产品到底提供什么服务，不要写收入。
- 价格：只写官网 pricing 页能确认的套餐金额；不确定就返回空字符串。
- 为什么有人愿意付钱：中文描述产品特别之处、好用之处、节省的成本或带来的结果，不要写 MRR/近30天收入/来源。
"""
    payload = {
        "任务": "根据官网文本补 revenue-products.csv 的中文字段。不要浏览，只使用提供的文本。",
        "产品名": row.get("产品名", ""),
        "网址": row.get("网址", ""),
        "必须返回JSON字段": ["做什么", "价格", "为什么有人愿意付钱"],
        "规则": sample,
        "官网文本": homepage.text[:9000],
        "pricing相关文本": pricing_text[:4000],
    }
    return json.dumps(payload, ensure_ascii=False)


def update_row(row: dict, args: argparse.Namespace, notes: list[str]) -> None:
    name = row.get("产品名", "")
    if (not row.get("MRR")) or (not row.get("近30天收入")):
        for trust_url in trust_urls(row):
            page = fetch(trust_url, timeout=args.timeout)
            if args.sleep:
                time.sleep(args.sleep)
            if page.status and page.text:
                mrr, last30 = extract_trust_revenue(page.text)
                if mrr and not row.get("MRR"):
                    row["MRR"] = mrr
                if last30 and not row.get("近30天收入"):
                    row["近30天收入"] = last30
                if row.get("MRR") and row.get("近30天收入"):
                    notes.append(f"{name}: TrustMRR revenue filled from {trust_url}")
                    break
        if (not row.get("MRR")) or (not row.get("近30天收入")):
            notes.append(f"{name}: revenue still needs TrustMRR verification")

    needs_profile = any(not row.get(k) for k in ["做什么", "价格", "为什么有人愿意付钱"])
    if not needs_profile:
        return
    homepage = fetch(row.get("网址", ""), timeout=args.timeout)
    if args.sleep:
        time.sleep(args.sleep)
    pricing_text = ""
    if homepage.status and homepage.text:
        pricing_url = find_pricing_url(homepage)
        if pricing_url:
            pricing_page = fetch(pricing_url, timeout=args.timeout)
            if args.sleep:
                time.sleep(args.sleep)
            pricing_text = concise_pricing(pricing_page.text)
    else:
        notes.append(f"{name}: homepage fetch failed: {homepage.error}")

    if args.llm == "none":
        notes.append(f"{name}: profile fields need LLM/manual fill")
        return

    prompt = build_llm_prompt(row, homepage, pricing_text)
    data = None
    try:
        if args.llm == "deepseek":
            data = call_deepseek(prompt, timeout=args.llm_timeout)
        elif args.llm == "claude":
            data = call_claude(prompt, timeout=args.llm_timeout, budget=args.claude_budget)
    except Exception as exc:
        notes.append(f"{name}: LLM failed: {exc}")
        return
    if not data:
        notes.append(f"{name}: LLM unavailable")
        return
    for field in ["做什么", "价格", "为什么有人愿意付钱"]:
        value = clean(str(data.get(field, "") or ""))
        if value and not row.get(field):
            row[field] = value
    notes.append(f"{name}: profile fields updated with {args.llm}")


def needs_work(row: dict) -> bool:
    if not row.get("MRR") or not row.get("近30天收入"):
        return True
    if any(not row.get(k) for k in ["做什么", "价格", "为什么有人愿意付钱"]):
        return True
    return False


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Fill revenue-products.csv from TrustMRR, official pricing pages, and optional LLM.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--start", type=int, default=1, help="1-based row index")
    parser.add_argument("--llm", choices=["none", "deepseek", "claude"], default="none")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--llm-timeout", type=int, default=90)
    parser.add_argument("--claude-budget", default="1.50")
    parser.add_argument("--sleep", type=float, default=0.5)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    rows = read_rows()
    targets = [(i, r) for i, r in enumerate(rows, start=1) if i >= args.start and needs_work(r)]
    if args.limit:
        targets = targets[:args.limit]

    RUNS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    notes: list[str] = []
    notes.append(f"targets={len(targets)} llm={args.llm} dry_run={args.dry_run}")

    for i, row in targets:
        notes.append(f"row {i}: {row.get('产品名', '')}")
        update_row(row, args, notes)

    if not args.dry_run and targets:
        backup = CSV_PATH.with_name(f"revenue-products.before-fill-{stamp}.csv")
        shutil.copy2(CSV_PATH, backup)
        write_rows(rows)
        notes.insert(1, f"backup={backup}")

    report = RUNS_DIR / f"revenue-products-fill-{stamp}.md"
    report.write_text("# revenue-products fill run\n\n" + "\n".join(f"- {n}" for n in notes) + "\n", encoding="utf-8")
    print(f"report={report}")
    for line in notes:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
