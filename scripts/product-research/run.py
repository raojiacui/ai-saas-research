"""Run the product-research MVP workflow."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from classify import classify_product, model_label
from csv_store import append_pending, atomic_write_text, ensure_csv, read_csv, read_products
from dedupe import build_index, normalize_domain
from discover import Candidate, parse_candidates
from enrich import extract_page, fetch_url, has_playwright_cli
from schemas import PENDING_HEADERS, PRODUCT_HEADERS, SEMANTIC_FIELDS, VIDEO_CATEGORY_FIELDS
from validate import validate_outputs, validate_product_row


ROOT = Path(__file__).resolve().parents[2]
PRODUCTS_CSV = ROOT / "products.csv"
PENDING_CSV = ROOT / "pending-products.csv"
RUNS_DIR = ROOT / "runs"


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def clean_decision(value: str) -> str:
    text = (value or "").strip().upper()
    if text.startswith("YES"):
        return "YES"
    if text.startswith("MAYBE"):
        return "MAYBE"
    if text.startswith("NO"):
        return "NO"
    return "UNAVAILABLE"


def admission_decision(row: Dict[str, str], focus: str) -> Tuple[bool, str]:
    if focus == "none":
        return True, "accepted: focus=none"
    ai_fit = clean_decision(row.get("ai_video_fit", ""))
    r2v_fit = clean_decision(row.get("reference_to_video_fit", ""))
    if ai_fit != "YES":
        return False, "ai_video_fit=%s" % ai_fit
    if focus == "ai-video":
        return True, "accepted: ai_video_fit=YES"
    if r2v_fit not in {"YES", "MAYBE"}:
        return False, "reference_to_video_fit=%s" % r2v_fit
    return True, "accepted: reference_to_video_fit=%s" % r2v_fit


def base_result_row(candidate: Candidate) -> Dict[str, str]:
    row = {header: "" for header in PENDING_HEADERS}
    row.update(
        {
            "产品名": candidate.name,
            "网址": candidate.url,
            "source_url": candidate.source_url,
            "candidate_url": candidate.url,
            "domain": normalize_domain(candidate.url),
            "timestamp": now_iso(),
        }
    )
    return row


def build_success_row(candidate: Candidate, fetch, extracted: Dict[str, str], classification) -> Dict[str, str]:
    website = fetch.final_url or candidate.url
    row = base_result_row(candidate)
    row.update(
        {
            "网址": website,
            "价格": "unavailable",
            "AITDK月访问量": "unavailable",
            "Top Keywords": "unavailable",
            "Top Regions": "unavailable",
            "domain": normalize_domain(website),
            "final_url": website,
            "http_status": str(fetch.status),
            "html_fetcher": fetch.fetcher,
            "page_title": extracted.get("page_title", ""),
            "meta_description": extracted.get("meta_description", ""),
            "pricing_url": extracted.get("pricing_url", ""),
            "llm_provider": classification.provider,
            "llm_model": classification.model,
            "llm_calls": str(classification.calls),
            "timestamp": now_iso(),
        }
    )
    row.update({field: classification.fields.get(field, "unavailable") for field in SEMANTIC_FIELDS + VIDEO_CATEGORY_FIELDS})
    if extracted.get("pricing_url"):
        row["价格"] = "pricing page found; needs manual extraction"
    for header in PRODUCT_HEADERS:
        row.setdefault(header, "unavailable")
        if row[header] == "":
            row[header] = "unavailable"
    return row


def build_failed_row(candidate: Candidate, failed_step: str, error_code: str, error: str, retry_count: int = 0, final_url: str = "", domain: str = "") -> Dict[str, str]:
    row = base_result_row(candidate)
    row.update(
        {
            "status": "failed",
            "reason": error_code,
            "final_url": final_url,
            "domain": domain or normalize_domain(final_url or candidate.url),
            "failed_step": failed_step,
            "error_code": error_code,
            "error": error[:500],
            "retry_count": str(retry_count),
            "timestamp": now_iso(),
        }
    )
    return row


def run(args: argparse.Namespace) -> int:
    started_at = now_iso()
    products = read_products(PRODUCTS_CSV)
    existing_index = build_index(products)
    pending_index = build_index(read_csv(PENDING_CSV))
    candidates = parse_candidates(args.candidate)
    if args.limit:
        candidates = candidates[: args.limit]

    result_rows: List[dict] = []
    created: List[dict] = []
    skipped: List[dict] = []
    failed: List[dict] = []
    duplicates: List[str] = []
    llm_calls = 0

    for candidate in candidates:
        duplicate = existing_index.check(candidate.name, candidate.url) or pending_index.check(candidate.name, candidate.url)
        if duplicate:
            duplicates.append("%s => %s" % (candidate.name, duplicate))
            continue

        fetch = fetch_url(candidate.url, timeout=args.fetch_timeout, max_retries=args.max_retries)
        domain = normalize_domain(fetch.final_url or candidate.url)
        if fetch.status == 0:
            row = build_failed_row(candidate, "fetch_homepage", "NETWORK_ERROR", fetch.error, fetch.retry_count, fetch.final_url, domain)
            result_rows.append(row)
            failed.append(row)
            continue
        if fetch.status >= 400:
            row = build_failed_row(candidate, "fetch_homepage", "HTTP_ERROR", "HTTP %s %s" % (fetch.status, fetch.error), fetch.retry_count, fetch.final_url, domain)
            result_rows.append(row)
            failed.append(row)
            continue

        extracted = extract_page(fetch.html, fetch.final_url or candidate.url)
        classification = classify_product(
            candidate.name,
            fetch.final_url or candidate.url,
            extracted.get("trimmed_text", ""),
            provider=args.llm_provider,
            timeout=args.llm_timeout,
        )
        llm_calls += classification.calls
        row = build_success_row(candidate, fetch, extracted, classification)
        row_errors = validate_product_row({**row, "source_url": candidate.source_url})
        if row_errors:
            row = build_failed_row(candidate, "validate_row", "VALIDATION_ERROR", "; ".join(row_errors), fetch.retry_count, fetch.final_url, domain)
            result_rows.append(row)
            failed.append(row)
            continue

        accepted, reason = admission_decision(row, args.focus)
        row["status"] = "pending" if accepted else "skipped"
        row["reason"] = reason
        result_rows.append(row)
        if accepted:
            created.append(row)
        else:
            skipped.append(row)

    if not args.dry_run:
        ensure_csv(PENDING_CSV, PENDING_HEADERS)
        append_pending(PENDING_CSV, result_rows)
        validate_outputs([PENDING_CSV])

    finished_at = now_iso()
    report = render_report(started_at, finished_at, candidates, created, skipped, failed, duplicates, llm_calls, args)
    if not args.dry_run:
        report_path = RUNS_DIR / ("product-research-%s.md" % dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
        atomic_write_text(report_path, report)
        print("report=%s" % report_path)
    print(report)
    return 0


def render_report(started_at: str, finished_at: str, candidates: List[Candidate], created: List[dict], skipped: List[dict], failed: List[dict], duplicates: List[str], llm_calls: int, args: argparse.Namespace) -> str:
    lines = [
        "# product-research run report",
        "",
        "- started_at: %s" % started_at,
        "- finished_at: %s" % finished_at,
        "- candidates: %s" % len(candidates),
        "- pending: %s" % len(created),
        "- skipped: %s" % len(skipped),
        "- duplicates: %s" % len(duplicates),
        "- failed: %s" % len(failed),
        "- focus: %s" % args.focus,
        "- output: pending-products.csv",
        "- llm_provider: %s" % args.llm_provider,
        "- llm_model: %s" % model_label(args.llm_provider),
        "- llm_calls: %s" % llm_calls,
        "- playwright_cli_available: %s" % has_playwright_cli(),
        "- dry_run: %s" % args.dry_run,
        "",
        "## pending",
    ]
    for row in created:
        lines.append("- %s | %s | ai_video=%s | r2v=%s | category=%s | llm_calls=%s" % (row.get("产品名"), row.get("domain"), row.get("ai_video_fit"), row.get("reference_to_video_fit"), row.get("video_category"), row.get("llm_calls")))
    lines.append("")
    lines.append("## skipped")
    for row in skipped:
        lines.append("- %s | %s | %s" % (row.get("产品名"), row.get("domain"), row.get("reason")))
    lines.append("")
    lines.append("## duplicates")
    if duplicates:
        lines.extend("- " + item for item in duplicates)
    lines.append("")
    lines.append("## failed")
    for row in failed:
        lines.append("- %s | %s | %s" % (row.get("产品名"), row.get("error_code"), row.get("error")))
    return "\n".join(lines) + "\n"


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI SaaS product research MVP")
    parser.add_argument("--candidate", action="append", required=True, help="NAME|URL|SOURCE_URL|SOURCE")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--focus", choices=["reference-to-video", "ai-video", "none"], default="reference-to-video")
    parser.add_argument("--llm-provider", choices=["none", "deepseek", "openai"], default="none")
    parser.add_argument("--fetch-timeout", type=int, default=12)
    parser.add_argument("--llm-timeout", type=int, default=30)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(run(parse_args(sys.argv[1:])))

